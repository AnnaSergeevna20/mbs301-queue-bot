from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple
from config import TIMEZONE

DAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье"
]

DAYS_RU_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

def get_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(TIMEZONE))
    except Exception:
        return datetime.now()

def parse_time_str(time_str: str) -> time:
    parts = time_str.strip().split(":")
    return time(int(parts[0]), int(parts[1]))

def check_queue_status(subject: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Проверяет, открыта ли запись на предмет.
    Возвращает (is_open: bool, status_description: str).
    """
    now = get_now()
    schedule_type = subject.get("schedule_type", "always")

    if schedule_type == "always":
        return True, "🟢 Открыта всегда"

    open_time_str = subject.get("open_time")
    close_time_str = subject.get("close_time")

    if not open_time_str or not close_time_str:
        return True, "🟢 Открыта"

    t_open = parse_time_str(open_time_str)
    t_close = parse_time_str(close_time_str)

    if schedule_type == "weekly":
        dow = subject.get("day_of_week")
        day_name = DAYS_RU[dow] if dow is not None and 0 <= dow <= 6 else "Указанный день"
        
        curr_dow = now.weekday()
        curr_time = now.time()

        if curr_dow == dow:
            if curr_time < t_open:
                return False, f"⏳ Откроется сегодня ({day_name}) в {open_time_str}"
            elif curr_time > t_close:
                return False, f"🔴 Запись закрыта (была открыта до {close_time_str})"
            else:
                return True, f"🟢 Открыта сегодня до {close_time_str}"
        else:
            return False, f"⏳ Запись откроется в {day_name} с {open_time_str} до {close_time_str}"

    elif schedule_type == "date":
        target_date_str = subject.get("target_date")
        if not target_date_str:
            return True, "🟢 Открыта"
        
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except Exception:
            return True, "🟢 Открыта"

        curr_date = now.date()
        curr_time = now.time()

        if curr_date < target_date:
            return False, f"⏳ Запись откроется {target_date.strftime('%d.%m.%Y')} в {open_time_str}"
        elif curr_date > target_date:
            return False, f"🔴 Запись завершена {target_date.strftime('%d.%m.%Y')}"
        else: # Сегодня
            if curr_time < t_open:
                return False, f"⏳ Откроется сегодня в {open_time_str}"
            elif curr_time > t_close:
                return False, f"🔴 Запись закрыта сегодня в {close_time_str}"
            else:
                return True, f"🟢 Открыта сегодня до {close_time_str}"

    return True, "🟢 Открыта"

def should_queue_be_cleared(subject: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Определяет, закрыта ли очередь и должна ли она быть очищена.
    Возвращает (should_clear: bool, cycle_id: str).
    Если очередь открыта прямо сейчас - возвращает (False, "").
    Если очередь закрыта - возвращает (True, идентификатор_цикла).
    """
    now = get_now()
    schedule_type = subject.get("schedule_type", "always")

    if schedule_type == "always":
        return False, ""

    close_time_str = subject.get("close_time")
    open_time_str = subject.get("open_time")
    if not close_time_str:
        return False, ""

    t_close = parse_time_str(close_time_str)
    t_open = parse_time_str(open_time_str) if open_time_str else time(0, 0)

    if schedule_type == "weekly":
        dow = subject.get("day_of_week")
        if dow is None:
            return False, ""

        curr_dow = now.weekday()
        curr_time = now.time()

        if curr_dow == dow:
            if curr_time >= t_close:
                # Сегодня день записи, и время закрытия наступило
                return True, f"weekly_{now.strftime('%Y-%m-%d')}"
            elif curr_time < t_open:
                # Сегодня день записи, но время открытия еще не настало (очищаем от прошлой недели)
                return True, f"pre_{now.strftime('%Y-%m-%d')}"
            else:
                # Прямо сейчас запись открыта! Не очищаем.
                return False, ""
        else:
            # Сегодня другой день недели (запись закрыта)
            # Находим дату последнего прошедшего дня dow
            days_since = (curr_dow - dow) % 7
            last_date = now.date() - timedelta(days=days_since)
            return True, f"weekly_{last_date.strftime('%Y-%m-%d')}"

    elif schedule_type == "date":
        target_date_str = subject.get("target_date")
        if not target_date_str:
            return False, ""
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except Exception:
            return False, ""

        curr_date = now.date()
        curr_time = now.time()

        if curr_date > target_date:
            return True, f"date_{target_date_str}"
        elif curr_date == target_date:
            if curr_time >= t_close:
                return True, f"date_{target_date_str}"
            elif curr_time < t_open:
                return True, f"pre_date_{target_date_str}"
            else:
                return False, ""
        else:
            # Дата еще не наступила
            return False, ""

    return False, ""

def format_queue_text(subject: Dict[str, Any], queue: List[Dict[str, Any]]) -> str:
    """
    Форматирует красивое сообщение с очередью для группы.
    """
    is_open, status_text = check_queue_status(subject)
    max_places = subject.get("max_places", 0)
    limit_str = f" / {max_places}" if max_places > 0 else ""

    text_parts = [
        f"📋 <b>Очередь: {subject['title']}</b>",
        f"Статус: {status_text}"
    ]

    # Инфо о расписании
    stype = subject.get("schedule_type", "always")
    if stype == "weekly":
        dow = subject.get("day_of_week", 0)
        day_name = DAYS_RU[dow]
        ot = subject.get("open_time", "")
        ct = subject.get("close_time", "")
        text_parts.append(f"⏰ Расписание: каждый {day_name} с {ot} до {ct}")
    elif stype == "date":
        d = subject.get("target_date", "")
        ot = subject.get("open_time", "")
        ct = subject.get("close_time", "")
        text_parts.append(f"📅 Дата: {d} с {ot} до {ct}")

    text_parts.append(f"👥 Записано: <b>{len(queue)}{limit_str}</b> чел.\n")

    if not queue:
        text_parts.append("<i>В очереди пока никого нет. Будь первым! 👇</i>")
    else:
        text_parts.append("📝 <b>Текущий список очереди:</b>")
        for idx, entry in enumerate(queue, start=1):
            name = entry["user_name"]
            uname = f" (@{entry['username']})" if entry.get("username") else ""
            text_parts.append(f"<b>{idx}.</b> {name}{uname}")

    return "\n".join(text_parts)
