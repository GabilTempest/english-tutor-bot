import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tutor_bot.db")))

# Telegram Bot Token from environment or fallback
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Default Timezone
DEFAULT_TIMEZONE = "Europe/Kyiv"
KYIV_TZ = ZoneInfo(DEFAULT_TIMEZONE)

# Reminder offset in minutes
REMINDER_MINUTES_BEFORE = 5

# Password for clearing and editing history
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
