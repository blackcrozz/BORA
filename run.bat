@echo off
setlocal enabledelayedexpansion

REM Always run from the folder where run.bat lives
cd /d "%~dp0"

title BORA AI Video Editor
color 0A

REM Check arguments
if "%~1"=="" (
    echo ============================================
    echo  BORA AI Video Editor
    echo ============================================
    echo.
    echo Usage:
    echo   run.bat video.mp4
    echo   run.bat video.mp4 --clip
    echo   run.bat video.mp4 --clip --clip-method gemini
    echo   run.bat video.mp4 --clip --clip-method llm
    echo   run.bat video.mp4 --translate id
    echo   run.bat video.mp4 --word-highlight
    echo.
    pause
    exit /b 0
)

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Check if video file exists
if not exist "%~1" (
    echo [ERROR] File not found: %~1
    echo Make sure the video file is in: %~dp0
    pause
    exit /b 1
)

REM Run the pipeline
echo ============================================
echo  Processing: %~1
echo ============================================
echo.
python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Pipeline failed. See above for details.
) else (
    echo.
    echo [DONE] Pipeline completed successfully!
)

echo.
pause