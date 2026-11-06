"""Check of the task catalog against independent guidance (paper v17, Section V-A): sources not used to
build catalog v1 (Cobb broiler guide rev. 2012, MSU Extension P2774, UGA Poultry Housing Tips 9(3)).
For each situation it records the first task of catalog v1 and v2 and whether the independent source
puts the same kind of action first. This is a document analysis by the authors, not an expert
evaluation. Aviagen's other publications are not independent of the Ross handbook and are not used.
Usage (from kit/): python3 validation/independent_guidance.py   -> independent_guidance.json
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edge"))
import tasks as TK  # noqa: E402

rows = list(csv.DictReader(open(os.path.join(HERE, "independent_guidance.csv"))))
first = [r for r in rows if r["id"] not in ("G2", "G7")]          # situations with a first task
# the v2 first tasks in the table are those of the catalog
mapping = {"G1": ("heat", 1), "G3": ("hot", 1), "G4": ("cold", 1), "G5": ("cold", 2), "G6": ("NH3", 1), "G8": ("CO2", 1)}
consistent = all(TK.MAP[mapping[r["id"]]][0] == r["catalog_v2_first"] for r in rows if r["id"] in mapping)
out = {
    "situations": len(rows), "first_task_situations": len(first),
    "first_task_agrees_v1": sum(r["first_task_agrees_v1"] == "yes" for r in first),
    "first_task_agrees_v2": sum(r["first_task_agrees_v2"] == "yes" for r in first),
    "all_agree_v2": all(r["first_task_agrees_v2"] == "yes" for r in rows),
    "changed_in_v2": [r["id"] for r in rows if r["change_in_v2"] != "-"],
    "table_matches_catalog_v2": consistent, "rule_version": TK.RULE_VERSION,
}
json.dump(out, open(os.path.join(HERE, "independent_guidance.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
sys.exit(0 if consistent else 1)
