"""Walking-time estimates: Naismith's rule with Langmuir corrections.

Naismith: 5 km/h (12 min/km) + 1 min per 10 m ascent.
Langmuir: gentle descent (paths) speeds you up, -10 min per 300 m;
steep/broken descent slows you down, +10 min per 300 m.
Terrain multiplier on movement time: path 1.0, rough 1.2, scramble 1.6.
Floor: no leg faster than 7.5 km/h equivalent (8 min/km).
Once a GPX exists, replace per-leg totals with Tobler's function integrated
along the track.
"""

TERRAIN_FACTOR = {"path": 1.0, "rough": 1.2, "scramble": 1.6}


def naismith_langmuir(distance_km: float, ascent_m: float, descent_m: float,
                      terrain: str = "path") -> int:
    if terrain not in TERRAIN_FACTOR:
        raise ValueError(f"unknown terrain: {terrain}")
    base = distance_km * 12 * TERRAIN_FACTOR[terrain]
    climb = ascent_m / 10
    descent = (descent_m / 300 * 10) * (-1 if terrain == "path" else 1)
    total = max(base + climb + descent, distance_km * 8)
    return round(total)
