"""Replay of the task catalog and possible causes (edge/tasks.py) on the 1,692 open records (Section V-A
of paper v17).

Input : data/replay_records.csv (levels of the revised rules P per record, from replay_v13.py)
Output: tasks_replay.json

Each record is one zone at one moment, rated without persistence (spot data), so its level is the raw
level P and its cause the indicators at that level. The 141 surveys (house, week, daily window) are
also replayed as house assessments (worst point, lowest point number on ties), as in the
fault-injection test. This describes what the catalog would have advised; whether the advice is right
is for the expert evaluation (kit/expert_eval). 95% CIs: cluster bootstrap over the 141 surveys.
"""
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edge"))
import tasks as TK  # noqa: E402

SRC = os.path.join(HERE, "..", "data", "replay_records.csv")
B = 10000
rng = random.Random(20261027)
IND = ("thermal", "NH3", "CO2")


def record_tasks(r):
    week = int(r["Week"])
    sub = {"thermal": int(r["thP"]), "NH3": int(r["nhP"]), "CO2": int(r["coP"])}
    level = int(r["P"])
    cause = "+".join(k for k in IND if sub[k] == level) if level else "none"
    t_star = float(r["Tstar"]) if week <= 3 else None
    inp = {"T": float(r["T"]), "RH": float(r["RH"])}
    tasks, notes, kind = TK.assessment_tasks(level, cause, sub, inp, week, t_star, r["diag18"] == "True")
    pcause = TK.possible_cause(level, cause, inp, week, t_star, r["diag18"] == "True")
    return level, cause, tasks, notes, kind, pcause


def boot(clusters, stat):
    keys = list(clusters)
    vals = []
    for _ in range(B):
        v = stat([r for k in (rng.choice(keys) for _ in keys) for r in clusters[k]])
        if v == v:
            vals.append(v)
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)]


def pct(c, n):
    return round(100.0 * c / n, 1) if n else None


