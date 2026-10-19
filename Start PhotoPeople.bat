@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup.ps1 first to install PhotoPeople.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "app.py"
