# SAP kit: function module, tables, daily house report and a test against a real SAP sandbox

**Status.** This ABAP has **not been run on an SAP system**: I could not reach SAP from where it
was written, and no ABAP syntax checker could be run either (the off-stack kit in `offstack/` runs
abaplint and the report's ABAP Unit tests on your own PC; see its README). The Python side (`../sil/sap_soap.py`)
was tested against a mock of the SOAP service (`../sil/soap_rfc_mock.py`). The sandbox test below is
what turns "met in emulation" (Table V, O4) into "met on SAP". Activation in SE11/SE37 runs SAP's
own syntax check, so fix any message it reports before testing.

Use only an SAP system you are authorised to use for research, such as a university (SAP University
Alliances) system or a sandbox your faculty provides. Do not use a company's system, or its data,
without written permission. The paper keeps any company anonymous.

## 0. Why the design looks like this

- **One function module does everything inside SAP.** BAPI_ALM_NOTIF_CREATE returns only a temporary
  number. The notification becomes real only when BAPI_ALM_NOTIF_SAVE and BAPI_TRANSACTION_COMMIT run
  in the *same* session. A stateless caller (SOAP over HTTP) therefore cannot call the three BAPIs one
  after another. The module calls them itself and commits the row and the notification together.
- **Duplicates are stopped by the assessment key, not by tRFC.** tRFC gives "exactly once" with a
  transaction ID, but only between the caller and SAP. Vendor documentation also reports that tRFC is
  not available through the SOAP service. An edge node that restarts resends the same assessment as a
  new call, so the key that rejects it must travel end to end. That is the end-to-end argument (Saltzer
  et al., 1984) cited in the paper.
- **The lock keeps the escalation count consistent.** Two calls for the same house (a retry overlapping
  a slow call) are serialised. With `_SCOPE = '2'` the lock passes to the update task and is released
  after the update. That only happens when an update module is registered, so the module calls
  `DEQUEUE` itself on the duplicate and error paths.
- **SOAP rather than PyRFC.** SAP archived PyRFC on 28 May 2026, and it needs the licensed NW RFC SDK.
  `/sap/bc/soap/rfc` ships with AS ABAP and needs only HTTP(S) and a user.
- **Tasks travel with the assessment; PM records whether they were done.** Each Moderate or Severe
  assessment carries up to three task codes from the versioned catalog (`../edge/tasks.py`,
  `task_catalog.csv`). `ZBRL_STRESS` stores them with the rule version. When an escalation opens a
  PM notification, the codes become header-level notification tasks (table `NOTIFTASK` of
  BAPI_ALM_NOTIF_CREATE, structure BAPI2080_NOTTASKI). Their status (outstanding → released →
  completed, with user and date) then records in PM whether the advice was carried out. The cause
  goes into the short text and `ZBRL_STRESS`; PM cause codes are not used, because they belong to
  notification items and damage codes that a house does not have.
- **A possible cause travels with the tasks.** The edge also sends a possible cause (`POSS_CAUSE`,
  4 characters, e.g. `COOL` "Cooling stage below the heat load"): a rule-based hint, not a
  diagnosis. It is stored in `ZBRL_STRESS` and put into the notification's short text.
- **A daily report closes the loop.** Program `Z_BRL_HOUSE_REPORT` runs every morning as a background
  job and lists, per house: data completeness, conditions, possible causes (flagging a cause that
  recurs) and the notification check (tasks completed, outstanding or overdue, and whether the house
  was back to Normal after a task was completed). Its logic is in class `ZCL_BRL_HOUSE_REPORT`, which
  reads nothing from the database, so ABAP Unit can test it; the same cases are in
  `../report/test_report.py` against the Python reference `../report/house_report.py`.
- **Moving to S/4HANA later.** The on-premise BAPI used here accepts tasks. If the module moves to an
  S/4HANA API, check that the API you use also creates notification tasks.
- **If SOAP calls are rejected**, look in SICF and SU53 first. SAP Community threads also mention SAP
  Notes on the security of the SOAP processor and on its whitelist of allowed function modules
  (reported as 1394100 and 1560878; check them in the SAP Support Portal). Ask your system
  administrator to allow function group ZBRL_FG.

---

## 1. What you need

| Item | Needed for | Notes |
|---|---|---|
| SAP ECC 6.0 or S/4HANA on-premise sandbox (AS ABAP 7.0x or later) with a developer key | everything | Any client in which you may create Z objects. |
| SAP Plant Maintenance (PM) customizing: a notification type and a functional location for the test house | PM mode only | Without PM (e.g. the ABAP Platform trial) run in LOG mode: escalations are written to `ZBRL_NOTIF` only, and the tasks stay in `ZBRL_STRESS`. |
| A task catalog (catalog type 2, code group e.g. `ZBRL`) in the notification type's catalog profile | PM mode with task codes | §4.1. Without it, set `ZBRL_TASK_GRP` blank: tasks are created as text only. |
| ICF service `/sap/bc/soap/rfc` active (transaction SICF) | the harness | It calls RFC-enabled function modules over HTTP(S). |
| Technical user (type System) with a role for function group `ZBRL_FG` | the harness | Authorization object S_RFC: RFC_TYPE = FUGR, RFC_NAME = ZBRL_FG, ACTVT = 16. Check SU53 after the first call. |

[REQUIRES AUTHOR INPUT] Which system you used (release, EhP or S/4HANA version, PM yes/no) goes into
the paper's Section V-C.

## 2. Dictionary objects (SE11)

Create everything in one package (for a sandbox, the local package `$ZBRL` is enough). Field names
must be identical in the structure and the table, because the function module uses
`MOVE-CORRESPONDING`. "Predefined type" means: in SE11 switch the field to *Predefined Type* and
enter the data type, length and decimals.

### 2.1 Structure `ZBRL_S_ASSESS` (interface of the function module)

| Field | Predefined type | Length | Dec. | Meaning |
|---|---|---|---|---|
| ASSESS_ID | CHAR | 36 | | UUID from house and window start: the idempotency key |
| FLOCK | CHAR | 20 | | Flock (production cycle) ID; test runs start with `TST` |
| HOUSE | NUMC | 3 | | House number |
| ZONE | NUMC | 2 | | Worst zone |
| WINDOW_TS | DEC | 15 | 0 | Window start, YYYYMMDDhhmmss (same format as data element TIMESTAMP) |
| LEVEL_CODE | INT1 | 3 | | 0 Normal, 1 Moderate, 2 Severe |
| CAUSE | CHAR | 30 | | e.g. `thermal+NH3` |
| EPISODE | CHAR | 1 | | `X` = first Severe window of an episode |
| THI | DEC | 5 | 2 | Temperature–humidity index, Eq. (1) |
| TDB | DEC | 5 | 2 | Dry-bulb temperature, °C |
| RH | DEC | 5 | 2 | Relative humidity, % |
| CO2 | INT4 | 10 | | ppm |
| NH3 | DEC | 5 | 1 | ppm |
| AIRSPEED | DEC | 5 | 2 | m/s |
| THVI_NOTE | INT1 | 3 | | THVI note level 0/1/2 (never changes the level) |
| AIRDIAG | CHAR | 1 | | `X` = low-air-speed diagnostic |
| N_ZONES | INT1 | 3 | | Number of zones rated |
| FUNC_LOC | CHAR | 40 | | Functional location of the house (SAPFuncLoc) |
| TASK1 | CHAR | 4 | | First task code (catalog `task_catalog.csv`), blank if Normal |
| TASK2 | CHAR | 4 | | Second task code |
| TASK3 | CHAR | 4 | | Third task code |
| RULE_VER | CHAR | 12 | | Version of the rule base and task catalog, e.g. `2026-10-v2` |
| POSS_CAUSE | CHAR | 4 | | Possible cause (`../edge/tasks.py`, POSSIBLE_CAUSES), blank if Normal |

### 2.2 Transparent table `ZBRL_STRESS`

Delivery class A, data class APPL1, size category 0, buffering not allowed.

| Field | Key | Type | Notes |
|---|---|---|---|
| MANDT | X | data element MANDT | client |
| ASSESS_ID | X | CHAR 36 | |
| FLOCK … POSS_CAUSE | | as in `ZBRL_S_ASSESS` | same names, same order |
| NOTIF_NO | | data element QMNUM | notification opened by this assessment, if any |
| CREATED_AT | | data element TIMESTAMP | when SAP stored it |
| CREATED_BY | | data element SYUNAME | technical user |

Secondary index `Z01` (non-unique): MANDT, FLOCK, HOUSE, ZONE, WINDOW_TS. It serves the
escalation count. The house report reads by FLOCK, HOUSE and WINDOW_TS; with many flocks add index
`Z02` (MANDT, FLOCK, HOUSE, WINDOW_TS).

### 2.3 Transparent table `ZBRL_NOTIF` (escalation log)

| Field | Key | Type | Notes |
|---|---|---|---|
| MANDT | X | MANDT | |
| FLOCK | X | CHAR 20 | |
| HOUSE | X | NUMC 3 | |
| ZONE | X | NUMC 2 | |
| NOTIF_TS | X | TIMESTAMP | window start of the triggering assessment |
| ASSESS_ID | | CHAR 36 | triggering assessment |
| QMNUM | | QMNUM | PM notification number (empty in LOG mode) |
| NMODE | | CHAR 4 | `PM` or `LOG` |
| CREATED_AT | | TIMESTAMP | |

### 2.4 Lock object `EZBRL_NOTIF`

Primary table `ZBRL_NOTIF`, lock mode E (write lock), lock parameters = its key fields. The function
module locks only FLOCK and HOUSE, so the lock covers all zones and times of that house. This
serialises calls for one house, which the escalation count needs (a retried call can overlap a slow
one). Activation generates `ENQUEUE_EZBRL_NOTIF` and `DEQUEUE_EZBRL_NOTIF`.

## 3. Function group `ZBRL_FG` (SE37 or SE80)

| Function module | Attributes | Source |
|---|---|---|
| `Z_BRL_STRESS_SAVE` | Remote-enabled module | `abap/Z_BRL_STRESS_SAVE.abap` |
| `Z_BRL_STRESS_POST` | Update module, start immediately | `abap/Z_BRL_STRESS_POST.abap` |
| `Z_BRL_STRESS_READ` | Remote-enabled module (test read-back; returns the PM tasks from `QMSM` in `ET_TASK`) | `abap/Z_BRL_STRESS_READ.abap` |
| `Z_BRL_TEST_RESET` | Remote-enabled module (deletes `TST…` flocks only) | `abap/Z_BRL_TEST_RESET.abap` |

Each file starts with the interface (Import/Export/Tables tab, all parameters *pass by value*);
create it in SE37 first, then paste the body. In a production system, transport only
`Z_BRL_STRESS_SAVE`, `Z_BRL_STRESS_POST` and the dictionary objects, not the two test modules.

### 3.1 House report: class and program

| Object | Transaction | Source |
|---|---|---|
| Class `ZCL_BRL_HOUSE_REPORT` (public, final) | SE24, source-code-based editor | `abap/ZCL_BRL_HOUSE_REPORT.abap`; test classes (Goto → Local Test Classes): `abap/ZCL_BRL_HOUSE_REPORT.testclasses.abap` |
| Program `Z_BRL_HOUSE_REPORT` (executable) | SE38 | `abap/Z_BRL_HOUSE_REPORT.abap` |

Create the class first (the program uses its types). Selection texts for the program: S_FLOCK
"Flock", S_HOUSE "House", P_DAYS "Report period (days)", P_NDAYS "Notifications of the last (days)",
P_INTV "Window length (s)". The report counts a PM task as completed when its completion date
(`QMSM-ERLDAT`) is filled, which IW22 does when the task is completed (system status TSCO).

## 4. Settings (STVARV, type Parameter)

| Variable | Value | Meaning |
|---|---|---|
| `ZBRL_PM_MODE` | `X` or blank | `X`: escalation creates a PM notification; blank: LOG mode |
| `ZBRL_NOTIF_TYPE` | e.g. `M1` | [REQUIRES AUTHOR INPUT] notification type configured in your sandbox |
| `ZBRL_PRIORITY` | e.g. `2` | [REQUIRES AUTHOR INPUT] priority allowed for that type |
| `ZBRL_TASK_GRP` | e.g. `ZBRL` or blank | Code group of the task catalog (§4.1); blank: tasks as text only |

### 4.2 Daily background job (the automatic report)

In SE38 save a variant `DAILY` of `Z_BRL_HOUSE_REPORT`: S_FLOCK = the current flock(s), P_DAYS = 1,
P_NDAYS = 7, P_INTV = 300. In SM36 create job `ZBRL_HOUSE_REPORT_DAILY`: step = program
`Z_BRL_HOUSE_REPORT` with variant `DAILY`; start condition daily at 06:00 (periodic); **Spool list
recipient** = the farm manager's SAP user or e-mail address. Sending the list by e-mail needs
SAPconnect (SCOT) to be configured in the system ([REQUIRES AUTHOR INPUT] whether your sandbox has
it; if not, the list stays in the spool, SP01, which is enough for the test). Run the job user in the
farm's time zone: the report takes "now" from the user's local date and time.

In PM mode the middleware sends the house's functional location: put it into a JSON file such as
`{"1": "BRL-F01-H001"}` and pass `--func-loc-map` to `middleware.py`.

### 4.1 Task catalog (PM mode)

Create code group `ZBRL` in catalog type 2 (Tasks), for example with transaction QS41, with the 13
codes of `task_catalog.csv`: the code, its short text (at most 40 characters) and, as long text, the
source of the task. Set the code group's status to released, and add it to the catalog profile of
the notification type in `ZBRL_NOTIF_TYPE` ([REQUIRES AUTHOR INPUT] which profile; ask whoever
maintains PM customizing in your sandbox). The module reads each code's short text from the
catalog for the task text. A new rule version means new or changed codes: keep old codes, so
notifications created under an older version stay readable.

## 5. Manual tests in SE37 (about 30 minutes)

Use flock `TST0-MANUAL`, house `001`, zone `01`, and run `Z_BRL_TEST_RESET` with prefix `TST0`
before you start. Record each result in the table.

| # | Input | Expected | Result |
|---|---|---|---|
| T1 | New ID A1, LEVEL_CODE 0, WINDOW_TS 20270101080000 | STORED, row in ZBRL_STRESS | |
| T2 | Same call as T1 again | DUPLICATE, still one row | |
| T3 | IDs S1, S2 with LEVEL_CODE 2, EPISODE X, CAUSE thermal, TASK1 FANS, TASK2 PADS, TASK3 PADC, RULE_VER 2026-10-v2, POSS_CAUSE COOL, at 09:00 and 10:00 | STORED twice, no notification; tasks and possible cause in the rows | |
| T4 | ID S3, as T3 at 11:00 | STORED, row in ZBRL_NOTIF (EV_NOTIF filled in PM mode) | |
| T5 | ID S4, LEVEL_CODE 2, EPISODE X at 12:00 | STORED, no new notification (count restarts after T4) | |
| T6 | ID S5 at 12:05 with LEVEL_CODE 2 and EPISODE blank | STORED, not counted | |
| T7 | PM mode, FUNC_LOC that does not exist, enough episodes to escalate | ERROR with the BAPI message, nothing stored | |
| T8 | Two SE37 sessions: hold a breakpoint after the ENQUEUE in session 1, start the same ID in session 2 | Session 2 waits, then returns DUPLICATE (or LOCKED after the enqueue wait) | |
| T9 | PM mode: open the notification of T4 in IW23 | Short text `Severe x3/24h Z01 COOL thermal`; three tasks FANS, PADS, PADC with code group ZBRL, status outstanding | |
| T10 | PM mode: in IW22 complete task FANS | Task status completed, with your user, date and time: the record that the advice was carried out | |
| T11 | PM mode, `ZBRL_TASK_GRP` blank, escalate again in zone 02 | Tasks created as text, e.g. `Task FANS rules 2026-10-v2`, without a code | |
| T12 | SE24: run the unit tests of `ZCL_BRL_HOUSE_REPORT` (Ctrl+Shift+F10) | 6 test methods, all passed | |
| T13 | SE38: run `Z_BRL_HOUSE_REPORT` for flock `TST0-MANUAL`, P_DAYS 7, P_INTV 0, after T10 | Section 4 lists the notification of T4 with FANS completed by your user and PADS, PADC outstanding (overdue once 24 h have passed); section 3 shows COOL | |
| T14 | SM36: schedule the job of §4.2 once (start immediately) | Job finished (SM37); list in the spool (SP01); with SAPconnect, the e-mail in SOST | |

## 6. Fault-injection test against the sandbox (the result for the paper)

From `kit/sil` on any PC that can reach the SAP host:

```
export SAP_PASSWORD='…'          # never put it on the command line
python3 sil_run.py --backend sap --runs 3 \
   --sap-url "https://<host>:<port>/sap/bc/soap/rfc?sap-client=<client>" \
   --sap-user <technical user> --out sil_results_sap.json
python3 summarise.py sil_results_sap.json
```

The harness replays the 141 survey windows of the open dataset through edge and middleware, injects
the same faults as in Section V-C (503 before SAP is called, acknowledgement lost after SAP
committed, reply after the client's timeout, edge crashes, middleware outages), reads the tables
back with `Z_BRL_STRESS_READ` and compares them with the independent oracle. Each run uses its own
flock prefix (`TST1-`, `TST2-`, …) and starts by deleting that prefix's earlier rows.

Pass criteria per run: `missing_windows = 0`, `duplicate_rows = 0`, `level_mismatch = 0`,
`task_mismatch = 0`, `pcause_mismatch = 0`, `notifications_created = notifications_expected` (5 per run),
`notification_trigger_mismatch = 0`, `notification_task_mismatch = 0` and
`notification_tasks = notification_tasks_expected` (15 per run), and for the house reports built from
the read-back tables `report_window_mismatch = 0` and `report_pcause_mismatch = 0`. In LOG mode the
harness takes a notification's tasks from its triggering row; in PM mode it reads them from the
notification (QMSM).
Run it first in LOG mode; repeat in PM mode if the sandbox has PM.

Before the first full run, call once with `--runs 1` and look at `runs/sap_idem_seed1/mw_stderr.log`:
if the SOAP response format differs from what `sap_soap.py` expects, the middleware logs
`sap_unavailable` for every call and the run never finishes; send me the raw response and the parser
can be adjusted.

### What to report in the paper (Section V-C and Table V, O4)

"In an SAP [release] sandbox, the same campaign over N runs stored all 141 × N assessments exactly
once with their tasks, with K resent assessments recognised as duplicates, and 5 × N notifications
[logged / opened as PM notifications with 15 × N tasks] as predicted; median call time was X ms. The
report class passed its 6 ABAP Unit tests on SAP, and the daily job listed the completed task of T10
with its user." Replace every bracket with your own numbers from `sil_results_sap.json` and T12–T14;
if anything fails, report it as it happened.
