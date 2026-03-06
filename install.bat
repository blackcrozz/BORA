@echo off
setlocal enabledelayedexpansion
title BORA AI Video Editor - Installer
color 0A

echo ============================================
echo  BORA AI Video Editor - Setup
echo ============================================
echo.

REM [1/6] Check Python
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+ from python.org
    pause
    exit /b 1
)
echo [OK] Python found.
echo.

REM [2/6] Check FFmpeg
echo [2/6] Checking FFmpeg...
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] FFmpeg not found. Please install FFmpeg and add it to PATH.
    echo Download from: https://ffmpeg.org/download.html
    pause
    exit /b 1
)
echo [OK] FFmpeg found.
echo.

REM [3/6] Upgrade pip
echo [3/6] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded.
echo.

REM [4/6] Install Python dependencies
echo [4/6] Installing Python dependencies...
pip install openai-whisper --quiet
pip install argostranslate --quiet
pip install python-dotenv --quiet
echo [OK] Dependencies installed.
echo.

REM [5/6] Create .env if not exists
echo [5/6] Checking .env file...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] .env created from .env.example
        echo      ^> Open .env and add your GEMINI_API_KEY if using Gemini clip method.
    ) else (
        echo GEMINI_API_KEY=your_key_here > .env
        echo [OK] .env created with placeholder.
    )
) else (
    echo [OK] .env already exists.
)
echo.

REM [6/6] Done
echo [6/6] Setup complete!
echo ============================================
echo  BORA is ready. Run with:
echo  run.bat your_video.mp4
echo ============================================
echo.
pause