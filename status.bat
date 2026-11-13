@echo off
setlocal
cd /d "%~dp0"
set "TALK_HOME=%~dp0"
set "TALK_CONFIG=%TALK_HOME%config\config.toml"
set "PYTHONPATH=%TALK_HOME%"
set "PYTHON=python"
if exist "%TALK_HOME%.venv\Scripts\python.exe" set "PYTHON=%TALK_HOME%.venv\Scripts\python.exe"
if exist "%TALK_HOME%runtime\python\python.exe" set "PYTHON=%TALK_HOME%runtime\python\python.exe"
"%PYTHON%" -B -X utf8 -m scripts.talk_runtime status --config config\runtime.json
set "RUNTIME_STATUS=%errorlevel%"
for /f "delims=" %%P in ('""%PYTHON%" -m scripts.portable_paths --port"') do set "PORT=%%P"
if not defined PORT (echo Cannot read configured port. & exit /b 1)
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri ('http://127.0.0.1:'+ $env:PORT +'/healthz') -TimeoutSec 2 | ConvertTo-Json -Compress } catch { Write-Output 'healthz unavailable' }"
exit /b %RUNTIME_STATUS%
