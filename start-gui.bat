@echo off
setlocal
cd /d "%~dp0"
set "TALK_HOME=%~dp0"
set "TALK_CONFIG=%TALK_HOME%config\config.toml"
set "PYTHONPATH=%TALK_HOME%"
set "PYTHON=python"
if exist "%TALK_HOME%runtime\python\python.exe" (
  set "PYTHON=%TALK_HOME%runtime\python\python.exe"
) else if exist "%TALK_HOME%.venv\Scripts\python.exe" (
  set "PYTHON=%TALK_HOME%.venv\Scripts\python.exe"
)
if not exist "%TALK_CONFIG%" (
  "%PYTHON%" -B -X utf8 -m scripts.portable_bootstrap --root "%TALK_HOME%." --apply
  if errorlevel 1 exit /b 1
)
if not exist "%TALK_HOME%config\runtime.json" (
  "%PYTHON%" -B -X utf8 -m scripts.portable_bootstrap --root "%TALK_HOME%." --apply
  if errorlevel 1 exit /b 1
)
"%PYTHON%" -B -X utf8 scripts\talk_launcher.py
exit /b %errorlevel%
