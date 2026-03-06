@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM  BORA AI Video Editor - Auto Installer (Windows)
REM ============================================================
REM
REM  USAGE: Double-click this file, or open Command Prompt and run:
REM      install.bat
REM
REM ============================================================

title BORA AI Video Editor - Installer

echo.
echo ============================================================
echo    BORA AI Video Editor - Installer
echo ============================================================
echo.

REM ------------------------------------------------------------------
REM STEP 1: Check Python
REM ------------------------------------------------------------------
echo [1/6] Checking Python...

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo    [X] Python is NOT installed or not in your PATH.
    echo.
    echo    Please install Python first:
    echo      1. Go to: https://www.python.org/downloads/
    echo      2. Click the big yellow "Download Python" button
    echo      3. Run the installer
    echo.
    echo    *** IMPORTANT ***
    echo    At the BOTTOM of the installer, CHECK the box:
    echo        [v] Add python.exe to PATH
    echo.
    echo    Then click "Install Now".
    echo.
    echo    After installing, close this window and run install.bat again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo    [OK] Found Python %PYVER%

REM Check version is 3.10+
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo    [X] Python 3.10 or higher is required. You have %PYVER%.
    echo    Please update: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------------
REM STEP 2: Check FFmpeg
REM ------------------------------------------------------------------
echo.
echo [2/6] Checking FFmpeg...

where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo    [!] FFmpeg not found. Trying to install automatically...
    echo.

    where winget >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo    Installing via winget (this may take a minute)...
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        echo.
        echo    NOTE: You may need to CLOSE and REOPEN this window
        echo    for FFmpeg to be recognized. If you see errors about
        echo    FFmpeg later, just close this and run install.bat again.
        echo.
    ) else (
        echo    ============================================================
        echo    Could not install FFmpeg automatically.
        echo    Please install it manually:
        echo.
        echo    OPTION A - Using PowerShell as Admin:
        echo      Run:  winget install ffmpeg
        echo.
        echo    OPTION B - Manual download:
        echo      1. Go to: https://www.gyan.dev/ffmpeg/builds/
        echo      2. Download "ffmpeg-release-essentials.zip"
        echo      3. Extract to C:\ffmpeg
        echo      4. Add C:\ffmpeg\bin to your System PATH
        echo    ============================================================
        echo.
    )
) else (
    echo    [OK] FFmpeg is installed
)

REM ------------------------------------------------------------------
REM STEP 3: Create Virtual Environment
REM ------------------------------------------------------------------
echo.
echo [3/6] Creating Python virtual environment...

if exist "venv\" (
    echo    [OK] Virtual environment already exists
) else (
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo    [X] Failed to create virtual environment.
        echo    Try running: python -m pip install --upgrade pip virtualenv
        pause
        exit /b 1
    )
    echo    [OK] Virtual environment created
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip quietly
echo.
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo    [OK] pip upgraded

REM ------------------------------------------------------------------
REM STEP 5: Install Python Packages
REM ------------------------------------------------------------------
echo.
echo [5/6] Installing Python packages...
echo    This may take several minutes. Please be patient!
echo.

echo    Installing openai-whisper (speech recognition)...
pip install openai-whisper >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] openai-whisper installed
) else (
    echo    [X] openai-whisper failed. Try manually: pip install openai-whisper
)

echo.
echo    Installing argostranslate (offline translation)...
pip install argostranslate >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] argostranslate installed
) else (
    echo    [X] argostranslate failed. Try manually: pip install argostranslate
)

REM ------------------------------------------------------------------
REM STEP 6: Download Whisper Model
REM ------------------------------------------------------------------
echo.
echo [6/6] Downloading Whisper AI model (~1.5 GB, one-time download)...
echo    This will take a few minutes depending on your internet speed.
echo.

python -c "import whisper; print('    Downloading...'); model = whisper.load_model('medium'); print('    [OK] Whisper medium model downloaded and cached!')"

if %ERRORLEVEL% NEQ 0 (
    echo    [!] Model download skipped. It will download on first use.
)

