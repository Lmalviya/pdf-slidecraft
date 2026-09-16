@echo off
setlocal enabledelayedexpansion
title PDF-SlideCraft (Local Mode)
color 0A

echo.
echo ============================================
echo   PDF-SlideCraft (Native Local Mode)
echo   Starting application natively...
echo ============================================
echo.

:: ---- Step 1: Check Python ----
echo [1/3] Checking Python installation...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    goto :end_with_pause
)
for /f "tokens=*" %%i in ('python --version') do echo [OK] Found %%i

:: ---- Step 2: Check / Install dependencies ----
echo.
echo [2/3] Checking Python dependencies...
python -c "import fastapi, gradio, pymupdf, pptx, rapidocr_onnxruntime, cv2, PIL" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing required packages (first time only, please wait)...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Failed to install Python dependencies!
        goto :end_with_pause
    )
)
echo [OK] Python dependencies ready.

:: ---- Step 3: Start Application ----
echo.
echo [3/3] Launching Application...
if not exist "output" mkdir output

set OUTPUT_DIR=output
set APP_HOST=127.0.0.1
set APP_PORT=7860

echo.
echo ============================================
echo   Application is ready!
echo   Opening: http://localhost:7860
echo   Converted PPTs saved to: %cd%\output\
echo   Press Ctrl+C or close window to stop.
echo ============================================
echo.

timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul
start http://localhost:7860

python -m uvicorn app.main:app --host 127.0.0.1 --port 7860

echo.
echo [INFO] Application stopped cleanly.
timeout /t 2 /nobreak >nul 2>&1
exit /b 0

:end_with_pause
echo.
echo ============================================
echo   Application encountered an error.
echo ============================================
echo.
pause
exit /b 1
