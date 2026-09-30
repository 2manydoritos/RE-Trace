@echo off
setlocal
cd /d "%~dp0"
title RE:Trace

rem --- find Python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python was not found. Install Python 3.10 - 3.13 from python.org
  echo and tick "Add python.exe to PATH" during setup.
  pause & exit /b 1
)

rem --- create / repair the environment
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import PySide6" >nul 2>nul || (
    echo Previous setup was incomplete. Repairing...
    rmdir /s /q .venv
  )
)
if not exist .venv\Scripts\python.exe (
  echo Setting up for first run. This takes a minute...
  %PY% -m venv .venv || ( echo Could not create the environment. & pause & exit /b 1 )
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || (
    echo.
    echo Installing PySide6 failed. See the error above.
    .venv\Scripts\python --version
    rmdir /s /q .venv
    pause & exit /b 1
  )
)

rem --- launch; if it crashes, show the error
.venv\Scripts\python run_tracker.py %*
if errorlevel 1 (
  echo.
  echo The tracker closed with an error. Details are above and in
  echo %APPDATA%\RE-Trace\crash.log
  pause
)
