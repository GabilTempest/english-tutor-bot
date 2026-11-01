from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import (
    get_or_create_group,
    get_upcoming_lessons,
    get_lesson_by_id,
    update_lesson_homework,
    get_all_lessons,
    get_target_chat_id
)
from utils.keyboards import (
    get_cancel_keyboard,
    get_main_menu_keyboard
)
from utils.time_utils import format_datetime_for_display
from states import HomeworkStates
from config import DEFAULT_TIMEZONE
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(Command("hw"))
@router.callback_query(F.data == "hw_menu")
async def show_current_hw(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)

    group = await get_or_create_group(target_id)
    upcoming = await get_upcoming_lessons(target_id, limit=1)

    tz_str = group.get("timezone", DEFAULT_TIMEZONE)
    tz_student = group.get("student_timezone", "")

    if not upcoming:
        # Check if there is any latest lesson
        all_lessons = await get_all_lessons(target_id, limit=1)
        if not all_lessons:
            msg = (
                "📝 <b>Домашнє завдання</b>\n\n"
                "Зараз немає жодного уроку в базі даних. Спочатку створіть розклад або додайте урок!"
            )
            kb = get_main_menu_keyboard(group.get("meeting_link", ""))
            if isinstance(event, CallbackQuery):
                await event.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
                await event.answer()
            else:
                await event.answer(msg, parse_mode="HTML", reply_markup=kb)
            return
        target_lesson = all_lessons[0]
        lesson_label = "останнього проведеного уроку"
    else:
        target_lesson = upcoming[0]
        lesson_label = "наступного уроку"

    dt_str = format_datetime_for_display(target_lesson["datetime_utc"], tz_str, tz_student)
    hw_text = target_lesson.get("homework", "").strip() or "<i>Домашнє завдання поки що не записано.</i>"

    text = (
        f"📝 <b>ДОМАШНЄ ЗАВДАННЯ</b> ({lesson_label})\n\n"
        f"🗓 <b>Урок:</b> {dt_str}\n\n"
        f"📖 <b>Завдання:</b>\n{hw_text}\n\n"
        f"<i>Учень або вчитель можуть записати або доповнити завдання кнопкою нижче:</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Записати / змінити ДЗ", callback_data=f"edit_hw_{target_lesson['id']}")],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("edit_hw_"))
async def prompt_edit_hw(call: CallbackQuery, state: FSMContext):
    lesson_id = int(call.data.split("_")[-1])
    lesson = await get_lesson_by_id(lesson_id)
    if not lesson:
        await call.answer("❌ Урок не знайдено!", show_alert=True)
        return

    group = await get_or_create_group(lesson["chat_id"])
    await state.update_data(lesson_id=lesson_id)
    await state.set_state(HomeworkStates.waiting_for_text)

    dt_str = format_datetime_for_display(
        lesson["datetime_utc"],
        group.get("timezone", DEFAULT_TIMEZONE),
        group.get("student_timezone", "")
    )
    current_hw = lesson.get("homework", "").strip()
    current_hw_note = f"\n\n<b>Поточне ДЗ:</b>\n{current_hw}" if current_hw else ""

    text = (
        f"✏️ <b>Запис домашнього завдання</b>\n"
        f"🗓 <b>Урок:</b> {dt_str}{current_hw_note}\n\n"
        f"Надішліть новий текст домашнього завдання (вправи, посилання, сторінки тощо):\n"
        f"<i>(Повідомлення можна надіслати прямо в чат)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(HomeworkStates.waiting_for_text)
async def process_homework_text(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    lesson = await get_lesson_by_id(lesson_id)

    if not lesson:
        await message.answer("❌ Урок не знайдено.")
        await state.clear()
        return

    hw_text = message.text.strip()
    await update_lesson_homework(lesson_id, hw_text)

    group = await get_or_create_group(lesson["chat_id"])
    dt_str = format_datetime_for_display(
        lesson["datetime_utc"],
        group.get("timezone", DEFAULT_TIMEZONE),
        group.get("student_timezone", "")
    )

    user_name = message.from_user.full_name
    if message.from_user.username:
        user_name += f" (@{message.from_user.username})"

    await state.clear()
    await message.answer(
        f"✅ <b>ДОМАШНЄ ЗАВДАННЯ ЗБЕРЕЖЕНО!</b>\n\n"
        f"🗓 <b>До уроку:</b> {dt_str}\n"
        f"👤 <b>Записав(-ла):</b> {user_name}\n\n"
        f"📖 <b>Текст завдання:</b>\n{hw_text}",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""))
    )
