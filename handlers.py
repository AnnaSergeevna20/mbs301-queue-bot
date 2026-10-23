import re
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_subjects, get_subject, add_subject, delete_subject,
    get_queue, add_to_queue, remove_from_queue, clear_queue,
    get_user_entry, set_subject_last_message, get_subject_last_message
)
from utils import check_queue_status, format_queue_text, DAYS_RU
from keyboards import (
    get_subjects_keyboard, get_subject_actions_keyboard,
    get_schedule_type_keyboard, get_days_of_week_keyboard,
    get_delete_subjects_keyboard, get_cancel_keyboard
)

router = Router()

class AddSubjectStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_schedule_type = State()
    waiting_for_day_of_week = State()
    waiting_for_date = State()
    waiting_for_open_time = State()
    waiting_for_close_time = State()
    waiting_for_limit = State()

class JoinCustomNameStates(StatesGroup):
    waiting_for_custom_name = State()

def clean_time(time_str: str) -> str:
    """Нормализует формат времени ЧЧ:ММ"""
    match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", time_str.strip())
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        return f"{h:02d}:{m:02d}"
    return ""

# ==================== БАЗОВЫЕ КОМАНДЫ ====================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "👋 <b>Привет! Я бот для ведения очередей по предметам.</b>\n\n"
        "Вы можете использовать меня прямо здесь или <b>добавить в беседу/группу группы</b>!\n\n"
        "📌 <b>Основные возможности:</b>\n"
        "• Запись в очередь на предметы в один клик\n"
        "• Автоматическое открытие и закрытие записи по расписанию (дни недели, часы)\n"
        "• Любой участник может добавить или удалить предмет\n"
        "• Возможность записаться со своим именем или по нику\n\n"
        "Нажмите /queue или кнопку ниже, чтобы посмотреть список предметов."
    )
    subjects = await get_subjects(message.chat.id)
    kb = get_subjects_keyboard(subjects, message.chat.id)
    await message.answer(welcome_text, reply_markup=kb)

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 <b>Справка по командам:</b>\n\n"
        "/queue или /list — список предметов и просмотр очередей\n"
        "/add_subject — добавить новый предмет с расписанием\n"
        "/del_subject — удалить предмет\n"
        "/help — это сообщение\n\n"
        "💡 <i>Совет: В группе просто нажмите кнопку нужного предмета, чтобы записаться!</i>"
    )
    await message.answer(help_text)

@router.message(Command("queue", "list"))
async def cmd_queue(message: Message, state: FSMContext):
    await state.clear()
    subjects = await get_subjects(message.chat.id)
    if not subjects:
        kb = get_subjects_keyboard([], message.chat.id)
        await message.answer(
            "📋 Список предметов пока пуст.\nВы можете добавить первый предмет с помощью кнопки ниже или команды /add_subject.",
            reply_markup=kb
        )
        return

    kb = get_subjects_keyboard(subjects, message.chat.id)
    await message.answer("📚 <b>Выберите предмет для просмотра очереди:</b>", reply_markup=kb)

# ==================== ПРОСМОТР И ДЕЙСТВИЯ С ОЧЕРЕДЬЮ ====================

@router.callback_query(F.data == "sub_refresh_list")
async def cb_refresh_subjects_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = call.message.chat.id
    subjects = await get_subjects(chat_id)
    kb = get_subjects_keyboard(subjects, chat_id)
    
    if not subjects:
        text = "📋 Список предметов пока пуст.\nДобавьте предмет кнопкой ниже:"
    else:
        text = "📚 <b>Выберите предмет для просмотра очереди:</b>"
        
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()

async def send_or_replace_queue_message(bot, chat_id: int, subject_id: int, old_msg_id: int = 0):
    """
    Удаляет предыдущее сообщение бота с очередью и отправляет в чат
    новое актуальное сообщение со всем списком и кнопками.
    """
    subject = await get_subject(subject_id)
    if not subject:
        return
    queue = await get_queue(subject_id)
    text = format_queue_text(subject, queue)
    kb = get_subject_actions_keyboard(subject_id, is_user_in_queue=False)

    # Собираем ID старых сообщений для удаления
    last_id = await get_subject_last_message(subject_id)
    ids_to_del = set()
    if old_msg_id:
        ids_to_del.add(old_msg_id)
    if last_id and last_id != 0:
        ids_to_del.add(last_id)

    for mid in ids_to_del:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    new_msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
    await set_subject_last_message(subject_id, new_msg.message_id)
    return new_msg

