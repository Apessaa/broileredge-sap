# Off-stack ABAP check: static check and unit tests on your own PC (no SAP system needed)

**Why this folder exists.** You asked for the ABAP to be run before a sandbox is available. It could
not be run where the kit was written: that environment could not reach the npm registry, and its
safety rules did not allow running third-party code downloaded from GitHub. Everything needed is in
this folder instead. On a PC with Node.js it takes about five minutes. First run (authors' PC, 28 Oct 2026; outputs in `results/2026-10-28_run1/`): abaplint 2.120.89
found **0 issues in 17 files** against ABAP 7.02. The unit tests did not run, because the library setting
pointed the transpiler at the wrong folder and the open-abap runtime (with `CL_ABAP_UNIT_ASSERT`) was never
loaded; `abap_transpile.json` was fixed. Second run (same day, `results/2026-10-28_run2/`): lint again 0 issues,
and **all 6 unit tests passed** (open-abap-core commit f735eed). Summary: `results/summary.json`.

## What it does

| Command | Tool | What it checks |
|---|---|---|
| `npm run lint` | abaplint | Parses and syntax-checks every ABAP object of the kit against **ABAP 7.02**: function group `ZBRL_FG` (4 modules), class `ZCL_BRL_HOUSE_REPORT`, program `Z_BRL_HOUSE_REPORT`, and the dictionary objects `ZBRL_S_ASSESS`, `ZBRL_STRESS`, `ZBRL_NOTIF` (`src/*.tabl.xml`, generated from `../SAP_KIT.md` §2). |
| `npm run unit` | abaplint transpiler + open-abap runtime | Translates `ZCL_BRL_HOUSE_REPORT` and its ABAP Unit test class to JavaScript and **runs the 6 unit tests** (gaps, conditions, possible causes, recurring causes, task status and the recovery check, time helpers). |

SAP standard objects (the BAPIs, `QMSM`, `TVARVC`, `QPCT`, the generated lock modules) are not in
the kit. abaplint therefore treats them as unknown ("void") and checks only our own code around
them.

**What it cannot show.** It does not replace SAP's own syntax check at activation, and it cannot run
anything that needs SAP: the BAPIs, the lock, the update task, PM notifications, or the background
job. Those are the sandbox tests T1–T14 in `../SAP_KIT.md`. Report this as an off-stack check, never
as a run on SAP.

## Steps

You need Node.js 20 LTS or newer (https://nodejs.org), git, and internet access. The transpiler
downloads the open-abap runtime library from GitHub.

**Quick way:** on Windows, double-click `run_check.cmd`; on macOS or Linux, run `sh run_check.sh`.
Each writes `install_output.txt`, `lint_output.txt` and `unit_output.txt` into this folder. Send me
all three. Use a personal laptop if a company laptop blocks npm or git.

**Step by step**, if you prefer the terminal:

```
cd kit/sap/offstack
npm install
npm run lint > lint_output.txt 2>&1
npm run unit > unit_output.txt 2>&1
```

Send me `lint_output.txt` and `unit_output.txt` (and `install_output.txt` if `npm install` failed).

**Expected result.** abaplint reports 0 issues, and all 6 test methods of `ltcl_report` pass. If
abaplint lists issues, they show file, line and rule; most first-run issues will be small 7.02 syntax
details, which I will fix in `../abap/`.

**If `npm install` fails** because a version is not found, run
`npm install --save-dev @abaplint/cli @abaplint/transpiler-cli @abaplint/runtime` and repeat the
steps.

**If `npm run unit` reports a configuration error** (the transpiler's configuration keys may have
changed), run `npx abap_transpile --help` and send me the output too.

## After changing the ABAP

The files in `src/` are generated from `../abap/*.abap`. After any change, regenerate them from `kit/`:

```
python3 sap/tools/make_offstack.py
```

## What to write in the paper if both pass

"The ABAP sources passed a static check against ABAP 7.02 (abaplint [version]), and the report logic
passed its six ABAP Unit tests after transpilation to JavaScript (abaplint transpiler [version],
open-abap runtime); this does not replace activation and testing on SAP." [REQUIRES AUTHOR INPUT]
Replace each version with the one printed by `npx abaplint --version` and `npm ls`.
