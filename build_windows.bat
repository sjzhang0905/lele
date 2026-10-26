@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run start_windows.bat once before building the EXE.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.10,<7"
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name LELE --collect-all vtkmodules --collect-all ase --hidden-import vtkmodules.qt.QVTKRenderWindowInteractor launch_app.py
if errorlevel 1 goto :failed
if not exist "dist\LELE\LELE.exe" goto :failed
".venv\Scripts\python.exe" -c "from pathlib import Path; from lele import APP_TITLE; Path(r'dist\LELE\VERSION.txt').write_text(APP_TITLE + '\n', encoding='utf-8')"
if errorlevel 1 goto :failed
echo Build version: v0.9.1
echo Check dist\LELE\VERSION.txt before starting.
echo EXE folder: dist\LELE\
pause
exit /b 0
:failed
echo Build failed.
pause
exit /b 1
