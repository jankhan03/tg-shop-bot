# docker/bot.Dockerfile

# Используем легковесный образ Python
FROM python:3.11-slim

# Устанавливаем переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Аргументы, которые будут передаваться из compose.yml
ARG MODULE_PATH=bot
ARG START_FILE=bot.py

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# --- Копирование исходного кода ---
# Копируем ОБЩИЙ файл конфига в рабочую директорию /app
COPY config.py .

# Копируем папку server, так как она нужна для импортов в admin_bot
COPY server/ ./server/

# Копируем содержимое папки с кодом бота (например, 'admin_bot')
# напрямую в рабочую директорию /app
COPY ${MODULE_PATH}/ .

# --- Установка зависимостей ---
# Устанавливаем зависимости из requirements.txt, который мы только что скопировали
RUN pip install --no-cache-dir -r requirements.txt

# --- Запуск приложения ---
# CMD остаётся таким же
CMD python -u ${START_FILE}
