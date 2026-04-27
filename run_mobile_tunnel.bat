@echo off
cd /d "%~dp0\mobile"
echo Starting Expo with Tunnel...
npx expo start --tunnel --clear
pause
