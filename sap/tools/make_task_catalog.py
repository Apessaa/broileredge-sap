"""Writes sap/task_catalog.csv from edge/tasks.py: the codes, short texts and long texts to enter in
the PM catalog (catalog type 2 'Tasks', code group from STVARV ZBRL_TASK_GRP, e.g. ZBRL).
Usage (from kit/): python3 sap/tools/make_task_catalog.py"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "edge"))
import tasks as T  # noqa: E402

SRC = {
    "ROSS": "Aviagen, Ross Broiler Management Handbook, 2025",
    "UGA-L": "Ritz, Fairchild and Lacy, Litter Quality and Broiler Performance, UGA Extension Bulletin 1267",
    "MED-E": "Medion, All About Closed House Broiler Equipment, 2023",
    "MED-C": "Medion, Getting To Know The Closed House Cage System, 2019",
}


def source_text(src, page):
    if src == "-":
        return "Design inference: no cited source states this action."
    parts = [SRC[s] for s in src.split("+")]
    return "Source: " + "; ".join(parts) + ("" if page == "-" else f", p. {page}") + "."


out = os.path.join(HERE, "..", "task_catalog.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["code_group", "code", "short_text_40", "basis", "long_text", "rule_version"])
    for code, (text, src, page, basis) in T.CATALOG.items():
        w.writerow(["ZBRL", code, text, basis, f"{source_text(src, page)} Basis {basis}.", T.RULE_VERSION])
print(open(out).read())
