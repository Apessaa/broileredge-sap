"""Steps (ii)-(v) of the edge software (Section IV-C): 5-min zone averages, rating, persistence and the
house assessment that is sent to SAP.

  (ii)  average the valid readings of each zone over a 5-min window;
  (iii) rate each indicator with Table II (rules_core); an indicator whose inputs are missing is
        reported as not rated instead of guessed;
  (iv)  persistence: a zone moves up to a level only after two consecutive windows at or above it and
        moves down only after three consecutive windows below its current level;
  (v)   the house level is the most severe zone (ties: lowest zone number), stored with its cause;
  (vi)  a Moderate or Severe assessment carries a possible cause and up to three first tasks from the
        task catalog (tasks.py), each traced to published guidance: preventive at Moderate,
        corrective at Severe.
A Severe episode starts when a zone's persisted level becomes Severe; SAP counts episode starts.
"""
import uuid
from collections import defaultdict, deque
from datetime import timedelta

import rules_core as M
import tasks as TK

NS = uuid.UUID("6f1c3c86-3f5a-4d36-9a5e-2f1c7f0b9d11")  # same namespace as the prototype
UP, DOWN = 2, 3
LEVEL_NAME = {0: "Normal", 1: "Moderate", 2: "Severe"}


class WindowAggregator:
    """Collects valid readings per (zone, quantity) for one window."""

    def __init__(self, house_wide=("V",)):
        self.house_wide = set(house_wide)
        self.sums = defaultdict(lambda: [0.0, 0])

    def add(self, readings):
        for r in readings:
            if r["valid"]:
                s = self.sums[(r["zone"], r["quantity"])]
                s[0] += r["value"]
                s[1] += 1

    def close(self, zones):
        means = {(z, q): s[0] / s[1] for (z, q), s in self.sums.items() if s[1]}
        self.sums.clear()
        out = {}
        for z in zones:
            inp = {q: means.get((z, q)) for q in ("T", "RH", "CO2", "NH3")}
            hv = [v for (zz, q), v in means.items() if q == "V"]
            inp["V"] = means.get((z, "V"), sum(hv) / len(hv) if hv else None)
            out[z] = inp
        return out


def rate_zone_partial(inp, week, weight_g):
    """Rate the indicators whose inputs exist. Returns None if nothing can be rated."""
    t, rh, v = inp.get("T"), inp.get("RH"), inp.get("V")
    levels, missing = {}, []
    if t is not None and rh is not None:
        levels["thermal"] = M.thermal_P(t, rh, week, weight_g)
    else:
        missing.append("thermal")
    for q, fn in (("NH3", M.nh3_P), ("CO2", M.co2_P)):
        if inp.get(q) is not None:
            levels[q] = fn(inp[q])
        else:
            missing.append(q)
    if not levels:
        return None
    level = max(levels.values())
    cause = "none" if level == 0 else "+".join(k for k in ("thermal", "NH3", "CO2") if levels.get(k) == level)
    notes = {}
    if t is not None and rh is not None:
        notes["thi"] = round(M.thi_humid_tropics(t, rh), 2)
        if v is not None:
            notes["thvi_note"] = M.thvi_note(t, rh, v)
            notes["air_speed_diag"] = bool(M.air_speed_diag(t, rh, v, week))
    if inp.get("NH3") is not None:
        notes["nh3_verify"] = bool(M.nh3_verify(inp["NH3"]))
    return {"levels": levels, "level": level, "cause": cause, "not_rated": missing, **notes}


class Persistence:
    """Per-zone level persistence (2 windows up, 3 windows down)."""

    def __init__(self, up=UP, down=DOWN):
        self.up, self.down = up, down
        self.hist = defaultdict(lambda: deque(maxlen=max(up, down)))
        self.level = defaultdict(int)
        self.cause = defaultdict(lambda: "none")

    def update(self, zone, raw_level, raw_cause):
        """Returns (persisted level, cause, episode_start)."""
        h = self.hist[zone]
        h.append((raw_level, raw_cause))
        cur = self.level[zone]
        before = cur
        last_up = [lv for lv, _ in list(h)[-self.up:]]
        last_down = [lv for lv, _ in list(h)[-self.down:]]
        if len(last_up) == self.up and min(last_up) > cur:
            cur = min(last_up)
        elif len(last_down) == self.down and max(last_down) < cur:
            cur = max(last_down)
        self.level[zone] = cur
        if cur == 0:
            self.cause[zone] = "none"
        elif raw_level == cur:
            self.cause[zone] = raw_cause  # freshest cause observed at the persisted level
        elif cur != before:
            self.cause[zone] = next((c for lv, c in reversed(h) if lv == cur), raw_cause)
        return cur, self.cause[zone], (cur == 2 and before != 2)


def assessment_id(flock, house, window_start_iso):
    return str(uuid.uuid5(NS, f"{flock}/H{house}/{window_start_iso}"))


def house_assessment(flock, house, window_start, week, weight_g, zone_inputs, persistence=None):
    """zone_inputs: {zone: inputs}. With persistence=None the raw levels are used (replay of spot data)."""
    zones = {}
    for z, inp in sorted(zone_inputs.items()):
        r = rate_zone_partial(inp, week, weight_g)
        if r is None:
            continue
        if persistence is not None:
            lvl, cause, ep = persistence.update(z, r["level"], r["cause"])
        else:
            lvl, cause, ep = r["level"], r["cause"], r["level"] == 2
        zones[z] = (lvl, cause, ep, r)
    if not zones:
        return None
    worst = min(zones, key=lambda z: (-zones[z][0], z))
    lvl, cause, ep, r = zones[worst]
    inp = zone_inputs[worst]
    t_star = M.ross_target(weight_g, inp["RH"]) if week <= 3 and inp.get("RH") is not None else None
    tasks, notes, kind = TK.assessment_tasks(lvl, cause, r["levels"], inp, week, t_star, r.get("air_speed_diag"))
    pcause = TK.possible_cause(lvl, cause, inp, week, t_star, r.get("air_speed_diag"))
    ts = window_start.isoformat()
    return {"assessment_id": assessment_id(flock, house, ts), "flock": flock, "house": house, "ts": ts,
            "week": week, "worst_zone": worst, "level": lvl, "cause": cause, "episode_start": int(ep),
            "raw_level": r["level"], "sub_levels": r["levels"], "not_rated": r["not_rated"],
            "thi": r.get("thi"), "thvi_note": r.get("thvi_note"), "air_speed_diag": r.get("air_speed_diag"),
            "nh3_verify": r.get("nh3_verify"),
            "inputs": inp, "n_zones": len(zones),
            "tasks": tasks, "task_notes": notes, "thermal_kind": kind, "possible_cause": pcause,
            "task_mode": {1: "preventive", 2: "corrective"}.get(lvl),
            "t_target": None if t_star is None else round(t_star, 1), "rule_version": TK.RULE_VERSION,
            "zone_levels": {z: v[0] for z, v in zones.items()},
            "zone_raw": {z: v[3]["level"] for z, v in zones.items()}}


def window_start(dt, seconds=300):
    """Start of the window containing dt (windows aligned to the local clock)."""
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    into = (dt - midnight).total_seconds()
    return midnight + timedelta(seconds=into - into % seconds)
