@echo off
REM ═══════════════════════════════════════════════════════════════
REM  Set the mobile app's backend URL to this PC's current LAN IP.
REM  Run this once before `npx expo start --tunnel` (or before
REM  `npx expo start` on LAN mode) to make the mobile app point to
REM  the right backend.
REM ═══════════════════════════════════════════════════════════════

cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [ERROR] venv not found. Run setup.bat first.
    pause & exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ============================================================
echo   Detecting this PC's LAN IP and updating mobile app config
echo ============================================================
echo.

python -c "import socket, json, os; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 53)); ip = s.getsockname()[0]; s.close(); print('Detected IP:', ip); p = 'mobile/app.json'; d = json.load(open(p)); d['expo']['extra']['apiBaseUrl'] = f'http://{ip}:8000'; json.dump(d, open(p, 'w'), indent=2); print(f'Updated {p}  -> apiBaseUrl: http://{ip}:8000')"

if errorlevel 1 (
    echo.
    echo [ERROR] Could not detect IP or update app.json. See output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   Done! Now restart Expo with --clear to pick up the change:
echo.
echo      cd mobile
echo      npx expo start --tunnel --clear
echo.
echo   (Or use --lan instead of --tunnel for faster dev.)
echo ============================================================
pause
