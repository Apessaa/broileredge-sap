"""Record-level replay of the rule sets on the open Zenodo dataset (doi:10.5281/zenodo.16043470).
Usage: python3 -I replay_v13.py data.xlsx [raw|corrected]
Period 1 = winter flock, Period 2 = summer flock (Coimbra et al. 2025, Poultry 4(3):38).
"""
import os, sys, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import stress_model_v13 as M

path = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else 'raw'
df = pd.read_excel(path, sheet_name=0)
df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
tcol, rcol = (('AirTemperature', 'Relative_Humidity') if mode == 'raw'
              else ('Corrected_Air_Temperature_Point', 'Corrected_Relative_Humidity_Point'))
df = df.rename(columns={tcol: 'T', rcol: 'RH', 'Wind_Speed': 'V', 'Ammonia': 'NH3'})
df['flock'] = df['Period'].map({1: 'winter', 2: 'summer'})
n_all = len(df)
need = ['T', 'RH', 'V', 'CO2', 'NH3']
d = df.dropna(subset=need).copy()
# flock sample weight per house and week (the design uses the flock's latest sample weight)
wt = df.groupby(['Period', 'House', 'Week'])['Chicken_weight'].median().rename('W')
d = d.join(wt, on=['Period', 'House', 'Week'])
assert d['W'].notna().all()
R = {'mode': mode, 'n_rows': n_all, 'n_complete': len(d),
     'n_by_flock': d.groupby('flock').size().to_dict()}

d['THI'] = [M.thi_humid_tropics(t, r) for t, r in zip(d['T'], d['RH'])]
d['THI2'] = [M.thi_thom(t, r) for t, r in zip(d['T'], d['RH'])]
d['Tstar'] = [M.ross_target(w, r) for w, r in zip(d['W'], d['RH'])]
d['dT'] = d['T'] - d['Tstar']
d['thP'] = [M.thermal_P(t, r, wk, w) for t, r, wk, w in zip(d['T'], d['RH'], d['Week'], d['W'])]
d['thP2'] = [M.thermal_P(t, r, wk, w, thi_fn=M.thi_thom) for t, r, wk, w in zip(d['T'], d['RH'], d['Week'], d['W'])]
d['thTHI'] = [M.band(x, 26, 29, incl_lo=False) for x in d['THI']]  # THI rule at every age (no age switch)
d['nhP'] = d['NH3'].map(M.nh3_P)
d['coP'] = d['CO2'].map(M.co2_P)
d['P'] = d[['thP', 'nhP', 'coP']].max(axis=1)
d['P2'] = d[['thP2', 'nhP', 'coP']].max(axis=1)
d['Pnoage'] = d[['thTHI', 'nhP', 'coP']].max(axis=1)
d['thO'] = [M.thermal_O(t, r, v) for t, r, v in zip(d['T'], d['RH'], d['V'])]
d['nhO'] = d['NH3'].map(M.nh3_O)
d['coO'] = d['CO2'].map(M.co2_O)
d['O'] = [None if th is None else max(th, a, b) for th, a, b in zip(d['thO'], d['nhO'], d['coO'])]
d['THVIc'] = [M.thvi(t, r, v) for t, r, v in zip(d['T'], d['RH'], d['V'])]
d['note'] = [M.thvi_note(t, r, v) for t, r, v in zip(d['T'], d['RH'], d['V'])]
d['diag18'] = [M.air_speed_diag(t, r, v, wk, 1.8) for t, r, v, wk in zip(d['T'], d['RH'], d['V'], d['Week'])]
d['diag203'] = [M.air_speed_diag(t, r, v, wk, 2.03) for t, r, v, wk in zip(d['T'], d['RH'], d['V'], d['Week'])]


def pct(x, n):
    return round(100.0 * x / n, 1) if n else None


def dist(s):
    s = s.dropna().astype(int)
    n = len(s)
    return {'n': n, 'N': pct((s == 0).sum(), n), 'M': pct((s == 1).sum(), n), 'S': pct((s == 2).sum(), n)}


