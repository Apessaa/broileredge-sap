"""Hardware cost per house from hardware_cost.csv (paper v24, Section IV-B). Output: cost_summary.json.
Prices are list or retail prices on the access date, before sales tax/VAT, shipping, import duty and installation.
EUR is converted at 0.8982 EUR per USD (YCharts, 28 Oct 2026). Items without a public price are listed, not estimated."""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EUR_PER_USD = 0.8982
rows = list(csv.DictReader(open(os.path.join(HERE, "hardware_cost.csv"), encoding="utf-8")))
lines, missing = [], []
for r in rows:
    if not r["unit_price"]:
        missing.append({"item": r["item"], "model": r["model"], "qty": int(r["qty"]), "note": r["note"]})
        continue
    unit = float(r["unit_price"]) / (EUR_PER_USD if r["currency"] == "EUR" else 1.0)
    lines.append({"item": r["item"], "model": r["model"], "qty": int(r["qty"]), "unit_usd": round(unit, 2),
                  "total_usd": round(unit * int(r["qty"]), 2)})
total = round(sum(x["total_usd"] for x in lines), 2)
big = sorted(lines, key=lambda x: -x["total_usd"])[:2]
out = {"eur_per_usd": EUR_PER_USD, "lines": lines, "total_usd_priced_items": total,
       "total_usd_rounded_100": int(round(total, -2)), "largest_items": [b["item"] for b in big],
       "not_priced": missing}
json.dump(out, open(os.path.join(HERE, "cost_summary.json"), "w"), indent=1)
for x in lines:
    print(f"{x['item']:<20} {x['qty']:>4} x {x['unit_usd']:>8.2f} = {x['total_usd']:>9.2f}")
print(f"total (priced items) USD {total:.2f}  ~ {out['total_usd_rounded_100']}; not priced: {[m['item'] for m in missing]}")
