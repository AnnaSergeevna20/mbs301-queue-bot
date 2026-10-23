from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any
from utils import DAYS_RU_SHORT

def get_subjects_keyboard(subjects: List[Dict[str, Any]], chat_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком всех доступных предметов.
    """
    buttons = []
    for sub in subjects:
        title = sub["title"]
        buttons.append([
            InlineKeyboardButton(
                text=f"📚 {title}", 
                callback_data=f"sub_view:{sub['id']}"
            )
        ])
    
    # Кнопки управления
    controls = [
        InlineKeyboardButton(text="➕ Добавить предмет", callback_data="sub_add"),
        InlineKeyboardButton(text="🗑 Удалить предмет", callback_data="sub_delete_list")
    ]
    buttons.append(controls)
    buttons.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data="sub_refresh_list")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subject_actions_keyboard(subject_id: int, is_user_in_queue: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура действий внутри конкретного предмета.
    """
    buttons = []
    
    if not is_user_in_queue:
        buttons.append([
            InlineKeyboardButton(text="➕ Записаться (по имени в TG)", callback_data=f"queue_join:{subject_id}"),
            InlineKeyboardButton(text="✍️ Записаться (ввести имя)", callback_data=f"queue_join_custom:{subject_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="❌ Выписаться из очереди", callback_data=f"queue_leave:{subject_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"queue_refresh:{subject_id}")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к предметам", callback_data="sub_refresh_list")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_schedule_type_keyboard() -> InlineKeyboardMarkup:
    """
    Выбор типа расписания при создании предмета.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Еженедельно (по дню недели)", callback_data="sched_weekly")],
        [InlineKeyboardButton(text="📅 Конкретная дата", callback_data="sched_date")],
        [InlineKeyboardButton(text="🟢 Всегда открыта", callback_data="sched_always")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

def get_days_of_week_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора дня недели (0=Пн .. 6=Вс).
    """
    row1 = [InlineKeyboardButton(text=DAYS_RU_SHORT[i], callback_data=f"dow_{i}") for i in range(4)]
    row2 = [InlineKeyboardButton(text=DAYS_RU_SHORT[i], callback_data=f"dow_{i}") for i in range(4, 7)]
    row_cancel = [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row_cancel])

def get_delete_subjects_keyboard(subjects: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Клавиатура удаления предметов.
    """
    buttons = []
    for sub in subjects:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {sub['title']}", 
                callback_data=f"sub_del_do:{sub['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sub_refresh_list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

def get_confirm_clear_keyboard(subject_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Да, очистить!", callback_data=f"queue_clear_yes:{subject_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"sub_view:{subject_id}")
        ]
    ])
