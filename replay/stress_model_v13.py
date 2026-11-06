"""Rule sets used in the paper (Table II = revised rules P; original rule set O; P' = P with the
Thom-form THI used in Coimbra et al. 2025). Rebuilt from the v12 specification.

Levels: 0 = Normal, 1 = Moderate, 2 = Severe.
"""
import math

LEVELS = ['Normal', 'Moderate', 'Severe']


def twb_stull(t, rh):
    """Stull (2011) wet-bulb temperature, t in degC, rh in %."""
    return (t * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t + rh)
            - math.atan(rh - 1.676331) + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
            - 4.686035)


def thi_humid_tropics(t, rh):
    """Eq. (1): THI = Tdb - (0.31 - 0.31 RH)(Tdb - 14.4), RH as a fraction (Omomowo & Falayi)."""
    f = rh / 100.0
    return t - (0.31 - 0.31 * f) * (t - 14.4)


def thi_thom(t, rh):
    """THI used by Coimbra et al. 2025: T - (0.55 - 0.0055 RH)(T - 14.5), RH in %."""
    return t - (0.55 - 0.0055 * rh) * (t - 14.5)


def thvi(t, rh, v, cap=True):
    """Eq. (2)-(3): THVI = (0.85 Tdb + 0.15 Twb) Vc^-0.058, Vc = min(max(V,0.2),1.2) if cap.
    Returns math.inf for v <= 0 when uncapped (index undefined in still air)."""
    if cap:
        vc = min(max(v, 0.2), 1.2)
    else:
        if v <= 0:
            return math.inf
        vc = v
    return (0.85 * t + 0.15 * twb_stull(t, rh)) * vc ** -0.058


def band(x, lo, hi, incl_lo=True):
    """incl_lo=True : Normal if x <= lo, Moderate if lo < x <= hi, Severe if x > hi.
    incl_lo=False: Normal if x <  lo, Moderate if lo <= x <= hi, Severe if x > hi."""
    if incl_lo:
        return 0 if x <= lo else (1 if x <= hi else 2)
    return 0 if x < lo else (1 if x <= hi else 2)


# Ross Broiler Pocket Guide (2025): optimum dry-bulb temperature (degC) by body weight (g) and RH.
ROSS_RH = (40, 50, 60, 70)
ROSS = {
    44: (36.0, 33.2, 30.8, 29.2),
    100: (33.7, 31.2, 28.9, 27.3),
    180: (32.5, 29.9, 27.7, 26.0),
    290: (31.3, 28.6, 26.7, 25.0),
    425: (30.2, 27.8, 25.7, 24.0),
    590: (29.0, 26.8, 24.8, 23.0),
    790: (27.7, 25.5, 23.6, 21.9),
    1015: (26.9, 24.7, 22.7, 21.3),
    1260: (25.7, 23.5, 21.7, 20.2),
    1530: (24.8, 22.7, 20.7, 19.3),
}
_W = sorted(ROSS)


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            f = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + f * (ys[i + 1] - ys[i])
    raise ValueError


def ross_target(weight_g, rh):
    """Bilinear interpolation of the Ross table, clamped at its edges (RH 40-70 %, 44-1530 g)."""
    rows = [_interp(rh, ROSS_RH, ROSS[w]) for w in _W]
    return _interp(weight_g, _W, rows)


# ---- revised rules P (Table II) ----
def thermal_P(t, rh, week, weight, thi_fn=thi_humid_tropics):
    if week <= 3:
        return band(abs(t - ross_target(weight, rh)), 2, 4, incl_lo=True)
    return band(thi_fn(t, rh), 26, 29, incl_lo=False)


def nh3_P(c):
    return band(c, 10, 20, incl_lo=True)


def co2_P(c):
    return band(c, 3000, 3500, incl_lo=True)


def thvi_note(t, rh, v):
    return band(thvi(t, rh, v, cap=True), 35, 38, incl_lo=False)


def air_speed_diag(t, rh, v, week, thr=1.8):
    return week >= 4 and thi_humid_tropics(t, rh) >= 26 and v < thr


# ---- original rule set O (the authors' earlier draft) ----
def thermal_O(t, rh, v):
    x = thvi(t, rh, v, cap=False)
    if math.isinf(x):
        return None  # undefined at V = 0
    return band(x, 26, 29, incl_lo=False)


def nh3_O(c):
    return band(c, 20, 40, incl_lo=True)


def co2_O(c):
    return band(c, 3000, 6000, incl_lo=True)


if __name__ == '__main__':
    print('T*(44 g, 65 %) =', round(ross_target(44, 65), 2))
    print('winter median THI ht/thom', round(thi_humid_tropics(26.7, 56.8), 2), round(thi_thom(26.7, 56.8), 2))
    print('winter median THVI cap/raw', round(thvi(26.7, 56.8, 0.075), 2), round(thvi(26.7, 56.8, 0.075, cap=False), 2))
    print('summer median THI ht/thom', round(thi_humid_tropics(28.9, 62.4), 2), round(thi_thom(28.9, 62.4), 2))
    print('Azzahra d1', round(thi_humid_tropics(27.3, 70), 2), round(thi_thom(27.3, 70), 2))
    print('Azzahra d3', round(thi_humid_tropics(29.2, 57.5), 2), round(thi_thom(29.2, 57.5), 2))
