@echo off
chcp 65001 > nul
echo ========================================================
echo           Зупинка Telegram-бота та процесів
echo ========================================================
echo.

powershell -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*english_tutor_bot*' -and ($_.CommandLine -like '*bot.py*' -or $_.CommandLine -like '*run_forever.py*') }; " ^
  "if ($procs) { " ^
  "    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Зупинено процес PID: ' + $_.ProcessId) }; " ^
  "    Write-Host '✅ Бот та супервайзер успішно зупинені.' -ForegroundColor Green " ^
  "} else { " ^
  "    Write-Host 'ℹ️ Працюючих процесів бота не виявлено.' -ForegroundColor Yellow " ^
  "}"

echo.
pause
