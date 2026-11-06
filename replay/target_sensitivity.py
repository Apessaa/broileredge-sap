"""Sensitivity of the brooding rule (weeks 1-3) to the target temperature T* (paper v18, Section V-A).

T* is a parameter of the design. The replay used the Ross target by body weight and RH, but the birds of the
open dataset are Cobb 500 and the houses followed their own programme. This script re-rates weeks 1-3 with
  ross        Ross target by weight and RH (the replay's T*, column Tstar)
  ross+k      the Ross target raised by k = 1..4 C
  cobb        Cobb Broiler Management Guide rev. 2012, p. 21, whole-house brooding, parent flocks > 30 weeks:
              day 0: 33, day 7: 30, day 14: 27, day 21: 24 C, interpolated at mid-week (day 3.5, 10.5, 17.5)
  local       the dataset authors' own target ranges (Coimbra da Silva et al. 2025): week 1 32-34, week 2 30-32,
              week 3 28-30 C, midpoints 33, 31, 29 C
and reports, per target: the share of weeks 1-3 records whose thermal level is Moderate or Severe, the share
of those that are too warm, the share of house assessments (surveys) Moderate or Severe overall, and the
escalations of the fault-injection test (three Severe windows of a zone within 24 h). Weeks 4-6 are unchanged.
95% CIs: cluster bootstrap over the surveys of weeks 1-3.   Output: target_sensitivity.json
"""
import csv
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edge"))
import rules_core as M  # noqa: E402

SRC = os.path.join(HERE, "..", "data", "replay_records.csv")
B = 5000
rng = random.Random(20261028)
COBB = ((0, 33.0), (7, 30.0), (14, 27.0), (21, 24.0))
LOCAL = {1: 33.0, 2: 31.0, 3: 29.0}


def cobb_target(week):
    day = 7 * (week - 1) + 3.5
    for (d0, t0), (d1, t1) in zip(COBB, COBB[1:]):
        if d0 <= day <= d1:
            return t0 + (t1 - t0) * (day - d0) / (d1 - d0)
    return COBB[-1][1]


def targets(r):
    wk, ross = int(r["Week"]), float(r["Tstar"])
    out = {"ross": ross, "cobb": cobb_target(wk), "local": LOCAL[wk]}
    for k in (1, 2, 3, 4):
        out[f"ross+{k}"] = ross + k
    return out


def boot(clusters, stat):
    keys = list(clusters)
    vals = sorted(v for v in (stat([r for k in (rng.choice(keys) for _ in keys) for r in clusters[k]])
                              for _ in range(B)) if v == v)
    return [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)]


def escalations(rows):
    """Escalation rule of the SAP module on survey windows: 3 Severe windows of a zone within 24 h."""
    base = {"winter": datetime(2000, 1, 3), "summer": datetime(2000, 7, 3)}
    hours = {1: 8, 2: 12, 3: 16}
    win = defaultdict(list)
    for r in rows:
        win[(r["flock"], int(r["House"]), int(r["Week"]), int(r["Time"]))].append((int(r["Sector"]), r["_P"]))
    sev = []
    for (f, h, wk, tw), pts in win.items():
        top = max(p for _, p in pts)
        if top == 2:
            zone = min(s for s, p in pts if p == top)
            sev.append((base[f] + timedelta(days=7 * (wk - 1), hours=hours[tw]), f, h, zone))
    sev.sort()
    n, last, hist = 0, {}, defaultdict(list)
    for ts, f, h, z in sev:
        k = (f, h, z)
        hist[k].append(ts)
        lower = max(ts - timedelta(hours=24), last.get(k, datetime.min))
        if sum(1 for t in hist[k] if lower < t <= ts) >= 3:
            n += 1
            last[k] = ts
    return n


def main():
    rows = list(csv.DictReader(open(SRC)))
    names = ["ross", "ross+1", "ross+2", "ross+3", "ross+4", "cobb", "local"]
    out = {"records_weeks1to3": 0, "targets": {}}
    young = [r for r in rows if int(r["Week"]) <= 3]
    out["records_weeks1to3"] = len(young)
    surveys = defaultdict(list)
    for r in young:
        surveys[(r["flock"], r["House"], r["Week"], r["Time"])].append(r)
    for name in names:
        for r in rows:
            wk = int(r["Week"])
            if wk <= 3:
                tstar = targets(r)[name]
                th = M.band(abs(float(r["T"]) - tstar), 2, 4, incl_lo=True)
                r["_th"], r["_warm"] = th, float(r["T"]) > tstar
            else:
                r["_th"], r["_warm"] = int(r["thP"]), False
            r["_P"] = max(r["_th"], int(r["nhP"]), int(r["coP"]))
        ms = [r for r in young if r["_th"] >= 1]
        share_ms = lambda s: sum(1 for r in s if r["_th"] >= 1) / len(s) if s else float("nan")
        warm = lambda s: (sum(1 for r in s if r["_th"] >= 1 and r["_warm"]) / sum(1 for r in s if r["_th"] >= 1)
                          if any(r["_th"] >= 1 for r in s) else float("nan"))
        sv = [max(r["_P"] for r in pts) for pts in surveys.values()]
        out["targets"][name] = {
            "thermal_MS_records": len(ms), "thermal_MS_share": round(share_ms(young), 4),
            "thermal_MS_share_ci95": boot(surveys, share_ms),
            "thermal_severe_records": sum(1 for r in young if r["_th"] == 2),
            "too_warm_share_of_MS": round(warm(young), 4) if ms else None,
            "surveys_weeks1to3_MS": sum(1 for v in sv if v >= 1), "surveys_weeks1to3": len(sv),
            "escalations_per_run": escalations(rows),
            "thermal_MS_share_by_flock": {f: round(share_ms([r for r in young if r["flock"] == f]), 4)
                                          for f in ("winter", "summer")},
        }
    out["cobb_targets_by_week"] = {w: round(cobb_target(w), 2) for w in (1, 2, 3)}
    json.dump(out, open(os.path.join(HERE, "target_sensitivity.json"), "w"), indent=1)
    for k, v in out["targets"].items():
        print(f"{k:7s} thermal M/S {v['thermal_MS_records']:4d} ({100 * v['thermal_MS_share']:.0f}%, CI "
              f"{100 * v['thermal_MS_share_ci95'][0]:.0f}-{100 * v['thermal_MS_share_ci95'][1]:.0f}%), severe "
              f"{v['thermal_severe_records']:4d}, too warm {v['too_warm_share_of_MS']}, surveys M/S "
              f"{v['surveys_weeks1to3_MS']}/{v['surveys_weeks1to3']}, escalations {v['escalations_per_run']}")


if __name__ == "__main__":
    main()
