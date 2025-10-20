FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ARG MODULE_PATH=bot
ARG START_FILE=bot.py
WORKDIR /app

COPY ${MODULE_PATH}/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY ${MODULE_PATH} /app/${MODULE_PATH}
WORKDIR /app/${MODULE_PATH}
CMD ["sh", "-c", "python -u ${START_FILE}"]
