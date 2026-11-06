"""Check every number of the paper (v34) that comes from the kit's result files, the pseudocode against the
code, the consistency and reviewer fixes, plus citation hygiene.
Usage (from kit/): python3 replay/check_claims_paper.py paper.docx
"""
import json
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

import docx

KIT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
E = json.load(open(f'{KIT}/edge/tests/edge_test_results.json'))
TT = json.load(open(f'{KIT}/edge/tests/tasks_test_results.json'))
C = json.load(open(f'{KIT}/replay/stats_ci.json'))
T = json.load(open(f'{KIT}/replay/tasks_replay.json'))
M = json.load(open(f'{KIT}/sil/sil_summary.json'))
X = json.load(open(f'{KIT}/sil/sil_summary_soapmock.json'))
G = json.load(open(f'{KIT}/validation/independent_guidance.json'))
R = json.load(open(f'{KIT}/report/report_summary.json'))
RT = json.load(open(f'{KIT}/report/report_test_results.json'))
TS = json.load(open(f'{KIT}/replay/target_sensitivity.json'))['targets']
L = json.load(open(f'{KIT}/lit/search_log.json'))
AB = json.load(open(f'{KIT}/sap/offstack/results/summary.json'))
BB = json.load(open(f'{KIT}/replay/baseline_burden.json'))
CS = json.load(open(f'{KIT}/cost/cost_summary.json'))
THS = json.load(open(f'{KIT}/replay/threshold_sensitivity.json'))

