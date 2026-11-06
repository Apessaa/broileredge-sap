"""Uncertainty and agreement statistics for the record-level replay (Section V-A of the paper).

Input: data/replay_records.csv (the 1,692 complete records with the levels computed by replay_v13.py).
  P  = revised rules, O = original rule set (blank where THVI is undefined), thP/thP2 = thermal level
  with the humid-tropics THI / the THI of [16], thTHI = THI rule applied in week 1.
Output: stats_ci.json

Records within one survey (house, week, daily window; 12 points) are not independent, so 95% CIs come
from a cluster bootstrap that resamples the 141 surveys (10,000 resamples, percentile intervals).
Cohen's kappa measures agreement between two rule sets beyond chance; the kappa CI uses the same
cluster bootstrap. All shares describe these eight flock-houses; they are not population estimates.
"""
import csv
import json
import os
import random
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "replay_records.csv")
B = 10000
rng = random.Random(20261026)


def kappa(pairs, weights=None):
    """Cohen's kappa for 3 ordered levels; weights='linear' gives linearly weighted kappa."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    cats = (0, 1, 2)
    w = (lambda i, j: 1 - abs(i - j) / 2) if weights == "linear" else (lambda i, j: 1.0 if i == j else 0.0)
    obs = sum(w(a, b) for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    exp = sum(w(i, j) * ca[i] * cb[j] for i in cats for j in cats) / n / n
    return (obs - exp) / (1 - exp) if exp < 1 else float("nan")


def boot(clusters, stat):
    keys = list(clusters)
    vals = []
    for _ in range(B):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in clusters[k]]
        v = stat(sample)
        if v == v:  # skip NaN
            vals.append(v)
    vals.sort()
    return round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)


def main():
    rows = list(csv.DictReader(open(SRC)))
    surveys = defaultdict(list)
    for r in rows:
        surveys[(r["flock"], r["House"], r["Week"], r["Time"])].append(r)
    lv = lambda x: int(float(x))
    out = {"records": len(rows), "surveys": len(surveys), "bootstrap_resamples": B}

    def share(sel, cond):
        def f(sample):
            s = [r for r in sample if sel(r)]
            return sum(1 for r in s if cond(r)) / len(s) if s else float("nan")
        return f

    stats = {
        "O_undefined": (share(lambda r: True, lambda r: r["O"] == ""), None),
        "O_ne_P_where_defined": (share(lambda r: r["O"] != "", lambda r: lv(r["O"]) != lv(r["P"])), None),
        "P2_ne_P_thermal_weeks4to6": (share(lambda r: int(r["Week"]) >= 4, lambda r: lv(r["thP"]) != lv(r["thP2"])), None),
        "week1_MS_THI_rule": (share(lambda r: int(r["Week"]) == 1, lambda r: lv(r["thTHI"]) >= 1), None),
        "week1_MS_brooding_rule": (share(lambda r: int(r["Week"]) == 1, lambda r: lv(r["thP"]) >= 1), None),
        "NH3_10_to_20": (share(lambda r: True, lambda r: 10 < float(r["NH3"]) <= 20), None),
    }
    for name, (f, _) in stats.items():
        out[name] = {"value": round(f(rows), 4), "ci95": boot(surveys, f)}

    def kap(sel, a, b, weights=None):
        return lambda sample: kappa([(lv(r[a]), lv(r[b])) for r in sample if sel(r)], weights)

    for name, f in {
        "kappa_O_vs_P": kap(lambda r: r["O"] != "", "O", "P"),
        "kappa_linear_O_vs_P": kap(lambda r: r["O"] != "", "O", "P", "linear"),
        "kappa_thermal_P_vs_P2_weeks4to6": kap(lambda r: int(r["Week"]) >= 4, "thP", "thP2"),
    }.items():
        out[name] = {"value": round(f(rows), 4), "ci95": boot(surveys, f)}
    # confusion matrix O (rows) x P (columns) where O is defined
    cm = Counter((lv(r["O"]), lv(r["P"])) for r in rows if r["O"] != "")
    out["confusion_O_rows_P_cols"] = [[cm[(i, j)] for j in range(3)] for i in range(3)]
    with open(os.path.join(HERE, "stats_ci.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
