"""Tests of the edge software against emulated devices (no hardware needed).

  python3 tests/test_edge.py            -> prints a summary and writes tests/edge_test_results.json

Groups
  A  frames: CRC and decoding reproduce the example frames printed in the S-NH3-01 datasheet
  B  round trip: every value of the 1,692 complete records of the open dataset is written into the
     emulated devices in the documented encoding, read back over a pseudo-terminal with the RTU
     master and decoded; boundary values of each sensor's range are added
  C  faults: silent device, one corrupted response, persistent corruption, exception response,
     device fault flags, anemometer status bit, rejected block read, out-of-range value, warm-up,
     stuck value, maintenance flag, and the Sentera register-offset check
  D  persistence rule (2 windows up, 3 down) and episode starts on constructed level sequences
  E  timing: one poll of the six planned devices over an emulated 9600-baud 8N1 line, compared
     with the frame time computed from the register blocks
Nothing here involves real sensors; group E measures the code's own overhead, not device latency.
"""
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import devices as D  # noqa: E402
import modbus_rtu as R  # noqa: E402
import pipeline as P  # noqa: E402
from acquire import Acquisition  # noqa: E402
from commission import detect_odmhm_offset  # noqa: E402
from emulator import Bus, EmulatedDevice  # noqa: E402

RECORDS = os.path.join(HERE, "..", "..", "data", "replay_records.csv")
PLAN = [("ODMHM-R", 1, 1), ("ODMHM-R", 2, 2), ("ODMHM-R", 3, 3), ("S-NH3-01", 11, 2), ("S-NH3-01", 12, 3),
        ("HD53LS.S", 21, 2)]
results = {}


def check(group, name, ok, **detail):
    results.setdefault(group, []).append({"test": name, "ok": bool(ok), **detail})
    if not ok:
        print("FAIL", group, name, detail)


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def make(baud=None, odmhm_offset=-1, timeout=0.15):
    emu = {u: EmulatedDevice(m, u, odmhm_offset) for m, u, _ in PLAN}
    bus = Bus(list(emu.values()), baud=baud)
    line = R.SerialLine(bus.port, 9600, "N", 1, timeout=timeout)
    master = R.Master(line)
    devs = [D.MODELS[m](u, z) for m, u, z in PLAN]
    return emu, bus, master, devs


def ready_acq(master, devs, clock, **kw):
    acq = Acquisition(master, devs, clock=clock, **kw)
    acq.t_start = -1e9
    acq.online_since = {d.unit: -1e9 for d in devs}
    return acq


def by_unit(readings):
    return {(r["unit"], r["quantity"]): r for r in readings}


# ------------------------------------------------------------------ A frames
def group_a():
    ex_req = {"0F0320000002CEE5": (0x0F, 3, 0x2000, 2), "0F0320040001CF25": (0x0F, 3, 0x2004, 1),
              "0F0320060001 6EE5".replace(" ", ""): (0x0F, 3, 0x2006, 1)}
    for hexs, args in ex_req.items():
        check("A", f"request {hexs}", R.read_request(*args).hex().upper() == hexs)
    # The datasheet prints the NH3 response twice with different third data bytes: '0F 03 04 3C BB 28 2F
    # 2F 9A' (frame line) and '3C BB 08 2F ... 2F 9A' (field breakdown). The printed CRC 2F 9A can match
    # only one of them; the master must reject the other as corrupted.
    frame_line = bytes.fromhex("0F03043CBB282F2F9A")
    breakdown = bytes.fromhex("0F03043CBB082F2F9A")
    check("A", "printed CRC 2F 9A matches the breakdown bytes 3C BB 08 2F", R.crc_ok(breakdown))
    check("A", "frame line 3C BB 28 2F (typo) is rejected as a CRC error", not R.crc_ok(frame_line))
    regs = R.parse_read_response(0x0F, 3, 2, breakdown)
    v, _ = D.SNH301(0x0F, 0).decode({0x2000: regs[0], 0x2001: regs[1]})
    check("A", "NH3 example decodes to 0.0 ppm (0.0228 at 0.1 ppm resolution)", v["NH3"] == 0.0, value=v["NH3"])
    t = R.parse_read_response(0x0F, 3, 1, bytes.fromhex("0F03020AF91767"))[0]
    check("A", "temperature example 0x0AF9 -> 28.09 C", t / 100 == 28.09 and R.crc_ok(bytes.fromhex("0F03020AF91767")))
    h = R.parse_read_response(0x0F, 3, 1, bytes.fromhex("0F030218BD1BF4"))[0]
    check("A", "humidity example 0x18BD -> 63.33 %RH", h / 100 == 63.33)


