"""Software-in-the-loop (SIL) test harness.

Runs the edge node and the middleware (+ mock SAP) as separate processes, replays the 141 survey
windows of the open dataset, and injects faults:
  * per request (middleware): 503 without processing, lost acknowledgement after commit,
    answer after the client's timeout;
  * process level (harness): SIGKILL of the edge node (power loss) and of the middleware (outage),
    each followed by a restart.
Afterwards it compares the mock SAP tables with an independent oracle computed from the replay
output (levels P per record): every window must be stored exactly once and the escalation rule
must open exactly the expected notifications. Mode "naive" switches the duplicate check off.
Tasks (v16): every stored row must carry the tasks expected for its window, and every notification
the tasks of the window that triggered it. The expected tasks apply the task catalog (tasks.py) to
the replay's levels, so this checks that tasks are delivered and recorded once and unchanged; the
mapping itself is checked by edge/tests/test_tasks.py.
Possible causes and reports (v17): every stored row must carry the expected possible cause, and the
house reports built from the stored tables (report/house_report.py, the logic of the ABAP report)
must count every window of each house once and give each notification the expected possible cause.
The reports of each run are written to <run>/house_reports.txt.

Backends
  mock       middleware calls sap_mock.py in-process (the v14 test; modes idem and naive)
  soap-mock  middleware calls soap_rfc_mock.py over HTTP/SOAP (tests sap_soap.py; mode idem)
  sap        middleware calls Z_BRL_STRESS_SAVE in a real SAP sandbox; tables are read back with
             Z_BRL_STRESS_READ and earlier test rows removed with Z_BRL_TEST_RESET (mode idem).
             Needs --sap-url, --sap-user and the environment variable SAP_PASSWORD.

Usage: python3 sil_run.py --runs 5 --out results.json
       python3 sil_run.py --backend sap --runs 3 --sap-url "https://host:44300/sap/bc/soap/rfc?sap-client=100" \
              --sap-user ZBRL_RFC --out sil_results_sap.json
"""
import argparse
import csv
import json
import os
import random
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import tasks as TK
from sap_soap import SoapBackend

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "report"))
import house_report as HR  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDS = os.path.join(HERE, "..", "data", "replay_records.csv")
PY = sys.executable


# ---------------- independent oracle (does not import the edge code) ----------------
def oracle(records_path):
    base = {"winter": datetime(2000, 1, 3), "summer": datetime(2000, 7, 3)}
    hours = {1: 8, 2: 12, 3: 16}
    win = defaultdict(list)
    with open(records_path, newline="") as f:
        for r in csv.DictReader(f):
            win[(r["flock"], int(r["House"]), int(r["Week"]), int(r["Time"]))].append(
                (int(r["Sector"]), int(r["P"]), r))
    rows, tasks, pcauses = [], {}, {}
    for (flock, house, week, tw), pts in win.items():
        top = max(p for _, p, _ in pts)
        zone = min(s for s, p, _ in pts if p == top)
        ts = base[flock] + timedelta(days=7 * (week - 1), hours=hours[tw])
        rows.append((flock, house, ts, zone, top))
        r = next(rec for s, _, rec in pts if s == zone)
        sub = {"thermal": int(r["thP"]), "NH3": int(r["nhP"]), "CO2": int(r["coP"])}
        cause = "+".join(k for k in ("thermal", "NH3", "CO2") if sub[k] == top) if top else "none"
        t_star = float(r["Tstar"]) if week <= 3 else None
        inp = {"T": float(r["T"]), "RH": float(r["RH"])}
        tasks[(flock, house, ts.isoformat())] = tuple(TK.assessment_tasks(
            top, cause, sub, inp, week, t_star, r["diag18"] == "True")[0])
        pcauses[(flock, house, ts.isoformat())] = TK.possible_cause(top, cause, inp, week, t_star, r["diag18"] == "True")
    rows.sort(key=lambda x: (x[2], x[1]))
    notif = 0
    triggers = set()
    last = {}
    severe = defaultdict(list)
    for flock, house, ts, zone, top in rows:
        if top != 2:
            continue
        k = (flock, house, zone)
        severe[k].append(ts)
        lower = ts - timedelta(hours=24)
        if k in last and last[k] > lower:
            lower = last[k]
        if sum(1 for t in severe[k] if lower < t <= ts) >= 3:
            notif += 1
            last[k] = ts
            triggers.add((flock, house, ts.isoformat()))
    windows = {(f, h, ts.isoformat()) for f, h, ts, _, _ in rows}
    levels = {(f, h, ts.isoformat()): (z, top) for f, h, ts, z, top in rows}
    return {"windows": windows, "levels": levels, "notifications": notif,
            "severe_windows": sum(1 for r in rows if r[4] == 2), "tasks": tasks, "triggers": triggers,
            "notification_tasks": sum(len(tasks[t]) for t in triggers),
            "windows_with_tasks": sum(1 for t in tasks.values() if t), "pcauses": pcauses,
            "notification_pcauses": Counter(pcauses[t] for t in triggers),
            "windows_per_house": Counter((f, h) for f, h, _ in windows)}


