@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BORA AI Video Editor
color 0A

if "%~1"=="" (
    echo Usage:
    echo   run.bat video.mp4
    echo   run.bat video.mp4 --clip
    echo   run.bat video.mp4 --clip --clip-method gemini
    echo   run.bat video.mp4 --translate id
    echo   run.bat video.mp4 --word-highlight
    pause
    exit /b 0
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

if not exist "%~1" (
    echo [ERROR] File not found: %~1
    pause
    exit /b 1
)

set VIDEO=%~1
shift
set ARGS=
:loop
if "%~1"=="" goto run
set ARGS=%ARGS% %~1
shift
goto loop

:run
echo ============================================
echo  Processing: %VIDEO%
echo ============================================
echo.
python main.py --input "%VIDEO%" %ARGS%

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Pipeline failed.
) else (
    echo.
    echo [DONE] Pipeline completed!
)
pause