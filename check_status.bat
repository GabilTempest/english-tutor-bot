@echo off
chcp 65001 > nul
echo ========================================================
echo          Статус Telegram-бота English Tutor
echo ========================================================
echo.

powershell -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*english_tutor_bot*' -and $_.CommandLine -like '*bot.py*' }; " ^
  "if ($procs) { " ^
  "    Write-Host '🟢 БОТ АКТИВНИЙ ТА ПРАЦЮЄ ОНЛАЙН!' -ForegroundColor Green; " ^
  "    Write-Host ('PID: ' + ($procs.ProcessId -join ', ')) " ^
  "} else { " ^
  "    Write-Host '🔴 Бот наразі не запущений.' -ForegroundColor Red " ^
  "}"

echo.
echo Останні 15 рядків логу (bot.log):
echo --------------------------------------------------------
powershell -Command "if (Test-Path 'bot.log') { Get-Content 'bot.log' -Tail 15 } else { Write-Host 'Файл логів ще не створено.' }"
echo --------------------------------------------------------
echo.
pause