d = docx.Document(sys.argv[1])
paras = [p.text for p in d.paragraphs]
cells = [c.text for t in d.tables for r in t.rows for c in r.cells]
text = '\n'.join(paras + cells).replace(' ', ' ').replace('​', '').replace('­', '')
r0 = lambda x: str(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
pct = lambda v: f'{r0(100 * v)}%'
pc = lambda n, d_: r0(100 * n / d_)
ci = lambda src, k: f'{r0(100 * src[k]["ci95"][0])}–{r0(100 * src[k]["ci95"][1])}%'
idem, naive, xi = M['idem'], M['naive'], X['idem']
B, ES = E['B_summary'], E['E_summary']
TCI = T['ci']
FT, TMS = T['first_task_counts'], T['records_MS']
surplus_tasks = naive['notification_tasks_total'] - naive['notification_tasks_expected_total']
checks = {
    # tests
    'edge tests all passed': E['passed'] == E['total'],
    'task tests all passed': TT['passed'] == TT['total'],
    'records round-tripped': f"{B['records']:,}" == '1,692' and '1,692 polls' in text,
    'transactions': f"({B['transactions']:,} transactions)" in text,
    'frame time 0.33 s': f"{ES['computed_frame_time_s']:.2f}" == '0.33' and '0.33 s' in text,
    'overhead within 10 ms': ES['overhead_s'] * 1000 < 10 and 'within 10 ms of the computed frame time' in text,
    # rule replay
    'O undefined 28% + CI': f"cannot rate {pct(C['O_undefined']['value'])} (CI {ci(C, 'O_undefined')})" in text,
    'abstract CI': f"28% (95% CI {ci(C, 'O_undefined')})" in text,
    'O != P + CI': f"on {pct(C['O_ne_P_where_defined']['value'])} (CI {ci(C, 'O_ne_P_where_defined')})" in text,
    'kappa O/P': f"κ = {C['kappa_O_vs_P']['value']:.2f}, CI {C['kappa_O_vs_P']['ci95'][0]:.2f}–{C['kappa_O_vs_P']['ci95'][1]:.2f}" in text,
    'week 1 THI rule': f"{pct(C['week1_MS_THI_rule']['value'])} (CI {ci(C, 'week1_MS_THI_rule')})" in text,
    'week 1 brooding': f"{pct(C['week1_MS_brooding_rule']['value'])} (CI {ci(C, 'week1_MS_brooding_rule')})" in text,
    "P' != P + kappa": f"{pct(C['P2_ne_P_thermal_weeks4to6']['value'])} (CI {ci(C, 'P2_ne_P_thermal_weeks4to6')}; κ = {C['kappa_thermal_P_vs_P2_weeks4to6']['value']:.2f})" in text,
    'NH3 10-20 share 7.2%': f"{100 * C['NH3_10_to_20']['value']:.1f}%" == '7.2%' and '(7.2%)' in text,
    # task replay
    'every M/S record got tasks': T['records_MS_with_task'] == TMS and f"all {TMS} Moderate or Severe records" in text,
    'mean tasks': f"({Decimal(str(T['task_instances'] / TMS)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} on average)" in text,
    'share E (abstract and text)': text.count(f"{pc(T['task_instances_basis_E'], T['task_instances'])}%") >= 2 and f"{T['task_instances']:,} tasks issued" in text,
    'first task CHBH + CI': f"chick behaviour in {pc(FT['CHBH'], TMS)}% (CI {ci(TCI, 'MS_first_task_CHBH_share')})" in text,
    'first task FANS + CI': f"fan stage in {pc(FT['FANS'], TMS)}% (CI {ci(TCI, 'MS_first_task_FANS_share')})" in text,
    'first task MVUP': f"NH3 in {pc(FT['MVUP'], TMS)}%" in text,
    'brooding too warm + CI': f"{pc(T['brooding_kind_counts']['hot'], T['brooding_thermal_cause_records'])}% (CI {ci(TCI, 'brooding_thermal_hot_share')})" in text,
    'cool chicks 510': f"cool chicks in {T['brooding_kind_counts']['hot']} records" in text,
    'pad guard RH and records': T['severe_heat_pads_withheld'] == 0 and f"below {r0(T['severe_heat_RH_max'])}% in all {T['severe_heat_records']} Severe heat records" in text,
    'first-task table row': all(f"{pc(T[f'first_task_counts_{n}'].get('CHBH', 0), T[f'records_MS_{n}'])}/{pc(T[f'first_task_counts_{n}'].get('FANS', 0), T[f'records_MS_{n}'])}/{pc(T[f'first_task_counts_{n}'].get('MVUP', 0), T[f'records_MS_{n}'])}" in cells for n in ('winter', 'summer')),
    'escalations brooding-warm (5 per run)': M['oracle']['notifications'] == 5 and 'all five escalations per run' in text,
    # fault injection
    'SIL request faults': f"{idem['request_faults_total']} request faults" in text and f"{idem['request_faults_total']} injected request faults" in text,
    'SIL edge crashes': text.count(f"{idem['edge_kills']} edge crashes") >= 2,
    'SIL outages': text.count(f"{idem['mw_kills']} middleware outages") >= 2,
    'SIL backlog': f"up to {idem['max_backlog_range'][1]} windows" in text,
    'SIL assessments, causes and tasks once': f"all {idem['assessments_total']} assessments were recorded exactly once with the expected level, possible cause and tasks" in text
        and idem['missing_total'] == 0 and idem['duplicate_rows_total'] == 0 and idem['level_mismatch_total'] == 0 and idem['task_mismatch_total'] == 0
        and idem['pcause_mismatch_total'] == 0,
    'SIL duplicates recognised': f"{idem['sap_duplicate_rejected']} resends" in text,
    'SIL notifications and tasks': f"exactly the {idem['notifications_created_total']} predicted notifications opened with their {idem['notification_tasks_total']} tasks" in text
        and idem['notifications_created_total'] == idem['notifications_expected_total']
        and idem['notification_tasks_total'] == idem['notification_tasks_expected_total']
        and idem['notification_trigger_mismatch_total'] == 0 and idem['notification_task_mismatch_total'] == 0,
    'SIL alerts 52': idem['local_alerts_per_run'] == [52, 52] and 'all 52 Severe windows' in text,
    'naive duplicates range': f"{naive['duplicate_rows_range'][0]}–{naive['duplicate_rows_range'][1]} duplicate rows" in text,
    'naive surplus range': f"{naive['surplus_notifications_range'][0]}–{naive['surplus_notifications_range'][1]} surplus" in text,
    'naive total duplicate rows (abstract)': f"{naive['duplicate_rows_total']} duplicate rows" in text,
    'naive surplus tasks': text.count(f"{surplus_tasks} surplus") >= 2,
    'SOAP mock 423 + 45 tasks': f"all {xi['assessments_total']} assessments exactly once" in text and f"all {xi['notification_tasks_total']} tasks" in text
        and xi['missing_total'] == 0 and xi['duplicate_rows_total'] == 0 and xi['task_mismatch_total'] == 0
        and xi['notification_tasks_total'] == xi['notification_tasks_expected_total'],
    'Table V 705 + 423': f"{idem['assessments_total']} + {xi['assessments_total']} assessments" in text,
    # hygiene
    'no tokens left': '[@' not in text,
    'no stale v15/v16 numbers': not re.search(r'279 (injected )?request faults|134 duplicate rows|131 resends|up to 66 windows|Three design principles|Four design principles|285 (injected )?request faults|136 resends|up to 64 windows|132 duplicate rows|66 surplus|Four results stand out|2026-10-v1', text),
    'tables referenced I-VI only': not re.search(r'Table VII\b', text) and all(f'Table {n}' in text for n in ('I', 'II', 'III', 'IV', 'V', 'VI')),
    'figures referenced 1-2 only': not re.search(r'Fig\. 3\b|Figs\. 1–3', text),
    'catalog version in caption': 'Catalog Version 2026-10-v2' in text and T['rule_version'] == '2026-10-v2',
    # possible causes, independent check, reports (v17)
    'possible causes in the replay': all(f"{pc(T['possible_cause_counts'][k], TMS)}%" in text for k in ('SETP', 'AIRF'))
        and f"litter in {pc(T['possible_cause_counts'].get('LITQ', 0) + T['possible_cause_counts'].get('WETL', 0), TMS)}%" in text
        and T['records_MS_without_possible_cause'] == 0,
    'independent check 6 of 7 (abstract, text, Table V)': G['first_task_agrees_v1'] == 6 and G['first_task_situations'] == 7
        and G['first_task_agrees_v2'] == 7 and text.count('six of seven situations') >= 2 and f"independent guides {G['first_task_agrees_v1']}/{G['first_task_situations']} (catalog then revised)" in text
        and 'seven of seven, is a design change, not a separate test' in text
        and G['table_matches_catalog_v2'],
    'reports: windows once, causes, overdue': f"All {R['mock_idem']['reports'] + R['soap-mock_idem']['reports']} reports counted every window" in text
        and idem['report_window_mismatch_total'] == 0 and xi['report_window_mismatch_total'] == 0
        and idem['report_pcause_mismatch_total'] == 0 and xi['report_pcause_mismatch_total'] == 0
        and R['mock_idem']['assessments_counted'] == idem['assessments_total']
        and f"each of the {idem['notifications_created_total']} notifications carried its possible cause" in text
        and set(R['mock_idem']['notification_possible_causes']) == {'SETP'}
        and f"all {idem['notification_tasks_total']} tasks were reported overdue" in text
        and R['mock_idem']['tasks'] == {'overdue': idem['notification_tasks_total']},
    'reports: SETP recurring in 7 of 8 houses': R['mock_idem']['recurring_houses']['SETP'] == 7 * R['mock_idem']['runs']
        and R['mock_idem']['reports'] == 8 * R['mock_idem']['runs'] and 'seven of the eight house-flocks' in text,
    'reports without the key': f"counted {R['mock_naive']['assessments_counted'] - idem['assessments_total']} duplicates as assessments" in text
        and f"listed {R['mock_naive']['notifications'] - R['mock_idem']['notifications']} surplus notifications" in text
        and sum(v for k, v in R['mock_naive']['notification_possible_causes'].items() if k != 'SETP') == 8 and 'eight for causes' in text
        and sum(v for k, v in R['mock_naive']['recurring_houses'].items() if k not in R['mock_idem']['recurring_houses']) == 1
        and 'one false recurring cause' in text,
    'report tests': RT['passed'] == RT['total'] and f"{RT['total']} checks on labelled synthetic sequences" in text,
    'target sensitivity (text)': all(f"{pct(TS[t]['thermal_MS_share'])} (CI {ci(TS, t).replace('ci95', '')})" in text
        for t in ()) or all(f"{r0(100 * TS[t]['thermal_MS_share'])}% (CI {r0(100 * TS[t]['thermal_MS_share_ci95'][0])}–{r0(100 * TS[t]['thermal_MS_share_ci95'][1])}%)" in text
        for t in ('ross', 'cobb', 'local'))
        and all(f"{r0(100 * TS[t]['too_warm_share_of_MS'])}%" in text for t in ('cobb', 'local'))
        and TS['ross']['escalations_per_run'] == 5 and TS['cobb']['escalations_per_run'] == 0
        and TS['local']['escalations_per_run'] == 0 and 'none of the five escalations per run remained' in text,
    'target sensitivity (Table IV row)': '/'.join(r0(100 * TS[t]['thermal_MS_share']) for t in ('ross', 'cobb', 'local')) in cells
        and all('/'.join(r0(100 * TS[t]['thermal_MS_share_by_flock'][f]) for t in ('ross', 'cobb', 'local')) in cells
                for f in ('winter', 'summer')),
    'literature search counts': f"OpenAlex (26 Oct. 2026; {L['openalex']['records']} records)" in text
        and f"Scopus ({L['scopus_erp']['records']} on ERP, {L['scopus_iot']['records_exported']:,} on IoT" in text
        and f"ScienceDirect ({L['sciencedirect']['records']})" in text and 'Garuda (28 Oct. 2026)' in text,
    'Prajna reference authors': 'U. R. Prajna, B. L. Gagan' in text and 'P. U R' not in text,
    'ABAP off-stack result': AB['lint']['issues'] == 0 and AB['unit']['failures'] == 0
        and f"abaplint found no issues in the {AB['lint']['files']} ABAP objects for release 7.02" in text
        and f"the six ABAP Unit tests" in text and AB['unit']['test_methods_run'] == 6
        and 'has not run yet' not in text and 'ABAP not yet run' not in text,
    'NH3 verify mark: 20% of records': (lambda rc, rows: f"{r0(100 * sum(rc.nh3_verify(float(r['NH3'])) for r in rows) / len(rows))}%" == '20%')(
        __import__('importlib').import_module('rules_core') if __import__('sys').path.insert(0, f'{KIT}/edge') is None else None,
        list(__import__('csv').DictReader(open(f'{KIT}/data/replay_records.csv'))))
        and "20% lay within the sensor's typical ±5 ppm error" in text and 'would carry the verify mark' in text,
    'title B and RQ consistent': 'rule-based edge intelligence' in text and 'mbedded intelligence' not in text,
    'outside comparison (set-point alarm)': (lambda L, L13, P46, U: f"P agreed with it on {r0(100 * L['agreement'])}% of records (κ = {L['kappa']:.2f}; {L13['kappa']:.2f} in weeks 1–3)" in text
        and f"P added {L['P_only_thermal_T_in_range_weeks4to6']} records of humid heat" in text
        and f"and {L['P_only_gas_only']} of NH3 or CO2" in text
        and f"the alarm flagged {L['ref_only']} records that P rated Normal, {L['ref_only_too_cold']} of them too cold" in text
        and f"missing {P46['ref_only_too_cold']} cold records after day 21" in text
        and f"The alarm would sound in {U['ctrl_alarm_windows']} of the {U['survey_windows']} survey windows; P flagged {U['ross']['MS']} ({U['local']['MS']} with the houses' targets)" in text
        and U['ross']['notifications_per_run'] == 5 and U['local']['notifications_per_run'] == 0
        and 'only five per run became SAP notifications (none with the houses' in text
        and f"set-point alarm on {r0(100 * L['agreement'])}% of records" in text)(
        BB['Plocal_vs_CTRL']['all'], BB['Plocal_vs_CTRL']['weeks1to3'], BB['P_vs_CTRL']['weeks4to6'], BB['burden']),
    'house-flock CI': f"to {r0(100 * BB['ci_house_flock']['O_undefined'][0])}–{r0(100 * BB['ci_house_flock']['O_undefined'][1])}% for the share O cannot rate" in text
        and BB['ci_house_flock']['clusters'] == 8,
    'Table I farm-test column': 'Farm test' in cells and 'Emulated only' in cells and 'Test house, 6 h' in cells,
    'summer medians explained': 'counts 5,184 observations per flock but the design yields 864' in text,
    'hardware cost sentence': f"costs about US${CS['total_usd_rounded_100']:,} per house before tax, mostly" in text
        and [m['item'] for m in CS['not_priced']] == ['Climate transmitter'] and 'except the three transmitters, priced on request' in text
        and set(CS['largest_items']) == {'RS-485 cable', 'Anemometer'} and 'mostly for the cable and the anemometer' in text,
    'CO2 band sensitivity': THS['bands']['alternative'] == [2500, 3000]
        and f"the CO2 level of {THS['co2_level_changed']} records changed but the overall level of one" in text
        and THS['P_changed'] == 1 and THS['by_bands']['alternative']['escalations_per_run'] == 5
        and 'and the five escalations per run remained' in text and '2,500 and 3,000 ppm' in text,
    'five design principles': 'Five tentative design principles' in text and all(f'DP{i},' in text for i in range(1, 6)),
}
# citations: first-appearance order (body paragraphs and tables in document order) and every reference cited
from docx.oxml.ns import qn  # noqa: E402
order_text = []
for el in d.element.body.iterchildren():
    if el.tag == qn('w:p'):
        sty = el.find(qn('w:pPr'))
        st = sty.find(qn('w:pStyle')).get(qn('w:val')) if sty is not None and sty.find(qn('w:pStyle')) is not None else ''
        if st == 'references':
            continue
        order_text.append(''.join(t.text or '' for t in el.iter(qn('w:t'))))
    elif el.tag == qn('w:tbl'):
        order_text.append(''.join(t.text or '' for t in el.iter(qn('w:t'))))
refs = [p for p in d.paragraphs if p.style.name == 'references']
seen = []
for m in re.finditer(r'\[(\d+)(?:, pp?\. [0-9, –]+)?\]', '\n'.join(order_text)):
    n = int(m.group(1))
    if n not in seen:
        seen.append(n)
# v28: PM defined at first use, why PM, and what the no-PM mode loses
checks['PM defined at first use'] = ('SAP Plant Maintenance (PM)' in text and
                                     text.find('SAP Plant Maintenance (PM)') < text.find('PM notification'))
checks['why PM notifications'] = "PM notification, SAP's standard record of work needed at a location" in text
checks['no-PM mode stated'] = 'only logged and task completion is not recorded' in text
# v29: Section IV as a walkthrough; the pseudocode must match the code in the kit
def src(rel):
    return open(f'{KIT}/{rel}', encoding='utf-8').read()
checks['walkthrough: Fig. 1 steps, Algorithms 1-5, Table IV'] = (
    'On site (a)' in text and 'To SAP (b)' in text and all(f'Algorithm {i}:' in text for i in range(1, 6))
    and 'Data Stores Read or Written by Each Part' in text and 'Fig. 2' not in text
    and 'Entity relationship diagram' not in text)
checks['acknowledgment matches the new figures'] = ('summarise it as Algorithms 1–5' in text and 'redraw Fig. 2' not in text
                                                    and 'produce Fig. 1 and Table IV' in text)
_acq, _live, _mw = src('edge/acquire.py'), src('edge/edge_live.py'), src('sil/middleware.py')
_save, _rep, _tk = src('sap/abap/Z_BRL_STRESS_SAVE.abap'), src('sap/abap/Z_BRL_HOUSE_REPORT.abap'), src('edge/tasks.py')
_post, _pipe, _rc = src('sap/abap/Z_BRL_STRESS_POST.abap'), src('edge/pipeline.py'), src('edge/rules_core.py')
checks['Alg. 1 = acquire.py (30 min stuck, flags)'] = ('STUCK_S = 30 * 60' in _acq and all(
    f in _acq for f in ('"device_fault"', '"range"', '"warmup"', '"stuck"', '"maintenance"', '"comm:"'))
    and 'unchanged for 30 min' in text)
checks['Alg. 2 = pipeline/tasks (2 up, 3 down; pad guard; notices)'] = (
    'PAD_RH_MAX, PAD_T_MIN, PAD_AGE_MIN_D = 75.0, 28.0, 14' in _tk and 'UP, DOWN = 2, 3' in _pipe and 'NH3_SENSOR_ERR = 5.0' in _rc
    and 'ass["level"] == 1 and prev_level == 0' in _live and 'ass["level"] == 2 and ass["episode_start"]' in _live
    and 'T > 28 °C, RH ≤ 75% and a > 14 d' in text and '2 windows (up) or 3 (down)' in text)
checks['Alg. 3 = edge_live/middleware (20 per poll, stored/duplicate, 400/503)'] = (
    'for _ in range(20)' in _live and '("stored", "duplicate")' in _live and 'CREATE TABLE IF NOT EXISTS outbox' in _live
    and '_reply(400' in _mw and '_reply(503' in _mw and '"/assessments"' in _mw and 'at most 20 times' in text)
checks['Alg. 4 = Z_BRL_STRESS_SAVE (lock, duplicate, >=3, PM mode, update task)'] = (
    "ENQUEUE_EZBRL_NOTIF" in _save and "ev_status = 'DUPLICATE'" in _save and 'lv_count >= 3' in _save
    and "'ZBRL_PM_MODE'" in _save and 'FROM qpct' in _save and "'Z_BRL_STRESS_POST' IN UPDATE TASK" in _save
    and "'LOCKED'" in _save and 'INSERT zbrl_stress' in _post and 'INSERT zbrl_notif' in _post
    and 'n ≥ 3' in text and 'EZBRL_NOTIF' in text)
checks['Alg. 5 = Z_BRL_HOUSE_REPORT (1 day, 7 days, QMSM, 5-min windows)'] = (
    'p_days  TYPE i DEFAULT 1' in _rep and 'p_ndays TYPE i DEFAULT 7' in _rep and 'p_intv  TYPE i DEFAULT 300' in _rep
    and 'FROM qmsm' in _rep and 'FROM zbrl_notif' in _rep and 'notifications of the last 7 days' in text)
# v30: Section V remade: the replay on others' data is gone, Section V shows the flow
REMOVED = ['O undefined 28% + CI', 'abstract CI', 'O != P + CI', 'kappa O/P', 'week 1 THI rule', 'week 1 brooding',
           "P' != P + kappa", 'NH3 10-20 share 7.2%', 'every M/S record got tasks', 'mean tasks',
           'share E (abstract and text)', 'first task CHBH + CI', 'first task FANS + CI', 'first task MVUP',
           'brooding too warm + CI', 'cool chicks 510', 'pad guard RH and records', 'first-task table row',
           'escalations brooding-warm (5 per run)', 'tables referenced I-VI only', 'possible causes in the replay',
           'independent check 6 of 7 (abstract, text, Table V)', 'target sensitivity (text)',
           'target sensitivity (Table IV row)', 'NH3 verify mark: 20% of records', 'outside comparison (set-point alarm)',
           'house-flock CI', 'summer medians explained', 'CO2 band sensitivity']
for k in REMOVED:
    del checks[k]
checks['tables referenced I-V only'] = not re.search(r'Table VI\b', text) and all(f'Table {n}' in text for n in
                                                                                   ('I', 'II', 'III', 'IV', 'V'))
checks['replay on others\' data removed everywhere'] = not any(x in text for x in (
    'Record-Level Replay', 'set-point alarm', '95% CI', 'Seven results stand out', 'independent guides 6/7',
    'six of seven situations', '(CI ', 'κ =', 'O is used below'))
checks['Section V shows the flow'] = all(h in text for h in (
    'System Flow and Demonstration', 'Flow of the System', 'Acquisition and Rating on the Edge (Steps 1–4a)',
    'Delivery and Escalation in SAP (Steps 4b–7b)', 'Task Follow-up and Daily Report (Steps 8b–9b)'))
checks['abstract and Table V use only our runs'] = (
    f"all {B['records']:,} open-data records exactly" in text
    and f"{idem['assessments_total']} assessments as expected (mocks)" in text
    and 'and 12 of 13 tasks (Table III)' in text and 'Partly (EVAL3)' not in text)
# v33: the 14 consistency fixes after Section V was remade
_ot = '\n'.join(order_text)
checks['v33 #1 test data introduced in V-B'] = ('1,728 records, 1,692 of them complete' in text and 'Cobb 500' in text
    and f"{BB['burden']['survey_windows']} survey windows in all" in text and 'eight house-flocks, weeks 1–6' in text)
checks['v33 #2 Ross target explained (practice, DP2)'] = ('which these Cobb houses deliberately exceeded' in text
    and 'applying the Ross target to Cobb birds brooded near 33 °C' in text)
checks['v33 #3 no unused O/P labels'] = 'rule set (O)' not in text and 'rules (P)' not in text
checks['v33 #4 no undefined replay or oracle'] = ('oracle' not in text and 'in a replay' not in text
    and "replaying the dataset's 141 survey windows" in text)
checks['v33 #5 138 duplicate rows stated in V-C'] = f"({naive['duplicate_rows_total']} in all)" in text
checks['v33 #6 house-flocks consistent'] = ('eight houses' not in text and 'eight house flocks' not in text
    and text.count('house-flocks') >= 3)
checks['v33 #7 Algorithm 5 says outstanding'] = 'or outstanding' in text and 'or open' not in text
checks['v33 #8 Algorithm 2 covers step 4b'] = 'steps 3, 4a, 4b' in text
checks['v33 #9 O3 evidence names possible causes'] = 'possible cause (IV-C)' in text
checks['v33 #10 no repeated opening sentence'] = ('This section follows one reading' not in text
    and text.count('Fig. 1 follows one reading through the system') == 1
    and text.count('Table IV lists the data stores each step reads or writes') == 1)
checks['v33 #11 mock SAP tables'] = 'report from the mock SAP tables' in text
checks['v33 #12 V-B: algorithms before the run'] = _ot.find('Algorithm 2:') < _ot.find('The test input is an open dataset')
checks['v33 #13 IV-D keeps reasons, steps in algorithms'] = ('BAPI_ALM_NOTIF_CREATE, then' not in text
    and 'As SOAP calls are stateless' in text)
checks['v33 #14 catalog revision points to its results'] = 'independent guidance (results in the replication package)' in text
# v34: fixes for the reviewer concerns (#13 AI disclosure and #14 anonymous link need the authors)
LOOP = json.load(open(f'{KIT}/edge/tests/loop_demo_results.json'))
checks['v34 #1 rules checked against their sources (40 task checks)'] = (TT['passed'] == TT['total'] == 40
    and '40 task checks compare the rules with their sources' in text)
checks['v34 #2/#5 closed loop end to end (3 episodes, 1 notification, completion, recovery)'] = (
    LOOP['passed'] == LOOP['total'] == 9 and LOOP['episodes'] == 3 and LOOP['notifications'] == 1
    and LOOP['report_recovery'] == {'back to Normal': len(LOOP['tasks'])}
    and f"({', '.join(LOOP['tasks'])}; possible cause {LOOP['possible_cause']})" in text
    and 'All nine checks passed in each of three runs' in text and 'the house back to Normal within three windows' in text)
checks['v34 #3 what is new, plainly'] = 'a closed loop that none of these works offers' in text
checks['v34 #4 Ross escalations named as a parameter error; loop escalation from heat stress'] = (
    'a parameter error that the report exposes' in text and 'the escalation followed heat stress' in text)
checks['v34 #6 IV-C no longer repeats Algorithm 2'] = 'Every 5 min, Algorithm 2 averages' not in text
checks['v34 #7 tentative principles with this paper\'s evidence'] = ('Five tentative design principles' in text
    and 'all remain to be tested in the field' in text)
checks['v34 #8 practitioner sources explained'] = 'the practitioner sources farms follow' in text
checks['v34 #9 no overclaim'] = 'turns monitoring into management' not in text
checks['v34 #10 why ECC 6.0'] = 'oldest SAP release still maintained' in text
checks['v34 #11 adoption needs'] = 'For adoption, a farm needs SAP PM with a functional location per house' in text
checks['v34 #12 acronyms spelled out'] = all(x in text for x in (
    'Internet of Things (IoT)', 'enterprise resource planning (ERP)', 'uninterruptible power supply (UPS)',
    'universally unique identifier (UUID)', 'remote function calls (RFC)',
    'business application programming interfaces (BAPIs)', 'the relative humidity RH', 'LLM: large language model'))
checks['citations in first-appearance order'] = seen == list(range(1, len(seen) + 1))
checks['every reference cited'] = len(seen) == len(refs)
bad = [k for k, ok in checks.items() if not ok]
for k, ok in checks.items():
    print('OK  ' if ok else 'FAIL', k)
print(f'{len(checks) - len(bad)}/{len(checks)} checks passed; references: {len(refs)}')
sys.exit(1 if bad else 0)
