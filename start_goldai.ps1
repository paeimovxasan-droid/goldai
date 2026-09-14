# ============================================================
# GoldAI Ultra — Watchdog (24/7 avtomatik qayta ishga tushiruvchi)
# Foydalanish: powershell -ExecutionPolicy Bypass -File start_goldai.ps1
# ============================================================

$BOT_DIR       = Split-Path -Parent $MyInvocation.MyCommand.Path
$SCRIPT        = Join-Path $BOT_DIR "run.py"
$LOG_DIR       = Join-Path $BOT_DIR "logs"
$STARTUP_LOG   = Join-Path $LOG_DIR "startup.log"
$RESTART_DELAY = 15

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}

function Log($msg) {
    $ts   = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $STARTUP_LOG -Value $line -Encoding UTF8
}

# Konsol kodlash
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   GoldAI Ultra - 24/7 Watchdog" -ForegroundColor Yellow
Write-Host "   `$10 => `$1,000,000 Capital Growth" -ForegroundColor Green
Write-Host "   To'xtatish: Ctrl+C" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $BOT_DIR
Log "=== GoldAI Ultra Watchdog ishga tushdi ==="

$run = 0
while ($true) {
    $run++
    Log ">>> [#$run] Bot ishga tushmoqda..."
    Write-Host ""

    # Botni shu oynaning o'zida ishga tushirish (chiqish ko'rinadi)
    python $SCRIPT --bot

    $code = $LASTEXITCODE

    if ($code -eq 0) {
        Log "Bot normal to'xtatildi (exit 0). Watchdog ham tugadi."
        break
    }

    Log "Bot to'xtadi (exit: $code). $RESTART_DELAY soniyada qayta yoqiladi..."
    Write-Host ""
    Write-Host "  [!!] $RESTART_DELAY soniyada qayta ishga tushadi..." -ForegroundColor Red

    for ($i = $RESTART_DELAY; $i -gt 0; $i--) {
        Write-Host "`r  Qayta: $i soniya...  " -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host ""
}
