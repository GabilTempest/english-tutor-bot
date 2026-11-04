import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

from config import DB_PATH, DEFAULT_TIMEZONE, REMINDER_MINUTES_BEFORE
from database import (
    get_pending_reminders,
    mark_reminder_sent,
    get_pending_post_checks,
    mark_post_check_sent,
    auto_update_lesson_statuses,
    generate_recurring_lessons_for_group,
    get_pending_unpaid_reminders,
    mark_unpaid_reminder_sent,
    get_paid_lesson_ids_for_group,
    get_chat_members
)
from utils.time_utils import format_datetime_for_display

logger = logging.getLogger(__name__)

async def check_reminders_job(bot: Bot):
    """Job that runs every 60 seconds to check if any lesson starts in 5 minutes."""
    try:
        now_utc = datetime.now(ZoneInfo("UTC"))
        # Window: from (now + 4 min) to (now + 6 min)
        start_window = (now_utc + timedelta(minutes=REMINDER_MINUTES_BEFORE - 1)).strftime("%Y-%m-%d %H:%M:%S")
        end_window = (now_utc + timedelta(minutes=REMINDER_MINUTES_BEFORE + 1)).strftime("%Y-%m-%d %H:%M:%S")

        lessons_to_remind = await get_pending_reminders(start_window, end_window)

        for lesson in lessons_to_remind:
            chat_id = lesson["chat_id"]
            meeting_link = lesson.get("meeting_link", "").strip()
            tz_primary = lesson.get("timezone", DEFAULT_TIMEZONE)
            tz_student = lesson.get("student_timezone", "")
            time_display = format_datetime_for_display(lesson["datetime_utc"], tz_primary, tz_student)
            
            # Homework section (only if homework is present)
            hw_text = lesson.get("homework", "").strip()
            hw_section = f"📝 <b>Домашнє завдання:</b>\n{hw_text}\n\n" if hw_text else ""

            # Meeting link section (only if link is present)
            has_valid_link = bool(meeting_link and (meeting_link.startswith("http://") or meeting_link.startswith("https://")))
            link_section = f"🔗 <b>Посилання на дзвінок:</b> {meeting_link}\n\n" if has_valid_link else ""

            # Tag chat members so everyone receives an alert/notification
            tag_list = []
            seen_uids = set()

            # 1. From database recorded members
            try:
                members = await get_chat_members(chat_id)
                for m in members:
                    uid = m["user_id"]
                    if uid not in seen_uids:
                        seen_uids.add(uid)
                        if m.get("username"):
                            tag_list.append(f"@{m['username']}")
                        elif m.get("first_name"):
                            tag_list.append(f'<a href="tg://user?id={uid}">{m["first_name"]}</a>')
            except Exception as e:
                logger.debug(f"Could not load chat members from DB for {chat_id}: {e}")

            # 2. In groups, fetch administrators / owner via Telegram API
            if chat_id < 0:
                try:
                    admins = await bot.get_chat_administrators(chat_id)
                    for a in admins:
                        if a.user.is_bot:
                            continue
                        uid = a.user.id
                        if uid not in seen_uids:
                            seen_uids.add(uid)
                            if a.user.username:
                                tag_list.append(f"@{a.user.username}")
                            elif a.user.first_name:
                                tag_list.append(f'<a href="tg://user?id={uid}">{a.user.first_name}</a>')
                except Exception as e:
                    logger.debug(f"Could not fetch chat administrators for {chat_id}: {e}")

            tags_section = f"👥 {' '.join(tag_list)}" if tag_list else ""

            body_lines = [
                f"🔔 <b>НАГАДУВАННЯ ПРО УРОК!</b>\n",
                f"🕒 Урок розпочнеться через <b>{REMINDER_MINUTES_BEFORE} хвилин</b>!\n🗓 <b>Час:</b> {time_display}"
            ]
            if link_section.strip():
                body_lines.append(link_section.strip())
            if hw_section.strip():
                body_lines.append(hw_section.strip())
            if tags_section.strip():
                body_lines.append(tags_section.strip())

            text = "\n\n".join(body_lines)

            reply_markup = None
            if has_valid_link:
                reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Приєднатися до уроку", url=meeting_link)]
                ])

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=False
                )
                await mark_reminder_sent(lesson["id"])
                logger.info(f"Reminder sent for lesson #{lesson['id']} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send reminder for lesson {lesson['id']} in chat {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Error in check_reminders_job: {e}", exc_info=True)

