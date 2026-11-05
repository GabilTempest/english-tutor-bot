import asyncio
import logging
import sys
import os
from pathlib import Path

# Add current directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.stdout.reconfigure(encoding='utf-8')

# Load .env file if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from database import init_db, record_chat_member
from scheduler import check_reminders_job, check_post_lesson_job, check_unpaid_reminders_job, maintenance_job
from handlers import routers

class TrackMembersMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        if not chat and hasattr(event, "message") and event.message:
            chat = event.message.chat
        if user and chat and chat.id < 0 and not getattr(user, "is_bot", False):
            try:
                await record_chat_member(chat.id, user.id, user.username or "", user.first_name or "")
            except Exception:
                pass
        return await handler(event, data)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("EnglishTutorBot")

APP_VERSION = "2026-11-05-v3"

async def health_check_handler(request):
    return web.Response(text=f"English Tutor Bot is RUNNING 24/7! (Version {APP_VERSION})", status=200, content_type="text/plain")

async def render_keepalive_job():
    url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if not url:
        return
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                logger.info(f"Render keepalive ping ({url}): HTTP {resp.status}")
    except Exception as e:
        logger.debug(f"Render keepalive ping: {e}")

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="menu", description="Головне меню"),
        BotCommand(command="balance", description="Баланс оплачених занять"),
        BotCommand(command="next", description="Найближчий урок"),
        BotCommand(command="hw", description="Домашнє завдання"),
        BotCommand(command="schedule", description="Щотижневий розклад"),
        BotCommand(command="lessons", description="Список та історія уроків"),
        BotCommand(command="reschedule", description="Перенести урок"),
        BotCommand(command="link", description="Посилання на онлайн-урок"),
        BotCommand(command="settings", description="Налаштування групи")
    ]
    await bot.set_my_commands(commands)

async def main():
    token = os.getenv("BOT_TOKEN", BOT_TOKEN).strip()
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error(
            "\n" + "=" * 60 + "\n"
            "ПОМИЛКА: Не вказано BOT_TOKEN!\n"
            "Будь ласка, вкажіть токен вашого Telegram-бота у файлі .env\n"
            "Приклад у файлі: BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz\n"
            "=" * 60
        )
        sys.exit(1)

    # 1. Initialize SQLite database
    logger.info("Initializing database...")
    await init_db()

    # 2. Setup Bot and Dispatcher
    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(TrackMembersMiddleware())
    dp.callback_query.outer_middleware(TrackMembersMiddleware())

    # 3. Register handlers
    for router in routers:
        dp.include_router(router)

    # 4. Setup scheduler for 5-minute reminders and recurring checks
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_reminders_job,
        trigger="interval",
        seconds=60,
        args=[bot],
        id="check_reminders",
        replace_existing=True
    )
    scheduler.add_job(
        check_post_lesson_job,
        trigger="interval",
        seconds=60,
        args=[bot],
        id="check_post_lesson",
        replace_existing=True
    )
    scheduler.add_job(
        check_unpaid_reminders_job,
        trigger="interval",
        seconds=60,
        args=[bot],
        id="check_unpaid_reminders",
        replace_existing=True
    )
    scheduler.add_job(
        maintenance_job,
        trigger="interval",
        minutes=30,
        id="maintenance",
        replace_existing=True
    )
    # If RENDER_EXTERNAL_URL is set, ping every 10 mins to keep container awake
    if os.getenv("RENDER_EXTERNAL_URL"):
        scheduler.add_job(
            render_keepalive_job,
            trigger="interval",
            minutes=10,
            id="render_keepalive",
            replace_existing=True
        )
    scheduler.start()
    logger.info("Scheduler started successfully (checking reminders every 60s).")

    # 5. Run immediate maintenance check
    await maintenance_job()

    # 6. Set commands menu in Telegram
    try:
        await set_bot_commands(bot)
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")

    # 7. Start lightweight HTTP healthcheck server for Render/Cloud if PORT is specified
    port_str = os.getenv("PORT")
    web_runner = None
    if port_str:
        try:
            port = int(port_str)
            app = web.Application()
            app.router.add_get("/", health_check_handler)
            app.router.add_get("/health", health_check_handler)
            web_runner = web.AppRunner(app)
            await web_runner.setup()
            site = web.TCPSite(web_runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Render/Cloud HTTP healthcheck server running on port {port}")
        except Exception as e:
            logger.warning(f"Could not start healthcheck HTTP server on port {port_str}: {e}")

    # 8. Start polling
    bot_info = await bot.get_me()
    logger.info(f"Bot @{bot_info.username} successfully started! Listening for updates...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        if web_runner:
            await web_runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
