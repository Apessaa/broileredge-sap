@echo off
REM Off-stack ABAP check of the broiler-house kit: abaplint (ABAP 7.02 syntax) and the 6 ABAP Unit tests of
REM ZCL_BRL_HOUSE_REPORT, run through the abaplint transpiler. Needs Node.js 20 or newer and git, with internet.
REM Double-click this file. It writes install_output.txt, lint_output.txt and unit_output.txt next to it.
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js is missing: install the LTS version from https://nodejs.org, then run this file again. & pause & exit /b 1)
where git >nul 2>nul || (echo git is missing: install it from https://git-scm.com, then run this file again. & pause & exit /b 1)
echo [1/3] Installing abaplint and the transpiler (first run only, 1-3 minutes)...
call npm install > install_output.txt 2>&1
echo [2/3] Running abaplint...
call npm run lint > lint_output.txt 2>&1
echo [3/3] Running the ABAP Unit tests...
call npm run unit > unit_output.txt 2>&1
echo.
echo Done. Please send these three files: install_output.txt, lint_output.txt, unit_output.txt
pause
