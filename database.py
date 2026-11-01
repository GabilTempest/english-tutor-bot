import aiosqlite
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from zoneinfo import ZoneInfo
import config

async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT DEFAULT '',
                meeting_link TEXT DEFAULT '',
                timezone TEXT DEFAULT 'Europe/Kyiv',
                student_timezone TEXT DEFAULT '',
                paid_lessons_balance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS recurring_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                day_of_week INTEGER, -- 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
                time_str TEXT,        -- '18:00'
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                datetime_utc TEXT,    -- 'YYYY-MM-DD HH:MM:SS'
                status TEXT DEFAULT 'scheduled', -- 'scheduled', 'completed', 'rescheduled', 'cancelled'
                rescheduled_to_id INTEGER,
                rescheduled_from_id INTEGER,
                rescheduled_by TEXT DEFAULT '',
                homework TEXT DEFAULT '',
                reminder_sent INTEGER DEFAULT 0,
                post_check_sent INTEGER DEFAULT 0,
                unpaid_reminder_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES groups(chat_id) ON DELETE CASCADE
            );
        """)
        await db.commit()

        # Migration: ensure post_check_sent column exists
        try:
            await db.execute("ALTER TABLE lessons ADD COLUMN post_check_sent INTEGER DEFAULT 0;")
            await db.commit()
        except Exception:
            pass

        # Migration: ensure paid_lessons_balance exists in groups
        try:
            await db.execute("ALTER TABLE groups ADD COLUMN paid_lessons_balance INTEGER DEFAULT 0;")
            await db.commit()
        except Exception:
            pass

        # Migration: ensure unpaid_reminder_sent exists in lessons
        try:
            await db.execute("ALTER TABLE lessons ADD COLUMN unpaid_reminder_sent INTEGER DEFAULT 0;")
            await db.commit()
        except Exception:
            pass

        # Migration: create user_groups table for private-to-group sync
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
                user_id INTEGER PRIMARY KEY,
                group_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()

async def track_user_group(user_id: int, group_id: int):
    """Associates a user with a group they interact in."""
    if not user_id or group_id >= 0:
        return
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_groups (user_id, group_id, updated_at) 
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET group_id=excluded.group_id, updated_at=CURRENT_TIMESTAMP""",
            (user_id, group_id)
        )
        await db.commit()

async def get_target_chat_id(chat_id: int, user_id: int = None) -> int:
    """
    If chat_id is negative (a group chat), tracks the user-group link and returns chat_id.
    If chat_id is positive (private 1-on-1 chat with bot), resolves to the user's active group
    or the latest registered group, providing seamless synchronization between private PM and group.
    """
    if chat_id < 0:
        if user_id:
            await track_user_group(user_id, chat_id)
        return chat_id

    # For private chat:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            async with db.execute("SELECT group_id FROM user_groups WHERE user_id = ?", (user_id,)) as c:
                row = await c.fetchone()
                if row and row["group_id"]:
                    return row["group_id"]

        # If not tracked yet, find the most recent group (chat_id < 0)
        async with db.execute("SELECT chat_id FROM groups WHERE chat_id < 0 ORDER BY created_at DESC LIMIT 1") as c:
            row = await c.fetchone()
            if row:
                if user_id:
                    await track_user_group(user_id, row["chat_id"])
                return row["chat_id"]

    return chat_id

async def get_or_create_group(chat_id: int, chat_title: str = "") -> Dict[str, Any]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                if chat_title and row["chat_title"] != chat_title:
                    await db.execute("UPDATE groups SET chat_title = ? WHERE chat_id = ?", (chat_title, chat_id))
                    await db.commit()
                return dict(row)

        await db.execute(
            "INSERT INTO groups (chat_id, chat_title, timezone) VALUES (?, ?, ?)",
            (chat_id, chat_title, config.DEFAULT_TIMEZONE)
        )
        await db.commit()
        async with db.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row)

async def set_meeting_link(chat_id: int, link: str):
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE groups SET meeting_link = ? WHERE chat_id = ?", (link, chat_id))
        await db.commit()

async def set_group_timezones(chat_id: int, timezone: str, student_timezone: str = ""):
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET timezone = ?, student_timezone = ? WHERE chat_id = ?",
            (timezone, student_timezone, chat_id)
        )
        await db.commit()

async def add_recurring_rule(chat_id: int, day_of_week: int, time_str: str):
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Check if already exists
        async with db.execute(
            "SELECT id FROM recurring_rules WHERE chat_id = ? AND day_of_week = ? AND time_str = ?",
            (chat_id, day_of_week, time_str)
        ) as cursor:
            if await cursor.fetchone():
                return
        await db.execute(
            "INSERT INTO recurring_rules (chat_id, day_of_week, time_str) VALUES (?, ?, ?)",
            (chat_id, day_of_week, time_str)
        )
        await db.commit()

