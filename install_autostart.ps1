# Optional helper: schedule the same launcher after the CURRENT USER logs in.
# MT5 IPC normally needs the interactive user session; SYSTEM-at-startup is not
# suitable and was intentionally removed.
param([switch]$Uninstall)

$TaskName = "GoldAI_Ultra_User"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $Root "START_GOLDAI.bat"

if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F
    exit $LASTEXITCODE
}

if (-not (Test-Path $Launcher)) {
    Write-Host "[!!] START_GOLDAI.bat topilmadi: $Launcher" -ForegroundColor Red
    exit 1
}

# ONLOGON under the current account preserves access to the MT5 terminal/IPC.
schtasks /Create /TN $TaskName /TR "`"$Launcher`"" /SC ONLOGON /RU $env:USERNAME /RL LIMITED /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] $TaskName yaratildi (current user login'dan keyin)." -ForegroundColor Green
    Write-Host "O'chirish: powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Uninstall"
}
