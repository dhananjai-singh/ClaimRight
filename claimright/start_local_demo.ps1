# ClaimRight free laptop backup: runs the whole app on this laptop with a free AI Studio Gemini key.
# No Google Cloud billing needed. The browser opens automatically. Stop with Ctrl+C.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$keyLine = Get-Content ".env.free" | Where-Object { $_ -match '^GOOGLE_API_KEY=\S+' }
if (-not $keyLine) {
    Write-Host "Add your AI Studio key to .env.free first (GOOGLE_API_KEY=...)." -ForegroundColor Yellow
    exit 1
}

# Pick the first free port (8080 is often taken, e.g. by Steam).
$port = $null
foreach ($p in 8090, 8091, 8092, 8093, 8094, 8095) {
    if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { $port = $p; break }
}
if (-not $port) { Write-Host "No free port found between 8090 and 8095." -ForegroundColor Red; exit 1 }

$env:CLAIMRIGHT_MODE = "free"
$env:PYTHONIOENCODING = "utf-8"
$url = "http://localhost:$port"
Write-Host "Starting ClaimRight (free mode) at $url ..." -ForegroundColor Green
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 4; Start-Process $u } -ArgumentList $url | Out-Null
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port
