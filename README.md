# Replication package: IoT–SAP monitoring of broiler-house living conditions, with possible causes, preventive and corrective tasks and a daily SAP report (paper v34)

Python 3.9+ with only the standard library (edge, tasks, SIL, expert analysis). The rule replay
additionally needs pandas, numpy and openpyxl; the claim checker needs python-docx. The expert forms
are rebuilt with Node.js and the `docx` package.

**Paper v34.** Section V shows the system flow and how it works:
Fig. 1, Table IV and Algorithms 1–5, with our own runs on emulated sensors and under injected faults. The rule
replay on the open dataset, the check against independent guidance and the set-point comparison (`replay/`,
`validation/`) were reported in earlier versions and are no longer in the paper; they stay here unchanged.

| Folder | What it contains | Paper |
|---|---|---|
| `data/replay_records.csv` | The 1,692 complete records of the open dataset doi:10.5281/zenodo.16043470 (CC BY 4.0), with the rule levels added | V-B, V-C (test input) |
| `edge/tasks.py` | Task catalog (13 tasks, each with its source and basis E stated / I inferred), the cause-to-task mapping, the cooling-pad guard and the 8 possible causes; version `2026-10-v2` | IV-C, Table III, Algorithm 2 |
| `validation/` | Check of the catalog against independent guidance (Cobb guide 2012, MSU P2774, UGA Poultry Housing Tips 9(3)): `independent_guidance.csv` and `.py` | not in v30–v34 (earlier versions) |
| `report/` | Daily house report: reference implementation of the ABAP report (`house_report.py`), 22 tests on synthetic sequences (`test_report.py`), reports of the fault-injection runs (`report_summary.py` → `report_summary.json`) and examples (`examples/`) | IV-D, V-D |
| `replay/` | Rule replay (`replay_v13.py`), independent recomputation of the replay table of earlier versions (`table4_check.py`), bootstrap CIs and Cohen's κ (`stats_ci.py` → `stats_ci.json`), task replay (`tasks_replay.py` → `tasks_replay.json`), CO2 band sensitivity (`threshold_sensitivity.py` → `threshold_sensitivity.json`), outside comparison with a set-point alarm, alarm burden and house-flock CIs (`baseline_burden.py` → `baseline_burden.json`), claim checker (`check_claims_paper.py`) | not in v30–v34 (earlier versions); claim checker for v34 |
| `edge/` | On-device software: Modbus RTU master (`modbus_rtu.py`), sensor register maps (`devices.py`), validity checks (`acquire.py`), windows, rating, persistence, tasks and assessments (`pipeline.py`, `rules*.py`, `tasks.py`), logger, alerts and outbox (`edge_live.py`), commissioning (`commission.py`) | IV, V-A, V-B, Algorithms 1–3 |
| `edge/tests/` | Emulated sensors on a pseudo-terminal (`emulator.py`); 50 acquisition and pipeline checks, including the NH3 verify mark (`test_edge.py`); 40 task and possible-cause checks (`test_tasks.py`); end-to-end smoke test with 15 checks, including the preventive notice, the alert's possible cause and the house report (`test_live_smoke.py`); closed-loop demonstration with 9 checks: three heat episodes, one PM notification, tasks completed by a script standing in for the farm office, recovery and recurring cause in the report (`test_loop_demo.py` → `loop_demo_results.json`) | V-B, V-D |
| `sil/` | Fault-injection test of the integration: edge, middleware, mock of the SAP module, SOAP client (`sap_soap.py`) and mock SOAP service with PM-style notification tasks; the house reports are built from the stored tables of every run; `sil_run.py --backend mock / soap-mock / sap`; the middleware is `middleware.py` | V-C, V-D, Algorithm 3 |
| `sap/` | ABAP sources (function module, update module, read-back, reset; report class `ZCL_BRL_HOUSE_REPORT` with 6 ABAP Unit tests and report program `Z_BRL_HOUSE_REPORT`), setup guide for a real SAP sandbox (`SAP_KIT.md`), the task catalog for PM (`task_catalog.csv`) and the off-stack check (`offstack/`: abaplint and ABAP Unit through the abaplint transpiler, to run on your PC). **Off-stack check passed on 28 Oct 2026** (abaplint: 0 issues in 17 files against ABAP 7.02; all 6 ABAP Unit tests of the report class, transpiled; `offstack/results/`). **Not yet run on SAP** | IV-D, V-C, V-D, Algorithms 4–5 |
| `figures/` | Fig. 1, the system walkthrough with numbered steps (`fig1_walkthrough.png`, script `fig1_walkthrough.py`, rendered by `fig1_render.js`); the data model: full entity–relationship diagram (`data_model_erd.png`) and a key-attribute version (`data_model_key_attributes.png`, script `fig2_data_model.py`), no longer printed in the paper, where Table IV lists the data stores | V-A, Fig. 1, Table IV |
| `cost/` | Hardware cost per house with sources and access dates (`hardware_cost.csv`), computed by `cost.py` → `cost_summary.json` (about US$3,100 for the priced items, 29 Oct 2026; the three Sentera transmitters are priced on request) | IV-B |
| `lit/` | Literature searches run by the authors on 26–28 Oct 2026 (OpenAlex, Scopus, ScienceDirect, Garuda): queries, limits, record counts and works kept (`search_log.md`, `search_log.json`) | II, Table I |
| `bench/` | Bench-test protocol and log analysis (`bench_analysis.py`) | next cycle |
| `expert_eval/` | Expert-evaluation protocol, one anonymous 3-page rating form in Indonesian with an English translation (no questions about the expert; 7 rules on an appropriateness scale and 12 statements plus an attention check; level, possible cause and tasks of 9 recorded conditions; every answer a rating 1–5), its item and case list (`form_spec.json`), scenarios, Indonesian briefing text and script (`BRIEFING_SLIDES_ID.md`), analysis (`analyse_expert.py`: I-CVI with exact CI, modified kappa, Aiken's V, a_wg and decision rules fixed in advance), form import and data checks (`import_forms.py`, `check_responses.py`), and the aggregate results of the review reported in the paper (`results/results_expert.json`, `.md`: per-item statistics only; the per-form ratings are not shared, as the consent text promised aggregate reporting) | V-E, Table VI |

## Where Algorithms 1–5 of Section V come from

| Algorithm | Code |
|---|---|
| 1 Acquisition (steps 1–2) | `edge/acquire.py`, `edge/modbus_rtu.py`, `edge/devices.py` |
| 2 Rating, possible cause, tasks, notices (steps 3, 4a) | `edge/pipeline.py`, `edge/rules_core.py`, `edge/tasks.py`, `edge/edge_live.py` |
| 3 Outbox and middleware (steps 4b–5b) | `edge/edge_live.py` (`send_one`), `sil/middleware.py`, `sil/sap_soap.py` |
| 4 Function module (steps 6b–7b) | `sap/abap/Z_BRL_STRESS_SAVE.abap`, `sap/abap/Z_BRL_STRESS_POST.abap` |
| 5 Daily house report (step 9b) | `sap/abap/Z_BRL_HOUSE_REPORT.abap`, `sap/abap/ZCL_BRL_HOUSE_REPORT.abap`; Python reference `report/house_report.py` |

## Re-running the results in the paper

```
python3 edge/tests/test_edge.py                         # 48/48 checks, round trip of all records (about 1 min)
python3 edge/tests/test_tasks.py                        # 40/40 checks of the catalog, mapping and possible causes
python3 edge/tests/test_live_smoke.py                   # whole chain with emulated sensors, 15 checks (about 90 s)
python3 edge/tests/test_loop_demo.py                    # closed loop: episodes, notification, completion, recovery, 9 checks (about 3 min)
python3 report/test_report.py                           # 22/22 checks of the house report (synthetic sequences)
python3 validation/independent_guidance.py              # catalog v1 and v2 against independent guidance
python3 replay/tasks_replay.py                          # task and possible-cause replay on the open records (fixed seed)
python3 replay/target_sensitivity.py                    # brooding rule with Ross, Ross+k, Cobb and the houses' own targets
cd sil && python3 sil_run.py --runs 5 --root runs && python3 summarise.py sil_results.json   # about 15 min
python3 sil_run.py --backend soap-mock --runs 3 --root runs_soap --out sil_results_soapmock.json \
        && python3 summarise.py sil_results_soapmock.json sil_summary_soapmock.json
cd .. && python3 report/report_summary.py sil/runs sil/runs_soap    # house reports of every run
cd ../replay && python3 stats_ci.py                    # CIs and κ (fixed seed)
python3 replay_v13.py data.xlsx raw                    # needs data.xlsx from doi:10.5281/zenodo.16043470
python3 table4_check.py data.xlsx raw                  # replay table of earlier versions (not in v30)
cd .. && python3 replay/check_claims_paper.py paper.docx   # every kit-derived number in the paper vs. the result files
```

**Outcome measures vs. counts.** The outcome measures of the fault-injection test do not change from
run to run: no missing rows, no duplicates, the expected level and tasks in every row, the predicted
notifications with their tasks. The counts of injected faults vary slightly, because process kills
depend on timing.

**What the tests cover.** The tests cover the logic, protocol, decoding and delivery, not the
sensors' accuracy, SAP's own behaviour or whether the tasks and possible causes are the right advice.
Those are the bench test and the SAP sandbox test; the expert review (three SAP experts, Section V-E) is formative. The report tests use
synthetic sequences (labelled as such); in the replay nobody completes a task, so every reported task
is open.

**Task sources.** Ross Broiler Management Handbook 2025 (pp. 13, 30, 31, 33); University of Georgia
Extension Bulletin 1267, *Litter Quality and Broiler Performance*; Medion, *All About Closed House
Broiler Equipment* and *Getting To Know The Closed House Cage System*. One task (HTSP, lower the
brooding set point) is a design inference and is marked as such everywhere it appears. The possible
causes and the independent check add the Cobb Broiler Management Guide (rev. 2012), Mississippi State
University Extension P2774 (2019) and UGA Poultry Housing Tips 9(3) (1997).
