"""Tests of the task catalog, its mapping and the possible causes (paper v17, Sections IV-C and V-A).
Writes tasks_test_results.json.
Usage (from kit/): python3 edge/tests/test_tasks.py
"""
import filecmp
import itertools
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = os.path.join(HERE, "..")
sys.path.insert(0, EDGE)
import pipeline as P  # noqa: E402
import tasks as T  # noqa: E402

results = []


def check(name, ok, **info):
    results.append({"check": name, "passed": bool(ok), **info})
    print("PASS" if ok else "FAIL", name, info if not ok else "")


def tk(level, cause, sub, inp, week, t_star=None, diag=False):
    return T.assessment_tasks(level, cause, sub, inp, week, t_star, diag)


# 1. catalog structure and SAP field lengths
check("catalog: codes <= 4 chars, texts <= 40 chars, every mapped code defined and every code mapped",
      not T.check_catalog(), problems=T.check_catalog())
check("rule version fits SAP field RULE_VER (CHAR 12)", len(T.RULE_VERSION) <= 12)
check("only HTSP is an inference (basis I)", [c for c, v in T.CATALOG.items() if v[3] == "I"] == ["HTSP"])
check("sil/tasks.py is identical to edge/tasks.py",
      filecmp.cmp(os.path.join(EDGE, "tasks.py"), os.path.join(EDGE, "..", "sil", "tasks.py"), shallow=False))

# 2. mapping cases (cause, level, guard)
cases = [
    ("heat Severe, RH 60%: fans, then pads, then pad check", tk(2, "thermal", {"thermal": 2}, {"T": 33, "RH": 60}, 5),
     ["FANS", "PADS", "PADC"]),
    ("heat Severe, RH 80%: pads withheld", tk(2, "thermal", {"thermal": 2}, {"T": 31, "RH": 80}, 5), ["FANS"]),
    ("heat Moderate + low air speed: fans, then fan belts and the inlet opening",
     tk(1, "thermal", {"thermal": 1}, {"T": 30, "RH": 70}, 5, diag=True), ["FANS", "FANB", "INLT"]),
    ("brooding cold Severe: heaters first, then chick behaviour (v2)",
     tk(2, "thermal", {"thermal": 2}, {"T": 26, "RH": 60}, 1, 31.0), ["HEAT", "CHBH", "MVCK"]),
    ("brooding cold Moderate: chick behaviour, then heaters (v2)",
     tk(1, "thermal", {"thermal": 1}, {"T": 28, "RH": 60}, 1, 31.0), ["CHBH", "HEAT", "MVCK"]),
    ("heat Severe + low air speed: fans, pads, then the fan belts before the pad pump (v2)",
     tk(2, "thermal", {"thermal": 2}, {"T": 33, "RH": 60}, 5, diag=True), ["FANS", "PADS", "FANB"]),
    ("heat Severe, RH 80% + low air speed: pads withheld, airflow checks",
     tk(2, "thermal", {"thermal": 2}, {"T": 31, "RH": 80}, 5, diag=True), ["FANS", "FANB", "INLT"]),
    ("brooding hot Severe: checks before lowering the set point",
     tk(2, "thermal", {"thermal": 2}, {"T": 34, "RH": 60}, 2, 29.0), ["CHBH", "MVCK", "HTSP"]),
    ("brooding, T missing: checks common to cold and hot", tk(1, "thermal", {"NH3": 0}, {}, 2), ["CHBH", "MVCK"]),
    ("NH3 Severe first, then the first task of thermal Moderate (breadth-first)",
     tk(2, "NH3", {"thermal": 1, "NH3": 2}, {"T": 30, "RH": 60}, 5), ["MVUP", "FANS", "LITC"]),
    ("NH3+CO2 Moderate tie: each indicator's first task before any second task",
     tk(1, "NH3+CO2", {"thermal": 0, "NH3": 1, "CO2": 1}, {"T": 30, "RH": 60}, 5), ["MVUP", "AIRQ", "LITC"]),
    ("brooding hot + CO2 Severe tie: chick behaviour, air quality, then ventilation check",
     tk(2, "thermal+CO2", {"thermal": 2, "NH3": 0, "CO2": 2}, {"T": 34, "RH": 60}, 2, 29.0), ["CHBH", "AIRQ", "MVCK"]),
    ("other indicator capped at the persisted level, cause first",
     tk(1, "thermal", {"thermal": 1, "NH3": 2}, {"T": 30, "RH": 60}, 5), ["FANS", "MVUP", "LITC"]),
    ("Normal: no task", tk(0, "none", {"thermal": 0}, {"T": 30, "RH": 60}, 5), []),
]
for name, got, exp in cases:
    check(f"mapping: {name}", got[0] == exp, got=got[0], expected=exp)

