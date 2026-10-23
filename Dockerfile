FROM python:3.11-slim

WORKDIR /app

# Установка переменных окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Omsk

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Команда запуска бота
CMD ["python", "main.py"]
