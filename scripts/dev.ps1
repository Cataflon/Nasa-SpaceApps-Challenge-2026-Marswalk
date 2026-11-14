# Pornește backendul și frontendul în ferestre separate.
$root = Split-Path -Parent $PSScriptRoot

# Situl sintetic e în .gitignore: îl regenerăm dacă lipsește sau e de la o versiune veche a generatorului.
# (Mesajele sunt fără diacritice: PowerShell 5.1 citește scriptul în ANSI.)
if (-not $env:MARSWALK_SITE -or $env:MARSWALK_SITE -eq "synthetic") {
    & "$root\.venv\Scripts\python.exe" "$root\pipeline\make_synthetic_site.py" --check | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Situl sintetic lipseste sau e vechi: il regenerez..."
        & "$root\.venv\Scripts\python.exe" "$root\pipeline\make_synthetic_site.py"
    }
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; ..\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "Backend: http://localhost:8000/api/health"
Write-Host "Frontend: http://localhost:5173"