async def clear_recurring_rules(chat_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM recurring_rules WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_recurring_rules(chat_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM recurring_rules WHERE chat_id = ? ORDER BY day_of_week, time_str",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def add_lesson(chat_id: int, datetime_utc: str, homework: str = "") -> int:
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO lessons (chat_id, datetime_utc, homework) VALUES (?, ?, ?)",
            (chat_id, datetime_utc, homework)
        )
        await db.commit()
        return cursor.lastrowid

async def get_lesson_by_id(lesson_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_lesson_homework(lesson_id: int, homework: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE lessons SET homework = ? WHERE id = ?", (homework, lesson_id))
        await db.commit()

async def reschedule_lesson(lesson_id: int, new_datetime_utc: str, rescheduled_by: str) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get old lesson
        async with db.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)) as cursor:
            old_lesson = await cursor.fetchone()
            if not old_lesson:
                raise ValueError("Lesson not found")

        # Create new lesson with inherited homework
        cursor = await db.execute(
            """INSERT INTO lessons (chat_id, datetime_utc, status, rescheduled_from_id, rescheduled_by, homework)
               VALUES (?, ?, 'scheduled', ?, ?, ?)""",
            (old_lesson["chat_id"], new_datetime_utc, lesson_id, rescheduled_by, old_lesson["homework"])
        )
        new_lesson_id = cursor.lastrowid

        # Update old lesson status
        await db.execute(
            "UPDATE lessons SET status = 'rescheduled', rescheduled_to_id = ?, rescheduled_by = ? WHERE id = ?",
            (new_lesson_id, rescheduled_by, lesson_id)
        )
        await db.commit()
        return new_lesson_id

async def cancel_lesson(lesson_id: int, cancelled_by: str = ""):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE lessons SET status = 'cancelled', rescheduled_by = ? WHERE id = ?",
            (cancelled_by, lesson_id)
        )
        await db.commit()