# 2b. possible causes (rule-based hints shown with the tasks and in the SAP house report)
pc = lambda level, cause, inp, week, t_star=None, diag=False: T.possible_cause(level, cause, inp, week, t_star, diag)
pcases = [
    ("heat, RH 60%: cooling stage below the load", pc(2, "thermal", {"T": 33, "RH": 60}, 5), "COOL"),
    ("heat, RH 80%: humid heat", pc(2, "thermal", {"T": 31, "RH": 80}, 5), "HUMH"),
    ("heat, RH 75.0% is not humid heat (pad limit)", pc(1, "thermal", {"T": 31, "RH": 75.0}, 5), "COOL"),
    ("heat + low air speed: low airflow", pc(1, "thermal", {"T": 30, "RH": 70}, 5, diag=True), "AIRF"),
    ("brooding cold: heaters or cold air", pc(1, "thermal", {"T": 28, "RH": 60}, 1, 31.0), "HTRC"),
    ("brooding hot: set point or heat above target", pc(2, "thermal", {"T": 34, "RH": 60}, 2, 29.0), "SETP"),
    ("brooding, T missing: no possible cause", pc(1, "thermal", {}, 2), None),
    ("NH3, RH 70%: wet litter", pc(2, "NH3", {"T": 30, "RH": 70.0}, 5), "WETL"),
    ("NH3, RH 69.9%: litter condition", pc(1, "NH3", {"T": 30, "RH": 69.9}, 5), "LITQ"),
    ("CO2: ventilation below need", pc(1, "CO2", {"T": 30, "RH": 60}, 5), "VENT"),
    ("NH3+CO2 tie: the first cause indicator (NH3)", pc(1, "NH3+CO2", {"T": 30, "RH": 60}, 5), "LITQ"),
    ("Normal: none", pc(0, "none", {"T": 30, "RH": 60}, 5), None),
]
for name, got, exp in pcases:
    check(f"possible cause: {name}", got == exp, got=got, expected=exp)
check("possible causes: codes <= 4 chars, texts <= 40 chars, every cause has a source",
      all(len(c) <= 4 and len(t) <= 40 and src for c, (t, src) in T.POSSIBLE_CAUSES.items()))

# 3. pad guard boundaries (Medion: RH <= 75%, T > 28 C, older than 14 days)
g = lambda rh, t, wk: "PADS" in tk(2, "thermal", {"thermal": 2}, {"T": t, "RH": rh}, wk)[0]
check("pad guard: RH 75.0% allowed, 75.1% withheld", g(75.0, 31, 5) and not g(75.1, 31, 5))
check("pad guard: T 28.0 C withheld, 28.1 C allowed",
      T.pad_guard({"T": 28.0, "RH": 60}, 5) is not None and T.pad_guard({"T": 28.1, "RH": 60}, 5) is None)
check("pad guard: week 3 (day 14) withheld, week 4 allowed", T.pad_guard({"T": 31, "RH": 60}, 3) is not None
      and T.pad_guard({"T": 31, "RH": 60}, 4) is None)

