# payment_project

API приёма оплаты курса для онлайн-школы: тарифы, создание платежа с промокодом
и рассрочкой, идемпотентность по `Idempotency-Key`, вебхук банка со сменой статуса.

**Стек:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg,
PostgreSQL 16, Alembic, pytest + httpx, ruff.

## Запуск

### Docker
```bash
git clone https://github.com/Anna9449/payment_project.git
cd payment_project
docker compose up --build
```
- API: http://localhost:8000
- Swagger: http://localhost:8000/api/openapi

Порядок запуска:
1. `postgres` — база; остальные сервисы ждут, пока она начнёт принимать подключения.
2. `tests` — прогоняет `pytest` в отдельной базе `payment_test` и завершается.
   Если хоть один тест упал, приложение не запускается
   (`service "tests" didn't complete successfully`).
3. `app` — выполняет `alembic upgrade head` (таблицы, тарифы `basic`/`standard`/`premium`,
   промокод `KVITTO10`) и запускает API.

Файл `.env` не нужен, все переменные заданы в `docker-compose.yml`.
Вывод тестов: `docker compose logs tests`.

### Локально
Нужен Python 3.11+ и Docker (для Postgres).
```bash
cp .env.example .env              # настройки БД и WEBHOOK_SECRET, без него приложение не стартует
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d postgres     # Postgres на localhost:5433
cd src
alembic upgrade head              # таблицы + тарифы + промокод
uvicorn main:app --reload
```

## Тесты
**В Docker** тесты запускаются автоматически при `docker compose up --build` (см. выше).
Только тесты, без приложения:
```bash
docker compose run --rm --build tests
```

**Локально** — сначала выполните первые три команды из раздела «Локально» (`.env`, venv,
зависимости), затем из корня репозитория:
```bash
docker compose up -d postgres
pytest -q
ruff check .
```
Тесты создают отдельную базу `payment_test` и не трогают данные разработки.
Каждый тест начинает с пустых таблиц и создаёт данные фабриками (`tests/factories.py`).

## Примеры запросов

Все id — UUID. Примеры ниже идут по порядку и передают id через переменные окружения.

```bash
# Тарифы
curl localhost:8000/tariffs
# → [{"id":"0ef51646-…","title":"basic","price":990000}, {"id":"4d515b57-…","title":"standard","price":1990000}, ...]

TARIFF_ID=$(curl -s localhost:8000/tariffs | python3 -c \
  "import sys, json; print(next(t['id'] for t in json.load(sys.stdin) if t['title'] == 'standard'))")

# Платёж: standard, промокод в нижнем регистре, рассрочка на 3 месяца
curl -X POST localhost:8000/payments \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" \
  -d "{\"tariff_id\": \"$TARIFF_ID\", \"email\": \"student@example.com\",
       \"method\": \"installment\", \"installment_months\": 3, \"promo_code\": \"kvitto10\"}"
# → 201, amount=1791000, discount=199000, schedule=[597000, 597000, 597000]
# Повтор с тем же Idempotency-Key → 200 и тот же платёж, второй не создаётся
# Ключ — UUID; пустое значение или не-UUID → 422

PAYMENT_ID=<id из ответа выше>

# Платёж по id
curl localhost:8000/payments/$PAYMENT_ID
# → 200; несуществующий id → 404, id не в формате UUID → 422

# Вебхук банка. Подпись: hex(HMAC-SHA256(тело, WEBHOOK_SECRET)), по умолчанию секрет change-me
BODY="{\"payment_id\": \"$PAYMENT_ID\", \"status\": \"succeeded\"}"
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac change-me | awk '{print $NF}')
curl -X POST localhost:8000/webhooks/bank \
  -H 'Content-Type: application/json' -H "X-Signature: $SIG" -d "$BODY"
# → 200 {"result": "ok"}
# запрещённый переход → 409 {"error": "invalid_transition"}, статус не меняется
# неверная подпись → 401
```

## Решения

- **Деньги.** Только `int` в копейках, в БД `BIGINT`, `float` нигде нет. Скидка
  `price * percent // 100`, округление вниз (для текущих цен остатка нет).
  `amount` — сумма к оплате после скидки, `discount` — размер скидки.
