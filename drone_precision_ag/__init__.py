"""
drone_precision_ag — Public API + Demo
Author: swordenkisk | github.com/swordenkisk/drone_precision_ag
Idea score: 94.9/100 from ideas_database.db
"""

import sys, math, hashlib
sys.path.insert(0, "..")

from drone_precision_ag.core.ndvi_engine    import NDVIEngine, NDVIMap, PrescriptionMap
from drone_precision_ag.swarm.fleet_coordinator import SwarmCoordinator


class PrecisionFarm:
    """Public API for drone precision fertilisation."""

    def __init__(self, field_area_ha: float = 10.0, drone_count: int = 4,
                 fertiliser: str = "NPK_20_10_10", max_dose_L_per_ha: float = 50.0):
        self.area         = field_area_ha
        self.n_drones     = drone_count
        self.fertiliser   = fertiliser
        self.ndvi_engine  = NDVIEngine(max_dose_L_per_ha)
        self.swarm        = SwarmCoordinator(drone_count, field_area_ha)

    def scan(self, seed: int = 42) -> NDVIMap:
        return self.ndvi_engine.simulate_scan(self.area, resolution_px=50, seed=seed)

    def prescribe(self, ndvi_map: NDVIMap) -> PrescriptionMap:
        return self.ndvi_engine.build_prescription(ndvi_map, self.fertiliser)

    def spray(self, rx_map: PrescriptionMap):
        return self.swarm.execute_mission(rx_map.total_litres)


# ─── Demo ──────────────────────────────────────────────────────────

def run_demo():
    print("=" * 65)
    print("  drone_precision_ag — Precision Fertilisation Demo")
    print("  Drone swarm + NDVI + variable-rate spray + oracle")
    print("  Author: swordenkisk | March 2026 | Score: 94.9/100")
    print("=" * 65)

    farm = PrecisionFarm(
        field_area_ha     = 25.0,
        drone_count       = 4,
        fertiliser        = "NPK_20_10_10",
        max_dose_L_per_ha = 50.0,
    )

    # ── Step 1: Scan ──────────────────────────────────────────────
    print("\n🛸 Step 1: Drone fleet scanning field (multispectral)...\n")
    ndvi_map = farm.scan(seed=7)
    print(ndvi_map.summary())

    # ── Step 2: Prescribe ─────────────────────────────────────────
    print("─" * 65)
    print("🗺️  Step 2: Building variable-rate prescription map...\n")
    rx_map = farm.prescribe(ndvi_map)
    print(rx_map.summary())

    # Environmental impact
    print(f"  🌍 Fertiliser prevented from runoff: {rx_map.savings_litres:.0f} L")
    print(f"     = {rx_map.savings_litres * 1.2:.0f} kg of NPK NOT polluting waterways")

    # ── Step 3: Execute swarm mission ─────────────────────────────
    print("\n─" * 65)
    print("🚁 Step 3: Swarm executing precision spray mission...\n")
    mission = farm.spray(rx_map)
    print(mission.summary())

    # Drone status
    print("  Drone status after mission:")
    for d in mission.drones:
        bar = "█" * int(d.battery_pct / 10) + "░" * (10 - int(d.battery_pct / 10))
        print(f"    {d.drone_id}  battery [{bar}] {d.battery_pct:.0f}%  "
              f"sprayed {d.total_sprayed_L:.1f}L")

    # ── Step 4: Oracle log ────────────────────────────────────────
    print("\n─" * 65)
    print("🔗 Step 4: Spray events logged to decentralised oracle\n")
    print(f"  Total oracle events : {len(mission.oracle_events)}")
    print(f"  Oracle TX hash      : {mission.oracle_tx_hash[:20]}...")
    print(f"  Sample event        :")
    ev = mission.oracle_events[0]
    for k, v in ev.items():
        if k != "position":
            print(f"    {k:15s}: {v}")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 65)
    uniform_L = 50.0 * farm.area
    precision_L = mission.total_litres
    savings_pct = 100 * (uniform_L - precision_L) / uniform_L
    print(f"  📊 IMPACT SUMMARY for {farm.area} ha field:")
    print(f"     Uniform application would use : {uniform_L:.0f} L")
    print(f"     Precision application used    : {precision_L:.0f} L")
    print(f"     Fertiliser saved              : {uniform_L-precision_L:.0f} L ({savings_pct:.0f}%)")
    print(f"     Mission time                  : {mission.duration_min:.0f} min")
    print(f"     Coverage rate                 : {farm.area/mission.duration_min*60:.1f} ha/hr")
    print()
    print(f"  🇩🇿 Scaled to Algeria's 8.5M ha:")
    algerian_savings = (uniform_L - precision_L) / farm.area * 8_500_000
    print(f"     Potential fertiliser savings  : {algerian_savings/1e9:.1f} billion litres/year")
    print(f"     Economic value (~$2.5/L NPK)  : ${algerian_savings*2.5/1e9:.0f}B/year")
    print("=" * 65)
    print("  🚁 drone_precision_ag — swordenkisk 🇩🇿 March 2026")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
