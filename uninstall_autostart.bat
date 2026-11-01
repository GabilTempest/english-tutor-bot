@echo off
chcp 65001 > nul
echo ========================================================
echo         Вимкнення автозапуску Telegram-бота
echo ========================================================
echo.

powershell -Command "Remove-Item -Path \"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\EnglishTutorBot.lnk\" -Force -ErrorAction SilentlyContinue; Write-Host '✅ Ярлик автозапуску видалено.' -ForegroundColor Yellow"

echo.
pause
