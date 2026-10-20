@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "benchmarks\run_comparison.py" %*
set "benchmark_exit=%errorlevel%"
pause
exit /b %benchmark_exit%
