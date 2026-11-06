"""Analysis of the expert rating form (Form_Expert_Rating_ID.docx; items and cases in form_spec.json).

  python3 analyse_expert.py responses.csv      -> results_expert.json and results_expert.md (next to responses.csv)
  python3 analyse_expert.py --selftest         -> checks the statistics on made-up inputs (not data!)

responses.csv: one row per expert, typed from the anonymous forms (template: responses_template.csv).
  row                 running number R01, R02, ... given at data entry; the form carries no code and asks
                      nothing about the expert
  R1..R7, T1..T5, CHK, S1..S5, G1, G2   Part A items 1..20 in form order: 1..5 or TD (cannot judge)
  C1_level, C1_cause, C1_tasks, ...     Part B, case 1..9 (form_spec.json): 1..5; Normal cases have only _level

Rules fixed before the data are collected (PROTOCOL.md section 4):
  primary analysis: every answer 1..5, TD excluded (experts choose TD for items outside their field; the
  form's Domain column shows who can best judge each item). Sensitivity: experts who passed the attention
  check only (CHK 1 or 2; CHK is reported, never analysed as an item).
  per item: n, TD count, median, IQR, I-CVI (share 4-5) with a Clopper-Pearson 95% CI, modified kappa
  (Polit, Beck & Owen 2007), Aiken's V (Aiken 1985), a_wg (Brown & Hauenstein 2005; for n >= 4).
  decision: n < 3 -> too few raters; kappa* < 0.60 or median <= 3 -> review; I-CVI meeting Lynn's rule (no
  disagreement for n <= 5, at most one for n >= 6) and median >= 4 and IQR <= 1 -> accept; otherwise revise.
  T5 and S5 are risk statements: reported as they are (4-5 = the expert sees the risk), with no decision.
"""
import csv
import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "form_spec.json"), encoding="utf-8"))
ITEMS = [i for i in SPEC["items"] if not i["attention_check"]]
CASES = SPEC["cases"]
VALID = {"1", "2", "3", "4", "5"}


# ---------------------------------------------------------------- statistics
def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(x, n, alpha=0.05):
    """Exact 95% CI for x successes in n trials (bisection on the binomial tail)."""
    if n == 0:
        return (None, None)

    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    lower = 0.0 if x == 0 else solve(lambda p: 1 - binom_cdf(x - 1, n, p) >= alpha / 2)
    upper = 1.0 if x == n else solve(lambda p: binom_cdf(x, n, p) <= alpha / 2)
    return (lower, upper)


def modified_kappa(agree, n):
    """Polit, Beck & Owen (2007): kappa* = (I-CVI - pc) / (1 - pc), pc = C(n, A) 0.5^n."""
    if n == 0:
        return None
    pc = math.comb(n, agree) * 0.5 ** n
    return (agree / n - pc) / (1 - pc)


def aiken_v(values, lo=1, c=5):
    return sum(v - lo for v in values) / (len(values) * (c - 1)) if values else None


def a_wg(values, lo=1, hi=5):
    """Brown & Hauenstein (2005) a_wg(1); None for fewer than 4 raters or when undefined."""
    k = len(values)
    if k < 4:
        return None
    m, s2 = statistics.mean(values), statistics.variance(values)
    if s2 == 0:
        return 1.0
    denom = ((hi + lo) * m - m ** 2 - hi * lo) * (k / (k - 1))
    return 1 - 2 * s2 / denom if denom > 0 else None


def lynn_ok(agree, n):
    return n >= 3 and (n - agree == 0 if n <= 5 else n - agree <= 1)


