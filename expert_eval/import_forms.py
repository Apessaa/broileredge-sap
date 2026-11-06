"""Read filled expert forms (Form_Expert_Rating_ID.docx filled in Word or a similar editor) into responses.csv.

  python3 -I import_forms.py <folder with the filled .docx forms> <output responses.csv>

Filled forms are untrusted input: run this with python3 -I, from this folder, and pass the form folder as an argument.
The forms are read in file-name order and numbered R01, R02, ...; neither file names nor document properties (author,
last editor, dates) are written anywhere. Rename the files neutrally (01.docx, 02.docx, ...) before sending them.

Answers it reads
  Part A (items 1-20): the column (1-5 or TD) that carries a mark (any text such as a tick or an X, a highlight or a
    cell shading). No mark: blank. More than one: ambiguous (left blank, listed for checking against the form).
  Part B (conditions 1-9, ratings a-c): a cell left with one digit, or with one digit set apart by bold, highlight,
    underline, colour or shading, or with all other digits struck through, or one digit followed by a note in brackets
    (the note is shown to the authors, not written to the data). Anything else: ambiguous.
Consent, per form
  whether the consent box on page 1 is ticked (a tick, a cross or a filled box in place of or next to the empty box,
  or a highlight on the consent line). An unticked box is listed: the paper may state consent only as it was given.
Integrity report, per form
  every change to the text outside the answer cells (an added note, a changed statement, a removed line), compared with
  the blank form in this folder, apart from a tick in the consent box; and the program that last saved the file (as
  recorded in the file, without names).
A form with ambiguous answers or integrity changes is still written, with those cells blank; check it by hand.
"""
import csv
import difflib
import glob
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SPEC = json.load(open(os.path.join(HERE, "form_spec.json"), encoding="utf-8"))
BLANK = os.path.join(HERE, "Form_Expert_Rating_ID.docx")
SCALE_A = ["1", "2", "3", "4", "5", "TD"]          # Part A columns 3..8
PART_B_COLS = {4: "level", 5: "cause", 6: "tasks"}  # Part B columns
MAX_XML = 20 * 1024 * 1024


def load(path):
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > MAX_XML:
            raise ValueError("document.xml too large")
        doc = ET.fromstring(z.read("word/document.xml"))
        app = ""
        if "docProps/app.xml" in z.namelist():
            m = re.search(rb"<Application>([^<]{0,80})</Application>", z.read("docProps/app.xml"))
            app = m.group(1).decode("utf-8", "replace") if m else ""
    return doc, app


def text_of(el):
    return "".join(t.text or "" for t in el.iter(W + "t"))


def runs_of(cell):
    """(text, distinct formatting key) for each text run in a table cell."""
    out = []
    for r in cell.iter(W + "r"):
        txt = "".join(t.text or "" for t in r.iter(W + "t"))
        if not txt:
            continue
        rpr = r.find(W + "rPr")
        key = []
        if rpr is not None:
            for tag in ("b", "u", "highlight", "color", "shd", "strike", "dstrike"):
                e = rpr.find(W + tag)
                if e is not None and e.get(W + "val", "true") not in ("0", "false", "none", "auto", "000000"):
                    key.append(tag)
        out.append((txt, tuple(sorted(key))))
    return out


def cell_marked(cell):
    if text_of(cell).strip():
        return True
    tcpr = cell.find(W + "tcPr")
    shd = tcpr.find(W + "shd") if tcpr is not None else None
    if shd is not None and (shd.get(W + "fill") or "").upper() not in ("", "AUTO", "FFFFFF", "F2F2F2"):
        return True
    if any(True for _ in cell.iter(W + "highlight")) or any(True for _ in cell.iter(W + "drawing")):
        return True
    return any(el.tag.endswith("}pict") for el in cell.iter())


def part_b_value(cell):
    """Returns (value or None, note)."""
    txt = text_of(cell)
    if txt.strip() in ("", "–", "-"):
        return None, ""
    digits = [ch for ch in txt if ch in "12345"]
    marks = re.sub(r"[\s12345]", "", txt)
    if len(digits) == 1 and not marks:
        return digits[0], ""
    m = re.fullmatch(r"\s*([1-5])\s*[(\[]\s*([^0-9]*?)\s*[)\]]?\s*", txt)
    if m:   # one number followed by a note in brackets: the number is the answer, the note is shown to the authors
        return m.group(1), f"note: {m.group(2)[:60]}"
    if set(digits) == set("12345") and len(digits) == 5:
        runs = [(t, k) for t, k in runs_of(cell) if any(ch in "12345" for ch in t)]
        per_digit = []
        for t, k in runs:
            per_digit += [(ch, k) for ch in t if ch in "12345"]
        keys = [k for _, k in per_digit]
        common = max(set(keys), key=keys.count)
        odd = [ch for ch, k in per_digit if k != common]
        if len(odd) == 1 and not marks:
            return odd[0], ""
        struck = [ch for ch, k in per_digit if ("strike" in k or "dstrike" in k)]
        if len(struck) == 4:
            return next(ch for ch, _ in per_digit if ch not in struck), ""
        if any(True for _ in cell.iter(W + "drawing")) or any(el.tag.endswith("}pict") for el in cell.iter()):
            return None, "a drawn shape: read the form"
        if len(odd) == 0 and not marks:
            return None, ""          # untouched: blank
    return None, f"cannot read {txt.strip()[:30]!r}"


def tables(doc):
    return [t for t in doc.iter(W + "tbl")]


