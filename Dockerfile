FROM python:3.10-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создаем папку для логов
RUN mkdir -p /app/logs

# Создание пользователя для безопасности
RUN useradd -m -r bot && chown -R bot /app
USER bot

# Экспоз порта для метрик
EXPOSE 8000

# Запуск приложения
CMD ["python", "run.py"]