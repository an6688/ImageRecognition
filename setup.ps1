$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& '.\.venv\Scripts\python.exe' -c 'from core import prepare_models; prepare_models(print)'
if ($LASTEXITCODE -ne 0) { throw 'Model download failed; rerun setup to retry' }
& '.\.venv\Scripts\python.exe' -c 'from pets import prepare_pet_model; prepare_pet_model(print)'
if ($LASTEXITCODE -ne 0) { throw 'Pet model download failed; rerun setup to retry' }
Write-Host 'Ready. Double-click Start PhotoPeople.bat.'
