"""Independent, vectorised recomputation of the Table IV values straight from data.xlsx
(does not import stress_model_v13 or the replay outputs). Usage:
python3 -I table4_check.py data.xlsx raw|corrected
"""
import sys
import numpy as np
import pandas as pd

mode = sys.argv[2] if len(sys.argv) > 2 else 'raw'
df = pd.read_excel(sys.argv[1], sheet_name=0)
df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
T_ = 'AirTemperature' if mode == 'raw' else 'Corrected_Air_Temperature_Point'
R_ = 'Relative_Humidity' if mode == 'raw' else 'Corrected_Relative_Humidity_Point'
df['W'] = df.groupby(['Period', 'House', 'Week'])['Chicken_weight'].transform('median')
d = df.dropna(subset=[T_, R_, 'Wind_Speed', 'CO2', 'Ammonia']).copy()
T = d[T_].to_numpy(float); RH = d[R_].to_numpy(float); V = d['Wind_Speed'].to_numpy(float)
NH3 = d['Ammonia'].to_numpy(float); CO2 = d['CO2'].to_numpy(float)
wk = d['Week'].to_numpy(int); W = d['W'].to_numpy(float); win = (d['Period'] == 1).to_numpy()

# Ross table, bilinear with clamping
ws = np.array([44, 100, 180, 290, 425, 590, 790, 1015, 1260, 1530], float)
rhs = np.array([40, 50, 60, 70], float)
tab = np.array([[36.0, 33.2, 30.8, 29.2], [33.7, 31.2, 28.9, 27.3], [32.5, 29.9, 27.7, 26.0],
                [31.3, 28.6, 26.7, 25.0], [30.2, 27.8, 25.7, 24.0], [29.0, 26.8, 24.8, 23.0],
                [27.7, 25.5, 23.6, 21.9], [26.9, 24.7, 22.7, 21.3], [25.7, 23.5, 21.7, 20.2],
                [24.8, 22.7, 20.7, 19.3]])
rowvals = np.array([[np.interp(r, rhs, tab[i]) for i in range(len(ws))] for r in RH])  # n x 10
Tstar = np.array([np.interp(w, ws, rv) for w, rv in zip(W, rowvals)])
thi1 = T - (0.31 - 0.31 * RH / 100) * (T - 14.4)
thi2 = T - (0.55 - 0.0055 * RH) * (T - 14.5)
def lvl_excl(x, lo, hi):   # <lo N, lo..hi M, >hi S
    return np.where(x < lo, 0, np.where(x <= hi, 1, 2))
def lvl_incl(x, lo, hi):   # <=lo N, (lo,hi] M, >hi S
    return np.where(x <= lo, 0, np.where(x <= hi, 1, 2))
brood = lvl_incl(np.abs(T - Tstar), 2, 4)
thP = np.where(wk <= 3, brood, lvl_excl(thi1, 26, 29))
thP2 = np.where(wk <= 3, brood, lvl_excl(thi2, 26, 29))
thTHI = lvl_excl(thi1, 26, 29)
nhP = lvl_incl(NH3, 10, 20); coP = lvl_incl(CO2, 3000, 3500)
P = np.maximum.reduce([thP, nhP, coP])
# O
Ostar = V > 0
twb = (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659)) + np.arctan(T + RH) - np.arctan(RH - 1.676331)
       + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH) - 4.686035)
base = 0.85 * T + 0.15 * twb
with np.errstate(divide='ignore'):
    thvi_raw = np.where(Ostar, base * np.where(Ostar, V, 1.0) ** -0.058, np.inf)
thvi_cap = base * np.clip(V, 0.2, 1.2) ** -0.058
thO = lvl_excl(thvi_raw, 26, 29)
O = np.maximum.reduce([thO, lvl_incl(NH3, 20, 40), lvl_incl(CO2, 3000, 6000)])
diag = (wk >= 4) & (thi1 >= 26) & (V < 1.8)

