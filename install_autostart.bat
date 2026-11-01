@echo off
chcp 65001 > nul
echo ========================================================
echo   Налаштування автозапуску бота разом із Windows
echo ========================================================
echo.

powershell -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\EnglishTutorBot.lnk\"); " ^
  "$s.TargetPath = \"wscript.exe\"; " ^
  "$s.Arguments = \"`\"%~dp0start_bot_silent.vbs`\"\"; " ^
  "$s.WorkingDirectory = \"%~dp0\"; " ^
  "$s.WindowStyle = 7; " ^
  "$s.Description = \"English Tutor Telegram Bot AutoStart\"; " ^
  "$s.Save(); " ^
  "Write-Host '✅ Автозапуск успішно встановлено!' -ForegroundColor Green; " ^
  "Write-Host 'Тепер бот запускатиметься у фоні автоматично при кожному старті Windows.'"

echo.
pause
