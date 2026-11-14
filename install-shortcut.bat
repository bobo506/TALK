@echo off
rem Create a desktop shortcut that opens TALK without a console window.
setlocal
cd /d "%~dp0"
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0runtime\python\python.exe" set "PYTHON=%~dp0runtime\python\python.exe"
"%PYTHON%" -B -X utf8 "%~dp0scripts\talk_desktop.py" --install-shortcut
if errorlevel 1 (
  echo Failed to create the desktop shortcut.
  pause
  exit /b 1
)
echo Desktop shortcut "TALK" created.
pause
exit /b 0
