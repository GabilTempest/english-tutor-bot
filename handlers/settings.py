import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from zoneinfo import ZoneInfo, available_timezones

from database import (
    get_or_create_group,
    set_meeting_link,
    set_group_timezones,
    clear_recurring_rules,
    add_recurring_rule,
    get_recurring_rules,
    generate_recurring_lessons_for_group,
    get_paid_balance,
    get_target_chat_id
)
from utils.keyboards import get_settings_keyboard, get_cancel_keyboard, get_main_menu_keyboard
from utils.time_utils import DAYS_UA
from states import SettingsStates
from config import DEFAULT_TIMEZONE

from datetime import datetime
import os
from aiogram.types import FSInputFile
import config
from database import init_db

router = Router()

DAY_MAP = {
    "понеділок": 0, "щопонеділка": 0, "пн": 0, "mon": 0, "monday": 0,
    "вівторок": 1, "щовівторка": 1, "вт": 1, "tue": 1, "tuesday": 1,
    "середа": 2, "середу": 2, "щосереди": 2, "ср": 2, "wed": 2, "wednesday": 2,
    "четвер": 3, "четверга": 3, "щочетверга": 3, "чт": 3, "thu": 3, "thursday": 3,
    "п'ятниця": 4, "пятниця": 4, "п'ятницю": 4, "пятницю": 4, "щоп'ятниці": 4, "щопятниці": 4, "пт": 4, "fri": 4, "friday": 4,
    "субота": 5, "суботу": 5, "щосуботи": 5, "сб": 5, "sat": 5, "saturday": 5,
    "неділя": 6, "неділю": 6, "щонеділі": 6, "нд": 6, "sun": 6, "sunday": 6
}

CITY_TO_TZ = {
    "варшава": "Europe/Warsaw",
    "warsaw": "Europe/Warsaw",
    "лондон": "Europe/London",
    "london": "Europe/London",
    "берлін": "Europe/Berlin",
    "berlin": "Europe/Berlin",
    "прага": "Europe/Prague",
    "prague": "Europe/Prague",
    "париж": "Europe/Paris",
    "братислава": "Europe/Bratislava",
    "рим": "Europe/Rome",
    "нью-йорк": "America/New_York",
    "new york": "America/New_York",
    "київ": "Europe/Kyiv",
    "kyiv": "Europe/Kyiv"
}

@router.message(Command("settings"))
@router.callback_query(F.data == "settings_menu")
async def show_settings_menu(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)

    group = await get_or_create_group(target_id)

    link = group.get("meeting_link") or "<i>Не встановлено</i>"
    primary_tz = group.get("timezone", DEFAULT_TIMEZONE)
    student_tz = group.get("student_timezone") or "<i>Не налаштовано</i>"

    rules = await get_recurring_rules(target_id)
    if rules:
        rules_text = "\n".join([f"• {DAYS_UA[r['day_of_week']]} о {r['time_str']}" for r in rules])
    else:
        rules_text = "<i>Регулярний розклад не налаштовано</i>"

    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""

    text = (
        f"⚙️ <b>НАЛАШТУВАННЯ ГРУПИ</b>{sync_tag}\n\n"
        f"🔗 <b>Посилання на дзвінок:</b>\n{link}\n\n"
        f"⏰ <b>Регулярні уроки:</b>\n{rules_text}\n\n"
        f"🌍 <b>Часовий пояс викладача:</b> {primary_tz}\n"
        f"👤 <b>Часовий пояс учня:</b> {student_tz}\n\n"
        f"<i>Оберіть пункт, який бажаєте змінити:</i>"
    )

    kb = get_settings_keyboard()
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# ----------------- MEETING LINK SETTINGS -----------------
@router.message(Command("link"))
async def cmd_link(message: Message, state: FSMContext):
    target_id = await get_target_chat_id(message.chat.id, message.from_user.id)
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and ("http://" in args[1] or "https://" in args[1]):
        link = args[1].strip()
        await set_meeting_link(target_id, link)
        group = await get_or_create_group(target_id)
        balance = await get_paid_balance(target_id)
        await message.answer(
            f"✅ <b>Посилання збережено:</b>\n{link}\n\n"
            f"Тепер я автоматично надсилатиму його за 5 хвилин до кожного уроку!",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(link, balance)
        )
        return

    await state.set_state(SettingsStates.waiting_for_meeting_link)
    await message.answer(
        "🔗 <b>Надішліть посилання на заняття</b> (Google Meet, Zoom, MS Teams тощо):",
        reply_markup=get_cancel_keyboard()
    )