@router.callback_query(F.data.startswith("sub_view:"))
async def cb_view_subject(call: CallbackQuery, state: FSMContext):
    await state.clear()
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден или был удалён.", show_alert=True)
        return

    queue = await get_queue(subject_id)
    user_entry = await get_user_entry(subject_id, call.from_user.id)
    is_in_queue = user_entry is not None

    text = format_queue_text(subject, queue)
    kb = get_subject_actions_keyboard(subject_id, is_user_in_queue=is_in_queue)
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
        await set_subject_last_message(subject_id, call.message.message_id)
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data.startswith("queue_refresh:"))
async def cb_refresh_queue(call: CallbackQuery):
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден.", show_alert=True)
        return

    queue = await get_queue(subject_id)
    user_entry = await get_user_entry(subject_id, call.from_user.id)
    is_in_queue = user_entry is not None

    text = format_queue_text(subject, queue)
    kb = get_subject_actions_keyboard(subject_id, is_user_in_queue=is_in_queue)
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
        await set_subject_last_message(subject_id, call.message.message_id)
        await call.answer("Список обновлён!")
    except Exception:
        await call.answer("Список уже актуален.")

@router.callback_query(F.data.startswith("queue_join:"))
async def cb_queue_join(call: CallbackQuery):
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден.", show_alert=True)
        return

    # Проверка статуса (время/день недели)
    is_open, status_text = check_queue_status(subject)
    if not is_open:
        await call.answer(f"⛔ Запись сейчас закрыта!\n{status_text}", show_alert=True)
        return

    # Определяем имя
    first_name = call.from_user.first_name or ""
    last_name = call.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip() or "Участник"
    username = call.from_user.username

    success, msg, pos = await add_to_queue(subject_id, call.from_user.id, full_name, username)
    if not success:
        await call.answer(f"⚠️ {msg}", show_alert=True)
        return

    await call.answer(f"🎉 Вы успешно записаны! Ваш номер: #{pos}", show_alert=True)

    # Удаляем старое сообщение бота и присылаем новое со всем списком
    await send_or_replace_queue_message(
        call.bot, 
        call.message.chat.id, 
        subject_id, 
        old_msg_id=call.message.message_id
    )

