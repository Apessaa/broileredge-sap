"""Analysis of a bench (or house) run of edge_live.py.

  python3 bench_analysis.py <log_dir> --config ../edge/config.json [--reference reference.csv] [--events events.csv]
      -> <log_dir>/bench_results.json and <log_dir>/bench_results.md

Inputs written by edge_live.py: readings_*.csv, assessments_*.csv, resources_*.csv and outbox.db.
Optional: reference.csv  (time, T, RH[, CO2, NH3]) from a calibrated reference instrument;
          events.csv     (start, end, kind, unit) - the disturbance log of the bench protocol.

Reports
  O1  completeness and errors per sensor; co-location agreement; bias against the reference
  O2  windows rated; level changes per day with and without the persistence rule, and the delay it adds
  O4  outbox: largest backlog and unsent rows at the end
  O6  poll duration (vs 0.33 s computed frame time), lateness of the 60 s cycle, CPU time, memory
Every number comes from the logs; nothing is estimated or filled in.
"""
import argparse
import csv
import glob
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edge"))
import pipeline as P  # noqa: E402


def read_all(pattern):
    rows = []
    for f in sorted(glob.glob(pattern)):
        rows += list(csv.DictReader(open(f)))
    return rows


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))] if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--config", required=True)
    ap.add_argument("--reference")
    ap.add_argument("--events")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    win_s = cfg.get("window_s", 300)
    R = read_all(os.path.join(a.log_dir, "readings_*.csv"))
    res_rows = read_all(os.path.join(a.log_dir, "resources_*.csv"))
    out = {"readings": len(R)}
    if not R:
        sys.exit("no readings found")
    t0, t1 = R[0]["time"], R[-1]["time"]
    span_h = (datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds() / 3600
    out["period"] = {"start": t0, "end": t1, "hours": round(span_h, 2)}

    # ---- O1: completeness, errors, agreement
    per = defaultdict(lambda: {"n": 0, "valid": 0, "flags": Counter()})
    for r in R:
        k = f"{r['model']}#{r['unit']}:{r['quantity']}"
        per[k]["n"] += 1
        per[k]["valid"] += r["valid"] == "1"
        for f in filter(None, r["flags"].split("|")):
            per[k]["flags"][f] += 1
    out["completeness"] = {k: {"valid_share": round(v["valid"] / v["n"], 4), "n": v["n"], "flags": dict(v["flags"])}
                           for k, v in sorted(per.items())}
    by_time = defaultdict(dict)
    for r in R:
        if r["valid"] == "1":
            by_time[r["time"]][(r["model"], r["unit"], r["quantity"])] = float(r["value"])
    agree = {}
    for q in ("T", "RH", "CO2", "NH3"):
        diffs = []
        for vals in by_time.values():
            v = [x for (m, u, qq), x in vals.items() if qq == q]
            if len(v) >= 2:
                diffs.append(max(v) - min(v))
        if diffs:
            agree[q] = {"polls": len(diffs), "median_spread": round(statistics.median(diffs), 3),
                        "p95_spread": round(pct(diffs, 0.95), 3), "max_spread": round(max(diffs), 3)}
    out["co_location_spread"] = agree  # meaningful only while the sensors sit side by side
    if a.reference:
        ref = list(csv.DictReader(open(a.reference)))
        bias = {}
        for q in ("T", "RH", "CO2", "NH3"):
            pairs = []
            for rr in ref:
                if not rr.get(q):
                    continue
                tr = datetime.fromisoformat(rr["time"])
                near = [(abs((datetime.fromisoformat(t) - tr).total_seconds()), vals) for t, vals in by_time.items()]
                near = [x for x in near if x[0] <= 90]
                if near:
                    _, vals = min(near, key=lambda x: x[0])
                    for (m, u, qq), x in vals.items():
                        if qq == q:
                            pairs.append((f"{m}#{u}", x - float(rr[q])))
            if pairs:
                bias[q] = {dev: {"n": len([d for dd, d in pairs if dd == dev]),
                                 "mean_bias": round(statistics.mean([d for dd, d in pairs if dd == dev]), 3),
                                 "mean_abs": round(statistics.mean([abs(d) for dd, d in pairs if dd == dev]), 3)}
                           for dev in sorted({d for d, _ in pairs})}
        out["bias_vs_reference"] = bias

    # ---- O2: windows, persistence
    placed = date.fromisoformat(cfg["flock"]["placement_date"])
    weight = cfg["flock"].get("initial_weight_g", 44)
    wins = defaultdict(lambda: P.WindowAggregator())
    zones = sorted({d["zone"] for d in cfg["devices"] if d["model"] == "ODMHM-R"})
    for r in R:
        ts = datetime.fromisoformat(r["time"])
        wins[P.window_start(ts, win_s)].add([{"valid": r["valid"] == "1", "zone": int(r["zone"]), "quantity": r["quantity"],
                                             "value": float(r["value"]) if r["value"] not in ("", "None") else None}])
    pers = P.Persistence()
    raw_changes = pers_changes = 0
    prev_raw, prev_p, pend = {}, {}, {}
    delays = []
    n_win = 0
    for ws in sorted(wins):
        week = (ws.date() - placed).days // 7 + 1
        zin = wins[ws].close(zones)
        n_win += 1
        for z, inp in zin.items():
            r = P.rate_zone_partial(inp, week, weight)
            if r is None:
                continue
            raw = r["level"]
            if z not in prev_p:  # start each zone at its first observed level, not at the class default
                pers.level[z], pers.cause[z] = raw, r["cause"]
            before = prev_p.get(z, raw)
            lvl, _, _ = pers.update(z, raw, r["cause"])
            if z in prev_raw and raw != prev_raw[z]:
                raw_changes += 1
            if lvl != before and z in prev_p:
                pers_changes += 1
            if raw > before and z not in pend:
                pend[z] = n_win                      # raw level rose above the persisted level
            if lvl > before and z in pend:
                delays.append(n_win - pend.pop(z))   # windows until the persisted level followed
            elif raw <= before:
                pend.pop(z, None)                    # short excursion filtered out
            prev_raw[z], prev_p[z] = raw, lvl
    days = max(span_h / 24, 1e-9)
    out["persistence"] = {"windows": n_win, "window_s": win_s, "raw_level_changes": raw_changes,
                          "persisted_level_changes": pers_changes,
                          "raw_changes_per_day": round(raw_changes / days, 1),
                          "persisted_changes_per_day": round(pers_changes / days, 1),
                          "reduction_share": round(1 - pers_changes / raw_changes, 3) if raw_changes else None,
                          "added_delay_windows_median": statistics.median(delays) if delays else None}

    # ---- O4: outbox
    db = os.path.join(a.log_dir, "outbox.db")
    if os.path.exists(db):
        con = sqlite3.connect(db)
        n, unsent = con.execute("SELECT COUNT(*), SUM(sent=0) FROM outbox").fetchone()
        out["outbox"] = {"assessments": n, "unsent_at_end": unsent or 0,
                         "max_backlog": max((int(r["unsent"]) for r in res_rows), default=None)}

    # ---- O6: device performance
    polls = [float(r["poll_s"]) for r in res_rows]
    late = [float(r["late_s"]) for r in res_rows]
    out["device"] = {"polls": len(polls), "poll_s_median": round(statistics.median(polls), 3) if polls else None,
                     "poll_s_p95": round(pct(polls, 0.95), 3) if polls else None, "poll_s_max": round(max(polls), 3) if polls else None,
                     "lateness_s_max": round(max(late), 3) if late else None,
                     "cpu_s_total": float(res_rows[-1]["cpu_s"]) if res_rows else None,
                     "max_rss_kb": max((int(r["maxrss_kb"]) for r in res_rows), default=None)}
    if span_h > 0 and res_rows:
        out["device"]["cpu_share"] = round(out["device"]["cpu_s_total"] / (span_h * 3600), 4)

    if a.events:
        ev = list(csv.DictReader(open(a.events)))
        rep = []
        for e in ev:
            s, t = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
            inside = [r for r in R if s <= datetime.fromisoformat(r["time"]) <= t and (not e.get("unit") or r["unit"] == e["unit"])]
            rep.append({"kind": e["kind"], "unit": e.get("unit"), "readings": len(inside),
                        "flags": dict(Counter(f for r in inside for f in filter(None, r["flags"].split("|"))))})
        out["events"] = rep

    json.dump(out, open(os.path.join(a.log_dir, "bench_results.json"), "w"), indent=1)
    md = ["# Bench results", "", f"Period: {out['period']['start']} to {out['period']['end']} ({out['period']['hours']} h), "
          f"{out['readings']} readings", "", "## Completeness (valid share)"]
    md += [f"- {k}: {v['valid_share']:.1%} of {v['n']} ({', '.join(f'{f} {c}' for f, c in v['flags'].items()) or 'no flags'})"
           for k, v in out["completeness"].items()]
    md += ["", "## Persistence", f"- {json.dumps(out['persistence'])}", "", "## Device", f"- {json.dumps(out['device'])}"]
    if "outbox" in out:
        md += ["", "## Outbox", f"- {json.dumps(out['outbox'])}"]
    open(os.path.join(a.log_dir, "bench_results.md"), "w").write("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