# ---------------- process helpers ----------------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def start_mw(d, port, mode, seed, cfg):
    cmd = [PY, os.path.join(HERE, "middleware.py"), "--port", str(port), "--db", os.path.join(d, "sap.db"),
           "--mode", mode, "--seed", str(seed), "--events", os.path.join(d, "mw_events.jsonl")]
    if cfg["backend"] != "mock":
        cmd += ["--backend", "soap", "--sap-url", cfg["sap_url"], "--sap-user", cfg["sap_user"]]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, "mw_stderr.log"), "a"),
                         env={**os.environ, "SAP_PASSWORD": cfg.get("sap_password", "")})
    wait_port(port)
    return p


def start_edge(d, port, mode, seed, prefix=""):
    return subprocess.Popen([PY, os.path.join(HERE, "edge.py"), "--records", RECORDS, "--db", os.path.join(d, "outbox.db"),
                             "--url", f"http://127.0.0.1:{port}/assessments", "--mode", mode, "--seed", str(seed),
                             "--events", os.path.join(d, "edge_events.jsonl"), "--flock-prefix", prefix],
                            stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, "edge_stderr.log"), "a"))


def run_once(mode, seed, root, cfg, max_edge_kills=6, max_mw_kills=5):
    d = os.path.join(root, f"{cfg['backend']}_{mode}_seed{seed}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    rng = random.Random(1000 + seed)
    port = free_port()
    prefix = cfg["prefix"] + f"{seed}-" if cfg["backend"] != "mock" else ""
    sap_proc = None
    if cfg["backend"] == "soap-mock":
        sport = free_port()
        sap_proc = subprocess.Popen([PY, os.path.join(HERE, "soap_rfc_mock.py"), "--port", str(sport), "--db",
                                     os.path.join(d, "sap.db"), "--user", "TESTUSER", "--password", "secret"],
                                    stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, "soap_stderr.log"), "a"))
        wait_port(sport)
        cfg = {**cfg, "sap_url": f"http://127.0.0.1:{sport}/sap/bc/soap/rfc?sap-client=100",
               "sap_user": "TESTUSER", "sap_password": "secret"}
    if cfg["backend"] != "mock":
        SoapBackend(cfg["sap_url"], cfg["sap_user"], cfg["sap_password"]).reset(prefix)
    mw = start_mw(d, port, mode, seed, cfg)
    edge = start_edge(d, port, mode, seed, prefix)
    edge_kills = mw_kills = 0
    outage_s = 0.0
    t0 = time.time()
    while True:
        time.sleep(rng.uniform(0.4, 1.2))
        if edge.poll() is not None:
            if edge.returncode == 0:
                break
            edge = start_edge(d, port, mode, seed + 100 * (edge_kills + 1), prefix)  # crashed by itself: restart
            continue
        a = rng.random()
        if a < 0.35 and edge_kills < max_edge_kills:
            edge.send_signal(signal.SIGKILL); edge.wait()
            edge_kills += 1
            time.sleep(0.1)
            edge = start_edge(d, port, mode, seed + 100 * edge_kills, prefix)
        elif a < 0.70 and mw_kills < max_mw_kills:
            mw.send_signal(signal.SIGKILL); mw.wait()
            mw_kills += 1
            down = rng.uniform(0.5, 3.0)
            outage_s += down
            time.sleep(down)
            mw = start_mw(d, port, mode, seed + 100 * mw_kills, cfg)
        if time.time() - t0 > 600:
            raise RuntimeError("run did not finish")
    elapsed = time.time() - t0
    mw.send_signal(signal.SIGTERM); mw.wait()
    rows = notifs = report_inputs = None
    if cfg["backend"] != "mock":  # read the tables back through the same SOAP interface
        st, nt, tk = SoapBackend(cfg["sap_url"], cfg["sap_user"], cfg["sap_password"]).read_back(prefix)
        key = lambda f, h, ts: (f[len(prefix):], int(h), datetime.strptime(ts, "%Y%m%d%H%M%S").isoformat())
        rows = [(r["ASSESS_ID"], *key(r["FLOCK"], r["HOUSE"], r["WINDOW_TS"]), int(r["ZONE"]), int(r["LEVEL_CODE"]),
                 tuple(r.get(k, "") for k in ("TASK1", "TASK2", "TASK3") if r.get(k)), r.get("POSS_CAUSE") or None)
                for r in st]
        by_id = {r[0]: r for r in rows}
        pm_tasks = defaultdict(list)
        for t in sorted(tk, key=lambda t: (t.get("QMNUM", ""), t.get("MANUM", ""))):
            pm_tasks[t.get("QMNUM", "")].append(t.get("MNCOD", ""))
        notifs = []
        for n in nt:  # PM mode: the notification's own tasks; LOG mode: the tasks of the triggering row
            trig = by_id.get(n["ASSESS_ID"])
            wkey = trig[1:4] if trig else key(n["FLOCK"], n["HOUSE"], n["NOTIF_TS"])
            ntasks = tuple(pm_tasks[n["QMNUM"]]) if n.get("NMODE") == "PM" else (trig[6] if trig else ())
            notifs.append((wkey, ntasks, n.get("NMODE", "")))
        # inputs of the house reports, as the ABAP report reads them (ZBRL_STRESS, ZBRL_NOTIF, QMSM)
        report_inputs = defaultdict(lambda: ([], [], []))
        for r in st:
            f, h, ts = key(r["FLOCK"], r["HOUSE"], r["WINDOW_TS"])
            report_inputs[(f, h)][0].append({"assess_id": r["ASSESS_ID"], "ts": ts, "zone": int(r["ZONE"]),
                                             "level": int(r["LEVEL_CODE"]), "cause": r.get("CAUSE", ""),
                                             "episode": 1 if r.get("EPISODE") == "X" else 0,
                                             "possible_cause": r.get("POSS_CAUSE") or None,
                                             "rule_version": r.get("RULE_VER", ""),
                                             "inputs": {k: float(r[k]) for k in ("THI", "NH3", "CO2")
                                                        if r.get(k) not in (None, "") and float(r[k]) > 0},
                                             "air_speed_diag": r.get("AIRDIAG") == "X"})
        for n in nt:
            f, h, ts = key(n["FLOCK"], n["HOUSE"], n["NOTIF_TS"])
            report_inputs[(f, h)][1].append({"notif_id": n["QMNUM"] or n["ASSESS_ID"], "ts": ts, "zone": int(n["ZONE"]),
                                             "trigger_id": n["ASSESS_ID"]})
            for t in tk:
                if t.get("QMNUM") == n["QMNUM"] and n["QMNUM"]:
                    done = (t.get("ERLDAT") or "").strip("0 ")
                    report_inputs[(f, h)][2].append({"notif_id": n["QMNUM"], "task_key": int(t["MANUM"]), "code": t["MNCOD"],
                                                     "completed_at": (datetime.strptime(t["ERLDAT"] + (t.get("ERLZEIT") or "000000"),
                                                                                        "%Y%m%d%H%M%S").isoformat() if done else None),
                                                     "completed_by": t.get("ERLNAM") or None})
        report_inputs = dict(report_inputs)
    if sap_proc:
        sap_proc.send_signal(signal.SIGTERM); sap_proc.wait()
    return d, {"edge_kills": edge_kills, "mw_kills": mw_kills, "outage_s": round(outage_s, 1),
               "elapsed_s": round(elapsed, 1), "prefix": prefix}, rows, notifs, report_inputs


