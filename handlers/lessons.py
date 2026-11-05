from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import (
    get_or_create_group,
    get_all_lessons,
    get_lesson_by_id,
    reschedule_lesson,
    cancel_lesson,
    add_lesson,
    get_upcoming_lessons,
    get_history_lessons,
    deduplicate_scheduled_lessons,
    clear_past_lessons,
    clear_all_lessons,
    update_lesson_status,
    delete_single_lesson,
    update_lesson_datetime,
    get_paid_balance,
    get_target_chat_id
)
from utils.keyboards import (
    get_lessons_list_keyboard,
    get_lesson_detail_keyboard,
    get_cancel_keyboard,
    get_select_lesson_keyboard,
    get_main_menu_keyboard,
    get_clear_options_keyboard,
    get_edit_lesson_menu_keyboard,
    get_status_select_keyboard
)
from utils.time_utils import (
    format_datetime_for_display,
    parse_user_datetime
)
from states import RescheduleStates, AddLessonStates, ClearHistoryStates, EditHistoryStates
from config import DEFAULT_TIMEZONE, ADMIN_PASSWORD

router = Router()

ITEMS_PER_PAGE = 5

@router.message(Command("lessons"))
async def cmd_lessons(message: Message, state: FSMContext):
    await state.clear()
    await show_lessons_page(message.chat.id, 0, message, tab="upcoming")

@router.callback_query(F.data.startswith("list_lessons_"))
async def cb_list_lessons(call: CallbackQuery, state: FSMContext):
    await state.clear()
    parts = call.data.split("_")
    tab = "upcoming"
    page = 0
    if len(parts) >= 4:
        tab = parts[2]
        try:
            page = int(parts[3])
        except ValueError:
            page = 0
    elif len(parts) == 3:
        if parts[2].isdigit():
            page = int(parts[2])
        else:
            tab = parts[2]
            page = 0
    await show_lessons_page(call.message.chat.id, page, call, tab=tab)
    await call.answer()

