"""Outside comparison, alarm burden and house-flock CIs for the record-level replay (paper v24, Section V-A).

1. Outside comparison. Two references that the authors did not design, both from the dataset paper
   (Coimbra da Silva et al. 2025, Section 2.2):
   CTRL  a set-point alarm such as a climate controller raises: house temperature outside the week's target
         range of the houses' programme (week 1: 32-34, 2: 30-32, 3: 28-30, 4: 26-28, 5-6: 22-26 C);
   DISC  the dataset authors' own discomfort label: any of temperature outside that range, RH outside 50-70%,
         NH3 > 20 ppm, CO2 > 3000 ppm, air speed outside 0.1-0.3 m/s (weeks 1-2) or 0.3-0.8 m/s (later).
   Each is compared with the revised rules P (Moderate or Severe vs Normal), per record. Neither reference
   is ground truth; CTRL shows what a set-point controller would flag, DISC what the data's authors called
   discomfort.
2. Burden. Per surveyed house-day (8 house-flocks x 6 weeks = 48 days, three survey windows each): survey
   windows rated Moderate or Severe (preventive notices or alerts), Severe windows (alerts), and maintenance
   notifications (escalations, from target_sensitivity.json), with the Ross target and with the houses' own
   targets in weeks 1-3.
3. Uncertainty by house-flock. The main CIs resample the 141 surveys; with only eight house-flocks, resampling
   house-flocks instead gives wider intervals, reported here for the key shares.
Output: baseline_burden.json
"""
import csv
import json
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "replay_records.csv")
TS = json.load(open(os.path.join(HERE, "target_sensitivity.json")))["targets"]
B = 5000
rng = random.Random(20261029)
T_RANGE = {1: (32, 34), 2: (30, 32), 3: (28, 30), 4: (26, 28), 5: (22, 26), 6: (22, 26)}
LOCAL_T = {1: 33.0, 2: 31.0, 3: 29.0}


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def band(x, lo, hi):
    return 0 if x <= lo else (1 if x <= hi else 2)


def ctrl(r):
    lo, hi = T_RANGE[int(r["Week"])]
    t = f(r["T"])
    return t < lo or t > hi


def disc(r):
    wk = int(r["Week"])
    lo, hi = T_RANGE[wk]
    t, rh, nh, co, v = (f(r[k]) for k in ("T", "RH", "NH3", "CO2", "V"))
    vlo, vhi = (0.1, 0.3) if wk <= 2 else (0.3, 0.8)
    return (t < lo or t > hi) or not (50 <= rh <= 70) or nh > 20 or co > 3000 or not (vlo <= v <= vhi)


def kappa2(pairs):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def p_local(r):
    """Level of P with the houses' own targets in weeks 1-3 (as in target_sensitivity.py)."""
    wk = int(r["Week"])
    th = band(abs(f(r["T"]) - LOCAL_T[wk]), 2, 4) if wk <= 3 else int(r["thP"])
    return max(th, int(r["nhP"]), int(r["coP"]))


def compare(rows, ref, level=lambda r: int(r["P"])):
    """Records flagged (Moderate or Severe) by the rules vs by the reference; disagreements by kind."""
    pairs = [(level(r) >= 1, bool(ref(r))) for r in rows]
    p_only = [r for r, (a, b) in zip(rows, pairs) if a and not b]
    r_only = [r for r, (a, b) in zip(rows, pairs) if b and not a]
    th = lambda r: (band(abs(f(r["T"]) - LOCAL_T[int(r["Week"])]), 2, 4) if level is p_local and int(r["Week"]) <= 3
                    else int(r["thP"]))
    warm = lambda r: f(r["T"]) > T_RANGE[int(r["Week"])][1]
    return {"records": len(rows), "P_flag": sum(a for a, _ in pairs), "ref_flag": sum(b for _, b in pairs),
            "both": sum(a and b for a, b in pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4),
            "kappa": round(kappa2(pairs), 3),
            "P_only": len(p_only), "P_only_thermal": sum(th(r) >= 1 for r in p_only),
            "P_only_gas_only": sum(th(r) == 0 for r in p_only),
            "P_only_thermal_T_in_range_weeks4to6": sum(th(r) >= 1 and int(r["Week"]) >= 4 for r in p_only),
            "ref_only": len(r_only), "ref_only_too_warm": sum(warm(r) for r in r_only),
            "ref_only_too_cold": sum(not warm(r) for r in r_only)}


