"""Builds sap/offstack/: the ABAP sources of sap/abap in abapGit file layout, with the dictionary
objects (from the field lists of SAP_KIT.md section 2) and the configuration to check and run them on
a PC without SAP:
  * abaplint (static check of all objects against ABAP 7.02 syntax),
  * the abaplint transpiler with the open-abap runtime (runs the ABAP Unit tests of
    ZCL_BRL_HOUSE_REPORT in Node.js).
Neither tool could be run where this kit was written (the npm registry was not reachable from that
environment), so the configuration has not been tried. Usage (from kit/): python3 sap/tools/make_offstack.py
"""
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SAP = os.path.dirname(HERE)
ABAP = os.path.join(SAP, "abap")
OUT = os.path.join(SAP, "offstack")
SRC = os.path.join(OUT, "src")

HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n<abapGit version="v1.0.0" serializer="LCL_OBJECT_{t}" '
        'serializer_version="v1.0.0">\n <asx:abap xmlns:asx="http://www.sap.com/abapxml" version="1.0">\n'
        '  <asx:values>')
TAIL = '  </asx:values>\n </asx:abap>\n</abapGit>\n'

# field, data type, length, decimals, data element (SAP_KIT.md 2.1); a data element replaces the type
ASSESS = [("ASSESS_ID", "CHAR", 36, 0), ("FLOCK", "CHAR", 20, 0), ("HOUSE", "NUMC", 3, 0), ("ZONE", "NUMC", 2, 0),
          ("WINDOW_TS", "DEC", 15, 0), ("LEVEL_CODE", "INT1", 3, 0), ("CAUSE", "CHAR", 30, 0), ("EPISODE", "CHAR", 1, 0),
          ("THI", "DEC", 5, 2), ("TDB", "DEC", 5, 2), ("RH", "DEC", 5, 2), ("CO2", "INT4", 10, 0), ("NH3", "DEC", 5, 1),
          ("AIRSPEED", "DEC", 5, 2), ("THVI_NOTE", "INT1", 3, 0), ("AIRDIAG", "CHAR", 1, 0), ("N_ZONES", "INT1", 3, 0),
          ("FUNC_LOC", "CHAR", 40, 0), ("TASK1", "CHAR", 4, 0), ("TASK2", "CHAR", 4, 0), ("TASK3", "CHAR", 4, 0),
          ("RULE_VER", "CHAR", 12, 0), ("POSS_CAUSE", "CHAR", 4, 0)]
INT = {"CHAR": ("C", 2), "NUMC": ("N", 2), "INT1": ("b", 0), "INT4": ("X", 0)}


def field(name, dtype=None, leng=0, dec=0, rollname=None, key=False):
    x = ["    <DD03P>", f"     <FIELDNAME>{name}</FIELDNAME>"]
    if key:
        x.append("     <KEYFLAG>X</KEYFLAG>")
    if rollname:
        x += [f"     <ROLLNAME>{rollname}</ROLLNAME>", "     <ADMINFIELD>0</ADMINFIELD>"]
        if key:
            x.append("     <NOTNULL>X</NOTNULL>")
        x.append("     <COMPTYPE>E</COMPTYPE>")
    else:
        if dtype == "DEC":
            inttype, intlen = "P", leng // 2 + 1
        elif dtype in ("INT1", "INT4"):
            inttype, intlen = INT[dtype][0], 1 if dtype == "INT1" else 4
        else:
            inttype, intlen = INT[dtype][0], INT[dtype][1] * leng
        x += ["     <ADMINFIELD>0</ADMINFIELD>", f"     <INTTYPE>{inttype}</INTTYPE>", f"     <INTLEN>{intlen:06d}</INTLEN>"]
        if key:
            x.append("     <NOTNULL>X</NOTNULL>")
        x += [f"     <DATATYPE>{dtype}</DATATYPE>", f"     <LENG>{leng:06d}</LENG>"]
        if dec:
            x.append(f"     <DECIMALS>{dec:06d}</DECIMALS>")
        x.append(f"     <MASK>  {dtype}</MASK>")
    x.append("    </DD03P>")
    return "\n".join(x)


def tabl(name, text, tabclass, fields):
    x = [HEAD.format(t="TABL"), "   <DD02V>", f"    <TABNAME>{name}</TABNAME>", "    <DDLANGUAGE>E</DDLANGUAGE>",
         f"    <TABCLASS>{tabclass}</TABCLASS>", f"    <DDTEXT>{text}</DDTEXT>"]
    if tabclass == "TRANSP":
        x += ["    <CONTFLAG>A</CONTFLAG>"]
    x += ["    <EXCLASS>1</EXCLASS>", "   </DD02V>"]
    if tabclass == "TRANSP":
        x += ["   <DD09L>", f"    <TABNAME>{name}</TABNAME>", "    <AS4LOCAL>A</AS4LOCAL>", "    <TABKAT>0</TABKAT>",
              "    <TABART>APPL1</TABART>", "    <BUFALLOW>N</BUFALLOW>", "   </DD09L>"]
    x += ["   <DD03P_TABLE>"] + fields + ["   </DD03P_TABLE>", TAIL]
    return "\n".join(x)


