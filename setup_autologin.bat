@echo off
title GoldAI Ultra — Auto-Login Sozlash
color 0A

echo ============================================================
echo   GoldAI Ultra — Auto-Login va Autostart O'rnatuvchi
echo ============================================================
echo.

:: Admin tekshiruvi
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [!!] Bu faylni O'NG TUGMA - "Run as administrator" bilan oching!
    echo.
    pause
    exit /b 1
)

echo [1/3] Auto-login yoqilmoqda (parolsiz Administrator)...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon   /t REG_SZ /d "1"             /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName  /t REG_SZ /d "Administrator" /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword  /t REG_SZ /d ""              /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "."            /f

echo [OK] Auto-login yoqildi

echo.
echo [2/3] Task Scheduler (SYSTEM darajasida) qo'shilmoqda...
schtasks /Create /TN "GoldAI_Ultra_Bot" /TR "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"D:\goldai_ultra_complete\goldai_ultra_complete\goldai_ultra\start_goldai.ps1\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
if %errorLevel% EQU 0 (
    echo [OK] Task Scheduler yoqildi - SYSTEM darajasida, login kerak emas
) else (
    echo [!!] Task Scheduler xatosi - lekin Startup folder va Registry allaqachon qo'shilgan
)

echo.
echo [3/3] Barcha sozlamalar tekshirilmoqda...
echo.
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon
schtasks /Query /TN "GoldAI_Ultra_Bot" /FO LIST 2>nul | findstr "Task Name\|Status\|Run As User"

echo.
echo ============================================================
echo   TAYYOR! Endi svet uchib yonganda:
echo   1. Kompyuter avtomatik yonadi
echo   2. Administrator sifatida avtomatik kiradi (parolsiz)
echo   3. GoldAI Ultra bot avtomatik ishga tushadi
echo   4. Internet uzilib qayta ulanishda watchdog bot qayta ishga tushiradi
echo ============================================================
echo.
pause
