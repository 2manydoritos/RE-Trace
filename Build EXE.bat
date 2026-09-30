@echo off
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv )
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --noconsole --onefile --name RE-Trace --icon kh2rt\icons\app.ico ^
  --add-data "kh2rt\milestones.json;kh2rt" --add-data "kh2rt\icons;kh2rt\icons" --add-data "kh2rt\fonts;kh2rt\fonts" run_tracker.py
echo.
echo Done: dist\RE-Trace.exe
pause
