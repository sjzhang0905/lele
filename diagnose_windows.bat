@echo off
setlocal
cd /d "%~dp0"
echo ========= Python installations =========
py -0p
echo ========= Python selected by PATH =========
python -c "import sys,platform,struct; print('Executable:',sys.executable); print('Version:',sys.version); print('Bits:',struct.calcsize('P')*8); print('Platform:',platform.platform()); print('Machine:',platform.machine())"
echo ========= Project virtual environment =========
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys,struct; print('Executable:',sys.executable); print('Version:',sys.version); print('Bits:',struct.calcsize('P')*8)"
  ".venv\Scripts\python.exe" -m pip -V
  ".venv\Scripts\python.exe" -m pip config list
) else (
  echo No .venv was created.
)
echo ========= Done =========
pause