# 1. level distributions
R['dist'] = {}
for f in ['winter', 'summer', 'all']:
    sub = d if f == 'all' else d[d.flock == f]
    R['dist'][f] = {k: dist(sub[k]) for k in ['P', 'O', 'P2', 'Pnoage', 'thP', 'nhP', 'coP']}
    R['dist'][f]['P_w13'] = dist(sub[sub.Week <= 3]['P'])
    R['dist'][f]['P_w46'] = dist(sub[sub.Week >= 4]['P'])
# by week (P)
R['P_by_week'] = {f: {int(w): dist(g['P']) for w, g in d[d.flock == f].groupby('Week')} for f in ['winter', 'summer']}

# 2. O vs P
o_ok = d[d['O'].notna()]
R['O_undefined_V0'] = int(d['O'].isna().sum())
R['O_undefined_by_flock'] = d[d['O'].isna()].groupby('flock').size().to_dict()
ch = o_ok[o_ok['O'].astype(int) != o_ok['P']]
R['O_vs_P'] = {'n_compared': len(o_ok), 'changed': len(ch), 'changed_pct': pct(len(ch), len(o_ok)),
               'O_higher': int((ch['O'].astype(int) > ch['P']).sum()), 'O_lower': int((ch['O'].astype(int) < ch['P']).sum())}
R['O_vs_P_by_flock'] = {f: {'n': int((o_ok.flock == f).sum()), 'changed': int((ch.flock == f).sum()),
                            'pct': pct((ch.flock == f).sum(), (o_ok.flock == f).sum())} for f in ['winter', 'summer']}
# sub-indicator changes
R['O_vs_P_thermal_changed'] = int((o_ok['thO'].astype(int) != o_ok['thP']).sum())
R['O_vs_P_nh3_changed'] = int((d['nhO'] != d['nhP']).sum())
R['O_vs_P_co2_changed'] = int((d['coO'] != d['coP']).sum())
# O severe due to low V extrapolation: V<0.2 and O thermal severe while capped THVI note < 38
lowv = o_ok[o_ok.V < 0.2]
R['lowV'] = {'n_V_lt_0.2_all': int((d.V < 0.2).sum()), 'n_V_eq_0': int((d.V == 0).sum()),
             'n_V_lt_0.2_by_flock': d[d.V < 0.2].groupby('flock').size().to_dict(),
             'O_thermal_severe_when_V_lt_0.2_pct': pct((lowv['thO'].astype(int) == 2).sum(), len(lowv)),
             'P_thermal_severe_when_V_lt_0.2_pct': pct((lowv['thP'] == 2).sum(), len(lowv))}

# 3. THI equation sensitivity (weeks 4-6)
w46 = d[d.Week >= 4]
R['THI_eq'] = {'n': len(w46), 'thermal_changed': int((w46.thP != w46.thP2).sum()),
               'thermal_changed_pct': pct((w46.thP != w46.thP2).sum(), len(w46)),
               'overall_changed': int((w46.P != w46.P2).sum()),
               'overall_changed_pct': pct((w46.P != w46.P2).sum(), len(w46)),
               'thermal_dist_ht': dist(w46.thP), 'thermal_dist_thom': dist(w46.thP2),
               'THI_ht_median': round(w46.THI.median(), 2), 'THI_thom_median': round(w46.THI2.median(), 2),
               'mean_diff': round((w46.THI - w46.THI2).mean(), 2)}
R['THI_eq_by_flock'] = {f: {'n': int((w46.flock == f).sum()),
                            'changed_pct': pct(((w46.thP != w46.thP2) & (w46.flock == f)).sum(), (w46.flock == f).sum()),
                            'ht': dist(w46[w46.flock == f].thP), 'thom': dist(w46[w46.flock == f].thP2)}
                        for f in ['winter', 'summer']}

