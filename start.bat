@echo off
setlocal
cd /d "%~dp0"
set "TALK_HOME=%~dp0"
set "TALK_CONFIG=%TALK_HOME%config\config.toml"
set "PYTHONPATH=%TALK_HOME%"
set "PYTHON=python"
if exist "%TALK_HOME%.venv\Scripts\python.exe" set "PYTHON=%TALK_HOME%.venv\Scripts\python.exe"
if exist "%TALK_HOME%runtime\python\python.exe" set "PYTHON=%TALK_HOME%runtime\python\python.exe"
if not exist "%TALK_CONFIG%" (
  "%PYTHON%" -B -X utf8 -m scripts.portable_bootstrap --root "%TALK_HOME%." --apply
  if errorlevel 1 exit /b 1
)
if not exist "%TALK_HOME%config\runtime.json" (
  "%PYTHON%" -B -X utf8 -m scripts.portable_bootstrap --root "%TALK_HOME%." --apply
  if errorlevel 1 exit /b 1
)
for /f "delims=" %%P in ('""%PYTHON%" -m scripts.portable_paths --port"') do set "PORT=%%P"
if not defined PORT (echo Cannot read configured port. & exit /b 1)
set "URL=http://127.0.0.1:%PORT%"
call :health
if not errorlevel 1 goto open
"%PYTHON%" -c "import socket,sys; s=socket.socket(); s.bind(('127.0.0.1',int(sys.argv[1]))); s.close()" %PORT%
if errorlevel 1 (echo Port %PORT% is occupied and TALK health check failed. & exit /b 1)
"%PYTHON%" -B -X utf8 -m scripts.talk_runtime serve --config config\runtime.json --apply --detach
if errorlevel 1 (echo Runtime failed to start. & exit /b 1)
for /l %%N in (1,1,30) do (
  call :health
  if not errorlevel 1 goto open
  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul
)
echo TALK health check timed out. Check data\state\runtime\launcher.err and status.bat.
exit /b 1
:health
powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri ($env:URL+'/healthz') -TimeoutSec 2; if ($r.status -ne 'ok') { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%
:open
start "" "%URL%/"
exit /b 0