# 4. properties over a grid of levels, ages and inputs
bad = []
for (th, nh, co), week, (t, rh), diag in itertools.product(itertools.product((0, 1, 2), repeat=3), range(1, 7),
                                                           ((25, 50), (31, 60), (34, 80), (None, None)), (0, 1)):
    sub = {"thermal": th, "NH3": nh, "CO2": co}
    level = max(sub.values())
    cause = "+".join(k for k in T.INDICATORS if sub[k] == level) if level else "none"
    inp = {"T": t, "RH": rh}
    tasks, notes, kind = tk(level, cause, sub, inp, week, 29.0 if week <= 3 else None, bool(diag and week >= 4))
    if len(tasks) > 3 or len(set(tasks)) != len(tasks) or any(c not in T.CATALOG for c in tasks):
        bad.append(("size/codes", sub, week, tasks))
    if bool(tasks) != bool(level):
        bad.append(("task iff Moderate/Severe", sub, week, tasks))
    if week <= 3 and any(c in ("FANS", "PADS", "PADC") for c in tasks):
        bad.append(("no fan or pad task before day 21 (Ross p.31: air speed at chick level < 0.15 m/s)", sub, week, tasks))
    if tasks:
        top = [k for k in T.INDICATORS if sub[k] == level][0]
        kind_top = T.thermal_kind(week, t, 29.0 if week <= 3 else None) if top == "thermal" else top
        if tasks[0] != next(c for c in T.MAP[(kind_top, level)] if not (c in T.PAD_TASKS and T.pad_guard(inp, week))):
            bad.append(("first task belongs to the first indicator at the highest level", sub, week, tasks))
    pcause = T.possible_cause(level, cause, inp, week, 29.0 if week <= 3 else None, bool(diag and week >= 4))
    unknown_t = week <= 3 and t is None and cause.split("+")[0] == "thermal"
    if (pcause is not None) != (bool(level) and not unknown_t) or (pcause and pcause not in T.POSSIBLE_CAUSES):
        bad.append(("possible cause iff Moderate/Severe (unless T is missing in brooding)", sub, week, pcause))
    if pcause == "HUMH" and any(c in T.PAD_TASKS for c in tasks):
        bad.append(("humid heat never gets a pad task", sub, week, tasks))
    if pcause == "AIRF" and sub == {"thermal": 2, "NH3": 0, "CO2": 0} and "FANB" not in tasks:
        bad.append(("low airflow at Severe heat (no other indicator flagged) gets the fan-belt check", sub, week, tasks))
check("grid (1,296 cases): <= 3 distinct catalog tasks; tasks iff Moderate/Severe; no fan/pad task before "
      "day 21; first task from the most severe indicator; possible cause iff Moderate/Severe and consistent "
      "with the tasks (no pads in humid heat, fan-belt check with low airflow)", not bad, failures=bad[:5])

# 5. house assessment with persistence: tasks follow the persisted level
p = P.Persistence()
inp = {1: {"T": 34.0, "RH": 70.0, "CO2": 1500.0, "NH3": 5.0, "V": 0.8}}
a1 = P.house_assessment("F1", 1, datetime(2027, 1, 1, 12, 0), 5, 2000, inp, p)
a2 = P.house_assessment("F1", 1, datetime(2027, 1, 1, 12, 5), 5, 2000, inp, p)
check("pipeline: no task while persistence holds the level at Normal, tasks once Severe",
      a1["level"] == 0 and a1["tasks"] == [] and a2["level"] == 2 and a2["tasks"][:1] == ["FANS"],
      a1=(a1["level"], a1["tasks"]), a2=(a2["level"], a2["tasks"]))
check("pipeline: assessment carries rule version and survives JSON",
      json.loads(json.dumps(a2))["tasks"] == a2["tasks"] and a2["rule_version"] == T.RULE_VERSION)
pb = P.Persistence()
young = {1: {"T": 35.0, "RH": 60.0, "CO2": 1500.0, "NH3": 5.0, "V": 0.1}}
for m in (0, 5):
    b = P.house_assessment("F2", 1, datetime(2027, 1, 1, 9, m), 1, 44, young, pb)
check("pipeline: brooding target from body weight and RH sets the direction (hot at 35 C, day 1-7)",
      b["thermal_kind"] == "hot" and b["tasks"][0] == "CHBH" and b["t_target"] is not None, got=(b["thermal_kind"], b["tasks"]))
check("local alert text names the source of each task", "ROSS p.13" in T.describe("HEAT") and "[-; I]" in T.describe("HTSP"))
check("pipeline: assessment carries the possible cause and the task mode (preventive / corrective)",
      a2["possible_cause"] in T.POSSIBLE_CAUSES and a2["task_mode"] == "corrective" and a1["task_mode"] is None
      and b["possible_cause"] == "SETP", got=(a2["possible_cause"], a2["task_mode"], b["possible_cause"]))

passed = sum(r["passed"] for r in results)
json.dump({"passed": passed, "total": len(results), "rule_version": T.RULE_VERSION, "checks": results},
          open(os.path.join(HERE, "tasks_test_results.json"), "w"), indent=1)
print(f"{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
