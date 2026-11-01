import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from config import DEFAULT_TIMEZONE

DAYS_UA = [
    "Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"
]

DAYS_UA_SHORT = [
    "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"
]

MONTHS_UA = [
    "", "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
]

def format_datetime_for_display(datetime_utc_str: str, tz_primary_str: str = DEFAULT_TIMEZONE, tz_student_str: str = "") -> str:
    """Formats a UTC datetime string into a readable Ukrainian representation with timezones."""
    dt_utc = datetime.strptime(datetime_utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
    
    # Primary timezone (Kyiv)
    try:
        primary_tz = ZoneInfo(tz_primary_str or DEFAULT_TIMEZONE)
    except Exception:
        primary_tz = ZoneInfo(DEFAULT_TIMEZONE)
    
    dt_primary = dt_utc.astimezone(primary_tz)
    day_name = DAYS_UA[dt_primary.weekday()]
    month_name = MONTHS_UA[dt_primary.month]
    time_str = dt_primary.strftime("%H:%M")
    
    # Simple city / label from timezone name
    primary_label = tz_primary_str.split("/")[-1].replace("_", " ") if tz_primary_str else "Київ"
    if primary_label == "Kyiv":
        primary_label = "Київ"

    res = f"{day_name}, {dt_primary.day} {month_name} о {time_str} ({primary_label})"

    # If student timezone is configured and different
    if tz_student_str and tz_student_str != tz_primary_str:
        try:
            student_tz = ZoneInfo(tz_student_str)
            dt_student = dt_utc.astimezone(student_tz)
            student_label = tz_student_str.split("/")[-1].replace("_", " ")
            student_time_str = dt_student.strftime("%H:%M")
            if dt_student.date() != dt_primary.date():
                res += f" / {student_time_str} ({student_label}, {dt_student.day} {MONTHS_UA[dt_student.month]})"
            else:
                res += f" / {student_time_str} ({student_label})"
        except Exception:
            pass

    return res

def format_short_date(datetime_utc_str: str, tz_str: str = DEFAULT_TIMEZONE) -> str:
    """Short format: 'Вт, 03.11 18:00'"""
    dt_utc = datetime.strptime(datetime_utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
    try:
        local_tz = ZoneInfo(tz_str or DEFAULT_TIMEZONE)
    except Exception:
        local_tz = ZoneInfo(DEFAULT_TIMEZONE)
    dt_local = dt_utc.astimezone(local_tz)
    short_day = DAYS_UA_SHORT[dt_local.weekday()]
    return f"{short_day}, {dt_local.strftime('%d.%m %H:%M')}"

def parse_user_datetime(text: str, tz_str: str = DEFAULT_TIMEZONE) -> Optional[datetime]:
    """
    Parses datetime string in user's timezone into UTC datetime.
    Supports formats:
    - 'DD.MM.YYYY HH:MM' or 'DD.MM.YY HH:MM'
    - 'DD.MM HH:MM' (uses current or next year)
    - 'HH:MM' (interpreted as today or tomorrow)
    """
    text = text.strip().lower()
    try:
        local_tz = ZoneInfo(tz_str or DEFAULT_TIMEZONE)
    except Exception:
        local_tz = ZoneInfo(DEFAULT_TIMEZONE)

    now_local = datetime.now(local_tz)

    # 1. Full date: DD.MM.YYYY HH:MM
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\s+(\d{1,2}):(\d{2})$", text)
    if m:
        day, month, year, hour, minute = map(int, m.groups())
        dt = datetime(year, month, day, hour, minute, tzinfo=local_tz)
        return dt.astimezone(ZoneInfo("UTC"))

    # 2. Date with 2-digit year: DD.MM.YY HH:MM
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2})\s+(\d{1,2}):(\d{2})$", text)
    if m:
        day, month, short_year, hour, minute = map(int, m.groups())
        year = 2000 + short_year
        dt = datetime(year, month, day, hour, minute, tzinfo=local_tz)
        return dt.astimezone(ZoneInfo("UTC"))

    # 3. Without year: DD.MM HH:MM
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})\s+(\d{1,2}):(\d{2})$", text)
    if m:
        day, month, hour, minute = map(int, m.groups())
        year = now_local.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=local_tz)
            # If the date is already in the past by more than 30 days, assume next year
            if dt < now_local - timedelta(days=30):
                dt = datetime(year + 1, month, day, hour, minute, tzinfo=local_tz)
            return dt.astimezone(ZoneInfo("UTC"))
        except ValueError:
            return None

    # 4. Words: 'сьогодні 18:00', 'завтра 18:00', 'післязавтра 18:00' (with optional 'о'/'в')
    m = re.match(r"^(сьогодні|завтра|післязавтра)(?:\s+(?:о|в))?\s+(\d{1,2}):(\d{2})$", text)
    if m:
        word, hour_s, min_s = m.groups()
        hour, minute = int(hour_s), int(min_s)
        target_date = now_local.date()
        if word == "завтра":
            target_date += timedelta(days=1)
        elif word == "післязавтра":
            target_date += timedelta(days=2)
        dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=local_tz)
        return dt.astimezone(ZoneInfo("UTC"))

    # 5. Day of week: 'понеділок 19:30', 'вівторок о 18:00'
    m = re.match(r"^([а-яіїєґa-z'’]+)(?:\s+(?:о|в))?\s+(\d{1,2}):(\d{2})$", text)
    if m:
        day_word, hour_s, min_s = m.groups()
        day_map = {
            "понеділок": 0, "пн": 0, "вівторок": 1, "вт": 1,
            "середа": 2, "середу": 2, "ср": 2, "четвер": 3, "чт": 3,
            "п'ятниця": 4, "пятниця": 4, "п'ятницю": 4, "пт": 4,
            "субота": 5, "суботу": 5, "сб": 5, "неділя": 6, "неділю": 6, "нд": 6
        }
        if day_word in day_map:
            target_weekday = day_map[day_word]
            days_ahead = (target_weekday - now_local.weekday()) % 7
            if days_ahead == 0 and datetime(now_local.year, now_local.month, now_local.day, int(hour_s), int(min_s), tzinfo=local_tz) <= now_local:
                days_ahead = 7  # If target time today has already passed, choose next week
            target_date = now_local.date() + timedelta(days=days_ahead)
            dt = datetime(target_date.year, target_date.month, target_date.day, int(hour_s), int(min_s), tzinfo=local_tz)
            return dt.astimezone(ZoneInfo("UTC"))

    return None
