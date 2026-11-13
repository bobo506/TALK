@echo off
setlocal
cd /d "%~dp0"
set "TALK_HOME=%~dp0"
set "TALK_CONFIG=%TALK_HOME%config\config.toml"
set "PYTHONPATH=%TALK_HOME%"
set "PYTHON=python"
if exist "%TALK_HOME%.venv\Scripts\python.exe" set "PYTHON=%TALK_HOME%.venv\Scripts\python.exe"
if exist "%TALK_HOME%runtime\python\python.exe" set "PYTHON=%TALK_HOME%runtime\python\python.exe"
"%PYTHON%" -B -X utf8 -m scripts.talk_runtime stop --config config\runtime.json --apply --wait
exit /b %errorlevel%
