from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any
from utils.time_utils import format_short_date
from config import DEFAULT_TIMEZONE

def get_main_menu_keyboard(meeting_link: str = "", paid_balance: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📅 Найближчий урок", callback_data="next_lesson"),
            InlineKeyboardButton(text="📝 Домашнє завдання", callback_data="hw_menu")
        ],
        [
            InlineKeyboardButton(text="📚 Усі уроки та історія", callback_data="list_lessons_0"),
            InlineKeyboardButton(text="🔄 Перенести урок", callback_data="reschedule_select")
        ],
        [
            InlineKeyboardButton(text=f"💳 Оплачено: {paid_balance} ур.", callback_data="balance_menu"),
            InlineKeyboardButton(text="⚙️ Налаштування", callback_data="settings_menu")
        ]
    ]
    if meeting_link:
        buttons.insert(0, [InlineKeyboardButton(text="🔗 Приєднатися до дзвінка", url=meeting_link)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_lessons_list_keyboard(
    lessons: List[Dict[str, Any]], 
    page: int = 0, 
    total_pages: int = 1, 
    tz_str: str = DEFAULT_TIMEZONE,
    paid_lesson_ids: set = None
) -> InlineKeyboardMarkup:
    buttons = []
    if paid_lesson_ids is None:
        paid_lesson_ids = set()
    
    status_icons = {
        "scheduled": "🟢",
        "completed": "✅",
        "rescheduled": "🔄",
        "cancelled": "❌"
    }
    
    for l in lessons:
        icon = status_icons.get(l.get("status"), "▫️")
        dt_str = format_short_date(l["datetime_utc"], tz_str)
        status = l.get("status")

        if status == "scheduled":
            if l["id"] in paid_lesson_ids:
                status_part = "Оплачено 💳"
            else:
                status_part = "Не оплачено ⏳"
        else:
            status_part = {
                "completed": "Відбувся",
                "rescheduled": "Перенесено",
                "cancelled": "Скасовано"
            }.get(status, "")
        
        has_hw = " 📝" if l.get("homework") else ""
        btn_text = f"{icon} {dt_str} ({status_part}){has_hw}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_lesson_{l['id']}_{page}")])

    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"list_lessons_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"list_lessons_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="➕ Додати разовий урок", callback_data="add_single_lesson"),
        InlineKeyboardButton(text="🗑 Очистити історію", callback_data="clear_history_prompt")
    ])
    buttons.append([
        InlineKeyboardButton(text="💳 Керувати оплатою", callback_data="balance_menu"),
        InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_clear_options_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Видалити минулі / перенесені / скасовані", callback_data="do_clear_past")],
        [InlineKeyboardButton(text="💥 Очистити абсолютно ВСІ уроки", callback_data="do_clear_all")],
        [InlineKeyboardButton(text="🔙 Скасувати", callback_data="list_lessons_0")]
    ])

def get_lesson_detail_keyboard(lesson: Dict[str, Any], page: int = 0) -> InlineKeyboardMarkup:
    lesson_id = lesson["id"]
    status = lesson.get("status")
    buttons = []

    # If scheduled, allow rescheduling, editing homework, and cancelling
    if status == "scheduled":
        buttons.append([
            InlineKeyboardButton(text="✏️ Записати / змінити ДЗ", callback_data=f"edit_hw_{lesson_id}"),
            InlineKeyboardButton(text="🔄 Перенести цей урок", callback_data=f"resched_action_{lesson_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="❌ Скасувати урок", callback_data=f"cancel_lesson_{lesson_id}")
        ])
    else:
        # For completed or rescheduled lessons, still allow viewing/updating past homework or notes
        buttons.append([
            InlineKeyboardButton(text="📝 Додати / редагувати ДЗ", callback_data=f"edit_hw_{lesson_id}")
        ])

    # Edit lesson with password option
    buttons.append([
        InlineKeyboardButton(text="⚙️ Редагувати цей запис (пароль)", callback_data=f"edit_lesson_auth_{lesson_id}_{page}")
    ])

    buttons.append([
        InlineKeyboardButton(text="🔙 До списку уроків", callback_data=f"list_lessons_{page}"),
        InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_lesson_menu_keyboard(lesson_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Змінити статус уроку", callback_data=f"edit_status_menu_{lesson_id}")],
        [InlineKeyboardButton(text="🕒 Змінити дату та час", callback_data=f"edit_dt_prompt_{lesson_id}")],
        [InlineKeyboardButton(text="📝 Змінити ДЗ", callback_data=f"edit_hw_{lesson_id}")],
        [InlineKeyboardButton(text="🗑 Видалити цей урок з історії", callback_data=f"delete_lesson_{lesson_id}")],
        [InlineKeyboardButton(text="🔙 Назад до уроку", callback_data=f"view_lesson_{lesson_id}_{page}")]
    ])

def get_status_select_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Заплановано", callback_data=f"set_stat_{lesson_id}_scheduled")],
        [InlineKeyboardButton(text="✅ Відбувся", callback_data=f"set_stat_{lesson_id}_completed")],
        [InlineKeyboardButton(text="🔄 Перенесено", callback_data=f"set_stat_{lesson_id}_rescheduled")],
        [InlineKeyboardButton(text="❌ Скасовано", callback_data=f"set_stat_{lesson_id}_cancelled")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"view_lesson_{lesson_id}_0")]
    ])

