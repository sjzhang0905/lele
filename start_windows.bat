@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LELE - launcher

rem Never silently use "py -3": it can select an unsupported Python (e.g. 3.15).
rem VTK on Windows requires a compatible 64-bit CPython wheel.
set "PYTHON_CMD="
py -3.12 -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.12"
    goto :run
)
py -3.11 -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.11"
    goto :run
)
python -c "import sys,struct; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :run
)

echo.
echo [ERROR] Compatible Python not detected.
echo LELE v1.0.1 needs 64-bit CPython 3.12 ^(preferred^) or 3.11.
echo Install Python 3.12 x64 from https://www.python.org/downloads/
echo Verify with: py -0p
echo Then double-click start_windows.bat again.
echo Note: Python 3.13/3.14/3.15 or 32-bit Python is not used by this launcher.
echo.
pause
exit /b 1

:run
echo [INFO] Using %PYTHON_CMD%
%PYTHON_CMD% windows_bootstrap.py %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo LELE did not start. See details above.
echo If installation failed, run diagnose_windows.bat and share its output.
pause
exit /b 1
