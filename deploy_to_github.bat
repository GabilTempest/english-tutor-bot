@echo off
chcp 65001 > nul
echo ========================================================
echo        Публікація бота на GitHub для хмари Render
echo ========================================================
echo.
echo Переконайтесь, що ви створили порожній репозиторій на GitHub:
echo https://github.com/new (назва: english-tutor-bot)
echo.
git push -u origin main
if %errorlevel% equ 0 (
    echo.
    echo ✅ Код успішно завантажено на GitHub!
    echo Тепер підключіть його на dashboard.render.com (Web Service).
) else (
    echo.
    echo ⚠️ Якщо репозиторій ще не створено, створіть його на https://github.com/new з назвою english-tutor-bot
)
echo.
pause
