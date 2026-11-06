"""One poll of all devices, with the validity checks of step (i) in Section IV-C of the paper.

A reading is valid only if the device answered with a correct frame, its own fault flag is clear,
the value lies inside the sensor's range, the sensor is not warming up, the value has changed within
the last 30 min, and no maintenance flag is set. Each reading keeps the reasons it was rejected, so
the IsValid flag of the data model can be explained later.
"""
import os
import time

from modbus_rtu import ExceptionResponse, ModbusError

STUCK_S = 30 * 60


class Acquisition:
    def __init__(self, master, devices, clock=time.monotonic, maintenance_file=None, stuck_s=STUCK_S):
        self.master = master
        self.devices = devices
        self.clock = clock
        self.maintenance_file = maintenance_file
        self.stuck_s = stuck_s
        self.t_start = clock()
        self.online_since = {}   # unit -> time the device answered again after a gap (warm-up restarts)
        self.last_value = {}     # (unit, quantity) -> (value, time it last changed)

    def _read_device(self, dev):
        regs = {}
        for fc, addr, count in dev.reads():
            try:
                vals = self.master.read_registers(dev.unit, fc, addr, count)
            except ExceptionResponse as e:
                if e.code == 2 and dev.mode == "block" and dev.singles:
                    dev.mode = "singles"  # device rejects the block over undocumented gaps
                    return self._read_device(dev)
                raise
            regs.update({addr + i: v for i, v in enumerate(vals)})
        return regs

    def poll(self):
        now = self.clock()
        maintenance = bool(self.maintenance_file and os.path.exists(self.maintenance_file))
        out = []
        for dev in self.devices:
            try:
                values, faults = dev.decode(self._read_device(dev))
                error = None
                if dev.unit not in self.online_since:
                    self.online_since[dev.unit] = now
            except ModbusError as e:
                values, faults, error = {}, {}, e.kind
                self.online_since.pop(dev.unit, None)  # a gap may mean a power cut: warm up again
            for q in dev.quantities:
                flags = []
                v = values.get(q)
                if error:
                    flags.append("comm:" + error)
                else:
                    if faults.get(q):
                        flags.append("device_fault")
                    lo, hi = dev.ranges[q]
                    if not lo <= v <= hi:
                        flags.append("range")
                    warm = getattr(dev, "warmup_s", 0)
                    if warm and now - max(self.online_since.get(dev.unit, now), self.t_start) < warm:
                        flags.append("warmup")
                    key = (dev.unit, q)
                    prev = self.last_value.get(key)
                    if prev is None or prev[0] != v:
                        self.last_value[key] = (v, now)
                    elif now - prev[1] >= self.stuck_s:
                        flags.append("stuck")
                if maintenance:
                    flags.append("maintenance")
                out.append({"unit": dev.unit, "model": dev.model, "zone": dev.zone, "quantity": q,
                            "value": v, "valid": not flags, "flags": flags})
        return out
