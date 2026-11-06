"""Edge node of the prototype (designed to run on a Raspberry Pi; runs on any Python 3 host).

For each measurement window it rates every zone with the revised rules, forms one StressAssessment
for the house (worst zone, level, cause and up to three first tasks from the task catalog), raises a
local alert when the level is Severe, and writes
the assessment to a local outbox (SQLite) in the same transaction as its production marker. A sender
then delivers the outbox in order to the middleware and marks a row as sent only after an explicit
acknowledgement, retrying with capped exponential back-off. In mode "idem" the assessment identifier
is derived from the house and window start (UUIDv5), so a recomputed assessment keeps its key.

In the software-in-the-loop test the windows are replayed from the open dataset: one survey
(house, week, daily window) is one window and its twelve measuring points are the zones.
"""
import argparse
import csv
import json
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta

import rules
import tasks as TK

NS = uuid.UUID("6f1c3c86-3f5a-4d36-9a5e-2f1c7f0b9d11")  # fixed namespace for assessment keys
BASE = {"winter": datetime(2000, 1, 3), "summer": datetime(2000, 7, 3)}  # artificial time base
WINDOW_HOUR = {1: 8, 2: 12, 3: 16}  # midpoints of the 07-09, 11-13 and 15-17 h windows


def load_windows(path):
    """Group records into windows (flock, house, week, time) in time order."""
    groups = OrderedDict()
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            key = (r["flock"], int(r["House"]), int(r["Week"]), int(r["Time"]))
            groups.setdefault(key, []).append(r)
    def ts_of(k):
        flock, house, week, tw = k
        return BASE[flock] + timedelta(days=7 * (week - 1), hours=WINDOW_HOUR[tw])
    keys = sorted(groups, key=lambda k: (ts_of(k), k[1]))
    return [(k, ts_of(k), groups[k]) for k in keys]


def make_assessment(key, ts, records, mode, prefix=""):
    flock, house, week, tw = key
    flock = prefix + flock
    zones = []
    for r in records:
        inp = {"T": float(r["T"]), "RH": float(r["RH"]), "V": float(r["V"]),
               "CO2": float(r["CO2"]), "NH3": float(r["NH3"])}
        rating = rules.rate_zone(inp["T"], inp["RH"], inp["V"], inp["CO2"], inp["NH3"], week, float(r["W"]))
        zones.append((int(r["Sector"]), inp, rating))
    h = rules.house_assessment(zones)
    week_w = float(records[0]["W"])  # flock's sample weight of the week (same for all points)
    inp = h["inputs"]
    t_star = rules.M.ross_target(week_w, inp["RH"]) if week <= 3 else None
    tasks, notes, kind = TK.assessment_tasks(h["level"], h["cause"], h["sub_levels"], inp, week, t_star,
                                             h["air_speed_diag"])
    pcause = TK.possible_cause(h["level"], h["cause"], inp, week, t_star, h["air_speed_diag"])
    ts_iso = ts.isoformat()
    if mode == "idem":
        aid = str(uuid.uuid5(NS, f"{flock}/H{house}/{ts_iso}"))
    else:
        aid = str(uuid.uuid4())
    return {"assessment_id": aid, "flock": flock, "house": house, "week": week, "window": tw,
            "ts": ts_iso, "n_zones": len(zones), **h, "tasks": tasks, "task_notes": notes,
            "thermal_kind": kind, "rule_version": TK.RULE_VERSION, "possible_cause": pcause,
            "task_mode": {1: "preventive", 2: "corrective"}.get(h["level"])}


def open_outbox(path):
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=FULL;")
    con.execute("""CREATE TABLE IF NOT EXISTS outbox (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, window_key TEXT UNIQUE, assess_id TEXT,
        payload TEXT, level INTEGER, sent INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0)""")
    con.execute("CREATE TABLE IF NOT EXISTS alerts (window_key TEXT PRIMARY KEY, raised REAL)")
    return con


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--mode", choices=("idem", "naive"), default="idem")
    ap.add_argument("--interval", type=float, default=0.08)
    ap.add_argument("--timeout", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--events", required=True)
    ap.add_argument("--flock-prefix", default="", help="e.g. TST1- for runs against an SAP sandbox")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    ev = open(args.events, "a", buffering=1)
    def log(kind, **kw):
        ev.write(json.dumps({"t": time.time(), "kind": kind, **kw}) + "\n")

    windows = load_windows(args.records)
    con = open_outbox(args.db)
    produced = {row[0] for row in con.execute("SELECT window_key FROM outbox")}
    todo = [w for w in windows if "|".join(map(str, w[0])) not in produced]
    log("start", pending_windows=len(todo))

    backoff = 0.0
    next_produce = next_send = time.time()
    while True:
        now = time.time()
        if todo and now >= next_produce:
            key, ts, recs = todo.pop(0)
            a = make_assessment(key, ts, recs, args.mode, args.flock_prefix)
            wk = "|".join(map(str, key))
            con.execute("BEGIN IMMEDIATE;")
            con.execute("INSERT OR IGNORE INTO outbox(window_key, assess_id, payload, level) VALUES (?,?,?,?)",
                        (wk, a["assessment_id"], json.dumps(a), a["level"]))
            if a["level"] == 2:  # local alert does not depend on the network
                con.execute("INSERT OR IGNORE INTO alerts(window_key, raised) VALUES (?,?)", (wk, now))
            con.execute("COMMIT;")
            backlog = con.execute("SELECT COUNT(*) FROM outbox WHERE sent=0").fetchone()[0]
            log("produced", backlog=backlog)
            next_produce = now + args.interval
        if now >= next_send:
            row = con.execute("SELECT seq, payload FROM outbox WHERE sent=0 ORDER BY seq LIMIT 1").fetchone()
            if row is None and not todo:
                log("done")
                return 0
            if row is not None:
                seq, payload = row
                con.execute("UPDATE outbox SET attempts=attempts+1 WHERE seq=?", (seq,))
                req = urllib.request.Request(args.url, data=payload.encode(), method="POST",
                                             headers={"Content-Type": "application/json"})
                ok, kind = False, None
                try:
                    with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                        res = json.loads(resp.read())
                        ok = resp.status == 200 and res.get("status") in ("stored", "duplicate")
                        kind = res.get("status")
                except urllib.error.HTTPError as e:
                    kind = f"http_{e.code}"
                except Exception as e:  # connection refused/reset, timeout, incomplete read
                    kind = type(e).__name__
                if ok:
                    con.execute("UPDATE outbox SET sent=1 WHERE seq=?", (seq,))
                    log("ack", status=kind)
                    backoff = 0.0
                    next_send = now
                else:
                    log("send_fail", error=kind)
                    backoff = min(max(0.05, backoff * 2), 0.5)
                    next_send = now + backoff * (0.5 + rng.random())
        time.sleep(0.003)


if __name__ == "__main__":
    sys.exit(main())
