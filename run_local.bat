@echo off
setlocal enabledelayedexpansion
title PDF to PPT Converter (Local Mode)
color 0A

echo.
echo ============================================
echo   PDF to Editable PPT Converter (Local)
echo   Starting application natively...
echo ============================================
echo.

:: ---- Step 1: Check Python ----
echo [1/5] Checking Python installation...
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
echo [2/5] Checking Python dependencies...
python -c "import fastapi, gradio, fitz, pptx, langchain, langgraph, PIL" >nul 2>&1
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

:: ---- Step 3: Check Ollama ----
echo.
echo [3/5] Checking Ollama...
ollama --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Ollama is not installed or not in PATH!
    echo Please install Ollama from https://ollama.com/download/windows
    echo.
    goto :end_with_pause
)
echo [OK] Ollama is installed.

:: Check if Ollama service is running
curl -sf http://localhost:11434/ >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Starting Ollama background service...
    start /B ollama serve >nul 2>&1
    timeout /t 3 /nobreak >nul
)
echo [OK] Ollama service is running.

:: ---- Step 4: Pull AI Model ----
echo.
echo [4/5] Checking AI model (qwen2.5vl:3b)...
ollama list | findstr /C:"qwen2.5vl:3b" >nul 2>&1
if !errorlevel! neq 0 (
    echo Pulling AI model (first time only, ~2GB download)...
    ollama pull qwen2.5vl:3b
    if !errorlevel! neq 0 (
        echo [WARNING] Model pull had an issue. The application will retry when processing.
    )
) else (
    echo [OK] AI model qwen2.5vl:3b is ready.
)

:: ---- Step 5: Start Application ----
echo.
echo [5/5] Launching Application...
if not exist "output" mkdir output

set OLLAMA_BASE_URL=http://localhost:11434
set OUTPUT_DIR=output
set APP_HOST=127.0.0.1
set APP_PORT=7860

echo.
echo ============================================
echo   Application is ready!
echo   Opening: http://localhost:7860
echo   Converted PPTs saved to: %cd%\output\
echo   Press Ctrl+C to stop.
echo ============================================
echo.

start http://localhost:7860
python -m uvicorn app.main:app --host 127.0.0.1 --port 7860

:end_with_pause
echo.
echo ============================================
echo   Application stopped or encountered an error.
echo ============================================
echo.
pause
