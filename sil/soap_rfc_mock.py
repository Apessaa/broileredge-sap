"""MOCK of SAP's /sap/bc/soap/rfc endpoint for the three function modules of the kit (NOT SAP).

It parses the SOAP request the way the SAP service is documented to (function module name as the
body element, parameters as children), runs the same logic as sap_mock.py, and answers with a
'<FM>.Response' element. It behaves like PM mode: each escalation is a notification whose tasks are
returned by Z_BRL_STRESS_READ in ET_TASK, with the field names of table QMSM. Its purpose is to
test sap_soap.py and the middleware's SOAP path end to end before the authors point them at a real
SAP sandbox.

  python3 soap_rfc_mock.py --port 8001 --db sap.db --user TESTUSER --password secret
"""
import argparse
import base64
import json
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import sap_mock

NS_RFC = "urn:sap-com:document:sap:rfc:functions"
NS_ENV = "http://schemas.xmlsoap.org/soap/envelope/"


def local(tag):
    return tag.rsplit("}", 1)[-1]


def envelope(inner):
    return (f'<?xml version="1.0" encoding="utf-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="{NS_ENV}">'
            f'<SOAP-ENV:Body>{inner}</SOAP-ENV:Body></SOAP-ENV:Envelope>').encode()


def fault(msg):
    return envelope(f"<SOAP-ENV:Fault><faultcode>SOAP-ENV:Server</faultcode><faultstring>{escape(msg)}"
                    f"</faultstring></SOAP-ENV:Fault>")


def node(name, value):
    if isinstance(value, list):
        return f"<{name}>" + "".join(node("item", v) for v in value) + f"</{name}>"
    if isinstance(value, dict):
        return f"<{name}>" + "".join(node(k, v) for k, v in value.items()) + f"</{name}>"
    return f"<{name}>{escape(str(value))}</{name}>"