REM ------------------------------------------------------------------
REM Create run.bat launcher
REM ------------------------------------------------------------------

(
echo @echo off
echo call venv\Scripts\activate.bat
echo.
echo if "%%~1"=="" (
echo     echo.
echo     echo   BORA AI Video Editor
echo     echo   =======================
echo     echo.
echo     echo   Usage: run.bat [video file] [options]
echo     echo.
echo     echo   EXAMPLES:
echo     echo     run.bat video.mp4
echo     echo       -- Basic captioning
echo     echo.
echo     echo     run.bat video.mp4 --style tiktok
echo     echo       -- TikTok style captions
echo     echo.
echo     echo     run.bat video.mp4 --word-highlight
echo     echo       -- Word-by-word highlight effect
echo     echo.
echo     echo     run.bat video.mp4 --translate es
echo     echo       -- Translate captions to Spanish
echo     echo.
echo     echo     run.bat video.mp4 --clip
echo     echo       -- Auto-generate short clips
echo     echo.
echo     echo     run.bat video.mp4 --style tiktok --word-highlight --translate es --clip
echo     echo       -- Full pipeline
echo     echo.
echo     echo   STYLES: tiktok, youtube, reels, minimal, srt
echo     echo.
echo     echo   LANGUAGES: es=Spanish, fr=French, de=German, ja=Japanese,
echo     echo              zh=Chinese, ko=Korean, pt=Portuguese, it=Italian
echo     echo.
echo     pause
echo     exit /b 0
echo ^)
echo.
echo if not exist "%%~1" (
echo     echo ERROR: File not found: %%~1
echo     echo Make sure the video file is in this folder.
echo     pause
echo     exit /b 1
echo ^)
echo.
echo python main.py --input "%%~1" %%2 %%3 %%4 %%5 %%6 %%7 %%8 %%9
echo.
echo echo.
echo echo Done! Check the "output" folder for your results.
echo echo.
echo pause
) > run.bat

REM ------------------------------------------------------------------
REM VERIFICATION
REM ------------------------------------------------------------------
echo.
echo ============================================================
echo    Verifying installation...
echo ============================================================
echo.

set PASS=0
set FAIL=0

python -c "import whisper" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] Whisper ............. installed
    set /a PASS+=1
) else (
    echo    [X]  Whisper ............. NOT installed
    set /a FAIL+=1
)

python -c "import argostranslate" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] Argos Translate ..... installed
    set /a PASS+=1
) else (
    echo    [X]  Argos Translate ..... NOT installed
    set /a FAIL+=1
)

where ffmpeg >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] FFmpeg .............. installed
    set /a PASS+=1
) else (
    echo    [X]  FFmpeg .............. NOT found (see instructions above)
    set /a FAIL+=1
)

echo.
echo ============================================================
if %FAIL% EQU 0 (
    echo    INSTALLATION COMPLETE - Everything looks good!
) else (
    echo    INSTALLATION COMPLETE - %FAIL% item(s) need attention
)
echo ============================================================
echo.
echo  HOW TO USE BORA:
echo.
echo    1. Copy your video file into this folder
echo.
echo    2. Open Command Prompt here:
echo       - Open this folder in File Explorer
echo       - Click the address bar at the top
echo       - Type: cmd
echo       - Press Enter
echo.
echo    3. Type one of these commands:
echo.
echo       run.bat video.mp4
echo         -- Transcribe and add captions
echo.
echo       run.bat video.mp4 --word-highlight
echo         -- Word-by-word highlight effect
echo.
echo       run.bat video.mp4 --translate es
echo         -- Translate captions to Spanish
echo.
echo       run.bat video.mp4 --clip
echo         -- Auto-generate short clips
echo.
echo       run.bat video.mp4 --word-highlight --translate es --clip
echo         -- Full pipeline (everything at once)
echo.
echo    4. Find your results in the "output" folder
echo.
echo    Type "run.bat" by itself to see all options.
echo.
pause
