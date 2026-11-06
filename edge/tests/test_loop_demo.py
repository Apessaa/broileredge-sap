"""Closed-loop demonstration (paper v34, Section V-D): from three heat episodes to a completed PM task
and recovery in the daily report, with the real edge program on emulated sensors and the mock SAP module.

  emulated bus -> edge_live.py (poll 1 s, 5-s windows) -> middleware -> mock SAP (escalation, PM tasks)
  -> a script completes the tasks in the mock PM table, standing in for the farm office (step 8b)
  -> house report built from the mock SAP tables (step 9b)

Scenario in zone 1 of a 30-day-old flock (THI rules apply from day 21): three heat episodes (34 C, 80% RH,
THI above the Severe class, air speed 1.5 m/s) separated by normal conditions. The third Severe episode
start within 24 h must open exactly one notification with the tasks of the triggering assessment; when the
tasks are completed the heat ends (the action takes effect), and the report must show every task completed
by the farm office and the house back to Normal within three windows. Time is compressed (5-s windows), so
this checks the code path and the order of events, not field behaviour or field timing.
  python3 tests/test_loop_demo.py            (about 3 min; writes loop_demo_results.json)
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = os.path.dirname(HERE)
KIT = os.path.dirname(EDGE)
sys.path.insert(0, EDGE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "report"))
import house_report as HR  # noqa: E402
import devices as D  # noqa: E402
from emulator import Bus, EmulatedDevice  # noqa: E402

HOT, NORMAL = (34.0, 80.0, 1200), (26.0, 65.0, 1200)   # normal: THI about 24.7 (< 26) at day 30


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = tempfile.mkdtemp(prefix="loop_demo_")
    plan = [("ODMHM-R", 1, 1), ("ODMHM-R", 2, 2), ("ODMHM-R", 3, 3), ("S-NH3-01", 11, 2), ("S-NH3-01", 12, 3),
            ("HD53LS.S", 21, 2)]
    emu = {u: EmulatedDevice(m, u) for m, u, _ in plan}
    bus = Bus(list(emu.values()))

    def setv(u, vals):
        with bus.lock:
            emu[u].set_registers(D.OdmhmR.encode(*vals))
    for u in (1, 2, 3):
        setv(u, NORMAL)
    with bus.lock:
        for u in (11, 12):
            emu[u].set_registers(D.SNH301.encode(5.0), table="hold")
        emu[21].set_registers(D.HD53LSS.encode(1.5))

    port = free_port()
    sap_db = os.path.join(tmp, "sap.db")
    mw = subprocess.Popen([sys.executable, os.path.join(KIT, "sil", "middleware.py"), "--port", str(port), "--db",
                           sap_db, "--p503", "0", "--plost", "0", "--pslow", "0",
                           "--events", os.path.join(tmp, "mw_events.jsonl")], stdout=subprocess.DEVNULL)
    time.sleep(1.0)
    cfg = json.load(open(os.path.join(EDGE, "config_example.json")))
    cfg.update({"bus": {"port": bus.port, "baud": 9600, "parity": "N", "stopbits": 1, "timeout_s": 0.3},
                "poll_s": 1, "window_s": 5, "log_dir": os.path.join(tmp, "logs"), "maintenance_file": None,
                "middleware_url": f"http://127.0.0.1:{port}/assessments"})
    cfg["flock"].update({"placement_date": (date.today() - timedelta(days=30)).isoformat(), "weights_csv": None,
                         "initial_weight_g": 1800})
    cfgp = os.path.join(tmp, "config.json")
    json.dump(cfg, open(cfgp, "w"), indent=1)
    log = {"completed_at": None, "notif_seen_at": None}

    def scenario():
        time.sleep(15)
        for _ in range(2):                      # episodes 1 and 2: 15 s heat, 25 s normal
            setv(1, HOT); time.sleep(15)
            setv(1, NORMAL); time.sleep(25)
        setv(1, HOT)                            # episode 3: heat until the farm office completes the tasks
        t_end = time.time() + 60
        while time.time() < t_end:
            try:
                con = sqlite3.connect(sap_db)
                n = con.execute("SELECT notif_id FROM notif ORDER BY notif_id").fetchall()
                con.close()
            except sqlite3.Error:
                n = []
            if n:
                log["notif_seen_at"] = datetime.now().isoformat(timespec="seconds")
                time.sleep(5)                   # staff act, then the farm office records it in PM
                now = datetime.now().isoformat(timespec="seconds")
                con = sqlite3.connect(sap_db)
                con.execute("UPDATE notif_task SET completed_at=?, completed_by='FARM_OFFICE' "
                            "WHERE notif_id=? AND completed_at IS NULL", (now, n[0][0]))
                con.commit(); con.close()
                log["completed_at"] = now
                setv(1, NORMAL)                 # the action takes effect
                return
            time.sleep(1)
        setv(1, NORMAL)
    threading.Thread(target=scenario, daemon=True).start()
    edge = subprocess.run([sys.executable, os.path.join(EDGE, "edge_live.py"), "--config", cfgp, "--minutes", "2.9"],
                          capture_output=True, text=True, timeout=400)
    time.sleep(1)
    mw.terminate(); mw.wait()
    ob = sqlite3.connect(os.path.join(cfg["log_dir"], "outbox.db"))
    n_out = ob.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    unsent = ob.execute("SELECT COUNT(*) FROM outbox WHERE sent=0").fetchone()[0]
    sev_alerts = ob.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    sap = sqlite3.connect(sap_db)
    n_sap, n_ids = sap.execute("SELECT COUNT(*), COUNT(DISTINCT assess_id) FROM zbrl_stress").fetchone()
    episodes = sap.execute("SELECT COUNT(*) FROM zbrl_stress WHERE zone=1 AND episode=1 AND level=2").fetchone()[0]
    notifs = sap.execute("SELECT notif_id, zone, trigger_id FROM notif").fetchall()
    trig = sap.execute("SELECT episode, level, poss_cause, task1, task2, task3 FROM zbrl_stress WHERE assess_id=?",
                       (notifs[0][2],)).fetchone() if notifs else None
    ntasks = sap.execute("SELECT code, completed_at, completed_by FROM notif_task").fetchall()
    rep = HR.build_report(*HR.load_mock(sap_db, cfg["flock"]["id"], cfg["flock"]["house"]),
                          cfg["flock"]["id"], cfg["flock"]["house"], interval_s=cfg["window_s"])
    nc = rep.get("notification_check", {})
    checks = {
        "three Severe episodes in zone 1, each with a local alert": episodes == 3 and sev_alerts == 3
            and edge.stdout.count("SEVERE in zone 1") == 3,
        "exactly one PM notification, in zone 1, opened by the third episode start": len(notifs) == 1
            and notifs[0][1] == 1 and trig is not None and trig[0] == 1 and trig[1] == 2,
        "the notification carries the tasks of the triggering assessment": trig is not None
            and [t for t in trig[3:] if t] == [c for c, _, _ in ntasks],
        "the farm office completed every task (completion recorded in the PM task table)": bool(ntasks)
            and all(c and b == "FARM_OFFICE" for _, c, b in ntasks),
        "report: every task completed by the farm office": nc.get("task_status", {}).get("completed") == len(ntasks)
            and all(i["by"] == "FARM_OFFICE" for n in nc.get("items", []) for i in n["tasks"]),
        "report: house back to Normal within three windows after completion":
            nc.get("recovery", {}).get("back to Normal") == len(ntasks),
        "report: the possible cause of the three episodes is flagged as recurring":
            trig is not None and trig[2] in [r["code"] for r in rep["possible_causes"]["recurring"]],
        "every closed window reached mock SAP once, outbox drained": n_sap == n_ids and unsent <= 1
            and n_sap >= n_out - 1,
        "report: every window, no gap": rep["data"]["gaps"] == [] and rep["data"]["received"] == n_sap,
    }
    for k, ok in checks.items():
        print("OK  " if ok else "FAIL", k)
    out = {"passed": sum(checks.values()), "total": len(checks), "checks": checks, "windows": n_sap,
           "episodes": episodes, "notifications": len(notifs), "possible_cause": trig[2] if trig else None,
           "tasks": [c for c, _, _ in ntasks], "notif_seen_at": log["notif_seen_at"], "completed_at": log["completed_at"],
           "report_task_status": nc.get("task_status"), "report_recovery": nc.get("recovery"),
           "recurring": rep["possible_causes"]["recurring"]}
    json.dump(out, open(os.path.join(HERE, "loop_demo_results.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    print(HR.render_text(rep))
    print("--- edge output ---\n" + edge.stdout)
    bus.stop()
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
