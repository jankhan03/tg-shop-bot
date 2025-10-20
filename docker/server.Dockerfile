FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# системные зависимости для psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq-dev && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

# копируем ваш серверный код
COPY server /app/server
# на случай, если он читает конфиг/окружение из корня
COPY .env /app/.env

ENV UVICORN_APP=server.main:app
CMD ["sh", "-c", "uvicorn \"$UVICORN_APP\" --host 0.0.0.0 --port 8000 --proxy-headers"]
