"""Summary of the house reports built from the SAP tables of the fault-injection runs (paper v17, V-C).

The reports are built with house_report.py from each run's mock SAP database (sap.db), as the ABAP
report would build them from ZBRL_STRESS, ZBRL_NOTIF and QMSM. Without completions (nobody completes
tasks in a replay) every task is open; 'now' is the last window of each house, so tasks of earlier
notifications are overdue.
Usage (from kit/): python3 report/report_summary.py <runs root of sil_run.py> [more roots]
                   -> report/report_summary.json
"""
import glob
import json
import os
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import house_report as HR  # noqa: E402


def run_reports(db):
    pairs = sqlite3.connect(db).execute("SELECT DISTINCT flock, house FROM zbrl_stress ORDER BY flock, house").fetchall()
    return [HR.build_report(*HR.load_mock(db, f, h), f, h) for f, h in pairs]


def main():
    out = {}
    for root in sys.argv[1:]:
        for d in sorted(glob.glob(os.path.join(root, "*_seed*"))):
            name = os.path.basename(d)
            backend, mode = name.split("_")[0], name.split("_")[1]
            reps = run_reports(os.path.join(d, "sap.db"))
            pc_n = Counter()
            for r in reps:
                pc_n.update(r["possible_causes"]["notifications"])
            s = out.setdefault(f"{backend}_{mode}", {"runs": 0, "reports": 0, "assessments_counted": 0,
                                                     "notifications": 0, "notification_possible_causes": Counter(),
                                                     "recurring_houses": Counter(), "tasks": Counter(), "per_run": []})
            s["runs"] += 1
            s["reports"] += len(reps)
            s["assessments_counted"] += sum(r["data"]["received"] for r in reps)
            s["notifications"] += sum(r["notification_check"]["notifications"] for r in reps)
            s["notification_possible_causes"].update(pc_n)
            rec = Counter(c["code"] for r in reps for c in r["possible_causes"]["recurring"])
            s["recurring_houses"].update(rec)
            for r in reps:
                s["tasks"].update(r["notification_check"]["task_status"])
            s["per_run"].append({"run": name, "assessments_counted": sum(r["data"]["received"] for r in reps),
                                 "notifications": sum(r["notification_check"]["notifications"] for r in reps),
                                 "notification_possible_causes": dict(pc_n), "recurring_houses": dict(rec)})
    for s in out.values():
        for k in ("notification_possible_causes", "recurring_houses", "tasks"):
            s[k] = dict(s[k])
    json.dump(out, open(os.path.join(HERE, "report_summary.json"), "w"), indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_run"} for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