- **График рассрочки.** `divmod(amount, months)`, остаток раздаётся по копейке первым
  платежам: сумма графика всегда равна `amount`, платежи отличаются не больше чем на 1.
  Пример: 1990000 на 3 месяца → `[663334, 663333, 663333]`.
- **Промокоды** хранятся в таблице `promo_codes`, ввод нормализуется (`strip().upper()`),
  поэтому `kvitto10` и `KVITTO10` равнозначны. Неизвестный или неактивный код → 422.
  Поддерживаются одноразовые коды: платёж занимает код, при `failed`/`refunded` код
  освобождается. Строка одноразового кода блокируется (`FOR UPDATE`), чтобы два
  одновременных платежа не заняли его оба; многоразовый код не блокируется, чтобы
  платежи с ним не выстраивались в очередь.
- **Идемпотентность.** Ключ — UUID (`Idempotency-Key`), хранится с UNIQUE в БД.
  Сначала ищем платёж по ключу.
  Если два одинаковых запроса пришли одновременно и оба не нашли платёж, второй `INSERT`
  падает на UNIQUE: ловим `IntegrityError` и возвращаем уже созданный платёж с кодом 200.
  Тело повторного запроса не сравнивается с первым — возвращается исходный платёж.
  Пустое значение или не в формате UUID → 422.
- **Статусы.** Разрешённые переходы описаны таблицей в `services/payments.py`:
  `pending → succeeded | failed`, `succeeded → refunded`. Строка платежа читается через
  `SELECT … FOR UPDATE`, чтобы два одновременных вебхука не прошли проверку по одному и
  тому же старому статусу. Переход в тот же статус (`pending → pending`) тоже запрещён:
  его нет среди разрешённых, поэтому 409 и статус не меняется.
- **Целостность в БД.** CHECK-ограничения: суммы положительные, срок только 3/6/12,
  срок и график есть тогда и только тогда, когда `method = installment`.
- **Ошибки.** Валидация (рассрочка без срока, срок у не-рассрочки, неизвестный способ
  оплаты, неверный email, id или `Idempotency-Key` не в формате UUID) → стандартный 422
  FastAPI. Остальные ошибки отдаются как `{"detail": "<код>"}`:

  | Код ответа | `detail` | Когда |
  |---|---|---|
  | 404 | `tariff_not_found`, `payment_not_found` | тариф или платёж не найден |
  | 422 | `promo_code_not_found`, `promo_code_inactive`, `promo_code_already_used` | промокод нельзя применить |
  | 401 | `invalid_signature` | неверная или отсутствующая подпись вебхука |
  | 500 | `internal_error` | непредвиденная ошибка БД; подробности с traceback — только в логах |

  Исключение — 409 вебхука: `{"error": "invalid_transition"}`, формат задан в ТЗ.
- **Email** приводится к нижнему регистру.
- **Id — UUID** (объявлен один раз в базовой модели). Платёжные id нельзя перебрать
  по порядку, как автоинкремент. Генерируются в Python (`uuid4`), а для вставок из миграций
  есть `server_default gen_random_uuid()`.

## Бонусы
- [x] Запуск через `docker compose up`
- [x] Подпись вебхука `X-Signature` (HMAC-SHA256 от тела, секрет из `WEBHOOK_SECRET`) → 401
- [x] Миграции Alembic
- [ ] `GET /payments` с фильтрами по `email` и `status` — не сделано
- [x] GitHub Actions: ruff, pytest и `alembic check` (миграции совпадают с моделями)
- [x] `CLAUDE.md` с правилами для ассистента

## Структура
```
src/
  main.py               приложение FastAPI
  api/v1/               эндпоинты: tariffs, payments, webhooks
  services/             бизнес-логика: payments (цена, график, статусы), tariffs
  schemas/              Pydantic-схемы запросов и ответов
  models/               SQLAlchemy-модели и enum'ы
  utils/bank_signature  проверка подписи вебхука
  migrations/           Alembic: схема и начальные данные
tests/                  pytest: test_api.py, фабрики, хелперы
Dockerfile              два этапа: app (приложение) и test (+ pytest и tests/)
docker-compose.yml      postgres → tests → app
.github/workflows/      CI: ruff, alembic check, pytest
```
