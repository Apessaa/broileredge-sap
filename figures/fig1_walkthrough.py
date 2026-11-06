"""Fig. 1 of paper v29: the v4 walkthrough diagram laid out vertically for one IEEE column.

Same steps and numbering as System_Diagram_v4 (1, 2, 3; a = on site: 4a, 5a; b = to SAP: 4b-9b).
Line styles differ without colour: solid = data, short dashes = acknowledgement, long dashes = to or from
people, dots = action in the house. Writes fig1_walkthrough.svg/.html; fig1_render.js writes fig1_walkthrough.png.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1000, 1470
INK, INK2, MUTED, LINE = "#0F172A", "#334155", "#64748B", "#CBD5E1"
TEAL, BLUE, GREEN = "#0F766E", "#0369A1", "#4D7C0F"
VIOLET, AMBER, ACT, BUSC = "#6D28D9", "#B45309", "#BE123C", "#1E293B"
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
DATA, ACK, PEOPLE_D, FEED = None, "9 8", "18 9", "2 10"
out, _markers = [], {}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=32, weight=700, fill=INK, anchor="middle"):
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
               f'fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>')


def rect(x, y, w, h, fill="#FFFFFF", stroke=None, sw=2, rx=8, dash=None):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"{s}{d}/>')


def circle(cx, cy, r, fill, stroke=None, sw=2):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"{s}/>')


def line(x1, y1, x2, y2, stroke=INK2, sw=2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
               f'stroke-width="{sw}" stroke-linecap="round"{d}/>')


def marker(color):
    mid = "m" + color.strip("#")
    if mid not in _markers:
        _markers[mid] = (f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="5" '
                         f'markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
                         f'fill="{color}"/></marker>')
    return mid


def path(pts, color=INK2, sw=5, dash=None):
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" '
               f'stroke-linecap="butt"{ds} marker-end="url(#{marker(color)})"/>')


def step(cx, cy, lab):
    r = 22 if len(lab) == 1 else 25
    circle(cx, cy, r, INK, "#FFFFFF", 3.5)
    text(cx, cy + (9 if len(lab) == 1 else 8), lab, 26 if len(lab) == 1 else 23, 800, "#FFFFFF")


def fan(cx, cy, r=17):
    circle(cx, cy, r, "#FFFFFF", INK2, 3)
    for a in (0, 120, 240):
        out.append(f'<ellipse cx="{cx}" cy="{cy - r * 0.45:.1f}" rx="{r * 0.25:.1f}" ry="{r * 0.45:.1f}" '
                   f'fill="{INK2}" transform="rotate({a} {cx} {cy})"/>')


def pi_board(x, y, w, h):
    rect(x, y, w, h, "#166534", "#14532D", 2, 12)
    for (hx, hy) in ((x + 12, y + 12), (x + w - 12, y + 12), (x + 12, y + h - 12), (x + w - 12, y + h - 12)):
        circle(hx, hy, 5, "#FFFFFF")
    for i in range(14):
        for j in range(2):
            rect(x + 28 + i * 7.6, y + 8 + j * 8, 5, 5, "#FBBF24", None, rx=1)
    rect(x + 30, y + 40, 50, 50, "#111827", None, rx=4)
    rect(x + 90, y + 46, 26, 26, "#1F2937", None, rx=3)
    for k in range(3):
        rect(x + w - 6, y + 26 + k * 27, 20, 20, "#94A3B8", "#475569", 1.5, 3)


def server(cx, top):
    for k in range(3):
        y = top + k * 44
        rect(cx - 70, y, 140, 38, "#FFFFFF", VIOLET, 3.5, 7)
        circle(cx - 48, y + 19, 6, VIOLET)
        circle(cx - 28, y + 19, 6, "#C4B5FD")
        line(cx - 6, y + 19, cx + 50, y + 19, "#C4B5FD", 5)


def gear(cx, cy, r=20, color=AMBER):
    for k in range(8):
        out.append(f'<rect x="{cx - 5:.1f}" y="{cy - r - 7:.1f}" width="10" height="14" rx="2" fill="{color}" '
                   f'transform="rotate({k * 45} {cx} {cy})"/>')
    circle(cx, cy, r, color)
    circle(cx, cy, r * 0.42, "#FFFFFF")


def database(cx, cy, w=100, h=110):
    rx, ry = w / 2, 15
    top, bot = cy - h / 2 + ry, cy + h / 2 - ry
    out.append(f'<path d="M{cx - rx},{top} L{cx - rx},{bot} A{rx},{ry} 0 0 0 {cx + rx},{bot} L{cx + rx},{top}" '
               f'fill="#FEF3C7" stroke="{AMBER}" stroke-width="3.5"/>')
    for t in (top + (bot - top) / 3, top + 2 * (bot - top) / 3):
        out.append(f'<path d="M{cx - rx},{t:.1f} A{rx},{ry} 0 0 0 {cx + rx},{t:.1f}" fill="none" '
                   f'stroke="{AMBER}" stroke-width="2.5"/>')
    out.append(f'<ellipse cx="{cx}" cy="{top}" rx="{rx}" ry="{ry}" fill="#FDE68A" stroke="{AMBER}" '
               f'stroke-width="3.5"/>')


def clipboard(cx, cy):
    rect(cx - 45, cy - 55, 90, 110, "#FFFFFF", AMBER, 3.5, 8)
    rect(cx - 20, cy - 64, 40, 18, "#FDE68A", AMBER, 3, 4)
    for k in range(3):
        y = cy - 26 + k * 28
        rect(cx - 30, y - 9, 16, 16, "#FFFFFF", INK2, 2.5, 3)
        if k < 2:
            out.append(f'<path d="M{cx - 27},{y - 1} l4,5 l8,-10" fill="none" stroke="#15803D" '
                       f'stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>')
        line(cx - 6, y, cx + 30, y, LINE, 5)


def report(cx, cy):
    x, y, w, h = cx - 45, cy - 55, 90, 110
    out.append(f'<path d="M{x},{y} L{x + w - 22},{y} L{x + w},{y + 22} L{x + w},{y + h} L{x},{y + h} Z" '
               f'fill="#FFFFFF" stroke="{AMBER}" stroke-width="3.5" stroke-linejoin="round"/>')
    out.append(f'<path d="M{x + w - 22},{y} L{x + w - 22},{y + 22} L{x + w},{y + 22}" fill="#FDE68A" '
               f'stroke="{AMBER}" stroke-width="3" stroke-linejoin="round"/>')
    for k in range(2):
        line(x + 14, y + 22 + k * 14, x + 52, y + 22 + k * 14, LINE, 5)
    for k, bh in enumerate((22, 38, 30)):
        rect(x + 18 + k * 20, y + h - 14 - bh, 13, bh, AMBER if k == 1 else "#FCD34D", None, rx=2)


def bell(cx, cy, c=ACT):
    out.append(f'<path d="M{cx - 17},{cy + 10} Q{cx - 15},{cy + 5} {cx - 15},{cy - 4} Q{cx - 15},{cy - 20} '
               f'{cx},{cy - 21} Q{cx + 15},{cy - 20} {cx + 15},{cy - 4} Q{cx + 15},{cy + 5} {cx + 17},{cy + 10} Z" '
               f'fill="{c}"/>')
    circle(cx, cy + 16, 5, c)


def person(cx, cy, r=46, two=False):
    circle(cx, cy, r, "#F1F5F9", LINE, 3)
    if two:
        for dx in (-13, 13):
            circle(cx + dx, cy - 10, 10.5, INK2)
            out.append(f'<path d="M{cx + dx - 17},{cy + 25} Q{cx + dx - 17},{cy + 5} {cx + dx},{cy + 5} '
                       f'Q{cx + dx + 17},{cy + 5} {cx + dx + 17},{cy + 25} Z" fill="{INK2}" stroke="#F1F5F9" '
                       f'stroke-width="2.5"/>')
    else:
        circle(cx, cy - 11, 12.5, INK2)
        out.append(f'<path d="M{cx - 23},{cy + 27} Q{cx - 23},{cy + 4} {cx},{cy + 4} Q{cx + 23},{cy + 4} '
                   f'{cx + 23},{cy + 27} Z" fill="{INK2}"/>')


# ---------------------------------------------------------------- 1 house
HX0, HX1, HY0, HY1, BUS = 60, 940, 78, 285, 256
m2x = lambda m: HX0 + m * (HX1 - HX0) / 120
step(36, 40, "1")
text(72, 52, "Broiler house", 34, 800, INK, "start")
rect(HX0, HY0, HX1 - HX0, HY1 - HY0, "#FFFDF7", INK2, 4, 6)
out.append(f'<path d="M{m2x(6):.0f},172 L{m2x(111):.0f},172" stroke="#BAE6FD" stroke-width="13" fill="none" '
           f'marker-end="url(#{marker("#BAE6FD")})"/>')
rect(HX0 + 2, HY0 + 2, 17, HY1 - HY0 - 4, "#BAE6FD", None, rx=2)
for yy in range(HY0 + 8, HY1 - 6, 10):
    line(HX0 + 4, yy, HX0 + 17, yy + 6, "#0284C7", 1.4)
for i in range(3):
    fan(HX1, HY0 + (i + 1) * (HY1 - HY0) / 4)
for m in (40, 80):
    line(m2x(m), HY0 + 6, m2x(m), HY1 - 6, "#94A3B8", 3, "10 8")
for i in range(3):
    text(m2x(20 + 40 * i), HY0 + 34, f"Zone {i + 1}", 27, 600, MUTED)
line(HX0, BUS, m2x(116.8), BUS, BUSC, 6)
rect(m2x(116.8), BUS - 9, 15, 18, "#FFFFFF", BUSC, 3, 2)
for m, row, col in [(20, 0, TEAL), (60, 0, TEAL), (100, 0, TEAL), (56, 1, GREEN), (64, 1, BLUE), (104, 1, BLUE)]:
    cx = m2x(m)
    top = 122 if row == 0 else 186
    line(cx, top + 32, cx, BUS, BUSC, 3)
    circle(cx, BUS, 6, BUSC)
    rect(cx - 16, top, 32, 32, col, None, rx=6)

# ---------------------------------------------------------------- 2 cable, 3 Raspberry Pi
PX0, PX1, PY0, PY1 = 150, 310, 398, 508
path([(HX0, BUS), (26, BUS), (26, 455), (PX0 - 8, 455)], BUSC, 6)
step(26, 360, "2")
pi_board(PX0, PY0, PX1 - PX0, PY1 - PY0)
step(PX1 + 6, PY0 - 6, "3")
text(348, 432, "Raspberry Pi", 32, 800, INK, "start")
text(348, 466, "edge device", 27, 500, MUTED, "start")

# a-path: on site
FHX, FHY = 800, 492
path([(PX1 + 20, FHY), (FHX - 56, FHY)], ACT, 5, PEOPLE_D)
step(545, FHY, "4a")
bell(598, FHY - 34)
person(FHX, FHY, two=True)
text(FHX, FHY + 86, "Farm head & staff", 31, 800, INK)
path([(FHX, FHY - 50), (FHX, HY1 + 10)], TEAL, 6, FEED)
step(FHX + 44, 382, "5a")

# b-path: middleware
MX = 235
path([(MX - 20, PY1 + 2), (MX - 20, 628)])
path([(MX + 20, 628), (MX + 20, PY1 + 6)], MUTED, 3.5, ACK)
step(MX - 74, 568, "4b")
server(MX, 634)
text(330, 712, "Middleware", 32, 800, INK, "start")

# SAP
SX0, SX1, SY0, SY1 = 20, 980, 808, 1252
rect(SX0, SY0, SX1 - SX0, SY1 - SY0, "#FFFBEB", "#F2C94C", 3, 16)
text(300, 852, "SAP ECC 6.0", 32, 800, AMBER, "start")
path([(MX - 20, 766), (MX - 20, 874)])
path([(MX + 20, 874), (MX + 20, 770)], MUTED, 3.5, ACK)
step(MX - 74, 828, "5b")
FX0, FX1, FY0, FY1 = 128, 344, 878, 958
rect(FX0, FY0, FX1 - FX0, FY1 - FY0, "#FFFFFF", AMBER, 3.5, 10)
gear(FX0 + 36, (FY0 + FY1) / 2)
text(FX0 + 132, FY0 + 35, "Function", 27, 800, INK)
text(FX0 + 132, FY0 + 66, "module", 27, 800, INK)
RCX, RCY = 530, 918
database(RCX, RCY)
text(RCX, RCY + 92, "Records", 31, 800, INK)
path([(FX1 + 2, RCY - 10), (RCX - 58, RCY - 10)])
step((FX1 + RCX - 54) / 2, RCY + 28, "6b")
TCX, TCY = 236, 1112
clipboard(TCX, TCY)
text(TCX, TCY + 96, "PM notification", 31, 800, INK)
path([(TCX, FY1 + 2), (TCX, TCY - 74)])
step(TCX - 58, (FY1 + TCY - 64) / 2, "7b")
DCX, DCY = 815, 918
report(DCX, DCY)
text(DCX, 852, "Daily report", 31, 800, INK)
path([(RCX + 52, RCY - 10), (DCX - 56, RCY - 10)], INK2, 4)
path([(TCX + 50, TCY), (700, TCY), (700, RCY + 30), (DCX - 56, RCY + 30)], INK2, 4)

# people at the bottom
SPY = 1360
person(TCX, SPY)
text(TCX, SPY + 86, "Staff or farm office", 31, 800, INK)
person(DCX, SPY)
text(DCX, SPY + 86, "Farm manager", 31, 800, INK)
path([(TCX, SPY - 50), (TCX, TCY + 112)], ACT, 5, PEOPLE_D)
step(TCX + 56, 1280, "8b")
path([(DCX, DCY + 60), (DCX, SPY - 54)], ACT, 5, PEOPLE_D)
step(DCX + 50, 1140, "9b")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
       f'<defs>{"".join(_markers.values())}</defs><rect width="{W}" height="{H}" fill="#FFFFFF"/>'
       + "\n".join(out) + "</svg>")
open(os.path.join(HERE, "fig1_walkthrough.svg"), "w").write(svg)
open(os.path.join(HERE, "fig1_walkthrough.html"), "w").write(
    f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}</style>'
    f'</head><body>{svg}</body></html>')
print("ok", W, H)