@router.callback_query(F.data == "set_link_action")
async def cb_set_link_action(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_meeting_link)
    text = (
        "🔗 <b>Налаштування посилання на онлайн-урок</b>\n\n"
        "Надішліть повідомленням постійне посилання для зустрічей (наприклад, посилання на Google Meet чи Zoom):\n\n"
        "<i>Бот автоматично додасть його до нагадувань за 5 хв до уроку.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(SettingsStates.waiting_for_meeting_link)
async def process_meeting_link(message: Message, state: FSMContext):
    link = message.text.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        await message.answer(
            "⚠️ Будь ласка, надішліть дійсне інтернет-посилання (має починатися з http:// або https://):",
            reply_markup=get_cancel_keyboard()
        )
        return

    target_id = await get_target_chat_id(message.chat.id, message.from_user.id)
    await set_meeting_link(target_id, link)
    group = await get_or_create_group(target_id)
    balance = await get_paid_balance(target_id)
    await state.clear()
    await message.answer(
        f"✅ <b>Постійне посилання успішно збережено!</b>\n\n"
        f"🔗 {link}\n\n"
        f"Бот надсилатиме його за 5 хвилин до кожного уроку.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(link, balance)
    )

# ----------------- REGULAR SCHEDULE SETTINGS -----------------
@router.message(Command("schedule"))
@router.message(Command("rules"))
async def cmd_schedule(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        message.text = args[1]
        await process_schedule_rules(message, state)
        return

    await cb_regular_rules_menu(message, state)

@router.callback_query(F.data == "regular_rules_menu")
async def cb_regular_rules_menu(call: CallbackQuery | Message, state: FSMContext = None):
    chat_id = call.chat.id if isinstance(call, Message) else call.message.chat.id
    user_id = call.from_user.id if hasattr(call, "from_user") and call.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)
    rules = await get_recurring_rules(target_id)
    if rules:
        rules_text = "\n".join([f"• <b>{DAYS_UA[r['day_of_week']]}</b> о <b>{r['time_str']}</b>" for r in rules])
    else:
        rules_text = "<i>Регулярних днів уроків ще немає.</i>"

    text = (
        f"📅 <b>РЕГУЛЯРНИЙ ЩОТИЖНЕВИЙ РОЗКЛАД</b>\n\n"
        f"{rules_text}\n\n"
        f"Ви можете задати дні та години занять (наприклад, щовівторка та щочетверга о 18:00), "
        f"і бот автоматично створить уроки наперед!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Задати новий розклад", callback_data="input_regular_rules")],
        [InlineKeyboardButton(text="🗑 Очистити щотижневий розклад", callback_data="clear_regular_rules")],
        [InlineKeyboardButton(text="🔙 Назад до налаштувань", callback_data="settings_menu")]
    ])
    if isinstance(call, CallbackQuery):
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await call.answer()
    else:
        await call.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "clear_regular_rules")
async def cb_clear_regular_rules(call: CallbackQuery):
    target_id = await get_target_chat_id(call.message.chat.id, call.from_user.id)
    await clear_recurring_rules(target_id)
    await call.answer("Розклад очищено!")
    await cb_regular_rules_menu(call, None)

