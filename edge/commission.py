"""Commissioning helpers for the RS-485 bus (run on the Raspberry Pi, one step at a time).

  python3 commission.py scan --port /dev/ttyUSB0 --baud 9600
      lists which of the planned addresses answer and what they report.
  python3 commission.py odmhm-offset --port /dev/ttyUSB0 --unit 1
      decides whether Sentera register N is protocol address N-1 or N (reads device type 1712).
  python3 commission.py odmhm-setup --port /dev/ttyUSB0 --baud 19200 --parity E --unit 1 --new-unit 2
      sets a factory-new ODMHM-R (19200 8E1, address 1) to the bus settings 9600 8N1, gives it its
      address and switches CO2 self-calibration off. Connect only this one device while doing so,
      then power-cycle it.

The HD53LS.S is configured with its own serial commands (CU5A21, CU5B3, CU5M0; see the bench
protocol), and the S-NH3-01 address with the special frame in its datasheet; neither is automated
here because the documents describe them only in prose.
"""
import argparse
import json

import devices as D
from modbus_rtu import Master, ModbusError, SerialLine

ODMHM_DEVICE_TYPE = 1712  # holding register 4 ('1.712' in the register map)


def detect_odmhm_offset(master, unit):
    """Return -1 if register N is address N-1, 0 if it is address N, None if undecided."""
    found = []
    for offset in (-1, 0):
        try:
            if master.read_registers(unit, 3, 4 + offset, 1)[0] == ODMHM_DEVICE_TYPE:
                found.append(offset)
        except ModbusError:
            pass
    return found[0] if len(found) == 1 else None


def scan(master, plan):
    report = []
    for e in plan:
        dev = D.MODELS[e["model"]](e["unit"], e["zone"])
        row = {"unit": e["unit"], "model": e["model"], "zone": e["zone"]}
        try:
            regs = {}
            for fc, addr, count in dev.reads():
                regs.update({addr + i: v for i, v in enumerate(master.read_registers(dev.unit, fc, addr, count))})
            row["values"], row["faults"] = dev.decode(regs)
            row["answers"] = True
        except ModbusError as ex:
            row["answers"], row["error"] = False, str(ex)
        if e["model"] == "ODMHM-R" and row["answers"]:
            row["register_offset"] = detect_odmhm_offset(master, e["unit"])
            try:
                row["co2_self_calibration"] = master.read_registers(e["unit"], 3, 40 + D.ODMHM_OFFSET, 1)[0]
            except ModbusError:
                pass
        if e["model"] == "HD53LS.S" and row["answers"]:
            try:
                row["speed_unit_code"] = master.read_registers(e["unit"], 4, 18, 1)[0]  # 0 = m/s
            except ModbusError:
                pass
        report.append(row)
    return report


def odmhm_setup(master, unit, new_unit, offset=D.ODMHM_OFFSET):
    """The register map does not say whether new communication settings apply at once or after a
    restart, so the communication registers are written last and a failed echo is only reported.
    Verify afterwards with 'scan' at 9600 8N1; if the device does not answer, use Sentera's 3SModbus."""
    hr = lambda n: n + offset
    done = {}
    master.write_register(unit, hr(40), 0)   # CO2 self-calibration off: a house rarely returns to 400 ppm weekly
    done["HR40 self-calibration=0"] = True
    for label, u, reg, val in (("HR1 address", unit, 1, new_unit), ("HR3 parity 8N1", new_unit, 3, 0),
                               ("HR2 baud 9600", new_unit, 2, 1)):
        try:
            done[label] = master.write_register(u, hr(reg), val)
        except ModbusError as e:
            done[label] = f"no echo ({e}); check after power-cycle"
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("scan", "odmhm-offset", "odmhm-setup"))
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="N")
    ap.add_argument("--config", default="config_example.json")
    ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--new-unit", type=int)
    a = ap.parse_args()
    m = Master(SerialLine(a.port, a.baud, a.parity, 1, timeout=0.5))
    if a.cmd == "scan":
        plan = json.load(open(a.config))["devices"]
        print(json.dumps(scan(m, plan), indent=1))
    elif a.cmd == "odmhm-offset":
        print("register offset:", detect_odmhm_offset(m, a.unit))
    else:
        print(json.dumps(odmhm_setup(m, a.unit, a.new_unit), indent=1))
        print("power-cycle the device and run 'scan' at 9600 8N1")


if __name__ == "__main__":
    main()
