"""Smoke test of the whole on-device chain with emulated sensors (no hardware, about 90 s):

  emulated bus -> edge_live.py (poll 1 s, 5-s windows) -> middleware (mock SAP) ; then bench_analysis.py

A scripted heat event in zone 1 (T 34 C, RH 80% from second 20 to 45) must raise zone 1 to Severe
after two windows and lower it after three; every closed window must reach the mock SAP exactly once.
The alert must name the possible cause (low airflow: air speed 1.5 m/s), list the first tasks with
their sources, withhold the cooling pads (RH 80% > 75%) and every row in SAP must carry the tasks the
edge sent. The house report built from the mock SAP tables must show every window, without gaps.
Time is compressed (5-s instead of 5-min windows), so this checks the code path, not field behaviour.
  python3 tests/test_live_smoke.py
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = os.path.dirname(HERE)
KIT = os.path.dirname(EDGE)
sys.path.insert(0, EDGE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(KIT, "report"))
import house_report as HR  # noqa: E402
import devices as D  # noqa: E402
from emulator import Bus, EmulatedDevice  # noqa: E402


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = tempfile.mkdtemp(prefix="live_smoke_")
    plan = [("ODMHM-R", 1, 1), ("ODMHM-R", 2, 2), ("ODMHM-R", 3, 3), ("S-NH3-01", 11, 2), ("S-NH3-01", 12, 3), ("HD53LS.S", 21, 2)]
    emu = {u: EmulatedDevice(m, u) for m, u, _ in plan}
    bus = Bus(list(emu.values()))

    def setv(u, t, rh, co2):
        with bus.lock:
            emu[u].set_registers(D.OdmhmR.encode(t, rh, co2))
    for u in (1, 2, 3):
        setv(u, 28.0, 65.0, 1200)
    with bus.lock:
        for u in (11, 12):
            emu[u].set_registers(D.SNH301.encode(5.0), table="hold")
        emu[21].set_registers(D.HD53LSS.encode(1.5))

    port = free_port()
    mw = subprocess.Popen([sys.executable, os.path.join(KIT, "sil", "middleware.py"), "--port", str(port), "--db",
                           os.path.join(tmp, "sap.db"), "--p503", "0", "--plost", "0", "--pslow", "0",
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

    def scenario():
        time.sleep(20); setv(1, 34.0, 80.0, 1200)   # heat and humidity in zone 1
        time.sleep(25); setv(1, 28.0, 65.0, 1200)
    threading.Thread(target=scenario, daemon=True).start()
    edge = subprocess.run([sys.executable, os.path.join(EDGE, "edge_live.py"), "--config", cfgp, "--minutes", "1.25"],
                          capture_output=True, text=True, timeout=200)
    time.sleep(1)
    mw.terminate(); mw.wait()
    an = subprocess.run([sys.executable, os.path.join(KIT, "bench", "bench_analysis.py"), cfg["log_dir"], "--config", cfgp],
                        capture_output=True, text=True)
    res = json.load(open(os.path.join(cfg["log_dir"], "bench_results.json")))
    ob = sqlite3.connect(os.path.join(cfg["log_dir"], "outbox.db"))
    n_out = ob.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    sev_alerts = ob.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    sap = sqlite3.connect(os.path.join(tmp, "sap.db"))
    n_sap, n_ids = sap.execute("SELECT COUNT(*), COUNT(DISTINCT assess_id) FROM zbrl_stress").fetchone()
    sev_first = {r[0] for r in sap.execute("SELECT task1 FROM zbrl_stress WHERE level=2")}
    sent = {aid: json.loads(pl)["tasks"] for aid, pl in ob.execute("SELECT assess_id, payload FROM outbox")}
    task_diff = [aid for aid, t1, t2, t3 in sap.execute("SELECT assess_id, task1, task2, task3 FROM zbrl_stress")
                 if [t for t in (t1, t2, t3) if t] != sent.get(aid)]
    pers = res["persistence"]
    rep = HR.build_report(*HR.load_mock(os.path.join(tmp, "sap.db"), cfg["flock"]["id"], cfg["flock"]["house"]),
                          cfg["flock"]["id"], cfg["flock"]["house"], interval_s=cfg["window_s"])
    checks = {
        "edge printed a Severe alert for zone 1": "SEVERE in zone 1" in edge.stdout,
        "one local alert (one episode)": sev_alerts == 1,
        "persistence: level follows one window after the raw rise": pers["added_delay_windows_median"] == 1,
        "persistence filters nothing here but changes no more often than raw": pers["persisted_level_changes"] <= pers["raw_level_changes"],
        "at least 12 windows closed": pers["windows"] >= 12,
        "every closed window in the outbox reached mock SAP once": n_sap == n_ids and n_sap >= n_out - 1,
        "outbox drained": res["outbox"]["unsent_at_end"] <= 1,
        "NH3 flagged as warming up (5 min)": "warmup" in res["completeness"]["S-NH3-01#11:NH3"]["flags"],
        "temperature always valid": res["completeness"]["ODMHM-R#1:T"]["valid_share"] == 1.0,
        "alert lists the first task with its source": "1. FANS Raise fan stage to increase air speed [MED-E; E]" in edge.stdout,
        "cooling pads withheld at RH 80% (Medion guard)": "pads withheld: RH 80% > 75%" in edge.stdout,
        "every row in SAP carries the tasks the edge sent; Severe rows start with FANS": not task_diff and sev_first == {"FANS"},
        "Moderate from Normal prints the preventive tasks (notice, not an alert)":
            re.search(r"MODERATE in zone 1: thermal - possible cause [A-Z]{4}: [^\n]+ - preventive tasks:\n"
                      r"   1\. FANS Raise fan stage", edge.stdout) is not None,
        "alert names the possible cause (air speed 1.5 m/s: low airflow) and the corrective tasks":
            "possible cause AIRF: Low airflow (fans, belts or inlet) - corrective tasks:" in edge.stdout,
        "house report from the SAP tables: every window, no gap, Severe windows with possible cause AIRF":
            not rep.get("empty") and rep["data"]["gaps"] == [] and rep["data"]["received"] == n_sap
            and rep["conditions"]["windows_per_level"]["Severe"] >= 1
            and "AIRF" in rep["possible_causes"]["moderate_or_severe_windows"],
    }
    for k, ok in checks.items():
        print("OK  " if ok else "FAIL", k)
    print(json.dumps({"windows": pers["windows"], "outbox": n_out, "sap_rows": n_sap, "persistence": pers,
                      "device": res["device"], "report_data": rep.get("data")}, indent=1))
    print(HR.render_text(rep))
    print("--- edge output ---\n" + edge.stdout)
    bus.stop()
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