@router.callback_query(F.data == "input_regular_rules")
async def cb_input_regular_rules(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📅 <b>Оберіть або введіть щотижневий розклад занять</b>\n\n"
        "Ви можете обрати один із популярних шаблонів занять в один клік або задати свій розклад:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Понеділок 19:30 + Четвер 19:00", callback_data="preset_sch_mon1930_thu1900")],
        [InlineKeyboardButton(text="🗓 Вівторок 18:00 + Четвер 18:00", callback_data="preset_sch_tue1800_thu1800")],
        [InlineKeyboardButton(text="🗓 Понеділок 19:00 + Середа 19:00", callback_data="preset_sch_mon1900_wed1900")],
        [InlineKeyboardButton(text="✏️ Ввести свій розклад вручну", callback_data="input_custom_schedule_text")],
        [InlineKeyboardButton(text="🔙 Назад до меню", callback_data="regular_rules_menu")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("preset_sch_"))
async def cb_preset_schedule(call: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)
    preset = call.data
    rules = []
    if preset == "preset_sch_mon1930_thu1900":
        rules = [(0, "19:30"), (3, "19:00")]
    elif preset == "preset_sch_tue1800_thu1800":
        rules = [(1, "18:00"), (3, "18:00")]
    elif preset == "preset_sch_mon1900_wed1900":
        rules = [(0, "19:00"), (2, "19:00")]

    if rules:
        await clear_recurring_rules(target_id)
        for day_idx, t_str in rules:
            await add_recurring_rule(target_id, day_idx, t_str)
        await generate_recurring_lessons_for_group(target_id, days_ahead=21)
        summary = "\n".join([f"• <b>{DAYS_UA[d]}</b> о <b>{t}</b>" for d, t in rules])
        group = await get_or_create_group(target_id)
        balance = await get_paid_balance(target_id)
        await call.message.edit_text(
            f"✅ <b>Щотижневий розклад успішно збережено!</b>\n\n"
            f"{summary}\n\n"
            f"🗓 Уроки на наступні 3 тижні автоматично згенеровано.\n"
            f"💳 Залишок оплачених занять: <b>{balance}</b> ур.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance)
        )
        await call.answer("Розклад збережено!")

