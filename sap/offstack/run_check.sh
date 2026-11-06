#!/bin/sh
# Off-stack ABAP check of the broiler-house kit: abaplint (ABAP 7.02 syntax) and the 6 ABAP Unit tests of
# ZCL_BRL_HOUSE_REPORT, run through the abaplint transpiler. Needs Node.js 20 or newer and git, with internet.
# Run: sh run_check.sh   It writes install_output.txt, lint_output.txt and unit_output.txt next to it.
cd "$(dirname "$0")" || exit 1
command -v node >/dev/null 2>&1 || { echo "Node.js is missing: install the LTS version from https://nodejs.org"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "git is missing: install it, then run this script again"; exit 1; }
echo "[1/3] Installing abaplint and the transpiler (first run only, 1-3 minutes)..."
npm install > install_output.txt 2>&1
echo "[2/3] Running abaplint..."
npm run lint > lint_output.txt 2>&1
echo "[3/3] Running the ABAP Unit tests..."
npm run unit > unit_output.txt 2>&1
echo
echo "Done. Please send these three files: install_output.txt, lint_output.txt, unit_output.txt"
