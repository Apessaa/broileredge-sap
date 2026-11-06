"""Minimal Modbus RTU master for Linux serial ports, using only the Python standard library.

Implements what the edge node needs from 'MODBUS over Serial Line V1.02' (Modbus Organization, 2006):
function codes 03 (read holding registers), 04 (read input registers) and 06 (write single register),
CRC-16 (polynomial 0xA001, low byte first), exception responses, and the 3.5-character silent
interval between frames (fixed 1.75 ms above 19200 baud, as the specification recommends).

Why no pymodbus here: this file has no third-party dependency, so it can be read in one sitting and
was tested in full against emulated devices (tests/). pymodbus can replace it on the device if the
authors prefer; the device classes in devices.py only need read_registers().
"""
import os
import select
import struct
import termios
import time

BAUD = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800, 9600: termios.B9600,
        19200: termios.B19200, 38400: termios.B38400, 57600: termios.B57600, 115200: termios.B115200}


# ---------------------------------------------------------------- frames
def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def add_crc(frame):
    c = crc16(frame)
    return bytes(frame) + bytes((c & 0xFF, c >> 8))


def crc_ok(frame):
    return len(frame) >= 4 and crc16(frame[:-2]) == (frame[-2] | (frame[-1] << 8))


def read_request(unit, fc, address, count):
    if fc not in (3, 4) or not 1 <= count <= 125:
        raise ValueError("only FC03/FC04 with 1..125 registers")
    return add_crc(struct.pack(">BBHH", unit, fc, address, count))


def write_single_request(unit, address, value):
    return add_crc(struct.pack(">BBHH", unit, 6, address, value & 0xFFFF))


class ModbusError(Exception):
    kind = "error"


class NoResponse(ModbusError):
    kind = "timeout"


class CRCError(ModbusError):
    kind = "crc"


class FrameError(ModbusError):
    kind = "frame"


class ExceptionResponse(ModbusError):
    kind = "exception"

    def __init__(self, code):
        super().__init__(f"exception code {code}")
        self.code = code


def parse_read_response(unit, fc, count, frame):
    """Return the register values of a FC03/FC04 response or raise a ModbusError."""
    if not frame:
        raise NoResponse("no response")
    if len(frame) >= 5 and frame[1] == (fc | 0x80):
        if not crc_ok(frame[:5]):
            raise CRCError("bad CRC in exception response")
        raise ExceptionResponse(frame[2])
    need = 5 + 2 * count
    if len(frame) < need:
        if len(frame) >= 4 and not crc_ok(frame):
            raise CRCError(f"short frame with bad CRC ({len(frame)} of {need} bytes)")
        raise FrameError(f"short frame ({len(frame)} of {need} bytes)")
    frame = frame[:need]
    if not crc_ok(frame):
        raise CRCError("bad CRC")
    if frame[0] != unit or frame[1] != fc or frame[2] != 2 * count:
        raise FrameError("unexpected address, function or byte count")
    return list(struct.unpack(f">{count}H", frame[3:3 + 2 * count]))


# ---------------------------------------------------------------- serial line
class SerialLine:
    """Raw Linux serial port (e.g. /dev/ttyUSB0 of a USB-RS485 adapter, or a pty in the tests)."""

    def __init__(self, path, baud=9600, parity="N", stopbits=1, timeout=0.5):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
        if parity == "E":
            cflag |= termios.PARENB
        elif parity == "O":
            cflag |= termios.PARENB | termios.PARODD
        if stopbits == 2:
            cflag |= termios.CSTOPB
        cc = attrs[6]
        cc[termios.VMIN], cc[termios.VTIME] = 0, 0
        termios.tcsetattr(self.fd, termios.TCSANOW, [0, 0, cflag, 0, BAUD[baud], BAUD[baud], cc])
        bits = 1 + 8 + (parity != "N") + stopbits
        self.char_time = bits / baud
        self.t35 = 3.5 * self.char_time if baud <= 19200 else 0.00175
        self.timeout = timeout
        self._idle_since = 0.0

    def close(self):
        os.close(self.fd)

    def transact(self, request, expected_len):
        """Send one request and return the raw response bytes (possibly empty or partial)."""
        wait = self._idle_since + self.t35 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        termios.tcflush(self.fd, termios.TCIFLUSH)  # discard late bytes of an earlier frame
        os.write(self.fd, request)
        termios.tcdrain(self.fd)
        deadline = time.monotonic() + self.timeout + expected_len * self.char_time
        buf = b""
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            r, _, _ = select.select([self.fd], [], [], left)
            if not r:
                break
            try:
                buf += os.read(self.fd, 512)
            except BlockingIOError:
                continue
            if len(buf) >= expected_len:
                break
            if len(buf) >= 5 and buf[1] & 0x80:  # exception response is 5 bytes
                break
        self._idle_since = time.monotonic()
        return buf


# ---------------------------------------------------------------- master
class Master:
    """Request/response with one retry on CRC, frame or timeout errors (not on exception responses)."""

    def __init__(self, line, retries=1):
        self.line = line
        self.retries = retries
        self.stats = {"requests": 0, "retries": 0, "timeout": 0, "crc": 0, "frame": 0, "exception": 0}

    def read_registers(self, unit, fc, address, count):
        req = read_request(unit, fc, address, count)
        last = None
        for attempt in range(self.retries + 1):
            self.stats["requests"] += 1
            if attempt:
                self.stats["retries"] += 1
            raw = self.line.transact(req, 5 + 2 * count)
            try:
                return parse_read_response(unit, fc, count, raw)
            except ExceptionResponse as e:
                self.stats["exception"] += 1
                raise e
            except ModbusError as e:
                self.stats[e.kind] += 1
                last = e
        raise last

    def write_register(self, unit, address, value):
        req = write_single_request(unit, address, value)
        raw = self.line.transact(req, 8)
        if len(raw) >= 5 and raw[1] == 0x86:
            raise ExceptionResponse(raw[2])
        if raw[:8] != req:
            raise FrameError("write not echoed")
        return True
