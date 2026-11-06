"""Client for SAP's SOAP interface to RFC-enabled function modules (ICF service /sap/bc/soap/rfc).

Why SOAP and not PyRFC: SAP archived PyRFC on 28 May 2026 ('no longer maintained'), and it needs the
licensed NW RFC SDK. The SOAP service ships with SAP NetWeaver AS ABAP, is activated in SICF and is
called over HTTP(S) with a user and password, so the middleware needs only the standard library.

Envelope: the body element is the function module name in namespace
urn:sap-com:document:sap:rfc:functions, parameters are child elements, TABLES parameters are sent as
empty elements and returned as <item> rows. The response element is read by local name
('<FM>.Response'), so namespace prefixes do not matter. Checked only against soap_rfc_mock.py here;
the first run against the sandbox must confirm the response format (see sap/TEST_PROTOCOL.md).
"""
import base64
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.sax.saxutils import escape

NS_RFC = "urn:sap-com:document:sap:rfc:functions"
NS_ENV = "http://schemas.xmlsoap.org/soap/envelope/"


class SapUnavailable(Exception):
    """Network, HTTP or SOAP-level failure: the call may or may not have run; retry later."""


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def build_envelope(fm, params, tables=()):
    def node(name, value):
        if isinstance(value, dict):
            return f"<{name}>" + "".join(node(k, v) for k, v in value.items()) + f"</{name}>"
        return f"<{name}>{escape(str(value))}</{name}>"
    body = "".join(node(k, v) for k, v in params.items()) + "".join(f"<{t}/>" for t in tables)
    return (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{NS_ENV}"><SOAP-ENV:Header/><SOAP-ENV:Body>'
            f'<urn:{fm} xmlns:urn="{NS_RFC}">{body}</urn:{fm}>'
            f'</SOAP-ENV:Body></SOAP-ENV:Envelope>').encode("utf-8")


def _to_py(el):
    kids = list(el)
    if not kids:
        return (el.text or "").strip()
    if all(_local(k.tag) == "item" for k in kids):
        return [_to_py(k) for k in kids]
    return {_local(k.tag): _to_py(k) for k in kids}


def parse_response(fm, xml_bytes):
    root = ET.fromstring(xml_bytes)
    body = next((e for e in root.iter() if _local(e.tag) == "Body"), None)
    if body is None:
        raise SapUnavailable("no SOAP body")
    for e in body:
        name = _local(e.tag)
        if name == "Fault":
            msg = " ".join(t.strip() for t in e.itertext() if t.strip())
            raise SapUnavailable(f"SOAP fault: {msg[:300]}")
        if name == f"{fm}.Response" or name.endswith(".Response"):
            return {_local(k.tag): _to_py(k) for k in e}
    raise SapUnavailable("no response element")


class SoapRfc:
    def __init__(self, url, user, password, timeout=10.0):
        self.url, self.timeout = url, timeout
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def call(self, fm, params, tables=()):
        req = urllib.request.Request(self.url, data=build_envelope(fm, params, tables), method="POST",
                                     headers={"Content-Type": "text/xml; charset=utf-8",
                                              "SOAPAction": f"{NS_RFC}:{fm}", "Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return parse_response(fm, resp.read())
        except urllib.error.HTTPError as e:
            data = e.read() if hasattr(e, "read") else b""
            if data:
                try:
                    parse_response(fm, data)
                except SapUnavailable as fault:
                    raise SapUnavailable(f"HTTP {e.code}: {fault}") from None
            raise SapUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError, ET.ParseError) as e:
            raise SapUnavailable(type(e).__name__) from None


def to_is_assess(a, func_loc=""):
    """StressAssessment (edge JSON) -> fields of DDIC structure ZBRL_S_ASSESS."""
    inp = a.get("inputs", {})
    num = lambda v, d: "" if v is None else f"{float(v):.{d}f}"
    t1, t2, t3 = (list(a.get("tasks") or []) + ["", "", ""])[:3]
    severe = a["level"] == 2
    episode = severe and bool(a.get("episode_start", 1))
    return {"ASSESS_ID": a["assessment_id"], "FLOCK": a["flock"][:20], "HOUSE": f"{int(a['house']):03d}",
            "ZONE": f"{int(a['worst_zone']):02d}",
            "WINDOW_TS": datetime.fromisoformat(a["ts"]).strftime("%Y%m%d%H%M%S"),
            "LEVEL_CODE": str(int(a["level"])), "CAUSE": str(a["cause"])[:30], "EPISODE": "X" if episode else "",
            "THI": num(a.get("thi"), 2), "TDB": num(inp.get("T"), 2), "RH": num(inp.get("RH"), 2),
            "CO2": "" if inp.get("CO2") is None else str(int(round(float(inp["CO2"])))),
            "NH3": num(inp.get("NH3"), 1), "AIRSPEED": num(inp.get("V"), 2),
            "THVI_NOTE": str(int(a.get("thvi_note") or 0)), "AIRDIAG": "X" if a.get("air_speed_diag") else "",
            "N_ZONES": str(int(a.get("n_zones", 0))), "FUNC_LOC": func_loc or a.get("func_loc", ""),
            "TASK1": t1, "TASK2": t2, "TASK3": t3, "RULE_VER": str(a.get("rule_version", ""))[:12],
            "POSS_CAUSE": str(a.get("possible_cause") or "")[:4]}


class SoapBackend:
    """Same contract as sap_mock.z_brl_stress_save: returns {"status", "notification"} or raises."""

    def __init__(self, url, user, password, func_loc_map=None, timeout=10.0):
        self.rfc = SoapRfc(url, user, password, timeout)
        self.func_loc_map = func_loc_map or {}

    def save(self, a):
        fl = self.func_loc_map.get(str(a["house"]), "")
        res = self.rfc.call("Z_BRL_STRESS_SAVE", {"IS_ASSESS": to_is_assess(a, fl)})
        status = (res.get("EV_STATUS") or "").upper()
        if status in ("STORED", "DUPLICATE"):
            return {"status": status.lower(), "notification": res.get("EV_NOTIF") or None}
        ret = res.get("ES_RETURN") or {}
        msg = ret.get("MESSAGE", "") if isinstance(ret, dict) else ""
        raise SapUnavailable(f"{status or 'no status'}: {msg}")

    def read_back(self, prefix):
        """Rows of ZBRL_STRESS and ZBRL_NOTIF for the prefix, and the PM tasks (QMSM) of its notifications."""
        res = self.rfc.call("Z_BRL_STRESS_READ", {"IV_FLOCK_PREFIX": prefix},
                            tables=("ET_STRESS", "ET_NOTIF", "ET_TASK"))
        as_list = lambda x: x if isinstance(x, list) else ([] if not x else [x])
        return as_list(res.get("ET_STRESS")), as_list(res.get("ET_NOTIF")), as_list(res.get("ET_TASK"))

    def reset(self, prefix):
        return int(self.rfc.call("Z_BRL_TEST_RESET", {"IV_FLOCK_PREFIX": prefix}).get("EV_DELETED") or 0)
