# Instalare completă: venv Python, dependențe, npm, sit sintetic.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\python.exe -m pip install numpy

& .\.venv\Scripts\python.exe pipeline\make_synthetic_site.py

Push-Location frontend
npm install
Pop-Location

Write-Host "Gata. Pornește cu: scripts\dev.ps1"