# ------------------------------------------------------------------ B round trip
def group_b():
    emu, bus, master, devs = make()
    acq = ready_acq(master, devs, Clock(), stuck_s=1e12)
    rows = list(csv.DictReader(open(RECORDS)))
    worst = {"T": 0.0, "RH": 0.0, "CO2": 0.0, "NH3": 0.0, "V": 0.0}
    exact = {k: 0 for k in worst}
    n = 0
    t0 = time.monotonic()
    for i, r in enumerate(rows):
        val = {k: float(r[k]) for k in worst}
        u_th, u_nh, u_v = (1, 2, 3)[i % 3], (11, 12)[i % 2], 21
        with bus.lock:
            emu[u_th].set_registers(D.OdmhmR.encode(val["T"], val["RH"], val["CO2"]))
            emu[u_nh].set_registers(D.SNH301.encode(val["NH3"]), table="hold")
            emu[u_v].set_registers(D.HD53LSS.encode(val["V"]))
        got = by_unit(acq.poll())
        exp = {"T": round(val["T"] * 10) / 10, "RH": round(val["RH"] * 10) / 10, "CO2": float(round(val["CO2"])),
               "NH3": round(val["NH3"], 1), "V": round(val["V"] * 100) / 100}
        for q, unit in (("T", u_th), ("RH", u_th), ("CO2", u_th), ("NH3", u_nh), ("V", u_v)):
            g = got[(unit, q)]
            if not g["valid"]:
                check("B", f"record {i} {q} valid", False, flags=g["flags"])
                continue
            worst[q] = max(worst[q], abs(g["value"] - val[q]))
            exact[q] += abs(g["value"] - exp[q]) < 1e-9
        n += 1
    el = time.monotonic() - t0
    for q in worst:
        check("B", f"{q}: all {n} decoded values equal the documented quantisation", exact[q] == n,
              exact=exact[q], max_abs_error=round(worst[q], 6))
    # boundaries of each sensor's documented range
    for t, rh, co2 in ((-30.0, 0.0, 0.0), (-0.1, 100.0, 10000.0), (70.0, 50.0, 400.0)):
        with bus.lock:
            emu[1].set_registers(D.OdmhmR.encode(t, rh, co2))
        g = by_unit(acq.poll())
        check("B", f"boundary T={t} RH={rh} CO2={co2}", g[(1, "T")]["value"] == t and g[(1, "RH")]["value"] == rh
              and g[(1, "CO2")]["value"] == co2 and g[(1, "T")]["valid"])
    for nh3 in (0.0, 0.1, 100.0):
        with bus.lock:
            emu[11].set_registers(D.SNH301.encode(nh3), table="hold")
        check("B", f"boundary NH3={nh3}", by_unit(acq.poll())[(11, "NH3")]["value"] == nh3)
    for v in (0.0, 0.01, 50.0):
        with bus.lock:
            emu[21].set_registers(D.HD53LSS.encode(v))
        check("B", f"boundary V={v}", by_unit(acq.poll())[(21, "V")]["value"] == v)
    results["B_summary"] = {"records": n, "polls": n, "transactions": master.stats["requests"],
                            "max_abs_error": {k: round(v, 6) for k, v in worst.items()},
                            "seconds": round(el, 1)}
    bus.stop()


