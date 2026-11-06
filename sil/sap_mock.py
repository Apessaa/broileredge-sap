"""Mock of the custom SAP function module (Z_BRL_STRESS_SAVE) used for software-in-the-loop tests.

It keeps the interface of the design: one call per StressAssessment, an idempotency check on the
assessment identifier, an insert into a table that mirrors ZBRL_STRESS, and the escalation rule
"three Severe episodes in one zone within 24 h open one maintenance notification on the house's
functional location". Insert and notification are written in one database transaction, as the
BAPI_ALM_NOTIF_CREATE -> BAPI_ALM_NOTIF_SAVE -> BAPI_TRANSACTION_COMMIT sequence would be committed
in one logical unit of work. In mode "naive" the idempotency check is switched off (ablation).
Escalation counts episode starts: the edge marks the first Severe window of each episode
(episode_start = 1). Payloads without that field (the replay of spot surveys, whose windows lie hours
apart) count every Severe window as one episode, which is what the v14 test did.
Tasks (v16/v17): each row keeps the assessment's task codes (TASK1-3), rule version and possible cause;
a notification gets the tasks of the assessment that triggered it, as PM notification tasks
(notif_task: outstanding until completed_at is set, like QMSM-ERLDAT/ERLZEIT in PM).
This is NOT SAP: it is a stand-in with the same interface for testing delivery behaviour.
"""
import json
import sqlite3
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS zbrl_stress (
    row_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    assess_id   TEXT NOT NULL,
    flock       TEXT NOT NULL,
    house       INTEGER NOT NULL,
    zone        INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    level       INTEGER NOT NULL,
    cause       TEXT NOT NULL,
    episode     INTEGER NOT NULL DEFAULT 0,
    task1       TEXT NOT NULL DEFAULT '',
    task2       TEXT NOT NULL DEFAULT '',
    task3       TEXT NOT NULL DEFAULT '',
    rule_ver    TEXT NOT NULL DEFAULT '',
    poss_cause  TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notif (
    notif_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    func_loc    TEXT NOT NULL,
    flock       TEXT NOT NULL,
    house       INTEGER NOT NULL,
    zone        INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    trigger_id  TEXT NOT NULL,
    task1       TEXT NOT NULL DEFAULT '',
    task2       TEXT NOT NULL DEFAULT '',
    task3       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notif_task (
    notif_id    INTEGER NOT NULL,
    task_key    INTEGER NOT NULL,
    code        TEXT NOT NULL,
    completed_at TEXT,
    completed_by TEXT,
    PRIMARY KEY (notif_id, task_key)
);
"""
UNIQUE_IDX = "CREATE UNIQUE INDEX IF NOT EXISTS ux_assess ON zbrl_stress(assess_id);"


def connect(path, mode):
    con = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=FULL;")
    con.executescript(SCHEMA)
    if mode == "idem":
        con.execute(UNIQUE_IDX)
    return con


def _parse(ts):
    return datetime.fromisoformat(ts)


def z_brl_stress_save(con, a, mode):
    """Returns {"status": "stored"|"duplicate", "notification": id|None}."""
    episode = int(a.get("episode_start", 1 if a["level"] == 2 else 0)) if a["level"] == 2 else 0
    t1, t2, t3 = (list(a.get("tasks") or []) + ["", "", ""])[:3]
    con.execute("BEGIN IMMEDIATE;")
    try:
        if mode == "idem":
            cur = con.execute("SELECT 1 FROM zbrl_stress WHERE assess_id=?", (a["assessment_id"],))
            if cur.fetchone():
                con.execute("COMMIT;")
                return {"status": "duplicate", "notification": None}
        con.execute(
            "INSERT INTO zbrl_stress(assess_id, flock, house, zone, ts, level, cause, episode, task1, task2, task3, "
            "rule_ver, poss_cause, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a["assessment_id"], a["flock"], a["house"], a["worst_zone"], a["ts"], a["level"], a["cause"], episode,
             t1, t2, t3, a.get("rule_version", ""), a.get("possible_cause") or "", json.dumps(a)),
        )
        notif_id = None
        if episode:
            row = con.execute(
                "SELECT MAX(ts) FROM notif WHERE flock=? AND house=? AND zone=?",
                (a["flock"], a["house"], a["worst_zone"]),
            ).fetchone()
            last_notif = row[0]
            t_now = _parse(a["ts"])
            t_from = (t_now - timedelta(hours=24)).isoformat()
            lower = max(t_from, last_notif) if last_notif else t_from
            cnt = con.execute(
                "SELECT COUNT(*) FROM zbrl_stress WHERE flock=? AND house=? AND zone=? AND episode=1 AND ts>? AND ts<=?",
                (a["flock"], a["house"], a["worst_zone"], lower, a["ts"]),
            ).fetchone()[0]
            if cnt >= 3:
                cur = con.execute(
                    "INSERT INTO notif(func_loc, flock, house, zone, ts, trigger_id, task1, task2, task3) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"BRL-{a['flock'].upper()}-H{a['house']}", a["flock"], a["house"], a["worst_zone"], a["ts"],
                     a["assessment_id"], t1, t2, t3),
                )
                notif_id = cur.lastrowid
                for k, code in enumerate((c for c in (t1, t2, t3) if c), 1):   # PM notification tasks, outstanding
                    con.execute("INSERT INTO notif_task(notif_id, task_key, code) VALUES (?,?,?)", (notif_id, k, code))
        con.execute("COMMIT;")
        return {"status": "stored", "notification": notif_id}
    except Exception:
        con.execute("ROLLBACK;")
        raise
