@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup.ps1 first to install the app.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "astro_app.py"