def describe(values, negative=False):
    v = sorted(values)
    out = {"n": len(v)}
    if not v:
        return {**out, "median": None, "q1": None, "q3": None, "i_cvi": None, "decision": None if negative else "too few raters"}
    q1, _, q3 = statistics.quantiles(v, n=4, method="inclusive") if len(v) > 1 else (v[0], v[0], v[0])
    agree = sum(1 for x in v if x >= 4)
    out.update({"median": statistics.median(v), "q1": q1, "q3": q3, "iqr": q3 - q1, "share_4_5": agree / len(v),
                "aiken_v": aiken_v(v), "a_wg": a_wg(v)})
    if negative:
        out["decision"] = None
        return out
    lo, hi = clopper_pearson(agree, len(v))
    kap = modified_kappa(agree, len(v))
    out.update({"i_cvi": agree / len(v), "i_cvi_ci95": (lo, hi), "kappa_star": kap})
    if len(v) < 3:
        out["decision"] = "too few raters"
    elif kap < 0.60 or out["median"] <= 3:
        out["decision"] = "review"
    elif lynn_ok(agree, len(v)) and out["median"] >= 4 and out["iqr"] <= 1:
        out["decision"] = "accept"
    else:
        out["decision"] = "revise"
    return out


# ---------------------------------------------------------------- data
def val(r, col):
    return int(r[col].strip()) if (r.get(col) or "").strip() in VALID else None


def passed_check(r):
    c = val(r, "CHK")
    return c is not None and c <= 2


MODES = ("all", "passed_check")


def collect(rows, col, mode):
    sel = rows if mode == "all" else [r for r in rows if passed_check(r)]
    return [v for v in (val(r, col) for r in sel) if v is not None]


def analyse(rows):
    out = {"n_experts": len(rows),
           "attention_check": {"passed (1-2)": sum(1 for r in rows if passed_check(r)),
                               "neutral (3)": sum(1 for r in rows if val(r, "CHK") == 3),
                               "failed (4-5)": sum(1 for r in rows if (val(r, "CHK") or 0) >= 4),
                               "blank or TD": sum(1 for r in rows if val(r, "CHK") is None)}}
    items = {}
    for it in ITEMS:
        res = {"number": it["number"], "block": it["block"], "domains": it["domains"], "negative": it["negative"],
               "td": sum(1 for r in rows if (r.get(it["id"]) or "").strip().upper() == "TD")}
        for mode in MODES:
            res[mode] = describe(collect(rows, it["id"], mode), it["negative"])
        items[it["id"]] = res
    out["items"] = items
    rule = [items[i["id"]]["all"]["i_cvi"] for i in ITEMS if i["block"] == "A1" and items[i["id"]]["all"]["i_cvi"] is not None]
    out["s_cvi_ave_rules"] = statistics.mean(rule) if rule else None
    cases = []
    for c in CASES:
        res = {**c, "ratings": {}}
        for part in (["level"] if c["normal"] else ["level", "cause", "tasks"]):
            res["ratings"][part] = {mode: describe(collect(rows, f"{c['case']}_{part}", mode)) for mode in MODES}
        cases.append(res)
    out["cases"] = cases
    for part in ("level", "cause", "tasks"):
        vals = [c["ratings"][part]["all"]["i_cvi"] for c in cases
                if part in c["ratings"] and c["ratings"][part]["all"]["i_cvi"] is not None]
        out[f"s_cvi_ave_cases_{part}"] = statistics.mean(vals) if vals else None
    return out


# ---------------------------------------------------------------- report
def f(x, d=2):
    return "–" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


def line(s):
    if not s["n"]:
        return "n = 0"
    txt = f"n = {s['n']}, median {f(s['median'], 1)} (IQR {f(s['q1'], 1)}–{f(s['q3'], 1)}), 4–5: {100 * s['share_4_5']:.0f}%"
    if s.get("i_cvi") is not None:
        lo, hi = s["i_cvi_ci95"]
        txt += f", I-CVI {f(s['i_cvi'])} (95% CI {f(lo)}–{f(hi)}), κ* {f(s['kappa_star'])}"
    txt += f", Aiken V {f(s['aiken_v'])}, a_wg {f(s['a_wg'])}"
    return txt + (f" → {s['decision']}" if s.get("decision") else "")