def boot_flock(rows, stat):
    cl = defaultdict(list)
    for r in rows:
        cl[(r["flock"], r["House"])].append(r)
    keys = list(cl)
    vals = sorted(v for v in (stat([x for k in (rng.choice(keys) for _ in keys) for x in cl[k]]) for _ in range(B))
                  if v == v)
    return [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)]


def main():
    rows = list(csv.DictReader(open(SRC)))
    out = {"records": len(rows), "reference_ranges": {"T_C_by_week": T_RANGE, "RH_pct": [50, 70], "NH3_max": 20,
                                                       "CO2_max": 3000, "V_weeks1to2": [0.1, 0.3], "V_later": [0.3, 0.8]}}
    early = [r for r in rows if int(r["Week"]) <= 3]
    late = [r for r in rows if int(r["Week"]) >= 4]
    out["P_vs_CTRL"] = {"all": compare(rows, ctrl), "weeks1to3": compare(early, ctrl), "weeks4to6": compare(late, ctrl)}
    out["P_vs_DISC"] = {"all": compare(rows, disc), "weeks1to3": compare(early, disc), "weeks4to6": compare(late, disc)}
    out["Plocal_vs_CTRL"] = {"all": compare(rows, ctrl, p_local), "weeks1to3": compare(early, ctrl, p_local)}
    out["DISC_flag_share"] = round(sum(disc(r) for r in rows) / len(rows), 4)
    out["CTRL_too_warm_share"] = round(sum(1 for r in rows if ctrl(r) and f(r["T"]) > T_RANGE[int(r["Week"])][1])
                                       / max(1, sum(ctrl(r) for r in rows)), 4)

    # burden per surveyed house-day
    surveys = defaultdict(list)
    for r in rows:
        surveys[(r["flock"], r["House"], r["Week"], r["Time"])].append(r)
    days = {(k[0], k[1], k[2]) for k in surveys}
    def windows(level_fn):
        tops = [max(level_fn(r) for r in pts) for pts in surveys.values()]
        return {"MS": sum(t >= 1 for t in tops), "S": sum(t == 2 for t in tops)}
    ross = windows(lambda r: int(r["P"]))
    local = windows(p_local)
    ctrl_w = sum(any(ctrl(r) for r in pts) for pts in surveys.values())
    nd = len(days)
    out["burden"] = {
        "survey_windows": len(surveys), "house_days": nd,
        "ross": {**ross, "MS_per_day": round(ross["MS"] / nd, 2), "S_per_day": round(ross["S"] / nd, 2),
                 "notifications_per_run": TS["ross"]["escalations_per_run"]},
        "local": {**local, "MS_per_day": round(local["MS"] / nd, 2), "S_per_day": round(local["S"] / nd, 2),
                  "notifications_per_run": TS["local"]["escalations_per_run"]},
        "ctrl_alarm_windows": ctrl_w, "ctrl_per_day": round(ctrl_w / nd, 2),
    }

    # CIs resampling house-flocks
    def share(sel, cond):
        return lambda s: (sum(1 for r in s if sel(r) and cond(r)) / sum(1 for r in s if sel(r))
                          if any(sel(r) for r in s) else float("nan"))
    out["ci_house_flock"] = {
        "clusters": len({(r["flock"], r["House"]) for r in rows}),
        "O_undefined": boot_flock(rows, share(lambda r: True, lambda r: r["O"] == "")),
        "O_ne_P_where_defined": boot_flock(rows, share(lambda r: r["O"] != "", lambda r: int(float(r["O"])) != int(r["P"]))),
        "week1_MS_THI_rule": boot_flock(rows, share(lambda r: r["Week"] == "1", lambda r: int(float(r["thTHI"])) >= 1)),
        "P_MS_all": boot_flock(rows, share(lambda r: True, lambda r: int(r["P"]) >= 1)),
        "kappa_P_CTRL_weeks4to6": boot_flock(late, lambda s: kappa2([(int(r["P"]) >= 1, ctrl(r)) for r in s])),
    }
    json.dump(out, open(os.path.join(HERE, "baseline_burden.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
