@echo off
rem Debug launcher: keeps the console open so errors are visible
cd /d "%~dp0"
echo Starting Benford Analyzer (console mode) ...
python "%~dp0run_gui.py" %*
if errorlevel 1 (
    echo.
    echo [ERROR] GUI exited with an error. See logs\gui.log for details.
    pause
)
