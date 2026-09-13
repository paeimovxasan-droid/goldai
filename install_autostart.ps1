# ============================================================
# GoldAI Ultra — Windows Autostart O'rnatuvchi
# Kompyuter yonganda bot avtomatik ishga tushadi (foydalanuvchi
# tizimga kirishini ham kutmaydi — SYSTEM darajasida ishlaydi)
#
# BIR MARTA ISHGA TUSHIRING:
#   powershell -ExecutionPolicy Bypass -File install_autostart.ps1
# ============================================================

param(
    [switch]$Uninstall   # O'chirish uchun: install_autostart.ps1 -Uninstall
)

$TASK_NAME = "GoldAI_Ultra_Bot"
$BOT_DIR   = Split-Path -Parent $MyInvocation.MyCommand.Path
$PS_SCRIPT = Join-Path $BOT_DIR "start_goldai.ps1"

# Admin tekshiruvi
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host "[!!] Administrator sifatida ishga tushiring!" -ForegroundColor Red
    Write-Host "     Sichqoncha o'ng tugma -> 'Run as administrator'" -ForegroundColor Yellow
    pause
    exit 1
}

# ─── O'chirish rejimi ────────────────────────────────────────
if ($Uninstall) {
    Write-Host "Task Scheduler dan '$TASK_NAME' o'chirilmoqda..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] '$TASK_NAME' o'chirildi." -ForegroundColor Green
    } catch {
        Write-Host "[!!] Topilmadi yoki o'chirishda xato: $_" -ForegroundColor Red
    }
    pause
    exit 0
}

# ─── O'rnatish ───────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GoldAI Ultra — Autostart O'rnatuvchi" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Task nomi  : $TASK_NAME"
Write-Host "  Skript     : $PS_SCRIPT"
Write-Host ""

if (-not (Test-Path $PS_SCRIPT)) {
    Write-Host "[!!] start_goldai.ps1 topilmadi: $PS_SCRIPT" -ForegroundColor Red
    pause
    exit 1
}

# Eski taskni o'chirish (mavjud bo'lsa)
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Eski task o'chirilmoqda..."
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

# Harakatni aniqlash: PowerShell skriptni ishga tushirish
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PS_SCRIPT`"" `
    -WorkingDirectory $BOT_DIR

# Trigger: tizim yonganda (foydalanuvchi login qilmasa ham)
$trigger = New-ScheduledTaskTrigger -AtStartup

# Sozlamalar: SYSTEM darajasida, tizim yongandan 30 soniya keyin
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)   # Cheksiz ishlaydi

# Principal: SYSTEM (login kerak emas)
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Task yaratish
Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "GoldAI Ultra 24/7 Trading Bot — `$10 => `$1,000,000 Capital Growth" `
    -Force | Out-Null

# Tekshirish
$task = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($task) {
    Write-Host ""
    Write-Host "[OK] Task muvaffaqiyatli o'rnatildi!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Holat: Kompyuter yonganida avtomatik ishga tushadi" -ForegroundColor White
    Write-Host "  Qayta o'chirish: install_autostart.ps1 -Uninstall" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Hozir ishga tushirish uchun:" -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName '$TASK_NAME'" -ForegroundColor Cyan
    Write-Host ""

    # Hoziroq ishga tushirishni so'rash
    $answer = Read-Host "Hozir bot ishga tushadimi? (y/N)"
    if ($answer -match '^[Yy]') {
        Start-ScheduledTask -TaskName $TASK_NAME
        Write-Host "[OK] Bot ishga tushirildi (fonda ishlaydi)." -ForegroundColor Green
    }
} else {
    Write-Host "[!!] Task yaratishda xato!" -ForegroundColor Red
}

Write-Host ""
pause
