# Backend — кредитование ИП/ООО (Alfa Hakaton)

Минимальный backend на **Python 3.12 + FastAPI + PostgreSQL**.
Сейчас сервис умеет только две вещи: сообщать состояние (`/health`) и отдавать
карточку компании по ИНН (`/api/companies/{inn}`). Бизнес-логика кредитования,
аутентификация и работа с заявками появятся позже.

## Стек

| Компонент         | Версия                |
| ----------------- | --------------------- |
| Python            | 3.12                  |
| FastAPI           | 0.115.6               |
| Uvicorn           | 0.34.0                |
| psycopg (3)       | 3.2.3                 |
| pydantic-settings | 2.7.1                 |
| PostgreSQL        | 14+ (проверено на 18) |

## Структура

```
backend/
├── .env.example        # пример переменных окружения (секретов нет)
├── .gitignore          # .venv, __pycache__, .env, *.pyc
├── requirements.txt    # зафиксированные зависимости
├── README.md
└── app/
    ├── __init__.py
    ├── config.py       # pydantic-settings: DATABASE_URL / PG*, APP_*, CORS_ORIGINS
    ├── db.py           # psycopg3: connection, ping()
    ├── main.py         # FastAPI app, CORS, роуты
    └── schemas.py      # pydantic-модели ответов
```

## Требования

