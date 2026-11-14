# Pornește backendul și frontendul în ferestre separate.
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; ..\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "Backend: http://localhost:8000/api/health"
Write-Host "Frontend: http://localhost:5173"