# ------------------------------------------------------------------ C faults
def group_c():
    emu, bus, master, devs = make()
    clock = Clock()
    acq = ready_acq(master, devs, clock, stuck_s=1e12)
    with bus.lock:
        for u in (1, 2, 3):
            emu[u].set_registers(D.OdmhmR.encode(28.0, 70.0, 1500))
        for u in (11, 12):
            emu[u].set_registers(D.SNH301.encode(8.0), table="hold")
        emu[21].set_registers(D.HD53LSS.encode(1.2))
    base = by_unit(acq.poll())
    check("C", "all six devices valid at start", all(r["valid"] for r in base.values()))

    def run(setup, teardown):
        with bus.lock:
            setup()
        s0 = dict(master.stats)
        t0 = time.monotonic()
        g = by_unit(acq.poll())
        dt = time.monotonic() - t0
        with bus.lock:
            teardown()
        return g, {k: master.stats[k] - s0[k] for k in s0}, dt

    g, st, dt = run(lambda: emu[12].faults.update(silent=True), lambda: emu[12].faults.clear())
    check("C", "silent NH3 sensor: its reading invalid (timeout), the other five valid",
          g[(12, "NH3")]["flags"] == ["comm:timeout"] and sum(r["valid"] for r in g.values()) == 11,
          poll_s=round(dt, 3), stats=st)
    g, st, _ = run(lambda: emu[1].faults.update(corrupt_once=True), lambda: emu[1].faults.clear())
    check("C", "one corrupted response: CRC error detected, retry succeeds",
          g[(1, "T")]["valid"] and st["crc"] == 1 and st["retries"] == 1, stats=st)
    g, st, _ = run(lambda: emu[2].faults.update(corrupt_always=True), lambda: emu[2].faults.clear())
    check("C", "persistent corruption: zone-2 readings invalid (crc)",
          g[(2, "T")]["flags"] == ["comm:crc"] and g[(1, "T")]["valid"], stats=st)
    g, st, _ = run(lambda: emu[3].faults.update(exception=4), lambda: emu[3].faults.clear())
    check("C", "exception response (04): invalid, no retry", g[(3, "CO2")]["flags"] == ["comm:exception"]
          and st["retries"] == 0, stats=st)
    g, _, _ = run(lambda: emu[1].set_registers({25: 1}), lambda: emu[1].set_registers({25: 0}))
    check("C", "CO2 fault flag (IR25): CO2 invalid, T and RH valid",
          g[(1, "CO2")]["flags"] == ["device_fault"] and g[(1, "T")]["valid"] and g[(1, "RH")]["valid"])
    g, _, _ = run(lambda: emu[1].set_registers({14: 1}), lambda: emu[1].set_registers({14: 0}))
    check("C", "humidity/temperature fault flag (IR14): T and RH invalid",
          not g[(1, "T")]["valid"] and not g[(1, "RH")]["valid"] and g[(1, "CO2")]["valid"])
    g, _, _ = run(lambda: emu[21].set_registers({17: 1}), lambda: emu[21].set_registers({17: 0}))
    check("C", "anemometer status bit0: V invalid", g[(21, "V")]["flags"] == ["device_fault"])
    g, _, _ = run(lambda: emu[21].faults.update(strict_gaps=True), lambda: None)
    hd = [d for d in devs if d.unit == 21][0]
    check("C", "anemometer rejects block read over undocumented registers: falls back to single reads",
          g[(21, "V")]["valid"] and hd.mode == "singles" and g[(21, "V")]["value"] == 1.2)
    g, _, _ = run(lambda: emu[1].set_registers(D.OdmhmR.encode(75.0, 70.0, 1500)),
                  lambda: emu[1].set_registers(D.OdmhmR.encode(28.0, 70.0, 1500)))
    check("C", "value outside the sensor range (75 C): flagged", g[(1, "T")]["flags"] == ["range"])
    # warm-up: a fresh acquisition flags NH3 for 300 s and the anemometer for 10 s
    c2 = Clock(0.0)
    acq2 = Acquisition(master, devs, clock=c2, stuck_s=1e12)
    g0 = by_unit(acq2.poll())
    c2.t = 11.0
    g1 = by_unit(acq2.poll())
    c2.t = 301.0
    g2 = by_unit(acq2.poll())
    check("C", "warm-up: NH3 flagged until 300 s, V until 10 s, T never",
          "warmup" in g0[(11, "NH3")]["flags"] and "warmup" in g0[(21, "V")]["flags"] and g0[(1, "T")]["valid"]
          and "warmup" in g1[(11, "NH3")]["flags"] and g1[(21, "V")]["valid"] and g2[(11, "NH3")]["valid"])
    # warm-up restarts after a communication gap (possible power cut of the sensor)
    with bus.lock:
        emu[11].faults.update(silent=True)
    c2.t = 400.0
    acq2.poll()
    with bus.lock:
        emu[11].faults.clear()
    c2.t = 460.0
    g3 = by_unit(acq2.poll())
    check("C", "warm-up restarts when a device answers again after a gap", "warmup" in g3[(11, "NH3")]["flags"])
    # stuck value
    c3 = Clock(0.0)
    acq3 = ready_acq(master, devs, c3)
    flags = []
    for k in range(32):
        c3.t = 60.0 * k
        flags.append(by_unit(acq3.poll())[(1, "CO2")]["flags"])
    check("C", "value unchanged for 30 min is flagged stuck (not before)",
          flags[29] == [] and flags[30] == ["stuck"], at_29=flags[29], at_30=flags[30])
    # maintenance flag
    mf = os.path.join(HERE, "maintenance.flag")
    open(mf, "w").close()
    acq4 = ready_acq(master, devs, Clock(), maintenance_file=mf, stuck_s=1e12)
    g = by_unit(acq4.poll())
    os.remove(mf)
    check("C", "maintenance flag marks every reading invalid", all("maintenance" in r["flags"] for r in g.values()))
    bus.stop()
    # Sentera register numbering: detect both conventions
    for off in (-1, 0):
        emu2, bus2, master2, _ = make(odmhm_offset=off)
        check("C", f"register-offset check finds offset {off}", detect_odmhm_offset(master2, 1) == off)
        bus2.stop()