def evaluate(d, mode, ora, rows=None, notifs=None, report_inputs=None):
    """rows: (assess_id, flock, house, ts, zone, level, tasks, possible cause); notifs: ((flock, house, ts), tasks, mode)."""
    if rows is None:
        con = sqlite3.connect(os.path.join(d, "sap.db"))
        rows = [(*r[:6], tuple(t for t in r[6:9] if t), r[9] or None) for r in con.execute(
            "SELECT assess_id, flock, house, ts, zone, level, task1, task2, task3, poss_cause FROM zbrl_stress")]
        notifs = [((f, h, ts), tuple(t for t in (t1, t2, t3) if t), "mock") for f, h, ts, t1, t2, t3 in con.execute(
            "SELECT flock, house, ts, task1, task2, task3 FROM notif")]
    stored_windows = defaultdict(int)
    level_mismatch = task_mismatch = 0
    pcause_mismatch = 0
    for aid, flock, house, ts, zone, level, tasks, pcause in rows:
        stored_windows[(flock, house, ts)] += 1
        exp = ora["levels"].get((flock, house, ts))
        if exp is None or exp != (zone, level):
            level_mismatch += 1
        if tuple(tasks) != ora["tasks"].get((flock, house, ts)):
            task_mismatch += 1
        if pcause != ora["pcauses"].get((flock, house, ts)):
            pcause_mismatch += 1
    trig = [w for w, _, _ in notifs]
    notif_trigger_mismatch = len(set(trig) ^ ora["triggers"]) + (len(trig) - len(set(trig)))
    notif_task_mismatch = sum(1 for w, t, _ in notifs if tuple(t) != ora["tasks"].get(w))
    notif_tasks = sum(len(t) for _, t, _ in notifs)
    # house reports (the ABAP report's logic) built from what SAP stored
    if report_inputs is None:
        db = os.path.join(d, "sap.db")
        pairs = sqlite3.connect(db).execute("SELECT DISTINCT flock, house FROM zbrl_stress").fetchall()
        reports = [HR.build_report(*HR.load_mock(db, f, h), f, h) for f, h in pairs]
    else:
        reports = [HR.build_report(*report_inputs[k], k[0], k[1]) for k in sorted(report_inputs)]
    with open(os.path.join(d, "house_reports.txt"), "w") as fh:
        fh.write("\n\n".join(HR.render_text(r) for r in reports))
    rep_notifs = sum(r["notification_check"]["notifications"] for r in reports if not r.get("empty"))
    rep_open = sum(v for r in reports if not r.get("empty") for k, v in r["notification_check"]["task_status"].items()
                   if k in ("outstanding", "overdue"))
    rep_pc = Counter()
    for r in reports:
        if not r.get("empty"):
            rep_pc.update(r["possible_causes"]["notifications"])
    rep_windows = Counter({(r["flock"], r["house"]): r["data"]["received"] for r in reports if not r.get("empty")})
    rep_recurring = sorted({c["code"] for r in reports if not r.get("empty") for c in r["possible_causes"]["recurring"]})
    missing = len(ora["windows"] - set(stored_windows))
    dup_rows = sum(c - 1 for c in stored_windows.values() if c > 1)
    ev = defaultdict(int)
    for line in open(os.path.join(d, "mw_events.jsonl")):
        ev[json.loads(line)["kind"]] += 1
    eev = defaultdict(int)
    max_backlog = 0
    for line in open(os.path.join(d, "edge_events.jsonl")):
        e = json.loads(line)
        eev[e["kind"]] += 1
        if e["kind"] == "produced":
            max_backlog = max(max_backlog, e["backlog"])
    ocon = sqlite3.connect(os.path.join(d, "outbox.db"))
    ev.setdefault("sap_unavailable", 0)
    alerts = ocon.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    return {
        "windows_expected": len(ora["windows"]), "rows_stored": len(rows), "windows_stored": len(stored_windows),
        "missing_windows": missing, "duplicate_rows": dup_rows, "level_mismatch": level_mismatch,
        "task_mismatch": task_mismatch, "rows_with_tasks": sum(1 for r in rows if r[6]),
        "pcause_mismatch": pcause_mismatch,
        "report_count": len(reports), "report_notifications": rep_notifs, "report_open_tasks": rep_open,
        "report_pcause_mismatch": sum((rep_pc - ora["notification_pcauses"]).values()) + sum((ora["notification_pcauses"] - rep_pc).values()),
        "report_window_mismatch": sum(1 for k in ora["windows_per_house"] if rep_windows.get(k) != ora["windows_per_house"][k]),
        "report_recurring": rep_recurring,
        "notifications_expected": ora["notifications"], "notifications_created": len(notifs),
        "notification_trigger_mismatch": notif_trigger_mismatch, "notification_task_mismatch": notif_task_mismatch,
        "notification_tasks": notif_tasks, "notification_tasks_expected": ora["notification_tasks"],
        "notification_mode": sorted({m for _, _, m in notifs}),
        "local_alerts": alerts, "severe_windows_expected": ora["severe_windows"],
        "injected_503": ev["injected_503"], "injected_lost_ack": ev["injected_lost_ack"], "injected_slow": ev["injected_slow"],
        "sap_duplicate_rejected": ev["sap_duplicate"], "sap_unavailable": ev["sap_unavailable"],
        "send_attempts": eev["ack"] + eev["send_fail"],
        "send_failures": eev["send_fail"], "edge_starts": eev["start"], "max_backlog": max_backlog,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(HERE, "sil_results.json"))
    ap.add_argument("--root", default=os.path.join(HERE, "runs"))
    ap.add_argument("--backend", choices=("mock", "soap-mock", "sap"), default="mock")
    ap.add_argument("--sap-url", default="")
    ap.add_argument("--sap-user", default="")
    ap.add_argument("--prefix", default="TST", help="test flocks are named <prefix><seed>-winter etc.")
    args = ap.parse_args()
    cfg = {"backend": args.backend, "sap_url": args.sap_url, "sap_user": args.sap_user,
           "sap_password": os.environ.get("SAP_PASSWORD", ""), "prefix": args.prefix}
    ora = oracle(RECORDS)
    results = {"backend": args.backend, "rule_version": TK.RULE_VERSION,
               "oracle": {"windows": len(ora["windows"]), "notifications": ora["notifications"],
                          "severe_windows": ora["severe_windows"], "windows_with_tasks": ora["windows_with_tasks"],
                          "notification_tasks": ora["notification_tasks"],
                          "notification_pcauses": dict(ora["notification_pcauses"])}, "runs": []}
    modes = ("idem", "naive") if args.backend == "mock" else ("idem",)
    for mode in modes:
        for seed in range(1, args.runs + 1):
            d, chaos, rows, notifs, report_inputs = run_once(mode, seed, args.root, cfg)
            res = evaluate(d, mode, ora, rows, notifs, report_inputs)
            res.update(chaos)
            res.update({"mode": mode, "seed": seed, "backend": args.backend})
            results["runs"].append(res)
            print(json.dumps(res), flush=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
