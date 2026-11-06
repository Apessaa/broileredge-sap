"""Possible causes and advisory tasks (paper v17, Section IV-C and Table III).

Every Moderate or Severe assessment carries a possible cause (a rule-based hint, not a diagnosis) and
up to three first tasks for the farm head: preventive at Moderate (act before conditions turn Severe),
corrective at Severe. Each task is a
code of at most 4 characters (the length of a task code in an SAP PM catalog) with a text of at most
40 characters (the length of a notification task's short text) and the published guidance it comes
from. Basis E: the action is stated in the cited guidance; basis I: the action is our inference.
The mapping from causes to tasks and the order of the tasks are design choices, to be evaluated with
experts (kit/expert_eval). Nothing here switches equipment: the house controller stays in charge.

Sources (printed page numbers; checked against the documents on 27 Oct 2026)
  ROSS   Aviagen, Ross Broiler Management Handbook, 2025. p.13: "Are the heaters running?", "Is the
         water pump functioning and the water being distributed evenly on the pads?", "Are the
         drinkers leaking?", litter squeeze test; p.30: "Before any temperature changes are made, the
         minimum ventilation rate must be checked"; p.31: air speed at chick level below 0.15 m/s
         (why no fan task is given before day 21); p.33: chick behaviour (Fig. 2.10) and "make routine
         air quality measurements, and adjust ventilation accordingly".
  UGA-L  C. W. Ritz, B. D. Fairchild and M. P. Lacy, Litter Quality and Broiler Performance, Univ. of
         Georgia Extension Bulletin 1267 (2005, reviewed 2026): increase minimum ventilation if ammonia
         is too high, beginning with at least 1 min out of 5; check watering systems for leaks; replace
         wet litter with clean, dry bedding; litter treatments are no substitute for good ventilation
         (why ventilation comes first).
  MED-E  Medion, All About Closed House Broiler Equipment (2023, updated 2025): "first increase the
         airspeed by the addition fan, then with the operation cooling pad"; clean dust and dirt from
         the fans every week or month.
  MED-C  Medion, Getting To Know The Closed House Cage System (2019, updated 2025): do not wet the
         cooling pad when humidity exceeds 75%; run the pad pump only above 28 C and for chickens
         older than 14 days; ensure the tightness of the fan belts so that every fan gives the same
         wind speed; adjust the inlet (curtain) opening to the desired air velocity in the house.
Independent guidance used to check the catalog and to support the possible causes (checked 28 Oct 2026)
  COBB   Cobb-Vantress, Cobb Broiler Management Guide, rev. 2012 (copy hosted by Texas A&M AgriLife):
         p.12 squeeze test; wet litter beneath drinkers -> check drinker water pressure; p.13 heaters at
         maximum output, serviced before pre-heating; p.16 chicks huddled (too cold) or spread out
         (too hot); p.21 "Always use birds' behavior and effective temperature as the ultimate guide to
         determine the correct temperature"; p.26 when air quality deteriorates, increase the run time;
         p.28 CO2 at most 3,000 ppm; inlet area matched to fan capacity; p.29 fan belts at correct
         tension; p.33 above 70% RH keep air velocity >= 3.0 m/s; p.36 no evaporative cooling above
         75% RH; p.37 evaporative cooling only above 28 C and never before all tunnel fans run.
  MSU    Tabler et al., Evaporative Cooling Systems: How and Why They Work, Mississippi State Univ.
         Extension P2774, 2019: p.3 all tunnel fans on before water trickles through the pads; p.4 poor
         fan maintenance may reduce air speed by 20% or more.
  UGA9   Czarick and Lacy, Controlling Litter Moisture and Ammonia, Poultry Housing Tips 9(3), Univ. of
         Georgia, 1997: keep house RH between 50 and 70%; ventilate before ammonia becomes a problem;
         with caked litter check drinker line height and pressure.
Version history: v1 (2026-10) first catalog; v2 (2026-10) after the check against independent guidance:
brooding-too-cold order changed to chick behaviour and heaters first (COBB p.13, p.16, p.21); possible
causes added; with low air speed the fan-belt check comes before the pad-pump check (MSU p.4; COBB p.29).
"""

RULE_VERSION = "2026-10-v2"   # stored with every assessment in SAP (field RULE_VER)
MAX_TASKS = 3

