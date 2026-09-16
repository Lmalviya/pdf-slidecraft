@echo off
setlocal enabledelayedexpansion
title PDF-SlideCraft - PDF to Editable PPT
color 0A

echo.
echo ============================================
echo   PDF-SlideCraft
echo   Starting application via Docker...
echo ============================================
echo.

:: ---- Step 0: Check if Docker is installed ----
echo [CHECK] Looking for Docker...
docker --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Docker is NOT installed on this system!
    echo.
    echo Please install Docker Desktop from:
    echo   https://www.docker.com/products/docker-desktop/
    echo.
    echo Alternatively, you can run locally using: run_local.bat
    echo.
    goto :end_with_pause
)
echo [OK] Docker is installed.

:: Detect Docker Compose command (docker compose vs docker-compose)
set COMPOSE_CMD=docker compose
docker compose version >nul 2>&1
if !errorlevel! neq 0 (
    set COMPOSE_CMD=docker-compose
)

:: ---- Step 1: Check if Docker daemon is running ----
echo [CHECK] Checking if Docker is running...
docker info >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Docker is not running. Attempting to start Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe" 2>nul
    if !errorlevel! neq 0 (
        start "" "%LOCALAPPDATA%\Docker\Docker Desktop.exe" 2>nul
    )
)

:: Wait for Docker to be ready (up to 2 minutes)
set /a WAIT_COUNT=0
set /a MAX_WAIT=24

:wait_docker_loop
docker info >nul 2>&1
if !errorlevel! equ 0 goto :docker_ready

set /a WAIT_COUNT+=1
if !WAIT_COUNT! geq !MAX_WAIT! (
    echo.
    echo [ERROR] Docker did not start within 2 minutes.
    echo Please start Docker Desktop manually and run this script again.
    echo.
    goto :end_with_pause
)
echo   Waiting for Docker to start... (!WAIT_COUNT!/%MAX_WAIT%)
timeout /t 5 /nobreak >nul 2>&1 || ping -n 6 127.0.0.1 >nul
goto :wait_docker_loop

:docker_ready
echo [OK] Docker is running.

:: ---- Step 2: Create output directory ----
echo.
echo [STEP 1/3] Checking environment and output directory...
if not exist "output" mkdir output
echo [OK] Output directory ready.

:: ---- Step 3: Build & Start Services ----
echo.
echo [STEP 2/3] Building & starting services (App + Ollama)...
%COMPOSE_CMD% up -d --build
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Failed to start services! Check docker logs above.
    goto :end_with_pause
)
echo [OK] Services started.

:: ---- Step 4: Ready & Open Browser ----
echo.
echo [STEP 3/3] Application is ready!
echo.
echo ============================================
echo.
echo   Web UI: http://localhost:7860
echo.
echo   Converted PPT files will be saved in:
echo       %cd%\output\
echo.
echo   [!] To stop: press Ctrl+C or close this window.
echo       All containers will be cleanly stopped.
echo.
echo ============================================
echo.

:: Open browser
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul
start http://localhost:7860

:: Stream logs attached; on Ctrl+C or exit, automatically stop containers
echo Streaming live application logs...
%COMPOSE_CMD% logs -f app

:: ---- Clean Shutdown (Preserves all data and images) ----
:cleanup
echo.
echo ============================================
echo   Stopping all PDF-SlideCraft containers...
echo   (All presentations, models, and images are preserved)
echo ============================================
%COMPOSE_CMD% stop
echo.
echo [OK] All services stopped safely.
timeout /t 2 /nobreak >nul 2>&1
exit /b 0

:: ---- Error exit point ----
:end_with_pause
echo.
echo ============================================
echo   Script stopped or encountered an error.
echo ============================================
echo.
pause
exit /b 1
