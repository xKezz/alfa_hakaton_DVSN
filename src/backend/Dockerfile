FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Контекст сборки — корень репозитория (см. docker-compose.yml).
COPY src/backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY src/backend /app/backend
# Пакет алгоритма скоринга: backend импортирует `src.credit_risk`
# (PYTHONPATH=/app), поэтому он должен лежать в /app/src/credit_risk вместе
# с src/credit_risk/data/weight.json.
COPY src/credit_risk /app/src/credit_risk
# Скрипты инициализации БД для сервиса db-init (docker-compose).
COPY src/db/DB.sql src/db/setup_db.py src/db/docker_init.py /app/DB/

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