# code: (text <= 40 chars, source, page, basis E/I)
CATALOG = {
    "FANS": ("Raise fan stage to increase air speed", "MED-E", "-", "E"),
    "PADS": ("Run cooling pads after raising fan stage", "MED-E+MED-C", "-", "E"),
    "PADC": ("Check pad pump and water distribution", "ROSS", "13", "E"),
    "FANB": ("Check fan belt tension and clean fans", "MED-C+MED-E", "-", "E"),
    "INLT": ("Set inlet opening to target air speed", "MED-C", "-", "E"),
    "MVCK": ("Check minimum ventilation rate", "ROSS", "30", "E"),
    "CHBH": ("Check chick behaviour at the brooders", "ROSS", "33", "E"),
    "HEAT": ("Check that heaters/brooders are running", "ROSS", "13", "E"),
    "HTSP": ("Lower brooding set point after checks", "-", "-", "I"),
    "MVUP": ("Raise minimum ventilation (>=1 of 5 min)", "UGA-L", "-", "E"),
    "LITC": ("Squeeze-test litter, check drinker leaks", "ROSS", "13", "E"),
    "LITR": ("Replace wet litter with dry bedding", "UGA-L", "-", "E"),
    "AIRQ": ("Measure air quality, adjust ventilation", "ROSS", "33", "E"),
}

# (cause kind, level) -> tasks in the order given to the farm head (the first is the 'first task')
MAP = {
    ("heat", 1): ["FANS"],
    ("heat", 2): ["FANS", "PADS", "PADC"],          # PADS and PADC only if the pad guard allows
    ("cold", 1): ["CHBH", "HEAT", "MVCK"],          # v2: behaviour and heaters before ventilation
    ("cold", 2): ["HEAT", "CHBH", "MVCK"],
    ("hot", 1): ["CHBH", "MVCK"],
    ("hot", 2): ["CHBH", "MVCK", "HTSP"],
    ("brooding", 1): ["CHBH", "MVCK"],              # thermal cause, but T or T* missing this window
    ("brooding", 2): ["CHBH", "MVCK"],
    ("NH3", 1): ["MVUP", "LITC"],
    ("NH3", 2): ["MVUP", "LITC", "LITR"],
    ("CO2", 1): ["AIRQ"],
    ("CO2", 2): ["AIRQ"],
}
DIAG_TASKS = ["FANB", "INLT"]                       # low-air-speed diagnostic (advice only)
PAD_TASKS = ("PADS", "PADC")
PAD_RH_MAX, PAD_T_MIN, PAD_AGE_MIN_D = 75.0, 28.0, 14   # MED-C
INDICATORS = ("thermal", "NH3", "CO2")
NH3_WET_RH = 70.0                                   # UGA9: keep house RH between 50 and 70%

# code: (text <= 40 chars, sources) -- the possible cause names the situation; tasks stay as mapped
POSSIBLE_CAUSES = {
    "AIRF": ("Low airflow (fans, belts or inlet)", "COBB p.28-29; MSU p.4; MED-C"),
    "HUMH": ("Humid heat: pads would add moisture", "COBB p.33, 36; MED-C"),
    "COOL": ("Cooling stage below the heat load", "MED-E; COBB p.37; MSU p.3"),
    "HTRC": ("Heaters low or cold air reaching chicks", "ROSS p.13; COBB p.13, 16"),
    "SETP": ("Set point or heat above the target", "ROSS p.30; COBB p.21"),
    "WETL": ("Wet litter, too little min. ventilation", "UGA9; COBB p.12, 26"),
    "LITQ": ("Litter condition (caked or built-up)", "UGA-L; COBB p.12"),
    "VENT": ("Ventilation below need for fresh air", "ROSS p.33; COBB p.26, 28"),
}


def thermal_kind(week, t, t_target):
    """'heat' from week 4 (THI rule); before that 'cold' or 'hot' relative to the brooding target T*."""
    if week >= 4:
        return "heat"
    if t is None or t_target is None:
        return "brooding"
    return "cold" if t < t_target else "hot"


def pad_guard(inputs, week):
    """None if pads may run, else the reason they are withheld (MED-C)."""
    rh, t = inputs.get("RH"), inputs.get("T")
    if rh is None or t is None:
        return "pads withheld: T or RH not measured"
    if rh > PAD_RH_MAX:
        return f"pads withheld: RH {rh:.0f}% > {PAD_RH_MAX:.0f}%"
    if t <= PAD_T_MIN:
        return f"pads withheld: T {t:.1f} C <= {PAD_T_MIN:.0f} C"
    if (week - 1) * 7 <= PAD_AGE_MIN_D:          # first day of the week of age, conservative
        return f"pads withheld: birds not older than {PAD_AGE_MIN_D} days"
    return None