# 4. brooding rule (weeks 1-3)
w13 = d[d.Week <= 3]
R['brood'] = {}
for f in ['winter', 'summer']:
    for wk in [1, 2, 3]:
        g = w13[(w13.flock == f) & (w13.Week == wk)]
        R['brood'][f + str(wk)] = {'n': len(g), 'W': round(g.W.median(), 0), 'T_med': round(g['T'].median(), 1),
                                   'RH_med': round(g.RH.median(), 1),
                                   'Tstar_med': round(g.Tstar.median(), 1), 'dT_med': round(g.dT.median(), 1),
                                   'cold_gt2': pct((g.dT < -2).sum(), len(g)), 'warm_gt2': pct((g.dT > 2).sum(), len(g)),
                                   'cold_gt4': pct((g.dT < -4).sum(), len(g)), 'warm_gt4': pct((g.dT > 4).sum(), len(g)),
                                   'thP': dist(g.thP), 'thTHI': dist(g.thTHI)}
# age switch ablation on weeks 1-3
R['age_ablation_w13'] = {'n': len(w13), 'thermal_changed_pct': pct((w13.thP != w13.thTHI).sum(), len(w13)),
                         'THI_rule_normal_but_cold_gt2': int(((w13.thTHI == 0) & (w13.dT < -2)).sum()),
                         'THI_rule_normal_but_cold_gt2_pct': pct(((w13.thTHI == 0) & (w13.dT < -2)).sum(), len(w13)),
                         'cold_gt2_total': int((w13.dT < -2).sum()), 'warm_gt2_total': int((w13.dT > 2).sum())}
# week-1 only
w1 = d[d.Week == 1]
R['week1'] = {f: {'n': int((w1.flock == f).sum()), 'cold_gt2_pct': pct(((w1.flock == f) & (w1.dT < -2)).sum(), (w1.flock == f).sum()),
                  'THI_normal_pct': pct(((w1.flock == f) & (w1.thTHI == 0)).sum(), (w1.flock == f).sum())} for f in ['winter', 'summer']}

# 5. air speed (weeks 4-6)
R['air'] = {}
for f in ['winter', 'summer', 'all']:
    g = w46 if f == 'all' else w46[w46.flock == f]
    R['air'][f] = {'n': len(g), 'V_med': round(g.V.median(), 2), 'V_p90': round(g.V.quantile(0.9), 2),
                   'V_lt_1.8_pct': pct((g.V < 1.8).sum(), len(g)), 'V_ge_1.8_pct': pct((g.V >= 1.8).sum(), len(g)),
                   'V_in_0.3_0.8_pct': pct(((g.V >= 0.3) & (g.V <= 0.8)).sum(), len(g)),
                   'warm_THI_ge26_pct': pct((g.THI >= 26).sum(), len(g)),
                   'diag18_pct': pct(g.diag18.sum(), len(g)), 'diag203_pct': pct(g.diag203.sum(), len(g)),
                   'diag18_n': int(g.diag18.sum()), 'diag203_n': int(g.diag203.sum()),
                   'diag18_of_warm_pct': pct(g.diag18.sum(), (g.THI >= 26).sum()),
                   'note_dist': dist(g.note), 'THVIc_max': round(g.THVIc.max(), 2)}

# 6. gases
R['gas'] = {}
for f in ['winter', 'summer', 'all']:
    g = d if f == 'all' else d[d.flock == f]
    n = len(g)
    R['gas'][f] = {'n': n, 'NH3_zero_pct': pct((g.NH3 == 0).sum(), n), 'NH3_gt10_pct': pct((g.NH3 > 10).sum(), n),
                   'NH3_gt20_pct': pct((g.NH3 > 20).sum(), n), 'NH3_max': float(g.NH3.max()),
                   'NH3_p90': float(g.NH3.quantile(0.9)), 'NH3_med': float(g.NH3.median()),
                   'NH3_mean': round(g.NH3.mean(), 2),
                   'NH3_edge_5_15_pct': pct(((g.NH3 > 5) & (g.NH3 <= 15)).sum(), n),
                   'NH3_edge_any_pct': pct((((g.NH3 > 5) & (g.NH3 <= 15)) | ((g.NH3 > 15) & (g.NH3 <= 25))).sum(), n),
                   'CO2_gt3000_pct': pct((g.CO2 > 3000).sum(), n), 'CO2_gt3500_pct': pct((g.CO2 > 3500).sum(), n),
                   'CO2_max': float(g.CO2.max()), 'CO2_med': float(g.CO2.median())}
