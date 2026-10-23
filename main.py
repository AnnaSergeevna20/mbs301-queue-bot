import asyncio
import logging
import sys

# Обеспечиваем корректный вывод UTF-8 и emoji в консоли Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN
from database import init_db, auto_clear_all_closed_queues
from handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def set_main_menu(bot: Bot):
    commands = [
        BotCommand(command="queue", description="📋 Посмотреть очереди / предметы"),
        BotCommand(command="add_subject", description="➕ Добавить предмет и расписание"),
        BotCommand(command="del_subject", description="🗑 Удалить предмет"),
        BotCommand(command="help", description="ℹ️ Помощь и справка"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def periodic_queue_cleaner():
    """Фоновая задача: автоматически очищает очереди после их закрытия"""
    while True:
        try:
            cleared = await auto_clear_all_closed_queues()
            if cleared > 0:
                logger.info(f"Автоматически очищено очередей после закрытия: {cleared}")
        except Exception as e:
            logger.error(f"Ошибка в periodic_queue_cleaner: {e}")
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health-check веб-сервер запущен на порту {port}")

async def main():
    if not BOT_TOKEN or BOT_TOKEN.strip() == "" or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("❌ ОШИБКА: Токен Telegram-бота не указан!")
        print("1. Откройте файл .env")
        print("2. Вставьте ваш токен от @BotFather в переменную BOT_TOKEN=")
        print("   Пример: BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("3. Запустите бота заново: python main.py")
        print("="*60 + "\n")
        sys.exit(1)

    # Инициализация базы данных SQLite
    await init_db()
    logger.info("База данных инициализирована.")

    # Создание экземпляра бота с HTML форматированием по умолчанию
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Подключение роутеров
    dp.include_router(router)

    # Установка меню команд в Telegram
    await set_main_menu(bot)

    # Запуск веб-сервера для совместимости с бесплатным тарифом Render Web Service
    await start_web_server()

    # Запуск фонового очистителя закрытых очередей
    asyncio.create_task(periodic_queue_cleaner())

    logger.info("Бот успешно запущен и ожидает сообщений...")
    
    # Удаляем вебхуки и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
