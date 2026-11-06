"""Emulated Modbus RTU slaves on a pseudo-terminal, written independently of modbus_rtu.py.

The emulator implements the register maps of the three sensor types as documented by their
manufacturers (see devices.py for the documents), answers FC03/FC04/FC06 requests with correct CRCs,
ignores frames with a bad CRC or for an absent address (as a real slave does), and can inject faults:
  silent           the device never answers (cable cut, wrong address, Modbus not yet active)
  corrupt_once     flip one bit in the next response (noise on the line)
  corrupt_always   flip one bit in every response
  exception        answer every read with the given exception code
  strict_gaps      reject reads that span undocumented registers with exception 02
With baud set, each transaction is delayed by the wire time of request and response plus the
3.5-character silent interval, so a poll takes as long as it would on a real 8N1 line.
"""
import os
import struct
import threading
import time


def crc16(data):  # deliberately re-implemented here (independent of modbus_rtu.crc16)
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            lsb = crc & 1
            crc >>= 1
            if lsb:
                crc ^= 0xA001
    return crc


def with_crc(body):
    c = crc16(body)
    return body + struct.pack("<H", c)


class EmulatedDevice:
    def __init__(self, model, unit, odmhm_offset=-1):
        self.model, self.unit = model, unit
        self.inp, self.hold = {}, {}
        self.faults = {}
        if model == "ODMHM-R":
            self.off = odmhm_offset
            self.inp_range = range(1 + self.off, 51 + self.off)          # input registers 1..50
            self.hold_range = range(1 + self.off, 71 + self.off)         # holding registers 1..70
            for reg, val in {1: unit, 2: 2, 3: 1, 4: 1712, 5: 0x0100, 6: 0x0110, 9: 0, 40: 1}.items():
                self.hold[reg + self.off] = val
            self.documented_inp = set(self.inp_range)                    # reserved ones return 0
        elif model == "S-NH3-01":
            self.inp_range = range(0)
            self.hold_range = range(0x2000, 0x2009)
            self.hold.update({0x2000: 0, 0x2001: 0, 0x2004: 2500, 0x2006: 6000, 0x2008: 100})
            self.documented_hold = {0x2000, 0x2001, 0x2004, 0x2006, 0x2008}
        elif model == "HD53LS.S":
            self.inp_range = range(0, 23)
            self.hold_range = range(0)
            self.documented_inp = {0, 1, 8, 10, 11, 14, 15, 16, 17, 18, 21, 22}
            self.inp[18] = 0  # unit m/s
        else:
            raise ValueError(model)

    def set_registers(self, regs_by_number, table="inp"):
        """regs_by_number uses the manufacturer's numbering (Sentera: 1-based)."""
        off = self.off if self.model == "ODMHM-R" else 0
        tgt = self.inp if table == "inp" else self.hold
        for n, v in regs_by_number.items():
            tgt[n + off] = v & 0xFFFF

    def read(self, fc, addr, count):
        rng, regs = (self.hold_range, self.hold) if fc == 3 else (self.inp_range, self.inp)
        span = range(addr, addr + count)
        if not rng or span.start < rng.start or span.stop > rng.stop:
            return None, 2
        if self.faults.get("strict_gaps"):
            documented = self.documented_hold if fc == 3 else self.documented_inp
            if any(a not in documented for a in span):
                return None, 2
        if self.model == "S-NH3-01" and any(a not in self.documented_hold for a in span):
            return None, 2
        return [regs.get(a, 0) for a in span], None


class Bus:
    """All emulated devices on one RS-485 line, served on the master side of a pty."""

    def __init__(self, devices, baud=None, parity="N", stopbits=1):
        self.devices = {d.unit: d for d in devices}
        self.master_fd, slave_fd = os.openpty()
        self.port = os.ttyname(slave_fd)
        self._slave_fd = slave_fd  # keep open so the pty stays alive
        self.char_time = (1 + 8 + (parity != "N") + stopbits) / baud if baud else 0.0
        self.t35 = 3.5 * self.char_time
        self.lock = threading.Lock()
        self.log = []
        self._stop = False
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def stop(self):
        self._stop = True

    def _respond(self, req):
        if len(req) != 8 or crc16(req[:-2]) != struct.unpack("<H", req[-2:])[0]:
            self.log.append(("bad_request_crc", req.hex()))
            return None
        unit, fc, addr, val = struct.unpack(">BBHH", req[:6])
        with self.lock:
            dev = self.devices.get(unit)
            if dev is None or dev.faults.get("silent"):
                return None
            if dev.faults.get("exception"):
                return with_crc(bytes((unit, fc | 0x80, dev.faults["exception"])))
            if fc in (3, 4):
                vals, exc = dev.read(fc, addr, val)
                if exc:
                    return with_crc(bytes((unit, fc | 0x80, exc)))
                resp = with_crc(bytes((unit, fc, 2 * val)) + struct.pack(f">{val}H", *vals))
            elif fc == 6 and addr in dev.hold_range:
                dev.hold[addr] = val
                resp = req
            else:
                return with_crc(bytes((unit, fc | 0x80, 1)))
            if dev.faults.get("corrupt_once") or dev.faults.get("corrupt_always"):
                dev.faults["corrupt_once"] = False
                b = bytearray(resp)
                b[3] ^= 0x10
                resp = bytes(b)
            return resp

    def _serve(self):
        buf = b""
        while not self._stop:
            try:
                chunk = os.read(self.master_fd, 256)
            except OSError:
                time.sleep(0.001)
                continue
            buf += chunk
            while len(buf) >= 8:
                req, buf = buf[:8], buf[8:]
                resp = self._respond(req)
                if resp is None:
                    continue
                if self.char_time:
                    time.sleep((len(req) + len(resp)) * self.char_time + self.t35)
                os.write(self.master_fd, resp)
