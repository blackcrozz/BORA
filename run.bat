@echo off
call venv\Scripts\activate.bat
if "%~1"=="" goto showhelp
if not exist "%~1" goto notfound
python main.py --input "%~1" %2 %3 %4 %5 %6 %7 %8 %9
pause
exit /b 0
:showhelp
echo.
echo   BORA AI Video Editor
echo   =====================
echo.
echo   Usage: run.bat video_file.mp4 [options]
echo.
echo   Examples:
echo     run.bat video.mp4
echo     run.bat video.mp4 --style tiktok
echo     run.bat video.mp4 --word-highlight
echo     run.bat video.mp4 --translate es
echo     run.bat video.mp4 --clip
echo     run.bat video.mp4 --word-highlight --translate es --clip
echo.
echo   Styles: tiktok  youtube  reels  minimal  srt
echo   Languages: es fr de ja zh ko pt it ar hi ru nl tr id vi th
echo.
pause
exit /b 0
:notfound
echo   ERROR: File not found: %~1
pause
exit /b 1