- Python **3.12**;
- PostgreSQL (локальный сервер или доступный по сети);
- [uv](https://docs.astral.sh/uv/) — опционально, можно использовать обычный `pip`.

## Установка

```bash
cd backend

# вариант с uv (рекомендуется)
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt

# вариант без uv
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

> Если uv не может писать в свой кэш вне рабочей директории (например, в
> ограниченной среде), задайте кэш внутри временного каталога:
> `UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements.txt`.

## Настройка .env

```bash
cd backend
cp .env.example .env
# откройте .env и укажите реальные параметры подключения
```

`.env` находится в `.gitignore`; в репозитории лежит только `.env.example`
с плейсхолдерами. Поддерживаются два способа задать подключение:

1. **`DATABASE_URL`** (приоритетный) — строка вида
   `postgresql://user:password@localhost:5432/alfa_hakaton`;
2. **разрозненные переменные** `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
   `PGPASSWORD` — используются, если `DATABASE_URL` не задан.

Дополнительно:

- `APP_HOST` / `APP_PORT` — адрес и порт для запуска через `python -m app.main`
  (по умолчанию `127.0.0.1:8000`);
- `CORS_ORIGINS` — origins через запятую, по умолчанию
  `http://localhost:5173,http://127.0.0.1:5173`.

Файл `.env` читается из текущей рабочей директории, поэтому запускайте команды
из каталога `backend/`.

## База данных

`DB.sql` в корне репозитория — **источник истины по схеме**. Backend его не
изменяет и не создаёт таблицы автоматически. Примените скрипт к своей БД:

```bash
# создать БД (если ещё нет)
createdb alfa_hakaton

# применить схему из корня репозитория
psql -d alfa_hakaton -f ../DB.sql
```

`DB.sql` содержит только DDL и не добавляет демо-данные. Для локальных
проверок компании можно вставить вручную, например:

```sql
INSERT INTO companies (
    inn, company_name, registration_date, company_status,
    industry, region_code, is_simplified_tax, dissolution_flag
) VALUES
    ('7701234567', 'ООО «Ромашка»', '2015-03-12', 'active', '62', '77', FALSE, FALSE),
    ('770123456789', 'ИП Иванов Иван Иванович', '2020-07-01', 'active', '47', '50', TRUE, FALSE);
```

Backend использует только таблицу `companies`. Поля `company_name`,
`registration_date`, `company_status`, `industry`, `region_code`,
`is_simplified_tax`, `dissolution_flag` могут быть `NULL` — API возвращает их
как `null`.

## Запуск

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Чтобы использовать `APP_HOST`/`APP_PORT` из `.env`:

```bash
cd backend
.venv/bin/python -m app.main
```

Для доступа снаружи (например, из контейнера) добавьте
`--host 0.0.0.0` к команде `uvicorn`.

## Эндпоинты

| Метод | Путь | Успех | Ошибки |
|---|---|---|---|
| GET | `/` | `200` — `{"service":"alfa-hakaton-backend","docs":"/docs"}` | — |
| GET | `/health` | всегда `200`, поле `database`: `ok` или `unavailable` | — |
| GET | `/api/companies/{inn}` | `200` — карточка компании | `422` — невалидный ИНН, `404` — не найдено, `503` — БД недоступна |
| POST | `/api/financial-statements` | `201` — сохранённая запись `financial_statements` | `404` — компания не найдена, `409` — отчётность за этот год уже есть, `422` — невалидные данные, `503` — БД недоступна |
| GET | `/api/loan-products` | `200` — список активных продуктов из `loan_catalog` (возможен пустой список) | `422` — невалидные параметры подбора, `503` — БД недоступна |
| GET | `/api/financial-statements/{inn}` | `200` — все годовые отчёты компании (по убыванию года, может быть `[]`) | `422` — невалидный ИНН, `503` — БД недоступна |
| GET | `/api/financial-statements/{inn}/latest` | `200` — последний по году отчёт компании | `404` — отчётности нет, `422` — невалидный ИНН, `503` — БД недоступна |

Правила валидации ИНН: только цифры, длина 10 (ООО) или 12 (ИП). Невалидный
ИНН возвращает `422` с понятным `detail`, например:
`{"detail":"ИНН должен состоять только из цифр и содержать 10 или 12 символов"}`.

Подбор продуктов (`GET /api/loan-products`) учитывает `is_active`, категорию бизнеса,
цель кредитования, сумму, срок и возраст бизнеса (`business_age`, мес.). Необязательный
параметр `credit_rating` — это рассчитанный скоринг заявителя: он сравнивается с
`min_credit_rating` продукта. Клиент его не выбирает, и текущий frontend его не передаёт;
параметр предусмотрен для следующего этапа со скорингом. Продукты с
`loan_purpose = 'other'` считаются универсальными и подходят под любую цель. Если
подходящих продуктов нет, возвращается пустой массив `[]`.

При сохранении финансовой отчётности (`POST /api/financial-statements`) компания
должна существовать в `companies` (иначе `404`), а на пару `(inn, report_year)`
действует ограничение БД `UNIQUE`, поэтому повторная запись за тот же год
возвращает `409 {"detail":"Отчётность за этот отчётный год уже существует"}`.
Все числовые поля необязательны: незаполненные значения сохраняются как `NULL`.

При недоступной БД `/health` продолжает отвечать `200`, а поиск компании и
сохранение отчётности возвращают `503 {"detail":"База данных недоступна"}`;
подробности пишутся в лог сервера, stack trace клиенту не отдаётся.

## Примеры curl

```bash
# информация о сервисе
curl -i http://127.0.0.1:8000/

# health-check (БД доступна)
curl -i http://127.0.0.1:8000/health
# {"status":"ok","database":"ok"}

# ООО, ИНН из 10 цифр
curl -i http://127.0.0.1:8000/api/companies/7701234567
# {"inn":"7701234567","company_name":"ООО «Ромашка»","registration_date":"2015-03-12",
#  "company_status":"active","industry":"62","region_code":"77",
#  "is_simplified_tax":false,"dissolution_flag":false}

# ИП, ИНН из 12 цифр
curl -i http://127.0.0.1:8000/api/companies/770123456789

# невалидный ИНН -> 422
curl -i http://127.0.0.1:8000/api/companies/123

# компания не найдена -> 404
curl -i http://127.0.0.1:8000/api/companies/9999999999

# нецифровой ИНН -> 422
curl -i http://127.0.0.1:8000/api/companies/77abc

# сохранить годовую финансовую отчётность -> 201
curl -i -X POST http://127.0.0.1:8000/api/financial-statements \
  -H 'Content-Type: application/json' \
  -d '{"inn":"3257029840","report_year":2025,"revenue":14000000,"net_profit":1900000,
       "assets":10000000,"current_assets":5500000,"total_equity":3600000,"longterm_debt":1000000,
       "shortterm_debt":1100000,"shortterm_liab":2300000,"retained_earnings":3100000,
       "profit_from_sales":2000000,"before_tax":2200000,"cash_equivalents":900000,
       "interest_payable":200000,"balance_operating":3900000}'

# повторная запись за тот же ИНН и год -> 409
curl -i -X POST http://127.0.0.1:8000/api/financial-statements \
  -H 'Content-Type: application/json' \
  -d '{"inn":"3257029840","report_year":2025,"revenue":1}'

# подбор активных кредитных продуктов из loan_catalog -> 200
curl -i 'http://127.0.0.1:8000/api/loan-products?amount=4150000&term_months=36&business_category=ip&purpose=equipment&business_age_months=36'
# пустой результат, если ничего не подходит
curl -i 'http://127.0.0.1:8000/api/loan-products?amount=999999999&term_months=36&business_category=ip'

# компания не найдена -> 404
curl -i -X POST http://127.0.0.1:8000/api/financial-statements \
  -H 'Content-Type: application/json' \
  -d '{"inn":"9999999999","report_year":2025}' 

# при остановленной БД
curl -i http://127.0.0.1:8000/health
# {"status":"ok","database":"unavailable"}
curl -i http://127.0.0.1:8000/api/companies/7701234567
# 503 {"detail":"База данных недоступна"}
```

## Ограничения и заметки

- Реализованы `/health`, поиск компании по ИНН, подбор активных продуктов из
  `loan_catalog` и сохранение годовой финансовой отчётности; заявки, скоринг,
  офферы и решения пока не реализованы.
- Аутентификации и авторизации нет — сервис рассчитан на локальную разработку
  и демо.
- Пул соединений не используется: на каждый запрос открывается новое
  подключение psycopg с `connect_timeout=5`. Для хакатонного MVP этого
  достаточно.
- Эндпоинты синхронные (`def`), поэтому FastAPI выполняет их в threadpool и не
  блокирует event loop.
- SQL-запросы параметризованы (`%(inn)s`), конкатенация пользовательского ввода
  в SQL не используется.
- CORS по умолчанию разрешает только dev-сервер Vite:
  `http://localhost:5173` и `http://127.0.0.1:5173`.