def main():
    rows = list(csv.DictReader(open(SRC)))
    surveys = defaultdict(list)
    for r in rows:
        level, cause, tasks, notes, kind, pcause = record_tasks(r)
        r.update(_level=level, _cause=cause, _tasks=tasks, _notes=notes, _kind=kind, _pcause=pcause)
        surveys[(r["flock"], r["House"], r["Week"], r["Time"])].append(r)
    ms = [r for r in rows if r["_level"] >= 1]
    inst = [c for r in ms for c in r["_tasks"]]
    first = Counter(r["_tasks"][0] for r in ms if r["_tasks"])
    out = {
        "rule_version": TK.RULE_VERSION, "records": len(rows), "surveys": len(surveys),
        "records_MS": len(ms), "records_MS_with_task": sum(1 for r in ms if r["_tasks"]),
        "records_N_with_task": sum(1 for r in rows if r["_level"] == 0 and r["_tasks"]),
        "tasks_per_MS_record": dict(sorted(Counter(len(r["_tasks"]) for r in ms).items())),
        "mean_tasks_per_MS_record": round(len(inst) / len(ms), 2),
        "task_instances": len(inst),
        "task_instances_basis_E": sum(1 for c in inst if TK.CATALOG[c][3] == "E"),
        "first_task_counts": dict(first.most_common()),
        "first_task_pct": {c: pct(n, len(ms)) for c, n in first.most_common()},
        "task_counts": dict(Counter(inst).most_common()),
        "catalog_codes_used": sorted(set(inst)),
        "possible_cause_counts": dict(Counter(r["_pcause"] for r in ms).most_common()),
        "possible_cause_pct": {c: pct(n, len(ms)) for c, n in Counter(r["_pcause"] for r in ms).most_common()},
        "records_MS_without_possible_cause": sum(1 for r in ms if not r["_pcause"]),
        "possible_cause_first_task": {f"{c}>{t}": n for (c, t), n in
                                      Counter((r["_pcause"], r["_tasks"][0]) for r in ms).most_common()},
        "possible_cause_by_level": {f"{c}@{lv}": n for (c, lv), n in
                                    Counter((r["_pcause"], r["_level"]) for r in ms).most_common()},
    }
    out["task_instances_basis_E_pct"] = pct(out["task_instances_basis_E"], len(inst))
    for name, sel in (("weeks1to3", lambda r: int(r["Week"]) <= 3), ("weeks4to6", lambda r: int(r["Week"]) >= 4),
                      ("winter", lambda r: r["flock"] == "winter"), ("summer", lambda r: r["flock"] == "summer")):
        sub = [r for r in ms if sel(r)]
        out[f"first_task_pct_{name}"] = {c: pct(n, len(sub)) for c, n in
                                         Counter(r["_tasks"][0] for r in sub).most_common()}
        out[f"records_MS_{name}"] = len(sub)
        out[f"first_task_counts_{name}"] = dict(Counter(r["_tasks"][0] for r in sub).most_common())
        inst_sub = [c for r in sub for c in r["_tasks"]]
        out[f"basis_E_pct_{name}"] = pct(sum(1 for c in inst_sub if TK.CATALOG[c][3] == "E"), len(inst_sub))
        brs = [r for r in sub if int(r["Week"]) <= 3 and "thermal" in r["_cause"].split("+")]
        out[f"brooding_hot_pct_{name}"] = pct(sum(1 for r in brs if r["_kind"] == "hot"), len(brs))

    # thermal direction in the brooding period (weeks 1-3), thermal in the cause
    br = [r for r in ms if int(r["Week"]) <= 3 and "thermal" in r["_cause"].split("+")]
    out["brooding_thermal_cause_records"] = len(br)
    out["brooding_kind_counts"] = dict(Counter(r["_kind"] for r in br))
    # cooling-pad guard among Severe heat ratings (thermal Severe from week 4)
    hs = [r for r in rows if int(r["Week"]) >= 4 and int(r["thP"]) == 2 and r["_level"] == 2]
    out["severe_heat_records"] = len(hs)
    out["severe_heat_pads_given"] = sum(1 for r in hs if "PADS" in r["_tasks"])
    out["severe_heat_pads_withheld"] = sum(1 for r in hs if any(n.startswith("pads withheld") for n in r["_notes"]))
    out["pads_withheld_reasons"] = dict(Counter(n.split(":")[1].split()[0] for r in hs for n in r["_notes"]))
    out["severe_heat_RH_max"] = max(float(r["RH"]) for r in hs) if hs else None
    out["diagnostic_task_records"] = sum(1 for r in ms if any(c in r["_tasks"] for c in TK.DIAG_TASKS))

    # survey level (house assessment = worst point), as in the fault-injection test
    sv = []
    for k, pts in surveys.items():
        top = max(r["_level"] for r in pts)
        worst = min((r for r in pts if r["_level"] == top), key=lambda r: int(r["Sector"]))
        sv.append(worst)
    sv_ms = [r for r in sv if r["_level"] >= 1]
    out["surveys_MS"] = len(sv_ms)
    out["survey_first_task_counts"] = dict(Counter(r["_tasks"][0] for r in sv_ms).most_common())
    out["survey_task_lists"] = dict(Counter("|".join(r["_tasks"]) for r in sv_ms).most_common())
    out["survey_possible_cause_counts"] = dict(Counter(r["_pcause"] for r in sv_ms).most_common())

    # CIs (cluster bootstrap over surveys)
    def share(sel, cond):
        def f(sample):
            s = [r for r in sample if sel(r)]
            return sum(1 for r in s if cond(r)) / len(s) if s else float("nan")
        return f
    stats = {
        "brooding_thermal_hot_share": share(lambda r: r["_level"] >= 1 and int(r["Week"]) <= 3
                                            and "thermal" in r["_cause"].split("+"), lambda r: r["_kind"] == "hot"),
        "severe_heat_pads_withheld_share": share(lambda r: int(r["Week"]) >= 4 and int(r["thP"]) == 2 and r["_level"] == 2,
                                                 lambda r: "PADS" not in r["_tasks"]),
        "MS_first_task_CHBH_share": share(lambda r: r["_level"] >= 1, lambda r: r["_tasks"][0] == "CHBH"),
        "MS_first_task_FANS_share": share(lambda r: r["_level"] >= 1, lambda r: r["_tasks"][0] == "FANS"),
    }
    out["ci"] = {}
    for name, f in stats.items():
        out["ci"][name] = {"value": round(f(rows), 4), "ci95": boot(surveys, f)}
    json.dump(out, open(os.path.join(HERE, "tasks_replay.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
