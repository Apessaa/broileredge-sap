"""Edge rating logic used by the prototype: zone rating (Table II of the paper) and house assessment.

Zone rating = revised rules P: thermal indicator (brooding rule before day 21, THI from week 4),
NH3 band and CO2 band; the zone level is the most severe indicator and the cause lists the
indicators at that level. The house assessment takes the most severe zone (ties: lowest zone number).
"""
import math
import rules_core as M

INDICATORS = ("thermal", "NH3", "CO2")


def rate_zone(t, rh, v, co2, nh3, week, weight_g):
    levels = {
        "thermal": M.thermal_P(t, rh, week, weight_g),
        "NH3": M.nh3_P(nh3),
        "CO2": M.co2_P(co2),
    }
    level = max(levels.values())
    cause = "none" if level == 0 else "+".join(k for k in INDICATORS if levels[k] == level)
    return {
        "levels": levels,
        "level": level,
        "cause": cause,
        "thi": round(M.thi_humid_tropics(t, rh), 2),
        "thvi_note": M.thvi_note(t, rh, v),
        "air_speed_diag": bool(M.air_speed_diag(t, rh, v, week)),
    }


def house_assessment(zones):
    """zones: list of (zone_id, inputs_dict, rating_dict). Returns the worst zone summary."""
    worst = None
    for zone_id, inputs, rating in sorted(zones, key=lambda z: z[0]):
        if worst is None or rating["level"] > worst[2]["level"]:
            worst = (zone_id, inputs, rating)
    zone_id, inputs, rating = worst
    return {
        "worst_zone": zone_id,
        "inputs": inputs,
        "level": rating["level"],
        "cause": rating["cause"],
        "sub_levels": rating["levels"],
        "thi": rating["thi"],
        "thvi_note": rating["thvi_note"],
        "air_speed_diag": rating["air_speed_diag"],
    }
