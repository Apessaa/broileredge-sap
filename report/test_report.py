"""Tests of the house report (paper v17, Section IV-D) on SYNTHETIC test sequences.

The sequences below are made up to exercise each branch of the report (gaps, levels, recurring
possible causes, outstanding / overdue / completed tasks and the recovery check). They are test
inputs, not data, and no result in the paper is computed from them. The end-to-end part writes
assessments through the mock SAP module (sil/sap_mock.py) and marks a task complete the way a user
would in PM (QMSM-ERLDAT/ERLZEIT/ERLNAM), then builds the report from the stored tables.
Writes report_test_results.json.   Usage (from kit/): python3 report/test_report.py
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "sil"))
import house_report as HR  # noqa: E402
import sap_mock  # noqa: E402

results = []
T0 = datetime(2027, 1, 4, 6, 0)


def check(name, ok, **info):
    results.append({"check": name, "passed": bool(ok), **info})
    print("PASS" if ok else "FAIL", name, info if not ok else "")


def row(i, level, zone=1, pc=None, episode=0, step=300, diag=False, **inp):
    return {"assess_id": f"A{i}", "ts": (T0 + timedelta(seconds=step * i)).isoformat(), "zone": zone, "level": level,
            "cause": "thermal" if level else "none", "possible_cause": pc, "episode": episode,
            "rule_version": "2026-10-v2", "inputs": inp or None, "air_speed_diag": diag}


# 1. data completeness: 12 windows of 5 min, windows 4-6 lost
rows = [row(i, 0, THI=24.0 + i / 10) for i in range(12) if i not in (4, 5, 6)]
rep = HR.build_report(rows, [], [], "TESTFLOCK", 1, interval_s=300)
d = rep["data"]
check("data: 9 of 12 windows received, one gap of 3 windows from 06:20", d["received"] == 9 and d["expected"] == 12
      and d["gaps"] == [{"from": "2027-01-04T06:20:00", "missing": 3}] and d["completeness"] == 0.75, got=d)
check("data: without an interval (spot surveys) no gap check is made", "gaps" not in
      HR.build_report(rows, [], [], "TESTFLOCK", 1)["data"])

# 2. conditions and possible causes
rows = [row(0, 0, 1, THI=25.0, NH3=8, CO2=1500), row(1, 1, 2, "COOL", THI=27.0, NH3=9, CO2=1600),
        row(2, 2, 2, "COOL", 1, diag=True, THI=29.5, NH3=10, CO2=1700), row(3, 2, 2, "COOL", 0, diag=True, THI=29.8),
        row(4, 1, 3, "WETL", NH3=21, RH=74), row(5, 0, 1, THI=25.5)]
rep = HR.build_report(rows, [], [], "TESTFLOCK", 1)
c, p = rep["conditions"], rep["possible_causes"]
check("conditions: windows per level and worst level per zone",
      c["windows_per_level"] == {"Normal": 2, "Moderate": 2, "Severe": 2}
      and c["worst_level_per_zone"] == {1: "Normal", 2: "Severe", 3: "Moderate"}, got=c)
check("conditions: peaks of THI, NH3 and CO2; windows with the low-air-speed diagnostic",
      c["peaks"] == {"THI": 29.8, "NH3": 21.0, "CO2": 1700.0} and c["low_air_speed_windows"] == 2, got=c)
check("possible causes: counted over Moderate and Severe windows and Severe episode starts",
      p["moderate_or_severe_windows"] == {"COOL": 3, "WETL": 1} and p["severe_episode_starts"] == {"COOL": 1}, got=p)

# 3. recurring possible causes: >= 2 notifications or >= 3 episode starts
rows = [row(i, 2, 1, "SETP", 1, step=3600) for i in range(3)] + [row(3 + i, 2, 2, "COOL", 1, step=3600) for i in range(3)] \
    + [row(6 + i, 2, 3, "WETL", 1, step=3600) for i in range(2)]
notifs = [{"notif_id": "N1", "ts": rows[0]["ts"], "zone": 1, "trigger_id": "A0"},
          {"notif_id": "N2", "ts": rows[1]["ts"], "zone": 1, "trigger_id": "A1"}]
rep = HR.build_report(rows, notifs, [], "TESTFLOCK", 1)
rec = [r["code"] for r in rep["possible_causes"]["recurring"]]
check("recurring: SETP (3 episode starts, 2 notifications) and COOL (3 episode starts); WETL (2 starts) not",
      rec == ["COOL", "SETP"], got=rec)
check("recurring: the text says the cause may be systematic", "RECURRING SETP (Set point or heat above the target)"
      in HR.render_text(rep))

# 4. notification check: outstanding, overdue, completed with the recovery check
rows = [row(0, 2, 2, "COOL", 1), row(1, 2, 2, "COOL"), row(2, 2, 2, "COOL"), row(3, 0, 1), row(4, 0, 1)]
n = [{"notif_id": "N1", "ts": rows[0]["ts"], "zone": 2, "trigger_id": "A0"}]
done = lambda i: (T0 + timedelta(seconds=300 * i + 60)).isoformat()
tasks = [{"notif_id": "N1", "task_key": 1, "code": "FANS", "completed_at": done(0), "completed_by": "TESTUSER"},
         {"notif_id": "N1", "task_key": 2, "code": "PADS", "completed_at": done(4), "completed_by": "TESTUSER"},
         {"notif_id": "N1", "task_key": 3, "code": "PADC", "completed_at": None, "completed_by": None}]
rep = HR.build_report(rows, n, tasks, "TESTFLOCK", 1, now=(T0 + timedelta(hours=2)).isoformat())
items = rep["notification_check"]["items"][0]["tasks"]
check("notification check: FANS completed and the house back to Normal within 3 windows",
      items[0]["status"] == "completed" and items[0]["recovery"] == "back to Normal" and items[0]["by"] == "TESTUSER", got=items[0])
check("notification check: completed after the last window -> too early to tell",
      items[1]["recovery"] == "too early to tell", got=items[1])
check("notification check: open task 2 h after the notification is outstanding", items[2]["status"] == "outstanding")
rep = HR.build_report(rows, n, tasks, "TESTFLOCK", 1, now=(T0 + timedelta(hours=25)).isoformat())
check("notification check: open task 25 h after the notification is overdue (> 24 h)",
      rep["notification_check"]["task_status"] == {"completed": 2, "overdue": 1}, got=rep["notification_check"]["task_status"])
rows2 = [row(0, 2, 2, "COOL", 1), row(1, 2, 2), row(2, 2, 2), row(3, 2, 2), row(4, 1, 2)]
t2 = [{"notif_id": "N1", "task_key": 1, "code": "FANS", "completed_at": done(0), "completed_by": "TESTUSER"},
      {"notif_id": "N1", "task_key": 2, "code": "PADS", "completed_at": done(1), "completed_by": "TESTUSER"}]
rep = HR.build_report(rows2, n, t2, "TESTFLOCK", 1)
check("recovery: still Severe in the 3 windows after completion -> not yet; Moderate among them -> improved",
      [t["recovery"] for t in rep["notification_check"]["items"][0]["tasks"]] == ["not yet", "improved, not Normal"],
      got=rep["notification_check"]["recovery"])
check("empty period: the report says so", "no assessments in the period" in HR.render_text(HR.build_report([], [], [], "X", 9)))

# 5. end to end through the mock SAP module (sil/sap_mock.py): store, escalate, complete a task in PM
def assessment(i, level, ep, pc, zone=2, tasks=("FANS", "PADS", "PADC")):
    return {"assessment_id": f"E{i}", "flock": "TESTFLOCK", "house": 1, "worst_zone": zone,
            "ts": (T0 + timedelta(minutes=5 * i)).isoformat(), "level": level, "cause": "thermal" if level else "none",
            "episode_start": ep, "tasks": list(tasks) if level else [], "rule_version": "2026-10-v2",
            "possible_cause": pc, "inputs": {"T": 31.0, "RH": 60.0}, "thi": 29.0 if level else 25.0}

seq = [assessment(0, 0, 0, None, 1), assessment(1, 2, 1, "COOL"), assessment(2, 0, 0, None, 1),
       assessment(3, 2, 1, "COOL"), assessment(4, 0, 0, None, 1), assessment(5, 2, 1, "COOL"),
       assessment(6, 2, 0, "COOL"), assessment(7, 0, 0, None, 1), assessment(8, 0, 0, None, 1)]
tmp = tempfile.mkdtemp(prefix="report_test_")
reports = {}
for mode in ("idem", "naive"):
    db = os.path.join(tmp, f"sap_{mode}.db")
    con = sap_mock.connect(db, mode)
    st = [sap_mock.z_brl_stress_save(con, a, mode)["status"] for a in seq]
    st += [sap_mock.z_brl_stress_save(con, seq[5], mode)["status"]]   # a resend after a lost acknowledgement
    nid = con.execute("SELECT notif_id FROM notif").fetchone()[0]
    # the farm head completes the first task in PM after window 6 (QMSM-ERLDAT/ERLZEIT/ERLNAM)
    con.execute("UPDATE notif_task SET completed_at=?, completed_by=? WHERE notif_id=? AND task_key=1",
                ((T0 + timedelta(minutes=31)).isoformat(), "TESTUSER", nid))
    rep = HR.build_report(*HR.load_mock(db, "TESTFLOCK", 1), "TESTFLOCK", 1, interval_s=300,
                          now=(T0 + timedelta(hours=26)).isoformat())
    reports[mode] = (st, rep)
st, rep = reports["idem"]
nc = rep["notification_check"]
check("end to end: 3 Severe episode starts open one notification with 3 PM tasks; the resend is rejected",
      st[-1] == "duplicate" and nc["notifications"] == 1 and len(nc["items"][0]["tasks"]) == 3, got=(st, nc["task_status"]))
check("end to end: the completed task is reported with its user and the house back to Normal; the open ones overdue",
      nc["task_status"] == {"completed": 1, "overdue": 2} and nc["items"][0]["tasks"][0]["recovery"] == "back to Normal"
      and nc["items"][0]["tasks"][0]["by"] == "TESTUSER", got=nc)
check("end to end: report data complete (9 of 9 windows) and the notification's possible cause is COOL",
      rep["data"]["received"] == 9 and rep["data"]["completeness"] == 1.0 and nc["items"][0]["possible_cause"] == "COOL"
      and rep["possible_causes"]["notifications"] == {"COOL": 1}, got=rep["data"])
check("end to end: THI peak taken from the stored payload", rep["conditions"]["peaks"].get("THI") == 29.0)
st_n, rep_n = reports["naive"]
check("without the idempotency key the resend is stored twice and the report counts 10 assessments for 9 windows",
      st_n[-1] == "stored" and rep_n["data"]["received"] == 10, got=rep_n["data"])

# 5b. a reporting period: earlier rows serve only the recovery check
rows = [row(0, 2, 2, "COOL", 1), row(1, 2, 2, "COOL"), row(2, 0, 1), row(3, 1, 3, "WETL"), row(4, 0, 1)]
n = [{"notif_id": "N1", "ts": rows[0]["ts"], "zone": 2, "trigger_id": "A0"}]
t3 = [{"notif_id": "N1", "task_key": 1, "code": "FANS", "completed_at": done(0), "completed_by": "TESTUSER"}]
rep = HR.build_report(rows, n, t3, "TESTFLOCK", 1, period_from=rows[1]["ts"])
check("period: conditions cover the rows after the start; the earlier trigger still gives the notification's "
      "possible cause and the recovery check", rep["data"]["received"] == 3
      and rep["possible_causes"]["moderate_or_severe_windows"] == {"WETL": 1}
      and rep["possible_causes"]["notifications"] == {"COOL": 1}
      and rep["notification_check"]["items"][0]["tasks"][0]["recovery"] == "back to Normal", got=rep)

# 6. the ABAP class uses the same limits and texts as this reference implementation
abap = open(os.path.join(KIT, "sap", "abap", "ZCL_BRL_HOUSE_REPORT.abap")).read()
const = dict(re.findall(r"CONSTANTS\s+(gc_\w+)\s+TYPE\s+i\s+VALUE\s+(\d+)\.", abap))
check("ABAP class constants equal the Python reference (24 h overdue, 3 windows, 2 notifications, 3 episodes)",
      const == {"gc_overdue_h": str(HR.OVERDUE_H), "gc_recover_win": str(HR.RECOVER_WINDOWS),
                "gc_recur_notif": str(HR.RECUR_NOTIFS), "gc_recur_epis": str(HR.RECUR_EPISODES)}, got=const)
texts = dict(re.findall(r"WHEN '(\w{4})'\. rv_text = '([^']*)'\.", abap))
check("ABAP possible-cause texts equal edge/tasks.py (POSSIBLE_CAUSES)",
      texts == {c: v[0] for c, v in HR.TK.POSSIBLE_CAUSES.items()}, got=texts)
unit = open(os.path.join(KIT, "sap", "abap", "ZCL_BRL_HOUSE_REPORT.testclasses.abap")).read()
check("ABAP Unit test class covers the same cases (6 test methods)", len(re.findall(r"FOR TESTING\.", unit)) == 6)

passed = sum(r["passed"] for r in results)
json.dump({"passed": passed, "total": len(results), "note": "synthetic test sequences, not data", "checks": results},
          open(os.path.join(HERE, "report_test_results.json"), "w"), indent=1)
print(f"{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
