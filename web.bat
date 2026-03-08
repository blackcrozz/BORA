@echo off
echo ============================================
echo  BORA Web UI
echo ============================================

cd /d %~dp0

REM Install Flask if not present
python -c "import flask" 2>nul || (
    echo Installing Flask...
    pip install flask werkzeug --break-system-packages
)

echo.
echo  Starting BORA Web UI...
echo  Open browser: http://localhost:5000
echo.

python web\app.py

pause
