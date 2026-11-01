from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter, KICKED, MEMBER, ADMINISTRATOR
from aiogram.fsm.context import FSMContext

from database import (
    get_or_create_group,
    get_upcoming_lessons,
    generate_recurring_lessons_for_group,
    get_target_chat_id
)
from utils.keyboards import get_main_menu_keyboard, get_lesson_detail_keyboard
from utils.time_utils import format_datetime_for_display

router = Router()

def get_welcome_text(group_title: str = "", meeting_link: str = "", balance: int = 0, is_synced: bool = False) -> str:
    if is_synced and group_title:
        title_part = f" для групи <b>{group_title}</b> <i>(🔄 синхронізовано з чатом)</i>"
    elif group_title:
        title_part = f" для групи <b>{group_title}</b>"
    else:
        title_part = ""
    link_info = f"\n🔗 <b>Постійне посилання:</b> {meeting_link}" if meeting_link else "\n⚠️ <i>Посилання на заняття ще не встановлено (налаштуйте в Меню -> Налаштування).</i>"
    balance_info = f"\n💳 <b>Оплачених занять на балансі:</b> {balance} ур."
    
    return (
        f"👋 <b>Привіт! Я бот для організації уроків англійської мови{title_part}.</b>\n\n"
        f"<b>Що я вмію:</b>\n"
        f"• 🔔 <b>Нагадувати за 5 хвилин</b> до уроку з прямим посиланням на зустріч.\n"
        f"• 💳 <b>Рахувати оплачені уроки</b> (показує біля кожного запланованого уроку: <i>Оплачено</i> чи <i>Очікує оплати</i>).\n"
        f"• 📝 <b>Зберігати домашнє завдання</b> (і учень, і викладач можуть записати ДЗ текстом).\n"
        f"• 🔄 <b>Переносити уроки</b> (при перенесенні чи скасуванні оплата не стягується!).\n"
        f"• 📚 <b>Зберігати історію</b> всіх уроків та опитувати, чи відбувся урок.{link_info}{balance_info}\n\n"
        f"<i>Оберіть дію в меню нижче або скористайтесь командами:</i>\n"
        f"• /menu — Головне меню\n"
        f"• /balance — Баланс оплачених занять\n"
        f"• /next — Найближчий урок\n"
        f"• /hw — Домашнє завдання\n"
        f"• /lessons — Список та історія уроків\n"
        f"• /schedule — Регулярний розклад\n"
        f"• /link — Посилання на дзвінок"
    )

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)
    if target_id < 0:
        await generate_recurring_lessons_for_group(target_id)
    group = await get_or_create_group(target_id, message.chat.title or message.from_user.full_name)
    balance = group.get("paid_lessons_balance", 0)
    text = get_welcome_text(group.get("chat_title", ""), group.get("meeting_link", ""), balance, is_synced=(chat_id > 0 and target_id < 0))
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance))

@router.message(Command("menu"))
@router.message(Command("help"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)
    group = await get_or_create_group(target_id, message.chat.title or message.from_user.full_name)
    balance = group.get("paid_lessons_balance", 0)
    text = get_welcome_text(group.get("chat_title", ""), group.get("meeting_link", ""), balance, is_synced=(chat_id > 0 and target_id < 0))
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance))

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)
    group = await get_or_create_group(target_id, call.message.chat.title or "")
    balance = group.get("paid_lessons_balance", 0)
    text = get_welcome_text(group.get("chat_title", ""), group.get("meeting_link", ""), balance, is_synced=(chat_id > 0 and target_id < 0))
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance))
    await call.answer()

@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)
    group = await get_or_create_group(target_id, call.message.chat.title or "")
    balance = group.get("paid_lessons_balance", 0)
    await call.message.edit_text("❌ Дію скасовано.", reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), balance))
    await call.answer("Скасовано")

@router.message(Command("next"))
@router.callback_query(F.data == "next_lesson")
async def show_next_lesson(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)
    group = await get_or_create_group(target_id)
    upcoming = await get_upcoming_lessons(target_id, limit=1)

    if not upcoming:
        msg = (
            "ℹ️ <b>Наразі немає запланованих найближчих уроків.</b>\n\n"
            "Ви можете додати урок вручну або налаштувати щотижневий регулярний розклад у Налаштуваннях."
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
            await event.answer()
        else:
            await event.answer(msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(group.get("meeting_link", "")))
        return

    lesson = upcoming[0]
    dt_formatted = format_datetime_for_display(
        lesson["datetime_utc"],
        group.get("timezone", "Europe/Kyiv"),
        group.get("student_timezone", "")
    )
    
    hw_text = lesson.get("homework", "").strip() or "<i>Домашнє завдання не записано</i>"
    link = group.get("meeting_link", "").strip()
    link_info = f"🔗 <b>Посилання на дзвінок:</b> {link}\n" if link else "⚠️ <i>Посилання ще не встановлено</i>\n"

    text = (
        f"📅 <b>НАЙБЛИЖЧИЙ УРОК</b>\n\n"
        f"🕒 <b>Дата та час:</b> {dt_formatted}\n"
        f"📌 <b>Статус:</b> 🟢 Заплановано\n"
        f"{link_info}\n"
        f"📝 <b>Домашнє завдання:</b>\n{hw_text}\n\n"
        f"<i>Ви можете записати нове ДЗ або перенести урок за допомогою кнопок нижче:</i>"
    )

    kb = get_lesson_detail_keyboard(lesson, page=0)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# Automatic greeting when bot is added to a group
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER | ADMINISTRATOR))
async def bot_added_to_chat(event: ChatMemberUpdated):
    chat = event.chat
    group = await get_or_create_group(chat.id, chat.title or "")
    welcome_text = (
        f"🎉 <b>Дякую за додавання бота до групи {chat.title}!</b>\n\n"
        f"Тепер я допомагатиму організовувати уроки англійської мови:\n"
        f"• Нагадуватиму за 5 хв до уроку\n"
        f"• Допомагатиму записувати домашнє завдання\n"
        f"• Дозволятиму учню та вчителю переносити заняття\n"
        f"• Зберігатиму всю історію та розклад уроків\n\n"
        f"👉 Почніть із налаштування постійного посилання на зустріч (/link) "
        f"або відкрийте /menu."
    )
    await event.bot.send_message(
        chat_id=chat.id,
        text=welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""))
    )
