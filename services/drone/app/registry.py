from __future__ import annotations

CALLSIGNS = ["Sentinel", "Vigil", "Warden", "Aegis", "Lookout", "Guardian", "Beacon", "Watchman"]


def default_drones(count: int, home_lat: float, home_lon: float, home_alt: float) -> list[dict]:
    """Default drone registry, mirroring the C2's seeded registry by id."""
    return [
        {
            "id": i,
            "callsign": CALLSIGNS[i] if i < len(CALLSIGNS) else f"Unit{i}",
            "home_lat": home_lat,
            "home_lon": home_lon,
            "home_alt": home_alt,
        }
        for i in range(count)
    ]
