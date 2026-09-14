@echo off
rem Launch the Benford Analyzer GUI. ASCII only + CRLF line endings (cmd.exe safe).
rem Failures are reported by run_gui.py: logs\gui.log + an error dialog.
cd /d "%~dp0"
set "PY=pythonw.exe"
where pythonw.exe >nul 2>nul
if errorlevel 1 set "PY=python.exe"
where %PY% >nul 2>nul
if errorlevel 1 goto nopython
start "" "%PY%" "%~dp0run_gui.py" %*
exit /b 0

:nopython
echo.
echo [ERROR] Python 3 not found in PATH.
echo Install Python 3, or run from a terminal:  python run_gui.py
echo.
pause
exit /b 1
