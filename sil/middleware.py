"""REST middleware of the prototype: receives StressAssessment JSON and calls the (mock) SAP function.

Fault injection for software-in-the-loop tests (all decided per request with a seeded RNG):
  p503   respond 503 without calling SAP (SAP or network unavailable)
  plost  call SAP (committed), then drop the connection without a response (lost acknowledgement)
  pslow  call SAP (committed), then answer only after the client's timeout has expired
Every injected fault is appended to an events file so that the test harness can count them.

Backends: "mock" calls sap_mock.py in-process (v14 test); "soap" calls Z_BRL_STRESS_SAVE in an SAP
system (or in soap_rfc_mock.py) through /sap/bc/soap/rfc. The SAP password is read from the
environment variable SAP_PASSWORD, never from the command line.
"""
import argparse
import json
import random
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import os

import sap_mock
from sap_soap import SapUnavailable, SoapBackend

REQUIRED = ("assessment_id", "flock", "house", "worst_zone", "ts", "level", "cause")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--mode", choices=("idem", "naive"), default="idem")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--p503", type=float, default=0.15)
    ap.add_argument("--plost", type=float, default=0.10)
    ap.add_argument("--pslow", type=float, default=0.05)
    ap.add_argument("--slow-s", type=float, default=1.5)
    ap.add_argument("--events", required=True)
    ap.add_argument("--backend", choices=("mock", "soap"), default="mock")
    ap.add_argument("--sap-url", default="")
    ap.add_argument("--sap-user", default="")
    ap.add_argument("--sap-timeout", type=float, default=10.0)
    ap.add_argument("--func-loc-map", default="", help="JSON file: house number -> functional location")
    args = ap.parse_args()
    backend = None
    if args.backend == "soap":
        flmap = json.load(open(args.func_loc_map)) if args.func_loc_map else {}
        backend = SoapBackend(args.sap_url, args.sap_user, os.environ.get("SAP_PASSWORD", ""), flmap,
                              args.sap_timeout)

    rng = random.Random(args.seed * 7919)
    lock = threading.Lock()
    con = sap_mock.connect(args.db, args.mode) if backend is None else None
    ev = open(args.events, "a", buffering=1)

    def log(kind, aid=None):
        ev.write(json.dumps({"t": time.time(), "kind": kind, "id": aid}) + "\n")

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # silence default logging
            pass

        def _reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/assessments":
                return self._reply(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length", "0"))
            try:
                a = json.loads(self.rfile.read(n))
                assert all(k in a for k in REQUIRED)
            except Exception:
                log("bad_request")
                return self._reply(400, {"error": "invalid assessment"})
            with lock:
                r = rng.random()
            if r < args.p503:
                log("injected_503", a["assessment_id"])
                return self._reply(503, {"error": "SAP unavailable"})
            if backend is None:
                with lock:
                    res = sap_mock.z_brl_stress_save(con, a, args.mode)
            else:
                try:
                    res = backend.save(a)  # concurrent calls allowed: SAP serialises per house (enqueue)
                except SapUnavailable as e:
                    log("sap_unavailable", a["assessment_id"])
                    return self._reply(503, {"error": str(e)[:200]})
            log("sap_" + res["status"], a["assessment_id"])
            if res["notification"]:
                log("notification", a["assessment_id"])
            if r < args.p503 + args.plost:
                log("injected_lost_ack", a["assessment_id"])
                try:  # reset the connection: the client never sees the acknowledgement
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    self.connection.close()
                except OSError:
                    pass
                self.close_connection = True
                return
            if r < args.p503 + args.plost + args.pslow:
                log("injected_slow", a["assessment_id"])
                time.sleep(args.slow_s)
            try:
                self._reply(200, res)
            except OSError:
                pass

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    srv.daemon_threads = True
    log("start")
    srv.serve_forever()


if __name__ == "__main__":
    main()