# ------------------------------------------------------------------ D persistence
def group_d():
    seqs = {
        "single Severe window ignored": ([0, 2, 0, 0], [0, 0, 0, 0]),
        "two Severe windows raise to Severe": ([0, 2, 2, 2], [0, 0, 2, 2]),
        "Moderate then Severe rises stepwise": ([0, 1, 2, 2], [0, 0, 1, 2]),
        "two windows below do not clear": ([2, 2, 0, 0, 2], [0, 2, 2, 2, 2]),
        "three windows below clear": ([2, 2, 0, 0, 0], [0, 2, 2, 2, 0]),
        "clears to the highest of the three": ([2, 2, 1, 0, 0], [0, 2, 2, 2, 1]),
        "alternating raw levels stay put": ([0, 2, 0, 2, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0]),
    }
    for name, (raw, exp) in seqs.items():
        p = P.Persistence()
        got = [p.update("z", lv, "x")[0] for lv in raw]
        check("D", name, got == exp, raw=raw, got=got, expected=exp)
    p = P.Persistence()
    eps = [p.update("z", lv, "thermal")[2] for lv in [2, 2, 2, 0, 0, 0, 2, 2]]
    check("D", "episode starts counted once per Severe period", eps == [False, True, False, False, False, False,
                                                                          False, True], got=eps)
    # end to end: house assessment with persistence and a missing NH3 input
    p = P.Persistence()
    inp = {1: {"T": 34.0, "RH": 80.0, "CO2": 1500.0, "NH3": None, "V": 0.5},
           2: {"T": 29.0, "RH": 60.0, "CO2": 1200.0, "NH3": 5.0, "V": 0.5}}
    a1 = P.house_assessment("F1", 1, datetime(2027, 1, 1, 12, 0), 5, 2000, inp, p)
    a2 = P.house_assessment("F1", 1, datetime(2027, 1, 1, 12, 5), 5, 2000, inp, p)
    check("D", "house assessment: Severe zone 1 needs two windows; NH3 reported as not rated",
          a1["level"] == 0 and a2["level"] == 2 and a2["worst_zone"] == 1 and a2["episode_start"] == 1
          and "NH3" in a2["not_rated"] and a1["assessment_id"] != a2["assessment_id"],
          a1=a1["level"], a2=a2["level"], cause=a2["cause"])
    # NH3 within the sensor's typical error (5 ppm) of a band edge: flagged for a manual check, level unchanged
    import rules_core as RC
    cases = {4.9: False, 5.0: False, 5.1: True, 10.0: True, 15.0: True, 20.0: True, 25.0: True, 25.1: False}
    got = {c: RC.nh3_verify(c) for c in cases}
    check("D", "NH3 verify note: 5 < NH3 <= 25 ppm, none outside", got == cases, got=got)
    p = P.Persistence()
    inp2 = {1: {"T": 26.0, "RH": 60.0, "CO2": 1200.0, "NH3": 12.0, "V": 2.0}}
    b = [P.house_assessment("F1", 1, datetime(2027, 1, 2, 12, 5 * i), 5, 2000, inp2, p) for i in range(2)]
    check("D", "NH3 verify note carried in the assessment without changing level or tasks",
          b[1]["nh3_verify"] is True and b[1]["level"] == RC.nh3_P(12.0) == 1 and b[1]["cause"] == "NH3"
          and b[1]["tasks"] == P.house_assessment("F1", 1, datetime(2027, 1, 2, 12, 15), 5, 2000, inp2, p)["tasks"],
          level=b[1]["level"], cause=b[1]["cause"], tasks=b[1]["tasks"])