def interface(src):
    """Parameters from the '*"' interface comment of a function module source."""
    params, section = [], None
    for line in src.splitlines():
        m = re.match(r'\*"\s+(IMPORTING|EXPORTING|TABLES|CHANGING)\s*$', line)
        if m:
            section = m.group(1)
            continue
        m = re.match(r'\*"\s+(?:VALUE\((\w+)\)|(\w+))\s+(TYPE|STRUCTURE)\s+(\w+)(\s+OPTIONAL)?', line)
        if m and section:
            params.append((section, m.group(1) or m.group(2), m.group(4), bool(m.group(5))))
    return params


def fm_xml(name, text, src, kind):
    x = ["    <item>", f"     <FUNCNAME>{name}</FUNCNAME>"]
    if kind == "rfc":
        x.append("     <REMOTE_CALL>R</REMOTE_CALL>")
    if kind == "update":
        x.append("     <UPDATE_TASK>1</UPDATE_TASK>")
    x.append(f"     <SHORT_TEXT>{text}</SHORT_TEXT>")
    groups = {"IMPORTING": ("IMPORT", "RSIMP"), "EXPORTING": ("EXPORT", "RSEXP"), "TABLES": ("TABLES", "RSTBL")}
    params = interface(src)
    for sec, (tag, item) in groups.items():
        ps = [p for p in params if p[0] == sec]
        if not ps:
            continue
        x.append(f"     <{tag}>")
        for _, pname, typ, opt in ps:
            x += [f"      <{item}>", f"       <PARAMETER>{pname}</PARAMETER>"]
            x.append(f"       <DBSTRUCT>{typ}</DBSTRUCT>" if sec == "TABLES" else f"       <TYP>{typ}</TYP>")
            if opt:
                x.append("       <OPTIONAL>X</OPTIONAL>")
            x.append(f"      </{item}>")
        x.append(f"     </{tag}>")
    x.append("    </item>")
    return "\n".join(x), params


def progdir(name, subc):
    return "\n".join([HEAD.format(t="FUGR" if subc in ("I", "F") else "PROG"), "   <PROGDIR>", f"    <NAME>{name}</NAME>",
                      f"    <SUBC>{subc}</SUBC>", "    <FIXPT>X</FIXPT>", "    <UCCHECK>X</UCCHECK>", "   </PROGDIR>"])


