"""Edge program for the Raspberry Pi: poll the bus every 60 s, rate every 5-min window, keep an outbox
and (optionally) send assessments to the middleware. Used for the bench test and later in the house.

  python3 edge_live.py --config config.json                 # runs until stopped (Ctrl-C / systemd)
  python3 edge_live.py --config config.json --minutes 10    # short trial

Files written to the log directory (one set per start):
  readings_<start>.csv     every reading with its validity flags          (bench analysis, step i)
  assessments_<start>.csv  every window: zone levels, raw and persisted   (persistence analysis)
  resources_<start>.csv    poll duration, lateness, CPU time and memory   (objective O6)
  outbox.db                assessments waiting for / acknowledged by SAP  (objective O4)
"""
import argparse
import csv
import json
import os
import resource
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import date, datetime

import devices as D
import pipeline as P
import tasks as TK
from acquire import Acquisition
from modbus_rtu import Master, SerialLine


def flock_state(cfg, today):
    """Week of age from the placement date and the latest sample weight (g) from the weights file."""
    placed = date.fromisoformat(cfg["flock"]["placement_date"])
    week = (today - placed).days // 7 + 1
    weight = cfg["flock"].get("initial_weight_g", 44)
    path = cfg["flock"].get("weights_csv")
    if path and os.path.exists(path):
        for row in csv.DictReader(open(path)):  # columns: date, weight_g
            if date.fromisoformat(row["date"]) <= today:
                weight = float(row["weight_g"])
    return week, weight