# ------------------------------------------------------------------ E timing
def frame_time(blocks, baud=9600, bits=10):
    tc = bits / baud
    return sum((8 + 5 + 2 * n) * tc + 2 * 3.5 * tc for n in blocks)


def group_e():
    emu, bus, master, devs = make(baud=9600, timeout=0.3)
    acq = ready_acq(master, devs, Clock(), stuck_s=1e12)
    acq.poll()
    times = []
    for _ in range(20):
        t0 = time.monotonic()
        acq.poll()
        times.append(time.monotonic() - t0)
    blocks = [25, 25, 25, 2, 2, 18]
    comp = frame_time(blocks)
    comp_v14 = frame_time([25, 25, 25, 7, 7, 18])
    med = statistics.median(times)
    results["E_summary"] = {"computed_frame_time_s": round(comp, 4), "computed_v14_with_7_reg_nh3_s": round(comp_v14, 4),
                            "measured_median_poll_s": round(med, 4), "measured_max_poll_s": round(max(times), 4),
                            "overhead_s": round(med - comp, 4), "polls": len(times)}
    check("E", "emulated 9600-baud poll within 15% of computed frame time", abs(med - comp) / comp < 0.15,
          **results["E_summary"])
    bus.stop()


if __name__ == "__main__":
    for g in (group_a, group_b, group_c, group_d, group_e):
        g()
    total = sum(len(v) for k, v in results.items() if isinstance(v, list))
    passed = sum(t["ok"] for k, v in results.items() if isinstance(v, list) for t in v)
    results["total"], results["passed"] = total, passed
    with open(os.path.join(HERE, "edge_test_results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print(f"{passed}/{total} checks passed")
    print(json.dumps({k: results[k] for k in ("B_summary", "E_summary")}, indent=1))
