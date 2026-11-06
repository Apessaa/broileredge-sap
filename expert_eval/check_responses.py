"""Check responses.csv before the analysis: columns, allowed values, blanks, duplicates and patterns worth a look.

  python3 check_responses.py responses.csv

Errors (the analysis would be wrong): a missing or unknown column, a value other than 1-5 (or TD in Part A),
a repeated row number, TD in Part B. Notes (allowed, but look at the form again): blank answers, a form whose
Part A answers are all the same number, the attention check (item 13) answered 4-5.
Exit status 1 if there is any error.
"""
import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "form_spec.json"), encoding="utf-8"))
TEMPLATE = open(os.path.join(HERE, "responses_template.csv"), encoding="utf-8").read().strip().split(",")
PART_A = [i["id"] for i in SPEC["items"]]
PART_B = [c for c in TEMPLATE if c.startswith("C") and "_" in c]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    rows = [r for r in rows if any(r.values())]
    errors, notes = [], []
    missing = [c for c in TEMPLATE if c not in header]
    extra = [c for c in header if c not in TEMPLATE]
    if missing:
        errors.append(f"missing columns: {missing}")
    if extra:
        errors.append(f"unknown columns: {extra}")
    ids = [r.get("row", "") for r in rows]
    for rid, n in Counter(ids).items():
        if not rid:
            errors.append("a row without a row number")
        elif n > 1:
            errors.append(f"row number {rid} appears {n} times")
    for r in rows:
        rid = r.get("row") or "?"
        for c in PART_A:
            v = r.get(c, "").upper()
            if v and v not in {"1", "2", "3", "4", "5", "TD"}:
                errors.append(f"{rid} {c}: {r[c]!r} is not 1-5 or TD")
        for c in PART_B:
            v = r.get(c, "").upper()
            if v == "TD":
                errors.append(f"{rid} {c}: TD is not an option in Part B")
            elif v and v not in {"1", "2", "3", "4", "5"}:
                errors.append(f"{rid} {c}: {r[c]!r} is not 1-5")
        blank_a = [c for c in PART_A if not r.get(c)]
        blank_b = [c for c in PART_B if not r.get(c)]
        if blank_a or blank_b:
            notes.append(f"{rid}: blank in Part A {blank_a or '-'}; Part B {blank_b or '-'}")
        vals = [r.get(c) for c in PART_A if r.get(c) and r.get(c).upper() != "TD" and c != "CHK"]
        if len(vals) >= 10 and len(set(vals)) == 1:
            notes.append(f"{rid}: every rated Part A item is {vals[0]} (straight-lining?): check the form")
        if all(r.get(c, "").upper() == "TD" for c in PART_A if c != "CHK"):
            notes.append(f"{rid}: every Part A item is TD: this form adds nothing to Part A")
        chk = r.get("CHK", "")
        if chk in {"4", "5"}:
            notes.append(f"{rid}: attention check (item 13) answered {chk}; the analysis also reports results without this form")
    print(f"{len(rows)} forms; {len(header)} columns")
    for e in errors:
        print("ERROR", e)
    for n in notes:
        print("note ", n)
    print("OK: ready for analyse_expert.py" if not errors else f"{len(errors)} error(s): fix them before the analysis")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
