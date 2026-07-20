@echo off
REM Aufgabenplaner-Wrapper fuer update_terminal.py (Windows).
REM Wechselt ins Skriptverzeichnis und loggt nach update.log.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
echo ----- %date% %time% ----- >> "%~dp0update.log"
%PY% "%~dp0update_terminal.py" >> "%~dp0update.log" 2>&1
