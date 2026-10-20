FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

CMD ["sh", "-c", "alembic upgrade head && gunicorn main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w 2"]


# Образ для тестов: те же зависимости + pytest и папка tests.
# Структура как в репозитории, чтобы работали pyproject.toml и requirements-dev.txt.
FROM app AS test

WORKDIR /project

COPY requirements-dev.txt pyproject.toml ./
COPY src/requirements.txt src/requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY src/ src/
COPY tests/ tests/

CMD ["pytest", "-q"]
