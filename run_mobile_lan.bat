@echo off
cd /d "%~dp0\mobile"
echo Starting Expo on LAN...
npx expo start --lan --clear
pause