async def get_all_lessons(chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    now_utc_str = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM lessons 
               WHERE chat_id = ? 
               ORDER BY 
                   CASE WHEN datetime_utc >= ? THEN 0 ELSE 1 END,
                   CASE WHEN datetime_utc >= ? THEN datetime_utc END ASC,
                   datetime_utc DESC 
               LIMIT ?""",
            (chat_id, now_utc_str, now_utc_str, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_upcoming_lessons(chat_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    now_utc_str = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM lessons 
               WHERE chat_id = ? AND status = 'scheduled' AND datetime_utc >= ?
               ORDER BY datetime_utc ASC 
               LIMIT ?""",
            (chat_id, now_utc_str, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_pending_reminders(window_start_utc: str, window_end_utc: str) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, g.meeting_link, g.timezone, g.student_timezone 
               FROM lessons l
               JOIN groups g ON l.chat_id = g.chat_id
               WHERE l.chat_id < 0
                 AND l.status = 'scheduled' 
                 AND l.reminder_sent = 0
                 AND l.datetime_utc >= ? 
                 AND l.datetime_utc <= ?""",
            (window_start_utc, window_end_utc)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def mark_reminder_sent(lesson_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE lessons SET reminder_sent = 1 WHERE id = ?", (lesson_id,))
        await db.commit()

async def get_pending_post_checks(max_datetime_utc: str, min_datetime_utc: str) -> List[Dict[str, Any]]:
    """Returns scheduled lessons that finished recently and need the 'Did the lesson take place?' prompt."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, g.meeting_link, g.timezone, g.student_timezone 
               FROM lessons l
               JOIN groups g ON l.chat_id = g.chat_id
               WHERE l.chat_id < 0
                 AND l.status = 'scheduled' 
                 AND l.post_check_sent = 0
                 AND l.datetime_utc <= ?
                 AND l.datetime_utc >= ?""",
            (max_datetime_utc, min_datetime_utc)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def mark_post_check_sent(lesson_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE lessons SET post_check_sent = 1 WHERE id = ?", (lesson_id,))
        await db.commit()

async def get_pending_unpaid_reminders(min_dt_utc: str, max_dt_utc: str) -> List[Dict[str, Any]]:
    """Returns scheduled lessons starting within the window (e.g. 15m to 24h) that haven't sent an unpaid reminder yet."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.*, g.meeting_link, g.timezone, g.student_timezone, g.paid_lessons_balance 
               FROM lessons l
               JOIN groups g ON l.chat_id = g.chat_id
               WHERE l.chat_id < 0
                 AND l.status = 'scheduled' 
                 AND COALESCE(l.unpaid_reminder_sent, 0) = 0
                 AND l.datetime_utc >= ? 
                 AND l.datetime_utc <= ?
               ORDER BY l.datetime_utc ASC""",
            (min_dt_utc, max_dt_utc)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def mark_unpaid_reminder_sent(lesson_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE lessons SET unpaid_reminder_sent = 1 WHERE id = ?", (lesson_id,))
        await db.commit()

async def get_paid_lesson_ids_for_group(chat_id: int) -> set:
    """Returns set of lesson IDs for currently prepaid upcoming lessons."""
    balance = await get_paid_balance(chat_id)
    if balance <= 0:
        return set()
    upcoming = await get_upcoming_lessons(chat_id, limit=balance)
    return {l["id"] for l in upcoming}

async def get_paid_balance(chat_id: int) -> int:
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute("SELECT paid_lessons_balance FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

async def add_paid_balance(chat_id: int, amount: int) -> int:
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET paid_lessons_balance = MAX(0, COALESCE(paid_lessons_balance, 0) + ?) WHERE chat_id = ?",
            (amount, chat_id)
        )
        await db.commit()
    return await get_paid_balance(chat_id)

async def set_paid_balance(chat_id: int, balance: int) -> int:
    await get_or_create_group(chat_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET paid_lessons_balance = ? WHERE chat_id = ?",
            (max(0, balance), chat_id)
        )
        await db.commit()
    return await get_paid_balance(chat_id)

async def deduct_paid_lesson(chat_id: int) -> int:
    """Deducts 1 paid lesson when a lesson actually takes place (completed)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET paid_lessons_balance = MAX(0, COALESCE(paid_lessons_balance, 0) - 1) WHERE chat_id = ?",
            (chat_id,)
        )
        await db.commit()
    return await get_paid_balance(chat_id)

async def refund_paid_lesson(chat_id: int) -> int:
    """Restores 1 paid lesson if a completed lesson is reverted to cancelled/scheduled."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET paid_lessons_balance = COALESCE(paid_lessons_balance, 0) + 1 WHERE chat_id = ?",
            (chat_id,)
        )
        await db.commit()
    return await get_paid_balance(chat_id)

async def update_lesson_status(lesson_id: int, status: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT chat_id, status FROM lessons WHERE id = ?", (lesson_id,)) as cursor:
            old_row = await cursor.fetchone()

        if old_row:
            old_status = old_row["status"]
            chat_id = old_row["chat_id"]
            # Deduct if newly completed
            if old_status != "completed" and status == "completed":
                await deduct_paid_lesson(chat_id)
            # Refund if changing away from completed
            elif old_status == "completed" and status != "completed":
                await refund_paid_lesson(chat_id)

        await db.execute("UPDATE lessons SET status = ? WHERE id = ?", (status, lesson_id))
        await db.commit()

async def delete_single_lesson(lesson_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        await db.commit()
        return cursor.rowcount > 0

async def update_lesson_datetime(lesson_id: int, new_datetime_utc: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE lessons SET datetime_utc = ? WHERE id = ?", (new_datetime_utc, lesson_id))
        await db.commit()

async def auto_update_lesson_statuses():
    """Only auto-expire lessons that are older than 7 days and still scheduled."""
    seven_days_ago = (datetime.now(ZoneInfo("UTC")) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """UPDATE lessons 
               SET status = 'completed' 
               WHERE status = 'scheduled' AND datetime_utc < ?""",
            (seven_days_ago,)
        )
        await db.commit()

async def generate_recurring_lessons_for_group(chat_id: int, days_ahead: int = 21):
    """Generates scheduled lesson instances based on recurring rules if not already present."""
    group = await get_or_create_group(chat_id)
    tz_str = group.get("timezone", config.DEFAULT_TIMEZONE) or config.DEFAULT_TIMEZONE
    try:
        group_tz = ZoneInfo(tz_str)
    except Exception:
        group_tz = ZoneInfo(config.DEFAULT_TIMEZONE)

    rules = await get_recurring_rules(chat_id)
    if not rules:
        return

    now_local = datetime.now(group_tz)
    start_date = now_local.date()
    end_date = start_date + timedelta(days=days_ahead)

    # Collect existing lesson datetimes in UTC
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT datetime_utc FROM lessons WHERE chat_id = ?", (chat_id,)) as cursor:
            existing = {r["datetime_utc"] for r in await cursor.fetchall()}

    curr_date = start_date
    while curr_date <= end_date:
        for rule in rules:
            if curr_date.weekday() == rule["day_of_week"]:
                hour, minute = map(int, rule["time_str"].split(":"))
                local_dt = datetime(curr_date.year, curr_date.month, curr_date.day, hour, minute, tzinfo=group_tz)
                # If lesson is in the past, skip
                if local_dt < now_local:
                    continue
                utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
                utc_str = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                if utc_str not in existing:
                    await add_lesson(chat_id, utc_str)
                    existing.add(utc_str)
        curr_date += timedelta(days=1)

async def clear_past_lessons(chat_id: int) -> int:
    """Deletes past, completed, rescheduled, or cancelled lessons."""
    now_utc_str = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            """DELETE FROM lessons 
               WHERE chat_id = ? AND (status IN ('completed', 'rescheduled', 'cancelled') OR datetime_utc < ?)""",
            (chat_id, now_utc_str)
        )
        await db.commit()
        return cursor.rowcount

async def clear_all_lessons(chat_id: int) -> int:
    """Deletes all lessons for chat_id."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("DELETE FROM lessons WHERE chat_id = ?", (chat_id,))
        await db.commit()
        return cursor.rowcount