def pct(mask, base_mask):
    return 100.0 * mask[base_mask].sum() / base_mask.sum()

out = {}
for name, m in [('winter', win), ('summer', ~win), ('all', np.ones_like(win, bool))]:
    r = {}
    r['n'] = int(m.sum())
    r['P_NMS'] = [round(pct(P == k, m), 1) for k in (0, 1, 2)]
    r['V0_pct'] = round(pct(~Ostar, m), 1)
    r['O_ne_P_pct'] = round(pct((O != P), m & Ostar), 1)
    w1 = m & (wk == 1)
    r['wk1_THI_MS_pct'] = round(pct(thTHI > 0, w1), 1)
    r['wk1_brood_MS_pct'] = round(pct(brood > 0, w1), 1)
    r['wk1_brood_N_pct'] = round(pct(brood == 0, w1), 1)
    r['dT_med_wk2'] = round(float(np.median((T - Tstar)[m & (wk == 2)])), 1)
    r['dT_med_wk3'] = round(float(np.median((T - Tstar)[m & (wk == 3)])), 1)
    w46 = m & (wk >= 4)
    r['P2_ne_P_thermal_w46_pct'] = round(pct(thP != thP2, w46), 1)
    r['diag_w46_pct'] = round(pct(diag, w46), 1)
    r['NH3_lod_gt10_gt20'] = [round(pct(NH3 == 0, m), 1), round(pct(NH3 > 10, m), 1), round(pct(NH3 > 20, m), 1)]
    r['CO2_gt3000_pct'] = round(pct(CO2 > 3000, m), 1)
    r['severe_n'] = int((P == 2)[m].sum())
    r['severe_brood_n'] = int(((P == 2) & (wk <= 3) & (thP == 2))[m].sum())
    r['thvi_cap_ge35_w46_n'] = int(((thvi_cap >= 35) & (wk >= 4))[m].sum())
    r['V_gt_0.8_w46_pct'] = round(pct(V > 0.8, w46), 1)
    r['V_lt_1.8_w46_pct'] = round(pct(V < 1.8, w46), 1)
    r['NH3_flip_pct'] = round(pct((NH3 > 5) & (NH3 <= 25), m), 1)
    r['NH3_10_20_pct'] = round(pct((NH3 > 10) & (NH3 <= 20), m), 1)
    r['Tstar_med_wk3'] = round(float(np.median(Tstar[m & (wk == 3)])), 1)
    out[name] = r

# spatial: worst point vs level of survey mean
d = d.assign(P=P)
keys = ['Period', 'House', 'Week', 'Time']
g = d.groupby(keys)
mean = g[[T_, R_, 'CO2', 'Ammonia']].mean()
worst = g['P'].max()
Wm = g['W'].first()
mT = mean[T_].to_numpy(); mR = mean[R_].to_numpy(); mW = Wm.to_numpy()
mwk = np.array([k[2] for k in mean.index])
rv = np.array([[np.interp(r, rhs, tab[i]) for i in range(len(ws))] for r in mR])
mTs = np.array([np.interp(w, ws, x) for w, x in zip(mW, rv)])
mthi = mT - (0.31 - 0.31 * mR / 100) * (mT - 14.4)
mth = np.where(mwk <= 3, lvl_incl(np.abs(mT - mTs), 2, 4), lvl_excl(mthi, 26, 29))
mlev = np.maximum.reduce([mth, lvl_incl(mean['Ammonia'].to_numpy(), 10, 20), lvl_incl(mean['CO2'].to_numpy(), 3000, 3500)])
gt = worst.to_numpy() > mlev
per = np.array([k[0] for k in mean.index])
out['spatial'] = {'n': int(len(gt)), 'all_pct': round(100 * gt.mean(), 1),
                  'winter_pct': round(100 * gt[per == 1].mean(), 1), 'summer_pct': round(100 * gt[per == 2].mean(), 1)}
import json
print(json.dumps(out, indent=1))
