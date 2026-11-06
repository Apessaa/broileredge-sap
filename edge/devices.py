"""Register maps and decoders of the three planned sensors, taken from the manufacturers' documents.

  ODMHM-R   Sentera, 'ODMHM-R Modbus register map', MBRM-ODMHM-R-EN-000, 17 Jan 2023.
            Input registers 1-50 (FC04), holding registers 1-70 (FC03/FC06). Factory default:
            address 1, 19200 baud (HR2=2), 8E1 (HR3=1); CO2 self-calibration on (HR40=1).
  S-NH3-01  Seeed Studio, 'NH3 sensor datasheet, module S-NH3-01', V1.1, May 2023.
            Holding registers (FC03): 0x2000-0x2001 NH3 float32 (ppm), 0x2004 T x100, 0x2006 RH x100,
            0x2008 max range. 9600 baud 8N1; no documented way to change the baud rate.
  HD53LS.S  Senseca (Delta OHM), 'HD53LS series ultrasonic anemometers: operating manual', V1.5.
            Input registers (FC04): 0 instantaneous speed x100, 10 average speed x100, 15/16 V/U x100,
            17 status (bit0 = speed measurement error), 18 unit (0 = m/s). Default address 1,
            19200 baud, 8E1 (serial commands CU5A/CU5B/CU5M); Modbus active 10 s after power-up.

The bus can only run at one speed and frame format. Because the NH3 sensor is fixed at 9600 8N1, the
ODMHM-R (HR2=1, HR3=0) and the HD53LS.S (CU5B3, CU5M0) must be reconfigured to 9600 8N1 before
installation (see commission.py and the bench protocol).

Two points the documents leave open and the commissioning step checks on the real devices:
  * Sentera numbers registers from 1. Whether register N is protocol address N-1 (the usual Modbus
    convention, the default here) or N is set by ODMHM_OFFSET; commission.py tells them apart by reading
    the device-type register (HR4 = 1712).
  * Whether the HD53LS.S answers one block read over the undocumented gaps (registers 2-7, 9, 12-13).
    If it answers with exception 02, the driver falls back to reading registers 0, 10 and 17 singly.
"""
import struct

ODMHM_OFFSET = -1  # protocol address = register number + offset


def s16(v):
    return v - 0x10000 if v >= 0x8000 else v


class Device:
    model = ""
    quantities = ()
    ranges = {}

    def __init__(self, unit, zone):
        self.unit = unit
        self.zone = zone
        self.mode = "block"

    def reads(self):
        """List of (fc, address, count) requests for one poll."""
        return [self.block] if self.mode == "block" else list(self.singles)

    def decode(self, regs):
        """regs: dict protocol address -> raw 16-bit value. Returns (values, faults)."""
        raise NotImplementedError


class OdmhmR(Device):
    model = "ODMHM-R"
    quantities = ("T", "RH", "CO2")
    ranges = {"T": (-30.0, 70.0), "RH": (0.0, 100.0), "CO2": (0.0, 10000.0)}

    def __init__(self, unit, zone, offset=ODMHM_OFFSET):
        super().__init__(unit, zone)
        self.offset = offset
        self.block = (4, 1 + offset, 25)  # input registers 1..25
        self.singles = [(4, 1 + offset, 1), (4, 5 + offset, 1), (4, 10 + offset, 1), (4, 14 + offset, 1),
                        (4, 21 + offset, 1), (4, 25 + offset, 1)]

    def ir(self, regs, n):
        return regs[n + self.offset]

    def decode(self, regs):
        values = {"T": s16(self.ir(regs, 1)) / 10.0, "RH": self.ir(regs, 10) / 10.0,
                  "CO2": float(self.ir(regs, 21))}
        th_fault = bool(self.ir(regs, 5)) or bool(self.ir(regs, 14))
        faults = {"T": th_fault, "RH": bool(self.ir(regs, 14)), "CO2": bool(self.ir(regs, 25))}
        return values, faults

    @staticmethod
    def encode(t, rh, co2, fault_t=0, fault_rh=0, fault_co2=0):
        """Inverse of decode, as register number -> raw value (used by the emulator)."""
        return {1: round(t * 10) & 0xFFFF, 5: fault_t, 10: round(rh * 10), 14: fault_rh,
                21: round(co2), 25: fault_co2}


class SNH301(Device):
    model = "S-NH3-01"
    quantities = ("NH3",)
    ranges = {"NH3": (0.0, 100.0)}
    warmup_s = 300  # 5 min typical (datasheet)

    def __init__(self, unit, zone):
        super().__init__(unit, zone)
        self.block = (3, 0x2000, 2)
        self.singles = [(3, 0x2000, 2)]

    def decode(self, regs):
        raw = struct.pack(">HH", regs[0x2000], regs[0x2001])
        nh3 = struct.unpack(">f", raw)[0]
        return {"NH3": round(nh3, 1)}, {"NH3": False}  # datasheet resolution 0.1 ppm

    @staticmethod
    def encode(nh3):
        hi, lo = struct.unpack(">HH", struct.pack(">f", nh3))
        return {0x2000: hi, 0x2001: lo}


class HD53LSS(Device):
    model = "HD53LS.S"
    quantities = ("V",)
    ranges = {"V": (0.0, 50.0)}
    warmup_s = 10  # Modbus active 10 s after power-up

    def __init__(self, unit, zone):
        super().__init__(unit, zone)
        self.block = (4, 0, 18)
        self.singles = [(4, 0, 1), (4, 10, 1), (4, 17, 1)]

    def decode(self, regs):
        return {"V": regs[0] / 100.0, "V_avg": regs[10] / 100.0}, {"V": bool(regs[17] & 1)}

    @staticmethod
    def encode(v, status=0):
        return {0: round(v * 100), 10: round(v * 100), 17: status, 18: 0}


MODELS = {c.model: c for c in (OdmhmR, SNH301, HD53LSS)}


def from_config(entries):
    """entries: list of dicts {model, unit, zone}."""
    return [MODELS[e["model"]](e["unit"], e["zone"]) for e in entries]