def main():
    if os.path.isdir(SRC):
        shutil.rmtree(SRC)
    os.makedirs(SRC)
    w = lambda fn, txt: open(os.path.join(SRC, fn), "w", newline="\n").write(txt)
    rd = lambda fn: open(os.path.join(ABAP, fn)).read()

    # dictionary
    w("zbrl_s_assess.tabl.xml", tabl("ZBRL_S_ASSESS", "Broiler stress assessment (interface)", "INTTAB",
                                     [field(*f) for f in ASSESS]))
    stress = [field("MANDT", rollname="MANDT", key=True), field("ASSESS_ID", "CHAR", 36, key=True)]
    stress += [field(*f) for f in ASSESS[1:]]
    stress += [field("NOTIF_NO", rollname="QMNUM"), field("CREATED_AT", rollname="TIMESTAMP"),
               field("CREATED_BY", rollname="SYUNAME")]
    w("zbrl_stress.tabl.xml", tabl("ZBRL_STRESS", "Broiler stress assessments", "TRANSP", stress))
    notif = [field("MANDT", rollname="MANDT", key=True), field("FLOCK", "CHAR", 20, key=True),
             field("HOUSE", "NUMC", 3, key=True), field("ZONE", "NUMC", 2, key=True),
             field("NOTIF_TS", rollname="TIMESTAMP", key=True), field("ASSESS_ID", "CHAR", 36),
             field("QMNUM", rollname="QMNUM"), field("NMODE", "CHAR", 4), field("CREATED_AT", rollname="TIMESTAMP")]
    w("zbrl_notif.tabl.xml", tabl("ZBRL_NOTIF", "Broiler stress escalation log", "TRANSP", notif))

    # function group
    fms = [("Z_BRL_STRESS_SAVE", "Store one stress assessment exactly once", "rfc"),
           ("Z_BRL_STRESS_POST", "Update module: insert row and log", "update"),
           ("Z_BRL_STRESS_READ", "Test read-back of TST flocks", "rfc"),
           ("Z_BRL_TEST_RESET", "Delete rows of TST flocks", "rfc")]
    items, n_params = [], {}
    for name, text, kind in fms:
        src = rd(f"{name}.abap")
        xml, params = fm_xml(name, text, src, kind)
        items.append(xml)
        n_params[name] = len(params)
        w(f"zbrl_fg.fugr.{name.lower()}.abap", src)
    w("zbrl_fg.fugr.xml", "\n".join([HEAD.format(t="FUGR"), "   <AREAT>Broiler stress assessments</AREAT>",
                                      "   <INCLUDES>", "    <SOBJ_NAME>LZBRL_FGTOP</SOBJ_NAME>",
                                      "    <SOBJ_NAME>SAPLZBRL_FG</SOBJ_NAME>", "   </INCLUDES>", "   <FUNCTIONS>"]
                                     + items + ["   </FUNCTIONS>", TAIL]))
    w("zbrl_fg.fugr.lzbrl_fgtop.abap", "FUNCTION-POOL zbrl_fg.\n")
    w("zbrl_fg.fugr.lzbrl_fgtop.xml", progdir("LZBRL_FGTOP", "I") + "\n" + TAIL)
    w("zbrl_fg.fugr.saplzbrl_fg.abap", "INCLUDE lzbrl_fgtop.\nINCLUDE lzbrl_fguxx.\n")
    w("zbrl_fg.fugr.saplzbrl_fg.xml", progdir("SAPLZBRL_FG", "F") + "\n" + TAIL)

    # class with unit tests
    w("zcl_brl_house_report.clas.abap", rd("ZCL_BRL_HOUSE_REPORT.abap"))
    w("zcl_brl_house_report.clas.testclasses.abap", rd("ZCL_BRL_HOUSE_REPORT.testclasses.abap"))
    w("zcl_brl_house_report.clas.xml", "\n".join([
        HEAD.format(t="CLAS"), "   <VSEOCLASS>", "    <CLSNAME>ZCL_BRL_HOUSE_REPORT</CLSNAME>", "    <LANGU>E</LANGU>",
        "    <DESCRIPT>Broiler house report: logic</DESCRIPT>", "    <STATE>1</STATE>", "    <CLSCCINCL>X</CLSCCINCL>",
        "    <FIXPT>X</FIXPT>", "    <UNICODE>X</UNICODE>", "    <WITH_UNIT_TESTS>X</WITH_UNIT_TESTS>", "   </VSEOCLASS>", TAIL]))

    # report program with its selection texts
    w("z_brl_house_report.prog.abap", rd("Z_BRL_HOUSE_REPORT.abap"))
    texts = [("R", "", "Daily broiler house report"), ("S", "S_FLOCK", "Flock"), ("S", "S_HOUSE", "House"),
             ("S", "P_DAYS", "Report period (days)"), ("S", "P_NDAYS", "Notifications of the last (days)"),
             ("S", "P_INTV", "Window length (s)")]
    tp = ["   <TPOOL>"]
    for i, k, e in texts:
        entry = e if i == "R" else " " * 8 + e
        tp += ["    <item>", f"     <ID>{i}</ID>"] + ([f"     <KEY>{k}</KEY>"] if k else []) + \
              [f"     <ENTRY>{entry}</ENTRY>", f"     <LENGTH>{len(entry)}</LENGTH>", "    </item>"]
    tp.append("   </TPOOL>")
    w("z_brl_house_report.prog.xml", progdir("Z_BRL_HOUSE_REPORT", "1") + "\n" + "\n".join(tp) + "\n" + TAIL)

    # configuration
    abaplint = {
        "global": {"files": "/src/**/*.*", "exclude": [], "noIssues": []},
        "dependencies": [],
        "syntax": {"version": "v702", "errorNamespace": "^(Z|Y|LCL_|TY_|LIF_|LTCL_)"},
        "rules": {"parser_error": True, "check_syntax": True, "unknown_types": True, "check_include": True,
                  "unused_variables": True, "unused_types": True, "keyword_case": False, "line_length": False},
    }
    json.dump(abaplint, open(os.path.join(OUT, "abaplint.json"), "w"), indent=2)
    transpile = {
        "input_folder": "src",
        "input_filter": ["zcl_brl_house_report"],
        "output_folder": "output",
        "libs": [{"url": "https://github.com/open-abap/open-abap-core", "folder": "/src"}],
        "write_unit_tests": True,
        "write_source_map": True,
        "options": {"ignoreSyntaxCheck": False, "addFilenames": True, "addCommonJS": True, "unknownTypes": "runtimeError"},
    }
    json.dump(transpile, open(os.path.join(OUT, "abap_transpile.json"), "w"), indent=2)
    package = {
        "name": "zbrl-offstack-abap-check", "version": "1.0.0", "private": True,
        "description": "abaplint (ABAP 7.02) and ABAP Unit via the abaplint transpiler for the broiler-house kit",
        "scripts": {
            "lint": "abaplint abaplint.json",
            "clean": "node -e \"require('fs').rmSync('output',{recursive:true,force:true})\"",
            "unit": "npm run clean && abap_transpile abap_transpile.json && node output/index.mjs",
            "test": "npm run lint && npm run unit",
        },
        "devDependencies": {"@abaplint/cli": "^2.100.0", "@abaplint/transpiler-cli": "^2.10.0",
                            "@abaplint/runtime": "^2.10.0"},
    }
    json.dump(package, open(os.path.join(OUT, "package.json"), "w"), indent=2)
    print("written:", sorted(os.listdir(SRC)), "parameters per function module:", n_params)


if __name__ == "__main__":
    main()
