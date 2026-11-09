@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run start_windows.bat once before building the EXE.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt "pyinstaller>=6.10,<7"
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name LELE --icon "lele\assets\lele.ico" --collect-all vtkmodules --collect-all ase --collect-data lele --hidden-import vtkmodules.qt.QVTKRenderWindowInteractor launch_app.py
if errorlevel 1 goto :failed
if not exist "dist\LELE\LELE.exe" goto :failed
".venv\Scripts\python.exe" -c "from pathlib import Path; from shutil import copy2; from lele import APP_TITLE; Path(r'dist\LELE\VERSION.txt').write_text(APP_TITLE + '\n', encoding='utf-8'); copy2('LICENSE', r'dist\LELE\LICENSE'); copy2('SOURCE_NOTICE.md', r'dist\LELE\SOURCE_NOTICE.md')"
if errorlevel 1 goto :failed
echo Build completed:
type "dist\LELE\VERSION.txt"
echo Check dist\LELE\VERSION.txt before starting.
echo EXE folder: dist\LELE\
pause
exit /b 0
:failed
echo Build failed.
pause
exit /b 1
