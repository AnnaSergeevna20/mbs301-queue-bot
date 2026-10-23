import aiosqlite
from typing import List, Optional, Dict, Any
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                schedule_type TEXT NOT NULL DEFAULT 'always', -- 'always', 'weekly', 'date'
                day_of_week INTEGER,                         -- 0=Пн, 1=Вт, ... 6=Вс
                target_date TEXT,                            -- YYYY-MM-DD
                open_time TEXT,                              -- HH:MM
                close_time TEXT,                             -- HH:MM
                max_places INTEGER DEFAULT 0,                -- 0 = без лимита
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
                UNIQUE(subject_id, user_id)
            );
        """)
        # Проверяем и добавляем колонку last_cleared_cycle если таблица уже создана
        try:
            await db.execute("ALTER TABLE subjects ADD COLUMN last_cleared_cycle TEXT DEFAULT ''")
        except Exception:
            pass

        # Проверяем и добавляем колонку last_message_id если её нет
        try:
            await db.execute("ALTER TABLE subjects ADD COLUMN last_message_id INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()

async def get_subjects(chat_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subjects WHERE chat_id = ? ORDER BY id ASC", 
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_subject(subject_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subjects WHERE id = ?", 
            (subject_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def add_subject(
    chat_id: int, 
    title: str, 
    schedule_type: str = "always",
    day_of_week: Optional[int] = None,
    target_date: Optional[str] = None,
    open_time: Optional[str] = None,
    close_time: Optional[str] = None,
    max_places: int = 0
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO subjects 
            (chat_id, title, schedule_type, day_of_week, target_date, open_time, close_time, max_places)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, title, schedule_type, day_of_week, target_date, open_time, close_time, max_places)
        )
        await db.commit()
        return cursor.lastrowid

async def delete_subject(subject_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM queue_entries WHERE subject_id = ?", (subject_id,))
        cursor = await db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_queue(subject_id: int) -> List[Dict[str, Any]]:
    await check_and_auto_clear_queue(subject_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM queue_entries 
            WHERE subject_id = ? 
            ORDER BY id ASC
            """,
            (subject_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def check_and_auto_clear_queue(subject_id: int) -> bool:
    """
    Проверяет, закрыта ли очередь предмета, и очищает её,
    если она еще не была очищена для этого закрытия.
    """
    from utils import should_queue_be_cleared

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)) as cursor:
            subject = await cursor.fetchone()
            if not subject:
                return False
            sub_dict = dict(subject)

        should_clear, cycle_id = should_queue_be_cleared(sub_dict)
        if should_clear and cycle_id:
            last_cleared = sub_dict.get("last_cleared_cycle") or ""
            if last_cleared != cycle_id:
                await db.execute("DELETE FROM queue_entries WHERE subject_id = ?", (subject_id,))
                await db.execute("UPDATE subjects SET last_cleared_cycle = ? WHERE id = ?", (cycle_id, subject_id))
                await db.commit()
                return True
    return False

async def auto_clear_all_closed_queues() -> int:
    """
    Проверяет все предметы и автоматически очищает закрытые очереди.
    """
    from utils import should_queue_be_cleared

    cleared_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM subjects WHERE schedule_type != 'always'") as cursor:
            subjects = await cursor.fetchall()

        for sub in subjects:
            sub_dict = dict(sub)
            should_clear, cycle_id = should_queue_be_cleared(sub_dict)
            if should_clear and cycle_id:
                last_cleared = sub_dict.get("last_cleared_cycle") or ""
                if last_cleared != cycle_id:
                    sub_id = sub_dict["id"]
                    await db.execute("DELETE FROM queue_entries WHERE subject_id = ?", (sub_id,))
                    await db.execute("UPDATE subjects SET last_cleared_cycle = ? WHERE id = ?", (cycle_id, sub_id))
                    cleared_count += 1
        if cleared_count > 0:
            await db.commit()
    return cleared_count

async def add_to_queue(
    subject_id: int, 
    user_id: int, 
    user_name: str, 
    username: Optional[str]
) -> tuple[bool, str, int]:
    """
    Возвращает (success, status_message, position)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Проверяем, существует ли предмет и есть ли лимит мест
        async with db.execute("SELECT max_places FROM subjects WHERE id = ?", (subject_id,)) as cursor:
            sub = await cursor.fetchone()
            if not sub:
                return False, "Предмет не найден или был удалён.", 0
            max_places = sub["max_places"]

        # Проверяем, записан ли уже
        async with db.execute(
            "SELECT id FROM queue_entries WHERE subject_id = ? AND user_id = ?",
            (subject_id, user_id)
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                return False, "Вы уже записаны в эту очередь!", 0

        # Проверяем лимит
        if max_places > 0:
            async with db.execute(
                "SELECT COUNT(*) as cnt FROM queue_entries WHERE subject_id = ?",
                (subject_id,)
            ) as cursor:
                count_row = await cursor.fetchone()
                if count_row and count_row["cnt"] >= max_places:
                    return False, f"Достигнут лимит мест ({max_places})!", 0

        # Добавляем в очередь
        await db.execute(
            """
            INSERT INTO queue_entries (subject_id, user_id, user_name, username)
            VALUES (?, ?, ?, ?)
            """,
            (subject_id, user_id, user_name, username)
        )
        await db.commit()

        # Вычисляем позицию
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM queue_entries WHERE subject_id = ? AND id <= (SELECT id FROM queue_entries WHERE subject_id = ? AND user_id = ?)",
            (subject_id, subject_id, user_id)
        ) as cursor:
            pos_row = await cursor.fetchone()
            pos = pos_row["cnt"] if pos_row else 1

        return True, "Успешно!", pos

async def remove_from_queue(subject_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM queue_entries WHERE subject_id = ? AND user_id = ?",
            (subject_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def clear_queue(subject_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM queue_entries WHERE subject_id = ?",
            (subject_id,)
        )
        await db.commit()
        return cursor.rowcount > 0

async def get_user_entry(subject_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    await check_and_auto_clear_queue(subject_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM queue_entries WHERE subject_id = ? AND user_id = ?",
            (subject_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_subject_last_message(subject_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subjects SET last_message_id = ? WHERE id = ?", (message_id, subject_id))
        await db.commit()

async def get_subject_last_message(subject_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_message_id FROM subjects WHERE id = ?", (subject_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else 0
