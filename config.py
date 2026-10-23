import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Омский государственный университет (ОмГУ) -> Asia/Omsk (UTC+6) по умолчанию,
# но можно настроить любую в .env, например Europe/Moscow
TIMEZONE = os.getenv("TIMEZONE", "Asia/Omsk")
DB_PATH = os.getenv("DB_PATH", "queue_bot.db")
