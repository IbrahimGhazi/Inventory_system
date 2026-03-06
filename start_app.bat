@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ===============================
REM Buildit Inventory – Launcher
REM ===============================

REM Get directory of this bat file
set BASE_DIR=%~dp0
set APP_DIR=%BASE_DIR%
set PYTHON_DIR=%BASE_DIR%\..\python
set PYTHON_EXE=%PYTHON_DIR%\python.exe

REM ---- Safety checks ----
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%APP_DIR%\manage.py" (
    echo [ERROR] manage.py not found
    pause
    exit /b 1
)

REM ---- Go to Django app folder ----
cd /d "%APP_DIR%"

REM ---- Upgrade pip (safe) ----
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1

REM ---- Install dependencies (first run) ----
if exist "requirements.txt" (
    "%PYTHON_EXE%" -m pip install -r requirements.txt
)

REM ---- Django setup ----
"%PYTHON_EXE%" manage.py migrate --noinput

REM ---- Collect static (optional, safe) ----
"%PYTHON_EXE%" manage.py collectstatic --noinput >nul 2>&1

REM ---- Start server ----
start "" "%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000

REM ---- Open browser ----
timeout /t 3 >nul
start http://127.0.0.1:8000/

exit
