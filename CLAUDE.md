# CLAUDE.md

Сервис платежей на FastAPI (тестовое задание). Python 3.11, Pydantic v2,
SQLAlchemy 2.0 async + asyncpg, PostgreSQL, Alembic, pytest + httpx.

## Команды
Все команды — из корня репозитория, кроме Alembic (из `src/`).
```bash
docker compose up -d postgres            # Postgres на localhost:5433
pytest -q                                # тесты (база payment_test создаётся сама)
ruff check .                             # линтер, должен быть чистым
cd src && alembic revision --autogenerate -m "..."   # новая миграция
cd src && alembic upgrade head && alembic check      # применить и сверить с моделями
```
Перед тем как сказать «готово», запусти `ruff check .` и `pytest -q` — то же самое
гоняет CI (`.github/workflows/ci.yml`), плюс `alembic check`.

## Структура
- `src/api/v1/` — тонкие роутеры: разбор запроса, вызов сервиса, ответ. Логики нет.
- `src/services/` — бизнес-логика. Сервисы наследуют `BaseService` (сессия в `self.db`),
  создаются через `get_*_service` и `Depends`. Ошибки — исключения из `services/exceptions.py`.
- `src/schemas/` — Pydantic DTO (`*CreateDTO` на вход, `*DTO` на выход, `from_attributes=True`).
- `src/models/` — модели SQLAlchemy. Первичный ключ `id: UUID` объявлен в `Base` — в моделях
  его не объявляй, FK на другие модели типизируй как `Mapped[uuid.UUID]`. Новую модель добавь
  в `models/__init__.py`, иначе Alembic её не увидит.
- `src/migrations/versions/` — миграции, в том числе начальные данные (тарифы, KVITTO10).
- `tests/` — `test_api.py`, данные создаются фабриками из `tests/factories.py`.

## Правила предметной области (не нарушать)
- Деньги — только `int` в копейках. Никаких `float` и `Decimal` в API и БД, колонки `BigInteger`.
- Скидка: `price * discount_percent // 100`. `amount = price - discount`.
- График рассрочки: `sum(schedule) == amount` всегда, лишние копейки — в первые платежи.
  Срок только 3, 6 или 12; `installment_months` и `schedule` есть только у `installment`.
- Промокод сравнивается без учёта регистра (в БД хранится в верхнем регистре).
  Неизвестный код → 422.
- Переходы статусов — только через `PaymentService.ALLOWED_TRANSITIONS`:
  `pending → succeeded | failed`, `succeeded → refunded`. Запрещённый → 409
  `{"error": "invalid_transition"}`, статус не меняется. Платёж читать с `FOR UPDATE`.
- Повтор с тем же `Idempotency-Key` возвращает существующий платёж с кодом 200.
  Защита от гонок — UNIQUE на `idempotency_key` + обработка `IntegrityError`, не убирать.
- Ошибки валидации — стандартный 422 FastAPI, свой формат не вводить.

## Стиль кода
- Импорты только абсолютные (`from models import ...`, `from services.base import ...`),
  без `from .x`. Порядок — как требует ruff (isort).
- Одинарные кавычки, длина строки до 100, аннотации типов везде.
- Комментарии и `summary` эндпоинтов — на русском; комментарий объясняет «почему», а не «что».
- Не добавляй зависимости без необходимости; версии фиксируются в `src/requirements.txt`
  (рантайм) и `requirements-dev.txt` (тесты, линтер).

## Миграции
- Схему меняй через модель + `alembic revision --autogenerate`, потом проверь сгенерированный
  файл руками.
- Уже применённые миграции не редактируй и не удаляй — только новая миграция.
- Начальные данные в миграциях пиши литералами, не импортируй константы из приложения.

## Тесты
- На каждое изменение логики — тест в `tests/test_api.py` через HTTP-клиент (`client`).
- Проверяй результат, а не только код ответа: тело ответа и состояние в БД (`db`).
- Данные создавай фабриками, на сиды из миграций не рассчитывай: тесты строят схему
  через `create_all` и очищают таблицы перед каждым тестом.