async def show_lessons_page(chat_id: int, page: int, event: Message | CallbackQuery, tab: str = "upcoming"):
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)
    group = await get_or_create_group(target_id)
    await deduplicate_scheduled_lessons(target_id)
    paid_balance = await get_paid_balance(target_id)

    upcoming_lessons = await get_upcoming_lessons(target_id, limit=50)
    history_lessons = await get_history_lessons(target_id, limit=50)

    paid_lesson_ids = {l["id"] for l in upcoming_lessons[:paid_balance]}

    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""
    tz_str = group.get("timezone", DEFAULT_TIMEZONE)

    lessons_to_show = upcoming_lessons if tab == "upcoming" else history_lessons
    total_items = len(lessons_to_show)
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_page_lessons = lessons_to_show[start_idx:end_idx]

    if tab == "upcoming":
        header_title = f"🗓 <b>ЗАПЛАНОВАНІ УРОКИ (Стор. {page + 1}/{total_pages})</b>{sync_tag}"
        legend = (
            f"💰 <b>Залишок оплачених занять:</b> <b>{paid_balance}</b> ур.\n\n"
            f"🟢 <b>(Оплачено 💳)</b> — входить у передоплату\n"
            f"⏳ <b>(Не оплачено)</b> — очікує оплати\n\n"
        )
        empty_note = "<i>ℹ️ Наразі немає запланованих майбутніх уроків.</i>"
    else:
        header_title = f"📚 <b>ІСТОРІЯ ПРОВЕДЕНИХ ТА МИНУЛИХ УРОКІВ (Стор. {page + 1}/{total_pages})</b>{sync_tag}"
        legend = (
            f"✅ <b>(Відбувся)</b> — проведений урок\n"
            f"🔄 <b>(Перенесено)</b> / ❌ <b>(Скасовано)</b> — плата не стягується\n\n"
        )
        empty_note = "<i>ℹ️ Історія проведених занять поки що порожня.</i>"

    if not current_page_lessons:
        content_text = f"{empty_note}\n\n<i>Оберіть потрібну вкладку вище:</i>"
    else:
        content_text = f"{legend}<i>Натисніть на урок нижче для перегляду деталей або дій:</i>"

    text = f"{header_title}\n\n{content_text}"

    kb = get_lessons_list_keyboard(
        lessons=current_page_lessons,
        page=page,
        total_pages=total_pages,
        tz_str=tz_str,
        paid_lesson_ids=paid_lesson_ids,
        tab=tab,
        upcoming_count=len(upcoming_lessons),
        history_count=len(history_lessons)
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("view_lesson_"))
async def cb_view_lesson(call: CallbackQuery):
    parts = call.data.split("_")
    lesson_id = int(parts[2])
    tab = "upcoming"
    page = 0
    if len(parts) >= 5:
        tab = parts[3]
        try:
            page = int(parts[4])
        except ValueError:
            page = 0
    elif len(parts) == 4:
        if parts[3].isdigit():
            page = int(parts[3])
        else:
            tab = parts[3]

    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    # If lesson is not scheduled, its natural tab is history
    if lesson.get("status") != "scheduled" and len(parts) < 5:
        tab = "history"

    group = await get_or_create_group(lesson["chat_id"])
    tz_primary = group.get("timezone", DEFAULT_TIMEZONE)
    tz_student = group.get("student_timezone", "")
    time_str = format_datetime_for_display(lesson["datetime_utc"], tz_primary, tz_student)

    status_dict = {
        "scheduled": "🟢 Заплановано",
        "completed": "✅ Відбувся",
        "rescheduled": "🔄 Перенесено",
        "cancelled": "❌ Скасовано"
    }
    status_text = status_dict.get(lesson.get("status"), lesson.get("status"))

    reschedule_info = ""
    if lesson.get("status") == "rescheduled":
        rescheduled_by = lesson.get("rescheduled_by") or "користувачем"
        if lesson.get("rescheduled_to_id"):
            new_l = await get_lesson_by_id(lesson["rescheduled_to_id"])
            if new_l:
                new_time = format_datetime_for_display(new_l["datetime_utc"], tz_primary, tz_student)
                reschedule_info = f"\n⚠️ <i>Урок перенесено ({rescheduled_by}) на:</i> {new_time}\n"
        else:
            reschedule_info = f"\n⚠️ <i>Урок було перенесено ({rescheduled_by})</i>\n"

    hw_text = lesson.get("homework", "").strip() or "<i>Домашнє завдання не записано</i>"

    paid_balance = await get_paid_balance(lesson["chat_id"])
    if lesson.get("status") == "scheduled":
        upcoming = await get_upcoming_lessons(lesson["chat_id"], limit=50)
        paid_ids = {l["id"] for l in upcoming[:paid_balance]}
        if lesson["id"] in paid_ids:
            payment_line = f"💳 <b>Оплата:</b> 🟢 Оплачено (входить у передоплату, баланс: {paid_balance} ур.)"
        else:
            payment_line = f"💳 <b>Оплата:</b> ⏳ Не оплачено (очікує оплати, баланс: {paid_balance} ур.)"
    elif lesson.get("status") == "completed":
        payment_line = "💳 <b>Оплата:</b> ✅ Списано з передоплати"
    else:
        payment_line = "💳 <b>Оплата:</b> 🆓 Плата не стягується (перенесено / скасовано)"

    text = (
        f"📖 <b>КАРТКА УРОКУ #{lesson['id']}</b>\n\n"
        f"🕒 <b>Дата та час:</b> {time_str}\n"
        f"📌 <b>Статус:</b> {status_text}\n"
        f"{payment_line}"
        f"{reschedule_info}\n"
        f"📝 <b>Домашнє завдання:</b>\n{hw_text}\n"
    )

    kb = get_lesson_detail_keyboard(lesson, page=page, tab=tab)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()