@router.callback_query(F.data == "input_custom_schedule_text")
async def cb_input_custom_schedule_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_schedule_rules)
    text = (
        "📅 <b>Введіть щотижневий розклад занять</b>\n\n"
        "Напишіть дні та години через кому або з нового рядка.\n\n"
        "<i>Приклади запису:</i>\n"
        "• <code>вівторок 18:00, четвер 18:00</code>\n"
        "• <code>понеділок 19:30, четвер 19:00</code>\n\n"
        "<i>Час вказуйте за Києвом.</i>\n\n"
        "💡 <b>Для груп:</b> якщо бот не адміністратор, ви можете надіслати команду:\n"
        "<code>/schedule понеділок 19:30, четвер 19:00</code>\n"
        "або відповісти реплаєм (Reply) на це повідомлення."
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(SettingsStates.waiting_for_schedule_rules)
async def process_schedule_rules(message: Message, state: FSMContext):
    raw_text = message.text.lower()
    # Split by commas or newlines
    tokens = re.split(r"[,;\n]+", raw_text)
    
    parsed_rules = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Find day and time: e.g. "понеділок 19:30", "четвер о 19:00", "вт 18:00"
        m = re.search(r"([а-яіїєґa-z'’]+)(?:\s+(?:о|в|-))?\s+(\d{1,2}:\d{2})", token)
        if m:
            day_str, time_str = m.groups()
            day_idx = DAY_MAP.get(day_str)
            if day_idx is not None:
                # normalize time to HH:MM
                h, mn = map(int, time_str.split(":"))
                time_norm = f"{h:02d}:{mn:02d}"
                parsed_rules.append((day_idx, time_norm))

    if not parsed_rules:
        await message.answer(
            "⚠️ Не вдалося розпізнати дні та години.\n"
            "Спробуйте, будь ласка, у форматі:\n"
            "<code>вівторок 18:00, четвер 18:00</code> або скористайтесь шаблонами.",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    target_id = await get_target_chat_id(message.chat.id, message.from_user.id)
    await clear_recurring_rules(target_id)
    for day_idx, t_str in parsed_rules:
        await add_recurring_rule(target_id, day_idx, t_str)

    # Generate lessons for the next 3 weeks
    await generate_recurring_lessons_for_group(target_id, days_ahead=21)
    await state.clear()

    summary = "\n".join([f"• <b>{DAYS_UA[d]}</b> о <b>{t}</b>" for d, t in parsed_rules])
    group = await get_or_create_group(target_id)
    balance = await get_paid_balance(target_id)
    await message.answer(
        f"✅ <b>Щотижневий розклад успішно збережено!</b>\n\n"
        f"{summary}\n\n"
        f"🗓 Уроки на наступні 3 тижні автоматично згенеровано. "
        f"Ви завжди можете переглянути їх у списку, додати ДЗ або перенести будь-який із них.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance)
    )

# ----------------- TIMEZONE SETTINGS -----------------
@router.callback_query(F.data == "set_tz_action")
async def cb_set_tz_action(call: CallbackQuery, state: FSMContext):
    chat_id = call.message.chat.id
    group = await get_or_create_group(chat_id)

    curr_primary = group.get("timezone", DEFAULT_TIMEZONE)
    curr_student = group.get("student_timezone") or "Не вказано"

    text = (
        f"🌍 <b>НАЛАШТУВАННЯ ЧАСОВИХ ПОЯСІВ</b>\n\n"
        f"🇺🇦 <b>Основний час:</b> {curr_primary}\n"
        f"👤 <b>Час учня:</b> {curr_student}\n\n"
        f"Якщо учень перебуває за кордоном, оберіть його часовий пояс нижче, "
        f"щоб у розкладі відображався подвійний час (наприклад: <i>18:00 Київ / 17:00 Варшава</i>):"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇵🇱 Варшава (Польща)", callback_data="quick_tz_Europe/Warsaw"),
            InlineKeyboardButton(text="🇬🇧 Лондон (Британія)", callback_data="quick_tz_Europe/London")
        ],
        [
            InlineKeyboardButton(text="🇩🇪 Берлін (Німеччина)", callback_data="quick_tz_Europe/Berlin"),
            InlineKeyboardButton(text="🇨🇿 Прага (Чехія)", callback_data="quick_tz_Europe/Prague")
        ],
        [
            InlineKeyboardButton(text="🇺🇸 Нью-Йорк (США)", callback_data="quick_tz_America/New_York"),
            InlineKeyboardButton(text="🇪🇸 Мадрид (Іспанія)", callback_data="quick_tz_Europe/Madrid")
        ],
        [
            InlineKeyboardButton(text="✍️ Ввести інше місто/пояс", callback_data="custom_tz_input"),
            InlineKeyboardButton(text="❌ Тільки Київ", callback_data="quick_tz_none")
        ],
        [InlineKeyboardButton(text="🔙 Назад до налаштувань", callback_data="settings_menu")]
    ])

    if isinstance(call, CallbackQuery):
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await call.answer()
    else:
        await call.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("quick_tz_"))
async def cb_quick_tz(call: CallbackQuery):
    tz_val = call.data.replace("quick_tz_", "")
    chat_id = call.message.chat.id
    group = await get_or_create_group(chat_id)

    if tz_val == "none":
        await set_group_timezones(chat_id, DEFAULT_TIMEZONE, "")
        msg = "✅ Додатковий пояс вимкнено. Усі уроки показуються за Києвом."
    else:
        await set_group_timezones(chat_id, DEFAULT_TIMEZONE, tz_val)
        label = tz_val.split("/")[-1].replace("_", " ")
        msg = f"✅ Часовий пояс учня встановлено: <b>{label} ({tz_val})</b>."

    await call.message.edit_text(msg, parse_mode="HTML", reply_markup=get_settings_keyboard())
    await call.answer()

