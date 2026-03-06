"""
drone_precision_ag — NDVI Engine
==================================
Multispectral vegetation index computation.

Indices computed:
  NDVI  = (NIR - RED) / (NIR + RED)         — general vegetation health
  NDRE  = (NIR - RedEdge) / (NIR + RedEdge) — nitrogen stress (early)
  NDWI  = (GREEN - NIR) / (GREEN + NIR)     — water content / irrigation need
  SAVI  = 1.5*(NIR-RED)/(NIR+RED+0.5)       — soil-adjusted (sparse crops)

Prescription zones:
  ZONE_SKIP    : NDVI > 0.65  → healthy, no treatment needed
  ZONE_LOW     : NDVI 0.45–0.65 → light dose
  ZONE_MEDIUM  : NDVI 0.25–0.45 → standard dose
  ZONE_HIGH    : NDVI < 0.25  → maximum dose (severely stressed)

Author: swordenkisk | github.com/swordenkisk/drone_precision_ag
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from enum import Enum


class FertZone(Enum):
    SKIP   = "SKIP"    # Healthy — no fertiliser
    LOW    = "LOW"     # Light dose  (25% of max)
    MEDIUM = "MEDIUM"  # Standard    (60% of max)
    HIGH   = "HIGH"    # Max dose    (100%)


@dataclass
class Pixel:
    """One multispectral pixel — represents ~5cm² of field."""
    x       : float   # GPS longitude
    y       : float   # GPS latitude
    red     : float   # Red band reflectance [0,1]
    nir     : float   # Near-infrared reflectance [0,1]
    green   : float   # Green band reflectance [0,1]
    rededge : float   # Red-edge band reflectance [0,1]

    @property
    def ndvi(self) -> float:
        d = self.nir + self.red
        return (self.nir - self.red) / d if d > 1e-6 else 0.0

    @property
    def ndre(self) -> float:
        d = self.nir + self.rededge
        return (self.nir - self.rededge) / d if d > 1e-6 else 0.0

    @property
    def ndwi(self) -> float:
        d = self.green + self.nir
        return (self.green - self.nir) / d if d > 1e-6 else 0.0

    @property
    def savi(self) -> float:
        L = 0.5
        d = self.nir + self.red + L
        return 1.5 * (self.nir - self.red) / d if d > 1e-6 else 0.0

    @property
    def zone(self) -> FertZone:
        n = self.ndvi
        if n > 0.65:   return FertZone.SKIP
        if n > 0.45:   return FertZone.LOW
        if n > 0.25:   return FertZone.MEDIUM
        return FertZone.HIGH


@dataclass
class NDVIMap:
    """Full field NDVI map — result of one drone scan."""
    pixels          : List[Pixel]
    field_area_ha   : float
    scan_altitude_m : float = 30.0
    resolution_cm   : float = 5.0

    @property
    def width(self) -> int:
        return int(math.sqrt(len(self.pixels))) or 1

    def avg_ndvi(self) -> float:
        return sum(p.ndvi for p in self.pixels) / max(len(self.pixels), 1)

    def zone_counts(self) -> Dict[FertZone, int]:
        counts = {z: 0 for z in FertZone}
        for p in self.pixels:
            counts[p.zone] += 1
        return counts

    @property
    def healthy_pct(self) -> float:
        zc = self.zone_counts()
        return 100 * zc[FertZone.SKIP] / max(len(self.pixels), 1)

    @property
    def stressed_pct(self) -> float:
        return 100 - self.healthy_pct

    def summary(self) -> str:
        zc   = self.zone_counts()
        n    = max(len(self.pixels), 1)
        return (
            f"NDVI Map [{len(self.pixels)} pixels, {self.field_area_ha:.1f} ha]\n"
            f"  Avg NDVI     : {self.avg_ndvi():.3f}\n"
            f"  SKIP (healthy): {100*zc[FertZone.SKIP]/n:.0f}%\n"
            f"  LOW           : {100*zc[FertZone.LOW]/n:.0f}%\n"
            f"  MEDIUM        : {100*zc[FertZone.MEDIUM]/n:.0f}%\n"
            f"  HIGH (stress) : {100*zc[FertZone.HIGH]/n:.0f}%\n"
        )


@dataclass
class PrescriptionMap:
    """Variable-rate fertiliser prescription derived from NDVI map."""
    pixels          : List[Pixel]
    doses_L_per_m2  : List[float]
    field_area_ha   : float
    max_dose        : float   # L/ha
    fertiliser_type : str = "NPK"

    @property
    def total_litres(self) -> float:
        # Each pixel represents field_area / n_pixels
        field_area_m2 = self.field_area_ha * 10_000
        pixel_area_m2 = field_area_m2 / max(len(self.pixels), 1)
        return sum(self.doses_L_per_m2) * pixel_area_m2

    @property
    def uniform_litres(self) -> float:
        """What uniform application would have used."""
        return self.max_dose * self.field_area_ha

    @property
    def savings_pct(self) -> float:
        u = self.uniform_litres
        return 100 * (u - self.total_litres) / u if u > 0 else 0.0

    @property
    def savings_litres(self) -> float:
        return max(self.uniform_litres - self.total_litres, 0.0)

    def summary(self) -> str:
        return (
            f"Prescription Map [{self.fertiliser_type}]\n"
            f"  Precision total   : {self.total_litres:.1f} L\n"
            f"  Uniform would use : {self.uniform_litres:.1f} L\n"
            f"  Savings           : {self.savings_pct:.0f}% ({self.savings_litres:.1f} L)\n"
            f"  Max dose          : {self.max_dose} L/ha\n"
        )


class NDVIEngine:
    """
    Core multispectral analysis engine.
    Computes NDVI maps and prescription maps from sensor data.
    """

    DOSE_FACTORS = {
        FertZone.SKIP  : 0.00,
        FertZone.LOW   : 0.25,
        FertZone.MEDIUM: 0.60,
        FertZone.HIGH  : 1.00,
    }

    def __init__(self, max_dose_L_per_ha: float = 50.0):
        self.max_dose = max_dose_L_per_ha

    def simulate_scan(
        self,
        field_area_ha: float,
        resolution_px: int = 400,
        seed: int = 42,
    ) -> NDVIMap:
        """
        Simulate a multispectral drone scan.
        Generates realistic NDVI variation with stressed patches.
        """
        rng     = random.Random(seed)
        pixels  = []
        n       = resolution_px

        # Create realistic field: mostly healthy with stressed patches
        stressed_centres = [
            (rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8), rng.uniform(0.1, 0.25))
            for _ in range(rng.randint(3, 7))
        ]

        for i in range(n):
            for j in range(n):
                fx, fy = i / n, j / n

                # Base health: slightly variable
                base_ndvi = rng.gauss(0.62, 0.08)

                # Stressed patches (Gaussian patches)
                for cx, cy, radius in stressed_centres:
                    d2 = (fx - cx)**2 + (fy - cy)**2
                    if d2 < radius**2:
                        stress = math.exp(-d2 / (2 * (radius*0.4)**2)) * 0.45
                        base_ndvi -= stress

                base_ndvi = max(0.05, min(0.90, base_ndvi))

                # Convert NDVI → band reflectances
                nir = base_ndvi * 0.5 + 0.1
                red = nir * (1 - base_ndvi) / (1 + base_ndvi) if base_ndvi > 0 else 0.2

                pixels.append(Pixel(
                    x       = fx,
                    y       = fy,
                    red     = max(0.01, red + rng.gauss(0, 0.005)),
                    nir     = max(0.01, nir + rng.gauss(0, 0.005)),
                    green   = max(0.01, base_ndvi * 0.3 + rng.gauss(0, 0.005)),
                    rededge = max(0.01, base_ndvi * 0.4 + rng.gauss(0, 0.005)),
                ))

        return NDVIMap(pixels=pixels, field_area_ha=field_area_ha)

    def build_prescription(self, ndvi_map: NDVIMap, fertiliser_type: str = "NPK") -> PrescriptionMap:
        """
        Build variable-rate prescription from NDVI map.
        dose(x,y) = max_dose × zone_factor × (1 - NDVI(x,y))
        """
        doses = []
        max_dose_per_m2 = self.max_dose / 10000  # L/ha → L/m²

        for p in ndvi_map.pixels:
            factor = self.DOSE_FACTORS[p.zone]
            # Modulate by exact NDVI within zone
            ndvi_modulation = max(0, 1 - p.ndvi)
            dose = max_dose_per_m2 * factor * ndvi_modulation
            doses.append(dose)

        return PrescriptionMap(
            pixels         = ndvi_map.pixels,
            doses_L_per_m2 = doses,
            field_area_ha  = ndvi_map.field_area_ha,
            max_dose       = self.max_dose,
            fertiliser_type= fertiliser_type,
        )