async def check_post_lesson_job(bot: Bot):
    """Job that checks if a lesson finished (e.g. 50+ mins after start) and asks if it took place."""
    try:
        now_utc = datetime.now(ZoneInfo("UTC"))
        # Lesson started between 24 hours ago and 50 minutes ago
        max_dt = (now_utc - timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S")
        min_dt = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        pending_checks = await get_pending_post_checks(max_dt, min_dt)

        for lesson in pending_checks:
            chat_id = lesson["chat_id"]
            tz_primary = lesson.get("timezone", DEFAULT_TIMEZONE)
            tz_student = lesson.get("student_timezone", "")
            time_display = format_datetime_for_display(lesson["datetime_utc"], tz_primary, tz_student)

            text = (
                f"🔔 <b>Час уроку завершився. Підкажіть, чи відбувся урок?</b>\n\n"
                f"🗓 <b>Урок:</b> {time_display}\n\n"
                f"<i>Оберіть, будь ласка, відповідь:</i>"
            )

            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Був", callback_data=f"held_yes_{lesson['id']}"),
                    InlineKeyboardButton(text="❌ Ні", callback_data=f"held_no_{lesson['id']}")
                ]
            ])

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                await mark_post_check_sent(lesson["id"])
                logger.info(f"Post-lesson check sent for lesson #{lesson['id']} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send post-lesson check for lesson {lesson['id']}: {e}")

    except Exception as e:
        logger.error(f"Error in check_post_lesson_job: {e}", exc_info=True)

async def check_unpaid_reminders_job(bot: Bot):
    """Job that runs every 60 seconds to check if any unpaid lesson is scheduled within the next 24 hours."""
    try:
        now_utc = datetime.now(ZoneInfo("UTC"))
        # 15 mins to 24 hours ahead
        min_dt = (now_utc + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        max_dt = (now_utc + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        candidate_lessons = await get_pending_unpaid_reminders(min_dt, max_dt)
        if not candidate_lessons:
            return

        # Cache paid lesson ids per chat_id to avoid redundant queries
        paid_ids_by_chat = {}

        for lesson in candidate_lessons:
            chat_id = lesson["chat_id"]
            if chat_id not in paid_ids_by_chat:
                paid_ids_by_chat[chat_id] = await get_paid_lesson_ids_for_group(chat_id)

            paid_ids = paid_ids_by_chat[chat_id]
            # If the lesson IS covered by prepaid balance, do NOT send unpaid reminder
            if lesson["id"] in paid_ids:
                continue

            tz_primary = lesson.get("timezone", DEFAULT_TIMEZONE)
            tz_student = lesson.get("student_timezone", "")
            time_display = format_datetime_for_display(lesson["datetime_utc"], tz_primary, tz_student)
            balance = lesson.get("paid_lessons_balance", 0) or 0

            text = (
                f"⚠️ <b>НАГАДУВАННЯ ПРО ОПЛАТУ ЗАНЯТТЯ</b>\n\n"
                f"Завтра заплановано урок англійської:\n"
                f"🗓 <b>{time_display}</b>\n\n"
                f"⏳ <b>Статус:</b> Не оплачено (залишок на балансі: <b>{balance}</b> ур.)\n\n"
                f"Будь ласка, своєчасно поповніть баланс занять, щоб урок відбувся за розкладом!\n"
                f"<i>(При завчасному скасуванні чи перенесенні уроку кошти не списуються).</i>"
            )

            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Поповнити баланс", callback_data="add_balance_prompt"),
                    InlineKeyboardButton(text="💳 Меню оплати", callback_data="balance_menu")
                ],
                [
                    InlineKeyboardButton(text="📖 Деталі уроку", callback_data=f"view_lesson_{lesson['id']}_0"),
                    InlineKeyboardButton(text="🔄 Перенести", callback_data=f"resched_action_{lesson['id']}")
                ]
            ])

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                await mark_unpaid_reminder_sent(lesson["id"])
                logger.info(f"Unpaid lesson reminder sent for lesson #{lesson['id']} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send unpaid reminder for lesson {lesson['id']} in chat {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Error in check_unpaid_reminders_job: {e}", exc_info=True)

async def maintenance_job():
    """Runs every hour to mark past lessons as completed and populate recurring lessons."""
    try:
        await auto_update_lesson_statuses()
        
        # Populate recurring lessons for all active groups
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT DISTINCT chat_id FROM groups") as cursor:
                groups = await cursor.fetchall()
                for (chat_id,) in groups:
                    await generate_recurring_lessons_for_group(chat_id, days_ahead=21)
    except Exception as e:
        logger.error(f"Error in maintenance_job: {e}", exc_info=True)
