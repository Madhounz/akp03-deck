@echo off
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up...
  python -m venv .venv || (echo Python not found. Install it from python.org and tick "Add to PATH". & pause & exit /b)
)
if not exist .venv\deps_v5.ok (
  echo Installing packages, this takes a minute the first time...
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt || (echo Could not install the main packages. & pause & exit /b)
  rem Extras: each one is optional, so one failing never blocks the rest
  for /f "usebackq delims=" %%p in ("optional.txt") do .venv\Scripts\python -m pip install -q "%%p" || echo   skipped %%p
  echo ok> .venv\deps_v5.ok
)
start "" .venv\Scripts\pythonw.exe launcher.pyw
