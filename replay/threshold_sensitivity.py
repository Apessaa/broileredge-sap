"""Sensitivity of the ratings to the CO2 bands (paper v26, Section V-A, #4).

The design's CO2 bands are Normal <= 3000, Moderate > 3000 to 3500, Severe > 3500 ppm (EU limit [17] and the
Ross guide [2]); the Severe band rests on one source. The alternative bands follow a review of broiler-house air
quality (Pereira et al. 2023, citing CIGR 1994): 2500 ppm recommended, 3000 ppm threshold limit, i.e. Normal <= 2500,
Moderate > 2500 to 3000, Severe > 3000 ppm. Thermal and NH3 levels are unchanged.
Reports: records whose CO2 level or overall level P changes, Moderate/Severe shares, CO2-caused M or S records, and
escalations per run (3 Severe windows of a zone within 24 h, as in target_sensitivity.py).
No broiler-specific THI classification with a stated formula could be verified (29-30 Oct 2026), so THI classes
are not varied here; the THI equation is varied in replay_v13.py (P').   Output: threshold_sensitivity.json
"""
import csv
import json
import os

from target_sensitivity import escalations

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "replay_records.csv")


def band(x, lo, hi):
    return 0 if x <= lo else (1 if x <= hi else 2)


def main():
    rows = list(csv.DictReader(open(SRC)))
    out = {"records": len(rows), "bands": {"design": [3000, 3500], "alternative": [2500, 3000]}}
    res = {}
    for name, (lo, hi) in out["bands"].items():
        for r in rows:
            co = band(float(r["CO2"]), lo, hi)
            r["_co"] = co
            r["_P"] = max(int(r["thP"]), int(r["nhP"]), co)
        assert name != "design" or all(r["_P"] == int(r["P"]) and r["_co"] == int(r["coP"]) for r in rows)
        res[name] = {"co2_M": sum(r["_co"] == 1 for r in rows), "co2_S": sum(r["_co"] == 2 for r in rows),
                     "MS": sum(r["_P"] >= 1 for r in rows), "S": sum(r["_P"] == 2 for r in rows),
                     "escalations_per_run": escalations(rows)}
        for r in rows:
            r["_P_" + name], r["_co_" + name] = r["_P"], r["_co"]
    out["by_bands"] = res
    out["co2_level_changed"] = sum(r["_co_design"] != r["_co_alternative"] for r in rows)
    out["P_changed"] = sum(r["_P_design"] != r["_P_alternative"] for r in rows)
    out["P_changed_share"] = round(out["P_changed"] / len(rows), 4)
    out["new_MS"] = sum(r["_P_design"] == 0 and r["_P_alternative"] >= 1 for r in rows)
    out["new_S"] = sum(r["_P_design"] < 2 and r["_P_alternative"] == 2 for r in rows)
    out["co2_max_ppm"] = max(float(r["CO2"]) for r in rows)
    out["records_co2_gt_2500"] = sum(float(r["CO2"]) > 2500 for r in rows)
    json.dump(out, open(os.path.join(HERE, "threshold_sensitivity.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