def get_balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати оплачені уроки", callback_data="add_balance_prompt")],
        [InlineKeyboardButton(text="✏️ Встановити точний баланс", callback_data="set_balance_prompt")],
        [InlineKeyboardButton(text="🔄 Скинути баланс до 0", callback_data="reset_balance_confirm")],
        [InlineKeyboardButton(text="📚 Переглянути уроки", callback_data="list_lessons_0")],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])

def get_add_balance_quick_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="+1", callback_data="add_bal_val_1"),
            InlineKeyboardButton(text="+2", callback_data="add_bal_val_2"),
            InlineKeyboardButton(text="+3", callback_data="add_bal_val_3"),
            InlineKeyboardButton(text="+4", callback_data="add_bal_val_4")
        ],
        [
            InlineKeyboardButton(text="+5", callback_data="add_bal_val_5"),
            InlineKeyboardButton(text="+8", callback_data="add_bal_val_8"),
            InlineKeyboardButton(text="+10", callback_data="add_bal_val_10"),
            InlineKeyboardButton(text="+12", callback_data="add_bal_val_12")
        ],
        [InlineKeyboardButton(text="✏️ Ввести число вручну текстом", callback_data="add_balance_custom_text")],
        [InlineKeyboardButton(text="🔙 До меню балансу", callback_data="balance_menu")]
    ])

def get_set_balance_quick_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="0", callback_data="set_bal_val_0"),
            InlineKeyboardButton(text="1", callback_data="set_bal_val_1"),
            InlineKeyboardButton(text="2", callback_data="set_bal_val_2"),
            InlineKeyboardButton(text="3", callback_data="set_bal_val_3")
        ],
        [
            InlineKeyboardButton(text="4", callback_data="set_bal_val_4"),
            InlineKeyboardButton(text="5", callback_data="set_bal_val_5"),
            InlineKeyboardButton(text="8", callback_data="set_bal_val_8"),
            InlineKeyboardButton(text="10", callback_data="set_bal_val_10")
        ],
        [InlineKeyboardButton(text="✏️ Ввести інше число вручну", callback_data="set_balance_custom_text")],
        [InlineKeyboardButton(text="🔙 До меню балансу", callback_data="balance_menu")]
    ])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати дію", callback_data="cancel_action")]
    ])

def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Змінити посилання на урок", callback_data="set_link_action")],
        [InlineKeyboardButton(text="📅 Налаштувати регулярний розклад", callback_data="regular_rules_menu")],
        [InlineKeyboardButton(text="🌍 Налаштувати часовий пояс", callback_data="set_tz_action")],
        [InlineKeyboardButton(text="🏠 Головне меню", callback_data="main_menu")]
    ])

def get_select_lesson_keyboard(lessons: List[Dict[str, Any]], action_prefix: str, tz_str: str = DEFAULT_TIMEZONE) -> InlineKeyboardMarkup:
    """Shows upcoming lessons to select for an action (e.g. reschedule or edit hw)."""
    buttons = []
    for l in lessons:
        dt_str = format_short_date(l["datetime_utc"], tz_str)
        buttons.append([
            InlineKeyboardButton(text=f"🗓 {dt_str}", callback_data=f"{action_prefix}_{l['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Скасувати", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