def rows(tbl):
    return [[c for c in tr.findall(W + "tc")] for tr in tbl.findall(W + "tr")]


CONSENT_KEYS = ("setuju untuk berpartisipasi", "agree to take part")
TICKS = set("☑☒✓✔✗✘■●xXvV")


def consent_ticked(doc):
    """True / False for the consent box on page 1; None if the consent line is not found."""
    for p in doc.iter(W + "p"):
        t = text_of(p)
        if any(k in t for k in CONSENT_KEYS):
            head = t.split("Saya")[0] if "Saya" in t else t.split("I have")[0]
            if any(ch in TICKS for ch in head):
                return True
            if "☐" not in head:          # the empty box was replaced by something else
                return bool(head.strip())
            if any(True for _ in p.iter(W + "highlight")) or any(True for _ in p.iter(W + "drawing")):
                return True
            return False
    return None


def outside_text(doc):
    """All text of the form outside the answer cells, as a list of lines (the consent line without its box)."""
    body = doc.find(W + "body")
    ts = tables(doc)
    answer_cells = set()
    for tbl in ts[1:3]:
        for r in rows(tbl)[1:]:
            answer_cells.update(id(c) for c in r[3:9])
    if len(ts) > 3:
        for r in rows(ts[3])[1:]:
            answer_cells.update(id(c) for c in r[4:7])
    out = []
    for el in body:
        if el.tag == W + "p":
            t = text_of(el).strip()
            if any(k in t for k in CONSENT_KEYS):
                t = "[consent line] " + t[t.index("Saya"):] if "Saya" in t else "[consent line] " + t[t.find("I have"):]
            if t:
                out.append(t)
        elif el.tag == W + "tbl":
            for r in rows(el):
                for c in r:
                    if id(c) not in answer_cells:
                        t = text_of(c).strip()
                        if t:
                            out.append(t)
    return out


def read_form(path, blank_lines):
    doc, app = load(path)
    ts = tables(doc)
    answers, issues, notes = {}, [], []
    if len(ts) != 4:
        return answers, [f"layout differs: {len(ts)} tables instead of 4"], app, None, notes, consent_ticked(doc)
    items = SPEC["items"]
    item_rows = rows(ts[1])[1:] + rows(ts[2])[1:]
    if len(item_rows) != len(items):
        issues.append(f"Part A has {len(item_rows)} rows instead of {len(items)}")
    for it, r in zip(items, item_rows):
        marked = [SCALE_A[i] for i, c in enumerate(r[3:9]) if cell_marked(c)]
        if len(marked) == 1:
            answers[it["id"]] = marked[0]
        elif len(marked) > 1:
            issues.append(f"item {it['number']} ({it['id']}): several columns marked {marked}")
    case_rows = rows(ts[3])[1:]
    if len(case_rows) != len(SPEC["cases"]):
        issues.append(f"Part B has {len(case_rows)} rows instead of {len(SPEC['cases'])}")
    for case, r in zip(SPEC["cases"], case_rows):
        for col, part in PART_B_COLS.items():
            if case["normal"] and part != "level":
                continue
            v, note = part_b_value(r[col])
            if v:
                answers[f"{case['case']}_{part}"] = v
                if note:
                    notes.append(f"Part B row {case['case'][1:]} ({part}) = {v}; {note}")
            elif note:
                issues.append(f"Part B row {case['case'][1:]} ({part}): {note}")
    diff = [d for d in difflib.unified_diff(blank_lines, outside_text(doc), lineterm="", n=0)
            if d[:1] in "+-" and not d.startswith(("+++", "---"))]
    return answers, issues, app, diff, notes, consent_ticked(doc)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    folder, out = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(folder, "*.docx")))
    if not files:
        print("no .docx forms in", folder)
        sys.exit(1)
    blank_doc, _ = load(BLANK)
    blank_lines = outside_text(blank_doc)
    cols = open(os.path.join(HERE, "responses_template.csv"), encoding="utf-8").read().strip().split(",")
    written, flagged, no_consent = [], 0, []
    for i, f in enumerate(files, 1):
        row_id = f"R{i:02d}"
        try:
            answers, issues, app, diff, notes, consent = read_form(f, blank_lines)
        except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as e:
            print(f"{row_id}: not read ({type(e).__name__}); type this form in by hand")
            flagged += 1
            continue
        row = {c: "" for c in cols}
        row["row"] = row_id
        row.update({k: v for k, v in answers.items() if k in row})
        written.append(row)
        filled = sum(1 for c in cols[1:] if row[c])
        print(f"{row_id}: {filled} of {len(cols) - 1} answers read; saved by: {app or '(no program recorded)'}; consent box: "
              + {True: "ticked", False: "NOT ticked", None: "not found"}[consent])
        if consent is not True:
            print("   check: the consent box is not ticked; record how this expert consented before the answers are used")
            no_consent.append(row_id)
        for s in issues:
            print("   check:", s)
        for s in notes:
            print("   read with a note (the number is the answer; the note is not written to the data):", s)
        if diff:
            print(f"   integrity: the text outside the answer cells differs from the blank form ({len(diff)} lines):")
            for d in diff[:8]:
                print("     ", d[:110])
        if issues or diff or diff is None or consent is not True:
            flagged += 1
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(written)
    print(f"\n{len(written)} forms written to {out}; {flagged} need a look (see 'check' and 'integrity' above).")
    if no_consent:
        print(f"Consent box not ticked on {len(no_consent)} form(s): {', '.join(no_consent)}.")
    print("Next: python3 check_responses.py", out)


if __name__ == "__main__":
    main()
