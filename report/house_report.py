"""House report built from the SAP record (paper v17, Section IV-D): the reference implementation of the
ABAP report Z_BRL_HOUSE_REPORT (sap/abap). In SAP a background job runs it every morning per house;
here it runs on the mock SAP tables of the fault-injection test or on rows read back from SAP.

Sections
  1 Data: assessments received; with an interval, the expected windows and the gaps
  2 Conditions: share of windows per level, worst level per zone, peaks of THI, NH3 and CO2, and the
    windows with the low-air-speed diagnostic
  3 Possible causes: of Moderate and Severe windows and of Severe episode starts; a possible cause that
    recurs (in >= 2 notifications or >= 3 episode starts) is flagged: the cause may be systematic
    (settings, equipment or the target), so repeating the task is not enough
  4 Notification check: each notification with its tasks, outstanding / completed / overdue (> 24 h),
    and for completed tasks whether the house was back to Normal within the next 3 windows (recovery
    check; a stored row is the house's worst zone, so a Normal row means every zone is Normal)

Usage: python3 house_report.py --db sap.db --all [--interval 300] [--now 2027-01-02T08:00:00]
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "edge"))
import tasks as TK  # noqa: E402

LEVEL = {0: "Normal", 1: "Moderate", 2: "Severe"}
OVERDUE_H, RECOVER_WINDOWS = 24, 3
RECUR_NOTIFS, RECUR_EPISODES = 2, 3


def _t(ts):
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)


def build_report(rows, notifs, tasks, flock, house, interval_s=None, now=None, period_from=None):
    """rows: dicts ts, zone, level, cause, possible_cause, tasks, episode, inputs (dict, optional)
    notifs: dicts notif_id, ts, zone, trigger_id;  tasks: dicts notif_id, task_key, code, completed_at, completed_by
    Rows up to period_from are used only for the recovery check (as iv_from in ZCL_BRL_HOUSE_REPORT)."""
    all_rows = sorted(rows, key=lambda r: _t(r["ts"]))
    rows = [r for r in all_rows if period_from is None or _t(r["ts"]) > _t(period_from)]
    rep = {"flock": flock, "house": house, "rule_versions": sorted({r.get("rule_version", "") for r in rows} - {""})}
    if not rows:
        rep["empty"] = True
        return rep
    t0, t1 = _t(rows[0]["ts"]), _t(rows[-1]["ts"])
    now = _t(now) if now else t1
    rep["period"] = (t0.isoformat(), t1.isoformat())
    # 1 data completeness
    data = {"received": len(rows), "not_rated_windows": sum(1 for r in rows if r.get("not_rated"))}
    if interval_s:
        times = sorted({_t(r["ts"]) for r in rows})
        data["expected"] = int((t1 - t0).total_seconds() // interval_s) + 1
        gaps = []
        for a, b in zip(times, times[1:]):
            missing = int((b - a).total_seconds() // interval_s) - 1
            if missing > 0:
                gaps.append({"from": (a + timedelta(seconds=interval_s)).isoformat(), "missing": missing})
        data["gaps"] = gaps
        data["completeness"] = round(len(times) / data["expected"], 4)
    rep["data"] = data
    # 2 conditions
    lv = Counter(int(r["level"]) for r in rows)
    zone_worst = defaultdict(int)
    for r in rows:
        zone_worst[int(r["zone"])] = max(zone_worst[int(r["zone"])], int(r["level"]))
    peaks = {}
    for key in ("THI", "NH3", "CO2"):
        vals = [float(r["inputs"][key]) for r in rows if r.get("inputs") and r["inputs"].get(key) is not None]
        if vals:
            peaks[key] = round(max(vals), 2)
    rep["conditions"] = {"windows_per_level": {LEVEL[k]: lv.get(k, 0) for k in LEVEL},
                         "share_per_level": {LEVEL[k]: round(lv.get(k, 0) / len(rows), 4) for k in LEVEL},
                         "worst_level_per_zone": {z: LEVEL[v] for z, v in sorted(zone_worst.items())}, "peaks": peaks,
                         "low_air_speed_windows": sum(1 for r in rows if r.get("air_speed_diag"))}
    # 3 possible causes
    pc_ms = Counter(r.get("possible_cause") for r in rows if int(r["level"]) >= 1 and r.get("possible_cause"))
    pc_ep = Counter(r.get("possible_cause") for r in rows if int(r.get("episode") or 0) and r.get("possible_cause"))
    by_id = {r["assess_id"]: r for r in all_rows if "assess_id" in r}
    pc_nt = Counter(by_id[n["trigger_id"]].get("possible_cause") for n in notifs
                    if n["trigger_id"] in by_id and by_id[n["trigger_id"]].get("possible_cause"))
    recurring = sorted({c for c, k in pc_nt.items() if k >= RECUR_NOTIFS} | {c for c, k in pc_ep.items() if k >= RECUR_EPISODES})
    rep["possible_causes"] = {"moderate_or_severe_windows": dict(pc_ms.most_common()),
                              "severe_episode_starts": dict(pc_ep.most_common()),
                              "notifications": dict(pc_nt.most_common()),
                              "recurring": [{"code": c, "text": TK.POSSIBLE_CAUSES.get(c, ("?",))[0]} for c in recurring]}
    # 4 notification check
    by_notif = defaultdict(list)
    for t in tasks:
        by_notif[t["notif_id"]].append(t)
    checks, counts = [], Counter()
    for n in sorted(notifs, key=lambda n: _t(n["ts"])):
        trig = by_id.get(n["trigger_id"], {})
        items = []
        for t in sorted(by_notif.get(n["notif_id"], []), key=lambda t: int(t["task_key"])):
            if t.get("completed_at"):
                after = [r for r in all_rows if _t(r["ts"]) > _t(t["completed_at"])][:RECOVER_WINDOWS]
                status = "completed"
                if any(int(r["level"]) == 0 for r in after):
                    recovery = "back to Normal"
                elif len(after) < RECOVER_WINDOWS:
                    recovery = "too early to tell"
                else:
                    recovery = "improved, not Normal" if min(int(r["level"]) for r in after) < 2 else "not yet"
                counts["recovery: " + recovery] += 1
            else:
                overdue = (now - _t(n["ts"])) > timedelta(hours=OVERDUE_H)
                status, recovery = ("overdue" if overdue else "outstanding"), None
            counts[status] += 1
            items.append({"task": t["code"], "text": TK.CATALOG.get(t["code"], ("?",))[0], "status": status,
                          "by": t.get("completed_by"), "recovery": recovery})
        checks.append({"notification": n["notif_id"], "ts": _t(n["ts"]).isoformat(), "zone": int(n["zone"]),
                       "possible_cause": trig.get("possible_cause"), "tasks": items})
    rep["notification_check"] = {"notifications": len(notifs),
                                 "task_status": {k: v for k, v in counts.items() if not k.startswith("recovery")},
                                 "recovery": {k.split(": ")[1]: v for k, v in counts.items() if k.startswith("recovery")},
                                 "items": checks}
    return rep


def render_text(rep):
    out = [f"HOUSE REPORT  flock {rep['flock']}  house {rep['house']}  rule version {', '.join(rep['rule_versions']) or '-'}"]
    if rep.get("empty"):
        return out[0] + "\n  no assessments in the period"
    d, c, p, n = rep["data"], rep["conditions"], rep["possible_causes"], rep["notification_check"]
    out.append(f"  period {rep['period'][0]} to {rep['period'][1]}")
    line = f"1 Data: {d['received']} assessments"
    if "expected" in d:
        line += f" of {d['expected']} expected ({100 * d['completeness']:.1f}%), {len(d['gaps'])} gap(s)"
        line += "".join(f"\n    gap from {g['from']}: {g['missing']} window(s) missing" for g in d["gaps"])
    out.append(line)
    sh = c["share_per_level"]
    out.append(f"2 Conditions: Normal {100 * sh['Normal']:.0f}%, Moderate {100 * sh['Moderate']:.0f}%, "
               f"Severe {100 * sh['Severe']:.0f}%; worst per zone "
               + ", ".join(f"{z}: {v}" for z, v in c["worst_level_per_zone"].items())
               + ("; peaks " + ", ".join(f"{k} {v}" for k, v in c["peaks"].items()) if c["peaks"] else "")
               + f"; low-air-speed diagnostic in {c['low_air_speed_windows']} window(s)")
    out.append("3 Possible causes (Moderate/Severe windows): "
               + (", ".join(f"{k} {v}" for k, v in p["moderate_or_severe_windows"].items()) or "none"))
    for r in p["recurring"]:
        out.append(f"    RECURRING {r['code']} ({r['text']}): may be systematic - check settings, equipment or the target")
    ts = n["task_status"]
    out.append(f"4 Notification check: {n['notifications']} notification(s); tasks "
               + (", ".join(f"{k} {v}" for k, v in sorted(ts.items())) or "none")
               + ("; after completion: " + ", ".join(f"{k} {v}" for k, v in sorted(n["recovery"].items()))
                  if n["recovery"] else ""))
    for it in n["items"]:
        out.append(f"    notification {it['notification']} at {it['ts']}, zone {it['zone']}, possible cause {it['possible_cause']}")
        for t in it["tasks"]:
            out.append(f"      {t['task']} {t['text']}: {t['status']}"
                       + (f" by {t['by']}" if t.get("by") else "") + (f", {t['recovery']}" if t.get("recovery") else ""))
    return "\n".join(out)


# ---------- data access: mock SAP tables (sil/sap_mock.py schema) ----------
def load_mock(db, flock, house):
    con = sqlite3.connect(db)
    rows = []
    for aid, ts, zone, level, cause, ep, t1, t2, t3, rv, pc, payload in con.execute(
            "SELECT assess_id, ts, zone, level, cause, episode, task1, task2, task3, rule_ver, poss_cause, payload "
            "FROM zbrl_stress WHERE flock=? AND house=?", (flock, house)):
        a = json.loads(payload)
        inp = dict(a.get("inputs") or {})
        if a.get("thi") is not None:
            inp["THI"] = a["thi"]
        rows.append({"assess_id": aid, "ts": ts, "zone": zone, "level": level, "cause": cause, "episode": ep,
                     "tasks": [t for t in (t1, t2, t3) if t], "rule_version": rv, "possible_cause": pc or None,
                     "inputs": inp, "not_rated": bool(a.get("not_rated")), "air_speed_diag": bool(a.get("air_speed_diag"))})
    notifs = [{"notif_id": i, "ts": ts, "zone": z, "trigger_id": tr} for i, ts, z, tr in con.execute(
        "SELECT notif_id, ts, zone, trigger_id FROM notif WHERE flock=? AND house=?", (flock, house))]
    ids = [n["notif_id"] for n in notifs]
    tasks = []
    if ids:
        q = "SELECT notif_id, task_key, code, completed_at, completed_by FROM notif_task WHERE notif_id IN (%s)" % ",".join("?" * len(ids))
        tasks = [{"notif_id": a, "task_key": b, "code": c, "completed_at": d, "completed_by": e} for a, b, c, d, e in con.execute(q, ids)]
    return rows, notifs, tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--flock")
    ap.add_argument("--house", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--interval", type=int, default=0, help="window length in s (0: spot data, no gap check)")
    ap.add_argument("--now")
    ap.add_argument("--json")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    pairs = sorted(con.execute("SELECT DISTINCT flock, house FROM zbrl_stress")) if a.all else [(a.flock, a.house)]
    reports = []
    for flock, house in pairs:
        rep = build_report(*load_mock(a.db, flock, house), flock, house, a.interval or None, a.now)
        reports.append(rep)
        print(render_text(rep) + "\n")
    if a.json:
        json.dump(reports, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
