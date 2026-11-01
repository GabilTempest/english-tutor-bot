from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import (
    get_or_create_group,
    get_paid_balance,
    add_paid_balance,
    set_paid_balance,
    get_target_chat_id
)
from utils.keyboards import (
    get_balance_keyboard,
    get_add_balance_quick_keyboard,
    get_set_balance_quick_keyboard,
    get_cancel_keyboard,
    get_main_menu_keyboard
)
from states import BalanceStates

router = Router()

@router.message(Command("balance"))
@router.message(Command("pay"))
@router.callback_query(F.data == "balance_menu")
async def show_balance_menu(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    user_id = event.from_user.id if hasattr(event, "from_user") and event.from_user else None
    target_id = await get_target_chat_id(chat_id, user_id)

    group = await get_or_create_group(target_id)
    balance = await get_paid_balance(target_id)
    group_name = group.get("chat_title") or ("Англійська Пн/Чт" if target_id < 0 else "")
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""

    # Check if command has arguments (e.g. /pay 2, /pay 4, /balance +2)
    if isinstance(event, Message):
        parts = event.text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip().lstrip("+").isdigit():
            amount = int(parts[1].strip().lstrip("+"))
            new_bal = await add_paid_balance(target_id, amount)
            await event.answer(
                f"✅ <b>Баланс успішно поповнено на +{amount} ур.!</b>{sync_tag}\n\n"
                f"💳 <b>Поточний залишок:</b> {new_bal} оплачених занять.\n"
                f"<i>Біля запланованих уроків оновлено позначки «Оплачено 💳».</i>",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
            )
            return

    text = (
        f"💳 <b>ОБЛІК ОПЛАЧЕНИХ УРОКІВ</b>{sync_tag}\n\n"
        f"💰 <b>Залишок оплачених занять:</b> <b>{balance}</b> ур.\n\n"
        f"<b>Як працює облік:</b>\n"
        f"• Біля найближчих {balance} запланованих уроків автоматично пишеться <b>(Оплачено 💳)</b>.\n"
        f"• Якщо урок виходить за межі балансу, пишеться <b>(Не оплачено ⏳)</b>.\n"
        f"• <b>Важливо:</b> якщо урок скасовано або перенесено — <b>плата не стягується</b>!\n"
        f"• Оплата списується лише тоді, коли урок підтверджено як такий, що <b>відбувся</b>.\n\n"
        f"<i>Оберіть дію нижче для зміни балансу:</i>"
    )

    kb = get_balance_keyboard()
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# ---------------- QUICK BUTTONS FOR ADDING BALANCE ----------------
@router.callback_query(F.data == "add_balance_prompt")
async def cb_add_balance_prompt(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "➕ <b>Поповнення кількості оплачених уроків</b>\n\n"
        "Скільки уроків оплатив учень?\n"
        "Оберіть кнопку швидкого поповнення нижче або натисніть «Ввести число вручну»:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_add_balance_quick_keyboard())
    await call.answer()

@router.callback_query(F.data.startswith("add_bal_val_"))
async def cb_add_bal_val(call: CallbackQuery, state: FSMContext):
    await state.clear()
    amount_str = call.data.split("_")[-1]
    if not amount_str.isdigit():
        await call.answer("Помилка", show_alert=True)
        return
    amount = int(amount_str)
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)

    new_bal = await add_paid_balance(target_id, amount)
    group = await get_or_create_group(target_id)
    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""

    await call.message.edit_text(
        f"✅ <b>Баланс успішно поповнено на +{amount} ур.!</b>{sync_tag}\n\n"
        f"💳 <b>Тепер на балансі:</b> <b>{new_bal}</b> оплачених занять.\n"
        f"У списку уроків найближчі заплановані заняття отримали статус <b>(Оплачено 💳)</b>.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
    )
    await call.answer(f"+{amount} додано!")

@router.callback_query(F.data == "add_balance_custom_text")
async def cb_add_balance_custom_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BalanceStates.waiting_for_add_amount)
    text = (
        "✏️ <b>Введіть кількість уроків повідомленням</b>\n\n"
        "Надішліть число (наприклад: <code>4</code> або <code>8</code>):\n\n"
        "<i>💡 Порада для груп: якщо бот не адміністратор, ви також можете надіслати команду <code>/pay 4</code> або відповісти реплаєм (Reply) на це повідомлення.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(BalanceStates.waiting_for_add_amount, ~F.text.startswith("/"))
@router.message(F.reply_to_message & F.reply_to_message.text.contains("Введіть кількість уроків"), ~F.text.startswith("/"))
async def process_add_balance(message: Message, state: FSMContext):
    val = message.text.strip().lstrip("+")
    if not val.isdigit() or int(val) <= 0:
        await message.answer(
            "⚠️ Будь ласка, надішліть ціле додатне число (наприклад: <code>4</code> або <code>8</code>):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    amount = int(val)
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)

    new_bal = await add_paid_balance(target_id, amount)
    group = await get_or_create_group(target_id)
    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""
    await state.clear()

    await message.answer(
        f"✅ <b>Баланс поповнено на +{amount} уроків!</b>{sync_tag}\n\n"
        f"💳 <b>Тепер на балансі:</b> <b>{new_bal}</b> оплачених занять.\n"
        f"У розкладі біля запланованих занять з'явилася позначка <b>(Оплачено 💳)</b>.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
    )

# ---------------- QUICK BUTTONS FOR SETTING BALANCE ----------------
@router.callback_query(F.data == "set_balance_prompt")
async def cb_set_balance_prompt(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "✏️ <b>Встановлення точного балансу уроків</b>\n\n"
        "Оберіть точну кількість оплачених занять, яка має бути на балансі зараз:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_set_balance_quick_keyboard())
    await call.answer()

@router.callback_query(F.data.startswith("set_bal_val_"))
async def cb_set_bal_val(call: CallbackQuery, state: FSMContext):
    await state.clear()
    val_str = call.data.split("_")[-1]
    if not val_str.isdigit():
        await call.answer("Помилка", show_alert=True)
        return
    balance = int(val_str)
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)

    new_bal = await set_paid_balance(target_id, balance)
    group = await get_or_create_group(target_id)
    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""

    await call.message.edit_text(
        f"✅ <b>Баланс встановлено:</b> <b>{new_bal}</b> оплачених занять.{sync_tag}\n\n"
        f"Позначки <b>(Оплачено 💳)</b> та <b>(Не оплачено ⏳)</b> автоматично оновлено.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
    )
    await call.answer(f"Баланс: {new_bal}")

@router.callback_query(F.data == "set_balance_custom_text")
async def cb_set_balance_custom_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BalanceStates.waiting_for_set_amount)
    text = (
        "✏️ <b>Введіть точну кількість оплачених занять</b>\n\n"
        "Надішліть число повідомленням (наприклад: <code>0</code>, <code>2</code>, <code>5</code>):\n\n"
        "<i>💡 Порада для груп: надішліть відповідь реплаєм (Reply) на це повідомлення або надайте боту права адміністратора в групі.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await call.answer()

@router.message(BalanceStates.waiting_for_set_amount, ~F.text.startswith("/"))
@router.message(F.reply_to_message & F.reply_to_message.text.contains("точну кількість"), ~F.text.startswith("/"))
async def process_set_balance(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 0:
        await message.answer(
            "⚠️ Будь ласка, надішліть невід'ємне число (наприклад: <code>0</code>, <code>3</code> або <code>6</code>):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    balance = int(val)
    chat_id = message.chat.id
    user_id = message.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)

    new_bal = await set_paid_balance(target_id, balance)
    group = await get_or_create_group(target_id)
    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""
    await state.clear()

    await message.answer(
        f"✅ <b>Баланс встановлено:</b> <b>{new_bal}</b> оплачених уроків.{sync_tag}\n\n"
        f"Позначки біля запланованих занять автоматично оновлено.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
    )

@router.callback_query(F.data == "reset_balance_confirm")
async def cb_reset_balance_confirm(call: CallbackQuery):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    target_id = await get_target_chat_id(chat_id, user_id)

    new_bal = await set_paid_balance(target_id, 0)
    group = await get_or_create_group(target_id)
    group_name = group.get("chat_title") or ""
    sync_tag = f" <i>(Група: <b>{group_name}</b>)</i>" if (chat_id > 0 and group_name) else ""

    await call.message.edit_text(
        f"🔄 <b>Баланс оплачених уроків скинуто до 0.</b>{sync_tag}\n\n"
        f"Усі заплановані уроки тепер мають статус <i>(Не оплачено ⏳)</i>.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(group.get("meeting_link", ""), new_bal)
    )
    await call.answer("Баланс скинуто")