@router.callback_query(F.data == "custom_tz_input")
async def cb_custom_tz_input(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_timezones)
    text = (
        "🌍 <b>Введіть місто або назву часового поясу учня:</b>\n\n"
        "<i>Приклади:</i>\n"
        "• <code>Варшава</code>, <code>Лондон</code>, <code>Берлін</code>, <code>Прага</code>\n"
        "• або офіційний формат IANA: <code>Europe/Bratislava</code>, <code>America/Chicago</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(SettingsStates.waiting_for_timezones)
async def process_custom_timezone(message: Message, state: FSMContext):
    raw_tz = message.text.strip().lower()
    resolved_tz = CITY_TO_TZ.get(raw_tz)

    if not resolved_tz:
        # Check if raw_tz matches any available timezone
        all_tzs = available_timezones()
        for tz in all_tzs:
            if raw_tz in tz.lower():
                resolved_tz = tz
                break

    if not resolved_tz:
        await message.answer(
            "⚠️ Не вдалося знайти такий часовий пояс.\n"
            "Введіть назву міста (наприклад: <i>Варшава, Лондон, Берлін, Нью-Йорк</i>) "
            "або пояс у форматі <code>Europe/Warsaw</code>:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    chat_id = message.chat.id
    await set_group_timezones(chat_id, DEFAULT_TIMEZONE, resolved_tz)
    await state.clear()

    label = resolved_tz.split("/")[-1].replace("_", " ")
    group = await get_or_create_group(chat_id)
    await message.answer(
        f"✅ <b>Часовий пояс учня успішно встановлено!</b>\n\n"
        f"🌍 {label} (<code>{resolved_tz}</code>)\n"
        f"Тепер час занять автоматично конвертуватиметься для зручності учня.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""))
    )

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if not os.path.exists(config.DB_PATH):
        await message.answer("❌ Файл бази даних ще не створено.")
        return
    now_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"tutor_bot_backup_{now_str}.db"
    doc = FSInputFile(config.DB_PATH, filename=filename)
    await message.answer_document(
        document=doc,
        caption="💾 <b>Резервна копія бази даних</b>\n\nЗбережіть цей файл. У разі потреби ви зможете відновити стан, надіславши файл боту або у відповідь на /restore.",
        parse_mode="HTML"
    )

@router.message(Command("restore"))
@router.message(F.document & (F.caption.contains("restore") | F.caption.contains("відновити")))
async def cmd_restore(message: Message):
    doc = message.document
    if not doc and message.reply_to_message and message.reply_to_message.document:
        doc = message.reply_to_message.document

    if not doc:
        await message.answer(
            "ℹ️ Щоб відновити базу даних, надішліть файл <code>.db</code> або дайте відповідь (Reply) на файл командою <code>/restore</code>.",
            parse_mode="HTML"
        )
        return

    file_name = doc.file_name or ""
    if not (file_name.endswith(".db") or file_name.endswith(".sqlite")):
        await message.answer("⚠️ Файл повинен мати розширення <code>.db</code> або <code>.sqlite</code>.", parse_mode="HTML")
        return

    try:
        file = await message.bot.get_file(doc.file_id)
        backup_path = str(config.DB_PATH) + ".bak"
        if os.path.exists(config.DB_PATH):
            import shutil
            shutil.copy2(config.DB_PATH, backup_path)

        await message.bot.download_file(file.file_path, destination=config.DB_PATH)
        await init_db()
        await message.answer("✅ <b>Базу даних успішно відновлено!</b>\nВсі уроки, розклад та історію завантажено.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Помилка відновлення бази даних: {e}")