def response(fm, params):
    return envelope(f'<rfc:{fm}.Response xmlns:rfc="{NS_RFC}">' + "".join(node(k, v) for k, v in params.items())
                    + f"</rfc:{fm}.Response>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--user", default="TESTUSER")
    ap.add_argument("--password", default="secret")
    args = ap.parse_args()
    con = sap_mock.connect(args.db, "idem")
    lock = threading.Lock()
    expected = "Basic " + base64.b64encode(f"{args.user}:{args.password}".encode()).decode()

    def save(params):
        p = params["IS_ASSESS"]
        a = {"assessment_id": p["ASSESS_ID"], "flock": p["FLOCK"], "house": int(p["HOUSE"]),
             "worst_zone": int(p["ZONE"]), "ts": datetime.strptime(p["WINDOW_TS"], "%Y%m%d%H%M%S").isoformat(),
             "level": int(p["LEVEL_CODE"]), "cause": p.get("CAUSE", ""),
             "episode_start": 1 if p.get("EPISODE") == "X" else 0,
             "tasks": [p[k] for k in ("TASK1", "TASK2", "TASK3") if p.get(k)], "rule_version": p.get("RULE_VER", ""),
             "possible_cause": p.get("POSS_CAUSE", ""),
             # stored like the ZBRL_STRESS fields THI, NH3, CO2 and AIRDIAG (the house report reads them)
             "thi": float(p["THI"]) if p.get("THI") else None,
             "inputs": {k: float(p[k]) for k in ("NH3", "CO2") if p.get(k)},
             "air_speed_diag": p.get("AIRDIAG") == "X"}
        with lock:
            r = sap_mock.z_brl_stress_save(con, a, "idem")
        return {"EV_NOTIF": f"{r['notification']:012d}" if r["notification"] else "",
                "EV_STATUS": r["status"].upper(), "ES_RETURN": {"TYPE": "", "MESSAGE": ""}}

    def read(p):
        pat = p["IV_FLOCK_PREFIX"] + "%"
        with lock:
            notif_by = {t: n for n, t in con.execute("SELECT notif_id, trigger_id FROM notif")}
            st = []
            for aid, f, h, z, ts, lv, ep, t1, t2, t3, rv, pc, ca, pl in con.execute(
                    "SELECT assess_id, flock, house, zone, ts, level, episode, task1, task2, task3, rule_ver, "
                    "poss_cause, cause, payload FROM zbrl_stress WHERE flock LIKE ?", (pat,)):
                a = json.loads(pl)
                inp = a.get("inputs") or {}
                st.append({"ASSESS_ID": aid, "FLOCK": f, "HOUSE": f"{h:03d}", "ZONE": f"{z:02d}",
                           "WINDOW_TS": datetime.fromisoformat(ts).strftime("%Y%m%d%H%M%S"), "LEVEL_CODE": lv,
                           "EPISODE": "X" if ep else "", "TASK1": t1, "TASK2": t2, "TASK3": t3, "RULE_VER": rv,
                           "POSS_CAUSE": pc, "CAUSE": ca, "NOTIF_NO": f"{notif_by[aid]:012d}" if aid in notif_by else "",
                           "THI": f"{a['thi']:.2f}" if a.get("thi") is not None else "0.00",
                           "NH3": f"{inp.get('NH3', 0):.1f}", "CO2": str(int(inp.get("CO2", 0))),
                           "AIRDIAG": "X" if a.get("air_speed_diag") else ""})
            nt, tk = [], []
            for n, f, h, z, ts, t, t1, t2, t3 in con.execute(
                    "SELECT notif_id, flock, house, zone, ts, trigger_id, task1, task2, task3 FROM notif "
                    "WHERE flock LIKE ?", (pat,)):
                nt.append({"FLOCK": f, "HOUSE": f"{h:03d}", "ZONE": f"{z:02d}",
                           "NOTIF_TS": datetime.fromisoformat(ts).strftime("%Y%m%d%H%M%S"), "ASSESS_ID": t,
                           "QMNUM": f"{n:012d}", "NMODE": "PM"})
                for i, code in enumerate(c for c in (t1, t2, t3) if c):
                    tk.append({"QMNUM": f"{n:012d}", "MANUM": f"{i + 1:04d}", "MNGRP": "ZBRL", "MNCOD": code,
                               "ERLDAT": "", "ERLZEIT": "", "ERLNAM": ""})
        return {"ET_STRESS": st, "ET_NOTIF": nt, "ET_TASK": tk}

    def reset(p):
        pre = p["IV_FLOCK_PREFIX"]
        if len(pre) < 4 or not pre.startswith("TST"):
            return {"EV_DELETED": -1}
        with lock:
            n = con.execute("DELETE FROM zbrl_stress WHERE flock LIKE ?", (pre + "%",)).rowcount
            n += con.execute("DELETE FROM notif WHERE flock LIKE ?", (pre + "%",)).rowcount
        return {"EV_DELETED": n}

    handlers = {"Z_BRL_STRESS_SAVE": save, "Z_BRL_STRESS_READ": read, "Z_BRL_TEST_RESET": reset}

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not self.path.startswith("/sap/bc/soap/rfc"):
                return self._send(404, fault("service not active"))
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.headers.get("Authorization") != expected:
                return self._send(401, fault("logon failed"))
            try:
                root = ET.fromstring(data)
                body = next(e for e in root.iter() if local(e.tag) == "Body")
                call = list(body)[0]
                fm = local(call.tag)
                params = {}
                for k in call:
                    params[local(k.tag)] = {local(x.tag): (x.text or "") for x in k} if len(k) else (k.text or "")
                out = handlers[fm](params)
            except KeyError as e:
                return self._send(500, fault(f"function module or parameter not found: {e}"))
            except Exception as e:  # noqa: BLE001 - report anything else as a SOAP fault
                return self._send(500, fault(f"{type(e).__name__}: {e}"))
            self._send(200, response(fm, out))

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
