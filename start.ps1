# PowerShell launcher — starts all AgentFinance AI services
# Usage: .\start.ps1

Write-Host "🚀 AgentFinance AI — Starting all services..." -ForegroundColor Cyan
Write-Host ""

# Copy .env.example to .env if not exists
if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "📝 Created .env from .env.example — please update with your API keys!" -ForegroundColor Yellow
}

# Create data directory
if (-not (Test-Path ".\backend\data")) {
    New-Item -ItemType Directory -Path ".\backend\data" -Force | Out-Null
}

# Start Module07 Bureau (port 8001)
Write-Host "📦 Installing module07 dependencies..." -ForegroundColor Yellow
Start-Process -FilePath "pip" -ArgumentList "install", "-r", "requirements.txt" `
    -WorkingDirectory ".\module07" -Wait -NoNewWindow

Write-Host "🏦 Starting Module07 Bureau (M07) on port 8001..." -ForegroundColor Green
$bureau = Start-Process -FilePath "python" -ArgumentList "-m", "app.main" `
    -WorkingDirectory ".\module07" -PassThru -NoNewWindow

# Wait a moment for bureau to start
Start-Sleep -Seconds 2

# Start Backend (port 8000)
Write-Host "⚡ Starting Backend on port 8000..." -ForegroundColor Green
$backend = Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory ".\backend" -PassThru -NoNewWindow

# Wait for backend to start
Start-Sleep -Seconds 3

# Start Frontend (port 3000)
Write-Host "🎨 Starting Frontend on port 3000..." -ForegroundColor Green
$frontend = Start-Process -FilePath "npm" -ArgumentList "run","dev" -WorkingDirectory ".\frontend" -PassThru -NoNewWindow

Write-Host ""
Write-Host "✅ All services started!" -ForegroundColor Green
Write-Host "   Frontend:    http://localhost:3000" -ForegroundColor White
Write-Host "   Backend:     http://localhost:8000" -ForegroundColor White
Write-Host "   Bureau Mock: http://localhost:8001" -ForegroundColor White
Write-Host "   API Docs:    http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow

# Wait for any process to exit
try {
    Wait-Process -Id $frontend.Id
} finally {
    Write-Host "Stopping all services..." -ForegroundColor Red
    Stop-Process -Id $bureau.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue
}