def open_outbox(path):
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=FULL;")
    con.execute("""CREATE TABLE IF NOT EXISTS outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT,
        window_key TEXT UNIQUE, assess_id TEXT, payload TEXT, level INTEGER, sent INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0, sent_at TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS alerts (window_key TEXT PRIMARY KEY, raised TEXT, cause TEXT)")
    return con


def send_one(con, url, timeout):
    row = con.execute("SELECT seq, payload FROM outbox WHERE sent=0 ORDER BY seq LIMIT 1").fetchone()
    if row is None:
        return None
    seq, payload = row
    con.execute("UPDATE outbox SET attempts=attempts+1 WHERE seq=?", (seq,))
    req = urllib.request.Request(url, data=payload.encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read())
            if resp.status == 200 and res.get("status") in ("stored", "duplicate"):
                con.execute("UPDATE outbox SET sent=1, sent_at=? WHERE seq=?", (datetime.now().isoformat(), seq))
                return True
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--minutes", type=float, default=0)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    os.makedirs(cfg["log_dir"], exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bus = cfg["bus"]
    master = Master(SerialLine(bus["port"], bus["baud"], bus["parity"], bus["stopbits"], bus["timeout_s"]))
    devs = D.from_config(cfg["devices"])
    acq = Acquisition(master, devs, maintenance_file=cfg.get("maintenance_file"))
    zones = sorted({d["zone"] for d in cfg["devices"] if d["model"] == "ODMHM-R"})
    agg, pers = P.WindowAggregator(), P.Persistence()
    con = open_outbox(os.path.join(cfg["log_dir"], "outbox.db"))
    f_read = open(os.path.join(cfg["log_dir"], f"readings_{stamp}.csv"), "w", newline="")
    f_ass = open(os.path.join(cfg["log_dir"], f"assessments_{stamp}.csv"), "w", newline="")
    f_res = open(os.path.join(cfg["log_dir"], f"resources_{stamp}.csv"), "w", newline="")
    w_read = csv.writer(f_read)
    w_read.writerow(["time", "unit", "model", "zone", "quantity", "value", "valid", "flags"])
    w_ass = csv.writer(f_ass)
    w_ass.writerow(["window_start", "week", "weight_g", "zone", "T", "RH", "CO2", "NH3", "V", "raw_level",
                    "level", "house_level", "worst_zone", "cause", "episode_start", "assessment_id", "tasks",
                    "possible_cause"])
    w_res = csv.writer(f_res)
    w_res.writerow(["time", "poll_s", "late_s", "cpu_s", "maxrss_kb", "unsent", "master_stats"])
    poll_s, win_s = cfg.get("poll_s", 60), cfg.get("window_s", 300)
    flock, house = cfg["flock"]["id"], cfg["flock"]["house"]
    url = cfg.get("middleware_url")
    t_end = time.time() + 60 * a.minutes if a.minutes else None
    current = P.window_start(datetime.now(), win_s)
    next_poll = time.time()
    prev_level = 0
    try:
        while t_end is None or time.time() < t_end:
            late = time.time() - next_poll
            t0 = time.monotonic()
            readings = acq.poll()
            poll_dur = time.monotonic() - t0
            now = datetime.now()
            for r in readings:
                w_read.writerow([now.isoformat(timespec="seconds"), r["unit"], r["model"], r["zone"], r["quantity"],
                                 r["value"], int(r["valid"]), "|".join(r["flags"])])
            f_read.flush()
            ws = P.window_start(now, win_s)
            if ws != current:  # close the previous window before adding readings of the new one
                week, weight = flock_state(cfg, current.date())
                zin = agg.close(zones)
                ass = P.house_assessment(flock, house, current, week, weight, zin, pers)
                if ass:
                    for z, lvl in ass["zone_levels"].items():
                        i = zin[z]
                        w_ass.writerow([current.isoformat(), week, weight, z, i["T"], i["RH"], i["CO2"], i["NH3"],
                                        i["V"], ass["zone_raw"][z], lvl, ass["level"], ass["worst_zone"], ass["cause"],
                                        ass["episode_start"], ass["assessment_id"], "|".join(ass["tasks"]),
                                        ass.get("possible_cause") or ""])
                    f_ass.flush()
                    key = f"{flock}|{house}|{ass['ts']}"
                    con.execute("BEGIN IMMEDIATE;")
                    con.execute("INSERT OR IGNORE INTO outbox(window_key, assess_id, payload, level) VALUES (?,?,?,?)",
                                (key, ass["assessment_id"], json.dumps(ass), ass["level"]))
                    severe = ass["level"] == 2 and ass["episode_start"]
                    if severe:
                        con.execute("INSERT OR IGNORE INTO alerts VALUES (?,?,?)", (key, now.isoformat(), ass["cause"]))
                    if severe or (ass["level"] == 1 and prev_level == 0):
                        # Severe: corrective tasks (alert); Moderate from Normal: preventive tasks (notice)
                        pc = ass.get("possible_cause")
                        print(f"[{now:%H:%M}] {'SEVERE' if severe else 'MODERATE'} in zone {ass['worst_zone']}: "
                              f"{ass['cause']}" + (f" - possible cause {pc}: {TK.POSSIBLE_CAUSES[pc][0]}" if pc else "")
                              + f" - {ass['task_mode']} tasks:", flush=True)
                        for i, code in enumerate(ass["tasks"], 1):  # the first tasks, with their sources
                            print(f"   {i}. {TK.describe(code)}", flush=True)
                        for note in ass["task_notes"]:
                            print(f"   note: {note}", flush=True)
                        if ass.get("nh3_verify"):
                            print("   check: NH3 is within the sensor's typical error (5 ppm) of a band edge; "
                                  "verify with indicator paper or a detector tube", flush=True)
                    prev_level = ass["level"]
                    con.execute("COMMIT;")
                current = ws
            agg.add(readings)
            if url:
                for _ in range(20):  # catch up after an outage, a few assessments per poll
                    if not send_one(con, url, cfg.get("send_timeout_s", 2.0)):
                        break
            ru = resource.getrusage(resource.RUSAGE_SELF)
            unsent = con.execute("SELECT COUNT(*) FROM outbox WHERE sent=0").fetchone()[0]
            w_res.writerow([now.isoformat(timespec="seconds"), round(poll_dur, 3), round(late, 3),
                            round(ru.ru_utime + ru.ru_stime, 2), ru.ru_maxrss, unsent, json.dumps(master.stats)])
            f_res.flush()
            next_poll += poll_s
            time.sleep(max(0.0, next_poll - time.time()))
    except KeyboardInterrupt:
        pass
    finally:
        for f in (f_read, f_ass, f_res):
            f.close()


if __name__ == "__main__":
    main()
