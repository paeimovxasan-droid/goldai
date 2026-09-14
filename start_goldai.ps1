# Legacy PowerShell wrapper. Use START_GOLDAI.bat for the supported one-click flow.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $Root "START_GOLDAI.bat"
if (-not (Test-Path $Launcher)) {
    Write-Error "START_GOLDAI.bat topilmadi: $Launcher"
    exit 1
}
& cmd.exe /c $Launcher
exit $LASTEXITCODE