def report(res):
    L = ["# Expert evaluation: results", "",
         f"- Experts: {res['n_experts']} (panel composition: the separate tally in PROTOCOL.md, not the form)",
         f"- Attention check: {res['attention_check']}", "",
         "Primary analysis: every answer 1–5, TD excluded.", "",
         "## Part A", ""]
    for iid, s in res["items"].items():
        tag = " (risk statement, no decision)" if s["negative"] else ""
        L.append(f"- {s['number']}. {iid}{tag}: {line(s['all'])}; TD {s['td']}")
        L.append(f"  - attention check passed only: {line(s['passed_check'])}")
    L += ["", f"S-CVI/Ave (mean I-CVI of the seven rule items): {f(res['s_cvi_ave_rules'])}", "", "## Part B", ""]
    for c in res["cases"]:
        L.append(f"- {c['case']} ({c['scenario']}, {c['level']}{', ' + c['possible_cause'] if c['possible_cause'] else ''}"
                 f"{'; ' + ' '.join(c['tasks']) if c['tasks'] else ''})")
        for part, s in c["ratings"].items():
            L.append(f"  - {part}: {line(s['all'])}")
    L += ["", "S-CVI/Ave of Part B: level " + f(res["s_cvi_ave_cases_level"]) + ", cause " + f(res["s_cvi_ave_cases_cause"])
          + ", tasks " + f(res["s_cvi_ave_cases_tasks"]), "",
          "Report every number above in the paper, including unfavourable ones. Ratings were given after the briefing;",
          "they show expert plausibility of the rules and tasks (ex ante, artificial), not field efficacy."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- self-test
def selftest():
    assert abs(clopper_pearson(5, 5)[0] - 0.025 ** (1 / 5)) < 1e-6 and abs(clopper_pearson(8, 8)[0] - 0.025 ** (1 / 8)) < 1e-6
    assert abs(modified_kappa(4, 5) - (0.8 - 5 / 32) / (1 - 5 / 32)) < 1e-12 and modified_kappa(5, 5) == 1.0
    assert abs(aiken_v([4] * 5) - 0.75) < 1e-12 and a_wg([4, 4, 4, 4, 4]) == 1.0 and a_wg([1, 5, 1, 5]) < 0
    assert lynn_ok(5, 5) and not lynn_ok(4, 5) and lynn_ok(5, 6) and lynn_ok(6, 7) and not lynn_ok(5, 7)
    assert describe([5, 5, 4, 4, 5])["decision"] == "accept" and describe([5, 5, 4, 4, 2])["decision"] == "revise"
    assert describe([3, 3, 2, 4, 3])["decision"] == "review" and describe([5, 5])["decision"] == "too few raters"
    rnd = random.Random(3)
    rows = []
    for i in range(7):
        r = {"row": f"T{i}", "CHK": "1" if i else "5"}
        r.update({it["id"]: str(rnd.choice([3, 4, 5])) for it in ITEMS})
        r["R1"] = "4" if i < 4 else "TD"
        for c in CASES:
            r[f"{c['case']}_level"] = "4"
            if not c["normal"]:
                r[f"{c['case']}_cause"], r[f"{c['case']}_tasks"] = "5", "4"
        rows.append(r)
    res = analyse(rows)
    assert res["n_experts"] == 7 and res["attention_check"]["failed (4-5)"] == 1
    assert res["items"]["R1"]["all"]["n"] == 4 and res["items"]["R1"]["td"] == 3
    assert res["items"]["R1"]["passed_check"]["n"] == 3 and res["items"]["T5"]["all"]["decision"] is None
    assert res["cases"][0]["ratings"]["level"]["all"]["n"] == 7 and "cause" not in res["cases"][0]["ratings"]
    assert res["s_cvi_ave_cases_level"] == 1.0 and report(res).count("- C") == len(CASES)
    print("selftest passed (made-up ratings: CI, kappa*, Aiken V, a_wg, Lynn rule, TD and attention check as expected)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
        sys.exit(0)
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")) if (r.get("row") or "").strip()]
    if not rows:
        print("No expert responses yet: type each form into responses.csv (one row per expert, see PROTOCOL.md "
              "section 3), then run this script again.")
        sys.exit(1)
    res = analyse(rows)
    outdir = os.path.dirname(os.path.abspath(sys.argv[1]))
    json.dump(res, open(os.path.join(outdir, "results_expert.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    open(os.path.join(outdir, "results_expert.md"), "w", encoding="utf-8").write(report(res))
    print(report(res))