def assessment_tasks(level, cause, sub_levels, inputs, week, t_target=None, air_speed_diag=False,
                     max_tasks=MAX_TASKS):
    """Tasks for one assessment.

    level, cause   the (persisted) level of the assessment and the indicators at that level
                   ('thermal', 'NH3', 'CO2', joined by '+');
    sub_levels     raw levels of the indicators in this window (missing = not rated);
    inputs         zone means (T, RH, ...); t_target = brooding target T* (weeks 1-3).
    The cause indicators come first (order thermal, NH3, CO2) at the assessment's level; any other
    indicator rated Moderate or Severe this window follows at its raw level, capped at the
    assessment's level. Tasks are taken breadth-first: each indicator's first task before any
    second task, so every flagged indicator gets advice. The low-air-speed diagnostic adds its tasks
    after the others but before the pad check (PADC): when air speed is low, the airflow is checked
    before the pad pump (possible cause AIRF). At most max_tasks are kept.
    Returns (tasks, notes, thermal kind or None)."""
    if not level:
        return [], [], None
    causes = [c for c in INDICATORS if c in str(cause).split("+")]
    items = [(c, level) for c in causes]
    items += sorted(((k, min(int(v), level)) for k, v in (sub_levels or {}).items()
                     if k in INDICATORS and k not in causes and v),
                    key=lambda kv: (-kv[1], INDICATORS.index(kv[0])))
    kind_t = thermal_kind(week, inputs.get("T"), t_target) if any(k == "thermal" for k, _ in items) else None
    notes, lists = [], []
    for ind, lvl in items:
        kind = kind_t if ind == "thermal" else ind
        lst = []
        for code in MAP[(kind, lvl)]:
            if code in PAD_TASKS:
                why = pad_guard(inputs, week)
                if why:
                    if why not in notes:
                        notes.append(why)
                    continue
            lst.append(code)
        lists.append(lst)
    tasks = []
    for rank in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if rank < len(lst) and lst[rank] not in tasks:
                tasks.append(lst[rank])
    if air_speed_diag:   # v2: with low air speed the airflow checks come before the pad check
        diag = [c for c in DIAG_TASKS if c not in tasks]
        at = tasks.index("PADC") if "PADC" in tasks else len(tasks)
        tasks[at:at] = diag
    return tasks[:max_tasks], notes, kind_t


def possible_cause(level, cause, inputs, week, t_target=None, air_speed_diag=False):
    """Possible cause of the first cause indicator (a rule-based hint), or None for Normal or unknown."""
    if not level:
        return None
    causes = [c for c in INDICATORS if c in str(cause).split("+")]
    if not causes:
        return None
    rh = inputs.get("RH")
    if causes[0] == "thermal":
        kind = thermal_kind(week, inputs.get("T"), t_target)
        if kind == "heat":
            if air_speed_diag:
                return "AIRF"
            return "HUMH" if rh is not None and rh > PAD_RH_MAX else "COOL"
        return {"cold": "HTRC", "hot": "SETP"}.get(kind)
    if causes[0] == "NH3":
        return "WETL" if rh is not None and rh >= NH3_WET_RH else "LITQ"
    return "VENT"


def describe(code):
    text, src, page, basis = CATALOG[code]
    where = src if page == "-" else f"{src} p.{page}"
    return f"{code} {text} [{where}; {basis}]"


def check_catalog():
    """Structural checks used by the tests: lengths, codes, every mapped code defined and used."""
    used = {c for v in MAP.values() for c in v} | set(DIAG_TASKS)
    problems = []
    for code, (text, src, page, basis) in CATALOG.items():
        if not (code.isupper() and len(code) <= 4):
            problems.append(f"{code}: code must be <= 4 upper-case characters")
        if len(text) > 40:
            problems.append(f"{code}: text has {len(text)} > 40 characters")
        if basis not in ("E", "I") or (basis == "E") != (src != "-"):
            problems.append(f"{code}: basis E needs a source, I has none")
    problems += [f"{c}: mapped but not in the catalog" for c in used - set(CATALOG)]
    problems += [f"{c}: in the catalog but never mapped" for c in set(CATALOG) - used]
    for code, (text, src) in POSSIBLE_CAUSES.items():
        if not (code.isupper() and len(code) <= 4) or len(text) > 40 or not src:
            problems.append(f"possible cause {code}: code <= 4, text <= 40 and a source are required")
    return problems


if __name__ == "__main__":
    for c in CATALOG:
        print(describe(c))
    for c, (t, src) in POSSIBLE_CAUSES.items():
        print(f"{c} {t} [{src}]")
    print("catalog problems:", check_catalog() or "none")
