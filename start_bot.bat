@echo off
chcp 65001 > nul
title English Tutor Telegram Bot
cd /d "%~dp0"

echo ========================================================
echo        Запуск Telegram-бота для уроків англійської
echo ========================================================
echo.

if not exist venv (
    echo [1/3] Створення віртуального оточення venv...
    python -m venv venv
)

if not exist venv\Lib\site-packages\aiogram (
    echo [2/3] Встановлення залежностей...
    venv\Scripts\pip install -r requirements.txt
)

echo [3/3] Запуск бота...
venv\Scripts\python.exe bot.py

pause