# ----------------- RESCHEDULE FLOW -----------------
@router.message(Command("reschedule"))
@router.message(Command("resched"))
@router.callback_query(F.data == "reschedule_select")
async def start_reschedule_selection(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)

    group = await get_or_create_group(target_id)
    upcoming = await get_upcoming_lessons(target_id, limit=5)

    if not upcoming:
        msg = "ℹ️ Немає запланованих уроків для перенесення."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(msg, reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
            await event.answer()
        else:
            await event.answer(msg, reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
        return

    # Direct instant rescheduling via command: e.g. /reschedule 04.11 19:00 or /reschedule 1 04.11 19:00
    if isinstance(event, Message) and event.text:
        parts = event.text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            raw_arg = parts[1].strip()
            target_lesson = upcoming[0]
            tz_str = group.get("timezone", DEFAULT_TIMEZONE)

            arg_parts = raw_arg.split(maxsplit=1)
            first_clean = arg_parts[0].lstrip("#")
            date_to_parse = raw_arg
            if first_clean.isdigit():
                spec_id = int(first_clean)
                found = next((l for l in upcoming if l["id"] == spec_id), None)
                if found and len(arg_parts) > 1:
                    target_lesson = found
                    date_to_parse = arg_parts[1].strip()

            parsed_dt = parse_user_datetime(date_to_parse, tz_str)
            if parsed_dt:
                new_utc_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
                user_name = event.from_user.full_name
                if event.from_user.username:
                    user_name += f" (@{event.from_user.username})"
                new_lesson_id = await reschedule_lesson(target_lesson["id"], new_utc_str, user_name)
                old_time_str = format_datetime_for_display(target_lesson["datetime_utc"], tz_str, group.get("student_timezone", ""))
                new_time_str = format_datetime_for_display(new_utc_str, tz_str, group.get("student_timezone", ""))
                success_text = (
                    f"🔄 <b>УРОК УСПІШНО ПЕРЕНЕСЕНО!</b>\n\n"
                    f"👤 <b>Ініціатор:</b> {user_name}\n"
                    f"⏳ <b>Було:</b> {old_time_str}\n"
                    f"✨ <b>Новий час:</b> {new_time_str}\n\n"
                    f"📌 <i>Домашнє завдання автоматично перенесено на новий урок #{new_lesson_id}.</i>"
                )
                await event.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
                return
            else:
                await event.answer(
                    "⚠️ Не вдалося розпізнати дату та час. Приклад: <code>/reschedule 04.11 19:00</code> або <code>/reschedule завтра 18:30</code>",
                    parse_mode="HTML"
                )
                return

    # If only 1 upcoming lesson, immediately proceed to reschedule it
    if len(upcoming) == 1:
        lesson = upcoming[0]
        await state.update_data(lesson_id=lesson["id"], chat_id=target_id)
        await state.set_state(RescheduleStates.waiting_for_new_datetime)
        prompt_text = (
            f"🔄 <b>Перенесення уроку #{lesson['id']}</b>\n"
            f"🗓 <b>Поточний час:</b> {format_datetime_for_display(lesson['datetime_utc'], group.get('timezone', DEFAULT_TIMEZONE))}\n\n"
            f"✍️ Надішліть <b>нову дату та час</b>:\n\n"
            f"💡 <b>Як надіслати в групі:</b>\n"
            f"1️⃣ Надішліть як <b>відповідь (Reply / Відповісти)</b> на це повідомлення бота: <code>04.11 19:00</code>\n"
            f"2️⃣ Або прямою командою: <code>/reschedule 04.11 19:00</code>\n"
            f"<i>(Якщо бот є Адміністратором групи, можна надіслати і звичайним повідомленням)</i>"
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(prompt_text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
            await event.answer()
        else:
            await event.answer(prompt_text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        return

    # If multiple upcoming lessons, show selector
    tz_str = group.get("timezone", DEFAULT_TIMEZONE)
    kb = get_select_lesson_keyboard(upcoming, "resched_action", tz_str)
    text = "🔄 <b>Оберіть урок, який потрібно перенести:</b>"
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("resched_action_"))
async def prompt_reschedule_datetime(call: CallbackQuery, state: FSMContext):
    try:
        lesson_id = int(call.data.split("_")[-1])
    except (ValueError, IndexError):
        await call.answer("❌ Помилка: урок не знайдено.", show_alert=True)
        return

    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    group = await get_or_create_group(lesson["chat_id"])
    await state.update_data(lesson_id=lesson_id, chat_id=lesson["chat_id"])
    await state.set_state(RescheduleStates.waiting_for_new_datetime)

    dt_str = format_datetime_for_display(lesson["datetime_utc"], group.get("timezone", DEFAULT_TIMEZONE), group.get("student_timezone", ""))
    text = (
        f"🔄 <b>Перенесення уроку #{lesson_id}</b>\n"
        f"🗓 <b>Поточний час:</b> {dt_str}\n\n"
        f"✍️ Надішліть <b>нову дату та час</b>:\n\n"
        f"💡 <b>Як надіслати в групі:</b>\n"
        f"1️⃣ Надішліть як <b>відповідь (Reply / Відповісти)</b> на це повідомлення бота: <code>04.11 19:00</code>\n"
        f"2️⃣ Або прямою командою: <code>/reschedule 04.11 19:00</code>\n"
        f"<i>(Якщо бот є Адміністратором групи, можна надіслати і звичайним повідомленням)</i>\n\n"
        f"<i>Приклади запису:</i>\n"
        f"• <code>04.11 19:00</code>\n"
        f"• <code>завтра 17:30</code>\n"
        f"• <code>10.11.2026 19:00</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(RescheduleStates.waiting_for_new_datetime, ~F.text.startswith("/"))
@router.message(F.reply_to_message & F.reply_to_message.text.contains("Перенесення уроку"), ~F.text.startswith("/"))
async def process_reschedule_datetime(message: Message, state: FSMContext):
    import re
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    lesson = None
    if lesson_id:
        lesson = await get_lesson_by_id(lesson_id)

    # Fallback if state was lost (e.g. after container restart or timeout)
    if not lesson and message.reply_to_message and message.reply_to_message.text:
        m = re.search(r"Перенесення уроку #(\d+)", message.reply_to_message.text)
        if m:
            lesson = await get_lesson_by_id(int(m.group(1)))

    if not lesson:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        target_id = await get_target_chat_id(chat_id, user_id)
        upcoming = await get_upcoming_lessons(target_id, limit=1)
        if upcoming:
            lesson = upcoming[0]
            lesson_id = lesson["id"]

    if not lesson:
        await message.answer("❌ Помилка: урок не знайдено.")
        await state.clear()
        return

    lesson_id = lesson["id"]
    group = await get_or_create_group(lesson["chat_id"])
    tz_str = group.get("timezone", DEFAULT_TIMEZONE)
    parsed_dt = parse_user_datetime(message.text, tz_str)

    if not parsed_dt:
        await message.answer(
            "⚠️ Не вдалося розпізнати дату та час. Спробуйте ще раз у форматі:\n"
            "<code>ДД.ММ ГГ:ХХ</code> (наприклад: <code>04.11 19:00</code> або <code>завтра 16:00</code>):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    user_name = message.from_user.full_name
    if message.from_user.username:
        user_name += f" (@{message.from_user.username})"

    new_utc_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    new_lesson_id = await reschedule_lesson(lesson_id, new_utc_str, user_name)

    old_time_str = format_datetime_for_display(lesson["datetime_utc"], tz_str, group.get("student_timezone", ""))
    new_time_str = format_datetime_for_display(new_utc_str, tz_str, group.get("student_timezone", ""))

    await state.clear()
    success_text = (
        f"🔄 <b>УРОК УСПІШНО ПЕРЕНЕСЕНО!</b>\n\n"
        f"👤 <b>Ініціатор:</b> {user_name}\n"
        f"⏳ <b>Було:</b> {old_time_str}\n"
        f"✨ <b>Новий час:</b> {new_time_str}\n\n"
        f"📌 <i>Домашнє завдання автоматично перенесено на новий урок #{new_lesson_id}.</i>"
    )
    await message.answer(success_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))

# ----------------- CANCEL FLOW -----------------
@router.callback_query(F.data.startswith("cancel_lesson_"))
async def cb_cancel_lesson(call: CallbackQuery):
    lesson_id = int(call.data.split("_")[-1])
    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    group = await get_or_create_group(lesson["chat_id"])
    user_name = call.from_user.full_name
    if call.from_user.username:
        user_name += f" (@{call.from_user.username})"

    await cancel_lesson(lesson_id, user_name)
    dt_str = format_datetime_for_display(lesson["datetime_utc"], group.get("timezone", DEFAULT_TIMEZONE), group.get("student_timezone", ""))

    text = (
        f"❌ <b>Урок скасовано.</b>\n\n"
        f"🗓 <b>Був запланований на:</b> {dt_str}\n"
        f"👤 <b>Скасував(-ла):</b> {user_name}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
    await call.answer("Урок скасовано")

# ----------------- ADD SINGLE LESSON -----------------
@router.callback_query(F.data == "add_single_lesson")
async def cb_prompt_add_single(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddLessonStates.waiting_for_datetime)
    text = (
        "➕ <b>Додавання разового уроку</b>\n\n"
        "Введіть дату та час початку уроку:\n"
        "• <code>ДД.ММ ГГ:ХХ</code> (наприклад <code>08.11 17:00</code>)\n"
        "• або <code>завтра 18:00</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(AddLessonStates.waiting_for_datetime)
async def process_add_single(message: Message, state: FSMContext):
    target_id = await get_target_chat_id(message.chat.id, message.from_user.id)
    group = await get_or_create_group(target_id)
    tz_str = group.get("timezone", DEFAULT_TIMEZONE)
    parsed_dt = parse_user_datetime(message.text, tz_str)

    if not parsed_dt:
        await message.answer(
            "⚠️ Не вдалося розпізнати дату та час. Спробуйте ще раз (наприклад: <code>05.11 18:30</code>):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    utc_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    lesson_id = await add_lesson(target_id, utc_str)
    time_display = format_datetime_for_display(utc_str, tz_str, group.get("student_timezone", ""))

    await state.clear()
    await message.answer(
        f"✅ <b>Урок успішно додано!</b>\n\n"
        f"🕒 <b>Час:</b> {time_display}\n"
        f"🆔 Урок #{lesson_id}\n\n"
        f"🔔 Нагадування надійде за 5 хвилин до початку.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""))
    )

# ----------------- CLEAR HISTORY FLOW (PASSWORD PROTECTED) -----------------
@router.callback_query(F.data == "clear_history_prompt")
async def cb_clear_history_prompt(call: CallbackQuery, state: FSMContext):
    await state.set_state(ClearHistoryStates.waiting_for_password)
    text = (
        "🔒 <b>Очищення історії уроків</b>\n\n"
        "Ця дія захищена паролем.\n"
        "Будь ласка, <b>надішліть пароль адміністратора</b> повідомленням у чат:\n\n"
        "<i>(Повідомлення з паролем буде автоматично видалено для безпеки)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(ClearHistoryStates.waiting_for_password)
async def process_clear_password(message: Message, state: FSMContext):
    entered_pass = message.text.strip()
    
    # Try to delete user's message with password immediately for security
    try:
        await message.delete()
    except Exception:
        pass

    expected_pass = ADMIN_PASSWORD
    if not expected_pass or entered_pass != expected_pass:
        await message.answer(
            "❌ <b>Невірний пароль!</b>\n"
            "Спробуйте ще раз або натисніть «Скасувати дію» нижче:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    await state.clear()
    text = (
        "🔓 <b>Пароль підтверджено!</b>\n\n"
        "Оберіть, що саме ви бажаєте видалити:\n\n"
        "• <b>🧹 Видалити минулі / перенесені / скасовані</b> — видалить лише старі або неактивні уроки, "
        "а всі майбутні заплановані заняття залишаться недоторканими.\n\n"
        "• <b>💥 Очистити абсолютно ВСІ уроки</b> — повністю видалить усі уроки цього чату з бази даних."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_clear_options_keyboard())

@router.callback_query(F.data == "do_clear_past")
async def cb_do_clear_past(call: CallbackQuery):
    chat_id = call.message.chat.id
    count = await clear_past_lessons(chat_id)
    group = await get_or_create_group(chat_id)
    text = (
        f"🧹 <b>Історію успішно очищено!</b>\n\n"
        f"Видалено записів: <b>{count}</b> (минулі, перенесені та скасовані уроки).\n"
        f"Усі майбутні заплановані уроки збережено."
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
    await call.answer("Минулі уроки очищено")

@router.callback_query(F.data == "do_clear_all")
async def cb_do_clear_all(call: CallbackQuery):
    chat_id = call.message.chat.id
    count = await clear_all_lessons(chat_id)
    group = await get_or_create_group(chat_id)
    text = (
        f"💥 <b>Повне очищення виконано!</b>\n\n"
        f"Усі уроки (<b>{count}</b> шт.) повністю видалено з бази даних.\n"
        f"Ви можете згенерувати новий розклад у Налаштуваннях або додати уроки вручну."
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
    await call.answer("Усі уроки видалено")

# ----------------- POST-LESSON CONFIRMATION ("ЧИ ВІДБУВСЯ УРОК?") -----------------
@router.callback_query(F.data.startswith("held_yes_"))
async def cb_held_yes(call: CallbackQuery):
    lesson_id = int(call.data.split("_")[-1])
    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    await update_lesson_status(lesson_id, "completed")
    user_name = call.from_user.full_name
    new_bal = await get_paid_balance(lesson["chat_id"])

    text = (
        f"✅ <b>Урок відбувся!</b>\n\n"
        f"👤 <b>Підтвердив(-ла):</b> {user_name}\n"
        f"📌 Статус оновлено на «Відбувся».\n"
        f"💳 Списано 1 заняття з передоплати. Залишок: <b>{new_bal}</b> ур."
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer("Урок позначено як такий, що відбувся!")

@router.callback_query(F.data.startswith("held_no_"))
async def cb_held_no(call: CallbackQuery):
    lesson_id = int(call.data.split("_")[-1])
    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    await update_lesson_status(lesson_id, "cancelled")
    user_name = call.from_user.full_name
    cur_bal = await get_paid_balance(lesson["chat_id"])

    text = (
        f"❌ <b>Урок не відбувся (Скасовано).</b>\n\n"
        f"👤 <b>Відмітив(-ла):</b> {user_name}\n"
        f"💳 <b>Оплата не стягується!</b> Залишок на балансі: <b>{cur_bal}</b> ур.\n\n"
        f"<i>Ви можете перенести його на інший зручний час за потреби:</i>"
    )
    kb = from_keyboards = get_cancel_keyboard()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Перенести цей урок", callback_data=f"resched_action_{lesson_id}")],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer("Урок позначено як скасований")

# ----------------- EDIT HISTORY FLOW (PASSWORD PROTECTED) -----------------
@router.callback_query(F.data.startswith("edit_lesson_auth_"))
async def cb_edit_lesson_auth(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    lesson_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 0

    await state.update_data(lesson_id=lesson_id, page=page)
    await state.set_state(EditHistoryStates.waiting_for_password)

    text = (
        f"🔒 <b>Редагування запису уроку #{lesson_id}</b>\n\n"
        f"Ця дія захищена паролем адміністратора.\n"
        f"Будь ласка, <b>надішліть пароль</b> повідомленням у чат:\n\n"
        f"<i>(Повідомлення з паролем буде негайно автоматично видалено для безпеки)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(EditHistoryStates.waiting_for_password)
async def process_edit_password(message: Message, state: FSMContext):
    entered_pass = message.text.strip()
    
    # Try to delete password message immediately
    try:
        await message.delete()
    except Exception:
        pass

    expected_pass = ADMIN_PASSWORD
    if not expected_pass or entered_pass != expected_pass:
        await message.answer(
            "❌ <b>Невірний пароль!</b>\n"
            "Спробуйте ще раз або натисніть «Скасувати дію» нижче:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    page = data.get("page", 0)
    await state.clear()

    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await message.answer("❌ Урок не знайдено.")
        return

    group = await get_or_create_group(lesson["chat_id"])
    time_str = format_datetime_for_display(
        lesson["datetime_utc"],
        group.get("timezone", DEFAULT_TIMEZONE),
        group.get("student_timezone", "")
    )

    text = (
        f"🔓 <b>Пароль підтверджено!</b>\n\n"
        f"🛠 <b>Редагування уроку #{lesson_id}</b>\n"
        f"🗓 <b>Час:</b> {time_str}\n"
        f"📌 <b>Поточний статус:</b> {lesson.get('status')}\n\n"
        f"<i>Оберіть, що саме ви бажаєте змінити:</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_edit_lesson_menu_keyboard(lesson_id, page))

@router.callback_query(F.data.startswith("edit_status_menu_"))
async def cb_edit_status_menu(call: CallbackQuery):
    lesson_id = int(call.data.split("_")[-1])
    text = "🔄 <b>Оберіть новий статус для цього уроку:</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_status_select_keyboard(lesson_id))
    await call.answer()

@router.callback_query(F.data.startswith("set_stat_"))
async def cb_set_status(call: CallbackQuery):
    parts = call.data.split("_")
    lesson_id = int(parts[2])
    new_status = parts[3]

    await update_lesson_status(lesson_id, new_status)
    status_ua = {
        "scheduled": "🟢 Заплановано",
        "completed": "✅ Відбувся",
        "rescheduled": "🔄 Перенесено",
        "cancelled": "❌ Скасовано"
    }.get(new_status, new_status)

    text = (
        f"✅ <b>Статус уроку #{lesson_id} успішно змінено на:</b>\n"
        f"📌 {status_ua}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_edit_lesson_menu_keyboard(lesson_id))
    await call.answer("Статус оновлено!")

@router.callback_query(F.data.startswith("delete_lesson_"))
async def cb_delete_single_lesson(call: CallbackQuery):
    lesson_id = int(call.data.split("_")[-1])
    await delete_single_lesson(lesson_id)
    text = f"🗑 <b>Урок #{lesson_id} успішно видалено з історії занять!</b>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard())
    await call.answer("Урок видалено")

@router.callback_query(F.data.startswith("edit_dt_prompt_"))
async def cb_edit_dt_prompt(call: CallbackQuery, state: FSMContext):
    lesson_id = int(call.data.split("_")[-1])
    await state.update_data(lesson_id=lesson_id)
    await state.set_state(EditHistoryStates.waiting_for_new_datetime)

    text = (
        f"🕒 <b>Зміна дати та часу для уроку #{lesson_id}</b>\n\n"
        f"Введіть нову дату та час:\n"
        f"• <code>ДД.ММ ГГ:ХХ</code> (наприклад <code>05.11 19:30</code>)\n"
        f"• або <code>завтра 18:00</code> / <code>четвер 19:00</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(EditHistoryStates.waiting_for_new_datetime)
async def process_edit_dt(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await message.answer("❌ Урок не знайдено.")
        await state.clear()
        return

    group = await get_or_create_group(lesson["chat_id"])
    tz_str = group.get("timezone", DEFAULT_TIMEZONE)
    parsed_dt = parse_user_datetime(message.text, tz_str)

    if not parsed_dt:
        await message.answer(
            "⚠️ Не вдалося розпізнати дату та час. Спробуйте ще раз у форматі:\n"
            "<code>ДД.ММ ГГ:ХХ</code> (наприклад: <code>06.11 19:00</code>):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    new_utc_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    await update_lesson_datetime(lesson_id, new_utc_str)
    await state.clear()

    time_display = format_datetime_for_display(new_utc_str, tz_str, group.get("student_timezone", ""))
    await message.answer(
        f"✅ <b>Дату та час уроку #{lesson_id} успішно оновлено!</b>\n\n"
        f"🕒 <b>Новий час:</b> {time_display}",
        parse_mode="HTML",
        reply_markup=get_edit_lesson_menu_keyboard(lesson_id)
    )