@router.callback_query(F.data.startswith("queue_join_custom:"))
async def cb_queue_join_custom(call: CallbackQuery, state: FSMContext):
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден.", show_alert=True)
        return

    # Проверка статуса
    is_open, status_text = check_queue_status(subject)
    if not is_open:
        await call.answer(f"⛔ Запись сейчас закрыта!\n{status_text}", show_alert=True)
        return

    # Проверка, не записан ли уже
    user_entry = await get_user_entry(subject_id, call.from_user.id)
    if user_entry:
        await call.answer("Вы уже записаны в эту очередь!", show_alert=True)
        return

    await state.set_state(JoinCustomNameStates.waiting_for_custom_name)
    await state.update_data(
        subject_id=subject_id, 
        message_id=call.message.message_id,
        chat_id=call.message.chat.id
    )

    await call.message.reply(
        f"✍️ <b>{call.from_user.first_name}</b>, напишите в ответ своё имя и фамилию для записи в очередь:",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(JoinCustomNameStates.waiting_for_custom_name)
async def process_custom_name(message: Message, state: FSMContext):
    data = await state.get_data()
    subject_id = data.get("subject_id")
    target_msg_id = data.get("message_id")
    chat_id = data.get("chat_id")

    custom_name = message.text.strip()
    if len(custom_name) < 2:
        await message.reply("Имя слишком короткое. Введите нормальное имя и фамилию:")
        return

    subject = await get_subject(subject_id)
    if not subject:
        await message.reply("Предмет больше не существует.")
        await state.clear()
        return

    is_open, status_text = check_queue_status(subject)
    if not is_open:
        await message.reply(f"⛔ Запись уже закрыта! ({status_text})")
        await state.clear()
        return

    username = message.from_user.username
    success, msg, pos = await add_to_queue(subject_id, message.from_user.id, custom_name, username)
    await state.clear()

    if not success:
        await message.reply(f"⚠️ {msg}")
        return

    # Пытаемся удалить сообщение с введенным именем, чтобы чат оставался чистым
    try:
        await message.delete()
    except Exception:
        pass

    # Удаляем старое сообщение бота и присылаем новое со всем списком в чат
    if chat_id:
        await send_or_replace_queue_message(
            message.bot, 
            chat_id, 
            subject_id, 
            old_msg_id=target_msg_id or 0
        )

@router.callback_query(F.data.startswith("queue_leave:"))
async def cb_queue_leave(call: CallbackQuery):
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден.", show_alert=True)
        return

    removed = await remove_from_queue(subject_id, call.from_user.id)
    if removed:
        await call.answer("Вы успешно выписались из очереди.", show_alert=True)
    else:
        await call.answer("Вы не были записаны в эту очередь.", show_alert=True)

    # Удаляем старое сообщение бота и присылаем новое со всем списком
    await send_or_replace_queue_message(
        call.bot, 
        call.message.chat.id, 
        subject_id, 
        old_msg_id=call.message.message_id
    )

# ==================== ДОБАВЛЕНИЕ ПРЕДМЕТА (FSM) ====================

@router.message(Command("add_subject"))
@router.callback_query(F.data == "sub_add")
async def start_add_subject(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddSubjectStates.waiting_for_title)

    text = "📝 <b>Шаг 1 из 4:</b> Введите название предмета (например, <i>Высшая математика</i> или <i>Физика Лаб</i>):"
    kb = get_cancel_keyboard()

    if isinstance(event, CallbackQuery):
        await event.message.reply(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)

@router.message(AddSubjectStates.waiting_for_title)
async def process_subject_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 2 or len(title) > 60:
        await message.reply("Название должно быть от 2 до 60 символов. Попробуйте еще раз:")
        return

    await state.update_data(title=title)
    await state.set_state(AddSubjectStates.waiting_for_schedule_type)
    
    text = f"📅 <b>Шаг 2 из 4:</b> Выберите расписание для предмета <b>{title}</b>:"
    kb = get_schedule_type_keyboard()
    await message.reply(text, reply_markup=kb)

@router.callback_query(AddSubjectStates.waiting_for_schedule_type, F.data == "sched_always")
async def process_sched_always(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    title = data["title"]
    chat_id = call.message.chat.id

    sub_id = await add_subject(
        chat_id=chat_id,
        title=title,
        schedule_type="always"
    )
    await state.clear()

    await call.message.edit_text(
        f"✅ Предмет <b>{title}</b> успешно добавлен!\nЗапись на него открыта всегда.",
        reply_markup=get_subjects_keyboard(await get_subjects(chat_id), chat_id)
    )
    await call.answer()

@router.callback_query(AddSubjectStates.waiting_for_schedule_type, F.data == "sched_weekly")
async def process_sched_weekly(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddSubjectStates.waiting_for_day_of_week)
    await call.message.edit_text(
        "🗓 <b>Выберите день недели</b>, в который будет проходить запись:",
        reply_markup=get_days_of_week_keyboard()
    )
    await call.answer()

@router.callback_query(AddSubjectStates.waiting_for_day_of_week, F.data.startswith("dow_"))
async def process_day_of_week(call: CallbackQuery, state: FSMContext):
    dow = int(call.data.split("_")[1])
    await state.update_data(day_of_week=dow, schedule_type="weekly")
    await state.set_state(AddSubjectStates.waiting_for_open_time)

    day_name = DAYS_RU[dow]
    await call.message.edit_text(
        f"⏰ Выбран день: <b>{day_name}</b>.\n\n"
        "<b>Шаг 3 из 4:</b> Введите <b>время открытия записи</b> в формате <code>ЧЧ:ММ</code> (например, <code>09:00</code> или <code>18:30</code>):",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.callback_query(AddSubjectStates.waiting_for_schedule_type, F.data == "sched_date")
async def process_sched_date(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddSubjectStates.waiting_for_date)
    await call.message.edit_text(
        "📅 Введите конкретную дату в формате <code>ДД.ММ.ГГГГ</code> (например, <code>25.10.2026</code>):",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(AddSubjectStates.waiting_for_date)
async def process_date_input(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        db_date_str = dt.strftime("%Y-%m-%d")
    except ValueError:
        await message.reply("Неверный формат даты. Введите дату как <code>ДД.ММ.ГГГГ</code> (например <code>25.10.2026</code>):")
        return

    await state.update_data(target_date=db_date_str, schedule_type="date")
    await state.set_state(AddSubjectStates.waiting_for_open_time)

    await message.reply(
        f"⏰ Дата: <b>{date_str}</b>.\n\n"
        "<b>Шаг 3 из 4:</b> Введите <b>время открытия записи</b> в формате <code>ЧЧ:ММ</code> (например, <code>09:00</code>):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSubjectStates.waiting_for_open_time)
async def process_open_time(message: Message, state: FSMContext):
    open_time = clean_time(message.text)
    if not open_time:
        await message.reply("Неверный формат времени. Введите в формате <code>ЧЧ:ММ</code> (например, <code>09:00</code>):")
        return

    await state.update_data(open_time=open_time)
    await state.set_state(AddSubjectStates.waiting_for_close_time)

    await message.reply(
        f"Время открытия: <b>{open_time}</b>.\n\n"
        "<b>Шаг 4 из 4:</b> Введите <b>время закрытия записи</b> в формате <code>ЧЧ:ММ</code> (например, <code>21:00</code>):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSubjectStates.waiting_for_close_time)
async def process_close_time(message: Message, state: FSMContext):
    close_time = clean_time(message.text)
    if not close_time:
        await message.reply("Неверный формат времени. Введите в формате <code>ЧЧ:ММ</code> (например, <code>21:00</code>):")
        return

    data = await state.get_data()
    open_time = data["open_time"]
    if close_time <= open_time:
        await message.reply(f"Время закрытия ({close_time}) должно быть позже времени открытия ({open_time})! Попробуйте снова:")
        return

    await state.update_data(close_time=close_time)
    await state.set_state(AddSubjectStates.waiting_for_limit)

    await message.reply(
        f"Время закрытия: <b>{close_time}</b>.\n\n"
        "🔢 Укажите максимальное количество мест (или введите <code>0</code>, если без ограничений):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSubjectStates.waiting_for_limit)
async def process_max_limit(message: Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        if limit < 0 or limit > 500:
            raise ValueError()
    except ValueError:
        await message.reply("Введите целое число от 0 до 500 (0 — без ограничений):")
        return

    data = await state.get_data()
    chat_id = message.chat.id

    title = data["title"]
    schedule_type = data.get("schedule_type", "always")
    day_of_week = data.get("day_of_week")
    target_date = data.get("target_date")
    open_time = data.get("open_time")
    close_time = data.get("close_time")

    await add_subject(
        chat_id=chat_id,
        title=title,
        schedule_type=schedule_type,
        day_of_week=day_of_week,
        target_date=target_date,
        open_time=open_time,
        close_time=close_time,
        max_places=limit
    )
    await state.clear()

    sched_info = ""
    if schedule_type == "weekly":
        sched_info = f"\n🗓 Каждый {DAYS_RU[day_of_week]} с {open_time} до {close_time}"
    elif schedule_type == "date":
        sched_info = f"\n📅 Дата {target_date} с {open_time} до {close_time}"

    limit_info = f"\nЛимит мест: {limit}" if limit > 0 else "\nЛимит мест: без ограничений"

    subjects = await get_subjects(chat_id)
    kb = get_subjects_keyboard(subjects, chat_id)
    await message.reply(
        f"✅ Предмет <b>{title}</b> успешно создан!{sched_info}{limit_info}\n\n"
        "Теперь участники могут записываться в очередь!",
        reply_markup=kb
    )

# ==================== УДАЛЕНИЕ ПРЕДМЕТА ====================

@router.message(Command("del_subject"))
@router.callback_query(F.data == "sub_delete_list")
async def show_delete_subjects(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    subjects = await get_subjects(chat_id)

    if not subjects:
        msg = "Нет предметов для удаления."
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await event.reply(msg)
        return

    kb = get_delete_subjects_keyboard(subjects)
    text = "🗑 <b>Выберите предмет, который хотите удалить:</b>\n<i>Внимание: очередь по этому предмету также будет удалена!</i>"

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.reply(text, reply_markup=kb)

@router.callback_query(F.data.startswith("sub_del_do:"))
async def cb_delete_subject_action(call: CallbackQuery):
    subject_id = int(call.data.split(":")[1])
    subject = await get_subject(subject_id)
    if not subject:
        await call.answer("Предмет не найден или уже удалён.", show_alert=True)
        return

    title = subject["title"]
    await delete_subject(subject_id)
    await call.answer(f"🗑 Предмет '{title}' удалён!", show_alert=True)

    chat_id = call.message.chat.id
    subjects = await get_subjects(chat_id)
    kb = get_subjects_keyboard(subjects, chat_id)
    await call.message.edit_text(
        f"Предмет <b>{title}</b> был успешно удалён.\n\n📚 Список оставшихся предметов:",
        reply_markup=kb
    )

# ==================== ОТМЕНА ДЕЙСТВИЯ ====================

@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = call.message.chat.id
    subjects = await get_subjects(chat_id)
    kb = get_subjects_keyboard(subjects, chat_id)
    await call.message.edit_text("❌ Действие отменено.", reply_markup=kb)
    await call.answer()
