@echo off
setlocal
cd /d "%~dp0"
set "TALK_HOME=%~dp0"
if exist "%TALK_HOME%config\config.toml" set "TALK_CONFIG=%TALK_HOME%config\config.toml"
set "PYTHONPATH=%TALK_HOME%"
set "PYTHON=python"
if exist "%TALK_HOME%runtime\python\python.exe" (
  set "PYTHON=%TALK_HOME%runtime\python\python.exe"
) else if exist "%TALK_HOME%.venv\Scripts\python.exe" (
  set "PYTHON=%TALK_HOME%.venv\Scripts\python.exe"
)
"%PYTHON%" -B -X utf8 scripts\talk_launcher.py
exit /b %errorlevel%
