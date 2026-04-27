@echo off
REM Run the CivicLens backend (Windows)
cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] venv not found. Run setup.bat first.
    pause & exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ============================================================
echo   CivicLens Backend
echo ============================================================
echo   Dashboard:  http://localhost:8000/dashboard/
echo   API docs:   http://localhost:8000/docs
echo   Health:     http://localhost:8000/api/health
echo.
echo   For mobile: find PC IP with "ipconfig", then edit
echo               mobile\app.json > extra > apiBaseUrl
echo ============================================================
echo.

cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
