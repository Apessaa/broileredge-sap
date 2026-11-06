"""Select the 12 zone conditions that experts rate in Part B of the questionnaire.

Source: data/replay_records.csv (open dataset, CC BY 4.0, rated with the revised rules P).
Selection (fixed seed, so the authors get the same sheet every time): four conditions per rule level
(Normal, Moderate, Severe); within a level, young birds (weeks 1-3, brooding rule) and older birds
(weeks 4-6, THI rule) and, where the data allow, NH3- and CO2-driven cases; at least three conditions on
which the original rule set O disagrees with P. The presentation order is shuffled.

Outputs
  scenarios.json      what experts see in Part B (no rule result)
  answer_key.json     rule level, cause, possible cause and the system's tasks per scenario: keep it
                      away from the experts until Form 1 is collected
  tasks_shown.json    what experts see in Part E of Form 2: level, cause, possible cause and tasks with
                      their sources for the scenarios rated Moderate or Severe (catalog v2)
"""
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "edge"))
import tasks as TK  # noqa: E402

SOURCE_LABEL = {"ROSS": "Ross Broiler Management Handbook 2025", "UGA-L": "UGA Bulletin 1267 (litter)",
                "MED-E": "Medion, closed-house equipment",
                "MED-C": "Medion, closed-house system", "-": "designers' inference, no source"}


def system_tasks(r):
    """(tasks, notes, thermal kind, possible cause) of the system for one record."""
    week, level = int(r["Week"]), int(r["P"])
    sub = {"thermal": int(r["thP"]), "NH3": int(r["nhP"]), "CO2": int(r["coP"])}
    cause = "+".join(k for k in TK.INDICATORS if sub[k] == level) if level else "none"
    t_star = float(r["Tstar"]) if week <= 3 else None
    inp = {"T": float(r["T"]), "RH": float(r["RH"])}
    tasks, notes, kind = TK.assessment_tasks(level, cause, sub, inp, week, t_star, r["diag18"] == "True")
    return tasks, notes, kind, TK.possible_cause(level, cause, inp, week, t_star, r["diag18"] == "True")


def source_of(code):
    text, src, page, basis = TK.CATALOG[code]
    lab = "; ".join(SOURCE_LABEL[x] for x in src.split("+"))
    return lab + ("" if page == "-" else f", p. {page}")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "replay_records.csv")
rng = random.Random(20261026)


def main():
    rows = list(csv.DictReader(open(SRC)))
    lv = lambda x: int(float(x)) if x != "" else None
    for r in rows:
        r["_P"], r["_O"] = lv(r["P"]), lv(r["O"])
        r["_young"] = int(r["Week"]) <= 3
    picked = []

    def take(cond, n=1):
        pool = [r for r in rows if cond(r) and r not in picked]
        rng.shuffle(pool)
        picked.extend(pool[:n])
        return len(pool[:n])

    for level in (0, 1, 2):
        got = 0
        got += take(lambda r: r["_P"] == level and r["_young"] and r["cause"] in ("thermal", "none"))
        got += take(lambda r: r["_P"] == level and not r["_young"] and r["cause"] in ("thermal", "none"))
        if level > 0:
            got += take(lambda r: r["_P"] == level and "NH3" in r["cause"] and r["_O"] is not None and r["_O"] != r["_P"])
            got += take(lambda r: r["_P"] == level and "CO2" in r["cause"]) or take(lambda r: r["_P"] == level)
        while got < 4:
            got += take(lambda r: r["_P"] == level and r["_O"] is not None and r["_O"] != r["_P"]) or take(
                lambda r: r["_P"] == level)
    assert len(picked) == 12, len(picked)
    rng.shuffle(picked)
    scen, key, shown = [], [], []
    for i, r in enumerate(picked, 1):
        sid = f"S{i:02d}"
        scen.append({"id": sid, "week": int(r["Week"]), "weight_g": round(float(r["W"])), "T_C": float(r["T"]),
                     "RH_pct": float(r["RH"]), "air_speed_ms": float(r["V"]), "CO2_ppm": round(float(r["CO2"])),
                     "NH3_ppm": float(r["NH3"])})
        tasks, notes, kind, pcause = system_tasks(r)
        key.append({"id": sid, "rule_level": r["_P"], "rule_cause": r["cause"], "original_rule_level": r["_O"],
                    "system_tasks": tasks, "task_notes": notes, "thermal_kind": kind, "possible_cause": pcause,
                    "rule_version": TK.RULE_VERSION,
                    "flock": r["flock"], "house": int(r["House"]), "week": int(r["Week"]), "window": int(r["Time"]),
                    "point": int(r["Sector"])})
        if tasks:
            shown.append({"id": sid, "level": ["Normal", "Moderate", "Severe"][r["_P"]], "cause": r["cause"],
                          "thermal_kind": kind, "notes": notes, "possible_cause": pcause,
                          "possible_cause_text": TK.POSSIBLE_CAUSES[pcause][0] if pcause else None,
                          "task_mode": "preventive" if r["_P"] == 1 else "corrective",
                          "tasks": [{"code": c, "text": TK.CATALOG[c][0], "source": source_of(c),
                                     "basis": TK.CATALOG[c][3]} for c in tasks]})
    json.dump(scen, open(os.path.join(HERE, "scenarios.json"), "w"), indent=1)
    json.dump(key, open(os.path.join(HERE, "answer_key.json"), "w"), indent=1)
    json.dump(shown, open(os.path.join(HERE, "tasks_shown.json"), "w"), indent=1)
    lvls = [k["rule_level"] for k in key]
    print("levels N/M/S:", lvls.count(0), lvls.count(1), lvls.count(2),
          "| O differs from P:", sum(1 for k in key if k["original_rule_level"] is not None and k["original_rule_level"] != k["rule_level"]),
          "| O undefined:", sum(1 for k in key if k["original_rule_level"] is None),
          "| scenarios with tasks:", len(shown))


if __name__ == "__main__":
    main()