R['NH3_by_week'] = {f: {int(w): {'gt10': pct((g.NH3 > 10).sum(), len(g)), 'gt20': pct((g.NH3 > 20).sum(), len(g)),
                                 'zero': pct((g.NH3 == 0).sum(), len(g))}
                        for w, g in d[d.flock == f].groupby('Week')} for f in ['winter', 'summer']}
R['CO2_by_week'] = {f: {int(w): {'gt3000': pct((g.CO2 > 3000).sum(), len(g))}
                        for w, g in d[d.flock == f].groupby('Week')} for f in ['winter', 'summer']}

# 7. causes of P Moderate/Severe
def cause(row):
    lv = row.P
    if lv == 0:
        return 'none'
    c = []
    if row.thP == lv: c.append('thermal')
    if row.nhP == lv: c.append('NH3')
    if row.coP == lv: c.append('CO2')
    return '+'.join(c)
d['cause'] = d.apply(cause, axis=1)
R['causes'] = {f: d[(d.flock == f) & (d.P > 0)]['cause'].value_counts().to_dict() for f in ['winter', 'summer']}
R['causes_all'] = d[d.P > 0]['cause'].value_counts().to_dict()

# 8. spatial: worst point vs averaged survey (house x flock x week x window)
rows = []
for key, g in d.groupby(['Period', 'House', 'Week', 'Time']):
    worst = g['P'].max()
    m = g[['T', 'RH', 'V', 'CO2', 'NH3']].mean()
    wk = key[2]; w = g['W'].iloc[0]
    avgP = max(M.thermal_P(m['T'], m['RH'], wk, w), M.nh3_P(m['NH3']), M.co2_P(m['CO2']))
    rows.append({'flock': 'winter' if key[0] == 1 else 'summer', 'worst': worst, 'avg': avgP,
                 'n_levels': g['P'].nunique(), 'T_range': g['T'].max() - g['T'].min(),
                 'NH3_range': g['NH3'].max() - g['NH3'].min(), 'npts': len(g)})
S = pd.DataFrame(rows)
R['spatial'] = {'n_surveys': len(S), 'worst_gt_avg': int((S.worst > S.avg).sum()),
                'worst_gt_avg_pct': pct((S.worst > S.avg).sum(), len(S)),
                'mixed_levels_pct': pct((S.n_levels > 1).sum(), len(S)),
                'T_range_med': round(S.T_range.median(), 1), 'NH3_range_med': round(S.NH3_range.median(), 1),
                'npts_min': int(S.npts.min())}

# 9. outliers and validation
R['outliers'] = {'T_gt_40': int((d['T'] > 40).sum()), 'RH_lt_25': int((d.RH < 25).sum()),
                 'T_max': float(d['T'].max()), 'RH_min': float(d.RH.min())}
# medians check
R['medians'] = {f: {c: float(d[d.flock == f][c].median()) for c in ['T', 'RH', 'V', 'CO2', 'NH3']} for f in ['winter', 'summer']}
# combined summary for P levels by flock & week band
R['P_w13_w46'] = {f: {'w13': dist(d[(d.flock == f) & (d.Week <= 3)]['P']), 'w46': dist(d[(d.flock == f) & (d.Week >= 4)]['P'])}
                  for f in ['winter', 'summer']}
R['O_by_flock'] = {f: dist(d[d.flock == f]['O']) for f in ['winter', 'summer']}
R['P2_by_flock'] = {f: dist(d[d.flock == f]['P2']) for f in ['winter', 'summer']}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'replay_{mode}.json')
with open(out, 'w') as fh:
    json.dump(R, fh, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
d.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f'replay_{mode}_records.csv'), index=False)
print(json.dumps(R, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
