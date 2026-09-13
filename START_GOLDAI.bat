@echo off
setlocal EnableExtensions EnableDelayedExpansion
title GoldAI Ultra - ForexClub MT5
color 0A

rem GoldAI Ultra single-click Windows launcher.
rem It never changes Windows auto-login or registry settings.
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "VENV=%ROOT%.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%ROOT%.env" (
    if not exist "%ROOT%.env.example" (
        echo [!!] .env.example topilmadi: %ROOT%
        pause
        exit /b 1
    )
    copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
    echo.
    echo [OK] .env yaratildi.
    echo Endi .env faylida MT5 login/parol/server va kerakli AI kalitlarini kiriting.
    echo Kalitlarni GitHub yoki Telegramga yubormang.
    echo.
    pause
    exit /b 2
)

where python >nul 2>&1
if errorlevel 1 (
    echo [!!] Python topilmadi. Python 3.10+ ni python.org dan o'rnating va PATH ga qo'shing.
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo [1/3] Izolyatsiya qilingan Python muhit yaratilmoqda...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [!!] venv yaratilmadi.
        pause
        exit /b 1
    )
)

set "STAMP=%VENV%\.goldai_requirements_v2"
if not exist "%STAMP%" (
    echo [2/3] Paketlar o'rnatilmoqda (birinchi ishga tushishda vaqt oladi)...
    "%PY%" -m pip install --upgrade pip --quiet
    "%PY%" -m pip install -r "%ROOT%requirements.txt"
    if errorlevel 1 (
        echo.
        echo [!!] Paketlar o'rnatilmadi. Internet/proxy yoki Python versiyasini tekshiring.
        pause
        exit /b 1
    )
    type nul > "%STAMP%"
) else (
    echo [2/3] Paketlar allaqachon o'rnatilgan.
)

"%PY%" -c "from pathlib import Path; print('[OK] GoldAI runtime tayyor: ' + str(Path.cwd()))"

echo.
echo [3/3] GoldAI Ultra ishga tushmoqda.
echo MT5 terminali ochiq bo'lsin, hisobga login qilingan bo'lsin va AutoTrading yoqilsin.
echo To'xtatish: Ctrl+C. Bot xato bilan chiqsa 15 soniyada qayta ishga tushadi.
echo.

:RUN
"%PY%" "%ROOT%run.py"
set "EXITCODE=!ERRORLEVEL!"
if "!EXITCODE!"=="0" goto DONE

echo.
echo [!!] Bot exit code !EXITCODE!. 15 soniyadan keyin qayta ishga tushadi...
timeout /t 15 /nobreak >nul
goto RUN

:DONE
echo.
echo GoldAI normal to'xtadi.
pause
exit /b 0
