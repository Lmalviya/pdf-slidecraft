@echo off
setlocal enabledelayedexpansion
title PDF to PPT Converter - Starting...
color 0A

echo.
echo ============================================
echo   PDF to Editable PPT Converter
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

:: ---- Step 1.5: Clean up any stale or conflicting containers ----
echo [CHECK] Cleaning up any previous container instances...
docker rm -f pdf2ppt-ollama pdf2ppt-app >nul 2>&1

:: ---- Step 2: Create output directory ----
echo.
echo [STEP 1/4] Creating output directory...
if not exist "output" mkdir output
echo [OK] Output directory ready.

:: ---- Step 3: Build containers ----
echo.
echo [STEP 2/4] Building application containers...
echo            (Using cached layers if already built...)
echo.
%COMPOSE_CMD% build
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Docker build failed! See error above.
    echo.
    echo Common fixes:
    echo   - Make sure Docker Desktop is fully started
    echo   - Make sure you have internet connection
    echo   - Try running: %COMPOSE_CMD% build --no-cache
    echo.
    goto :end_with_pause
)
echo [OK] Build complete.

:: ---- Step 4: Start services ----
echo.
echo [STEP 3/4] Starting services (Ollama + App)...
%COMPOSE_CMD% up -d --remove-orphans
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Failed to start services! Resetting containers and retrying...
    docker rm -f pdf2ppt-ollama pdf2ppt-app >nul 2>&1
    %COMPOSE_CMD% up -d --remove-orphans
    if !errorlevel! neq 0 (
        echo [ERROR] Could not start containers. Check logs above.
        goto :end_with_pause
    )
)
echo [OK] Services started.

:: ---- Step 5: Wait for Ollama to be healthy ----
echo.
echo [STEP 4/4] Waiting for Ollama to be ready...
set /a OLLAMA_WAIT=0
set /a OLLAMA_MAX=20

:wait_ollama_loop
docker exec pdf2ppt-ollama ollama list >nul 2>&1
if !errorlevel! equ 0 goto :ollama_ready

set /a OLLAMA_WAIT+=1
if !OLLAMA_WAIT! geq !OLLAMA_MAX! (
    echo.
    echo [WARNING] Ollama is taking longer to respond. Proceeding to model check...
    goto :pull_model
)
echo   Waiting for Ollama to initialize... (!OLLAMA_WAIT!/%OLLAMA_MAX%)
timeout /t 3 /nobreak >nul 2>&1 || ping -n 4 127.0.0.1 >nul
goto :wait_ollama_loop

:ollama_ready
echo [OK] Ollama is ready.

:: ---- Step 6: Pull model ----
:pull_model
echo.
echo [INFO] Checking AI model (qwen2.5vl:3b)...
echo        (If not downloaded yet, it will download ~2GB now. Please wait...)
echo.
docker exec pdf2ppt-ollama ollama pull qwen2.5vl:3b
if !errorlevel! neq 0 (
    echo.
    echo [WARNING] Model pull had an issue. The app will try again on first use.
)
echo [OK] Model ready.

:: ---- Done! ----
echo.
echo ============================================
echo.
echo   Application is ready!
echo.
echo   Opening browser: http://localhost:7860
echo.
echo   Converted PPT files will be saved in:
echo       %cd%\output\
echo.
echo   To stop: press Ctrl+C or close this window.
echo.
echo ============================================
echo.

:: Open browser
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul
start http://localhost:7860

:: Show live logs
echo Showing application logs... (press Ctrl+C to stop)
echo.
%COMPOSE_CMD% logs -f app
goto :end_with_pause

:: ---- Error exit point ----
:end_with_pause
echo.
echo ============================================
echo   Script stopped or encountered an error.
echo ============================================
echo.
pause
exit /b 1
