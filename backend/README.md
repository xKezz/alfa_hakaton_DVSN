# Backend — кредитование ИП/ООО (Alfa Hakaton)

Backend на **Python 3.12 + FastAPI + PostgreSQL** для кредитования ИП/ООО.
Сервис отдаёт состояние (`/health`), карточку компании по ИНН, каталог и подбор
кредитных продуктов, финансовую отчётность, авторизацию из таблицы `login`,
а также полный цикл кредитной заявки: вызов существующего алгоритма скоринга
(`src/credit_risk`), сохранение рейтинга, автоматическое решение или передача
заявки сотруднику.

## Стек

| Компонент         | Версия                |
| ----------------- | --------------------- |
| Python            | 3.12                  |
| FastAPI           | 0.115.6               |
| Uvicorn           | 0.34.0                |
| psycopg (3)       | 3.2.3                 |
| pydantic-settings | 2.7.1                 |
| asyncpg           | 0.30.0                |
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
    ├── config.py            # pydantic-settings: DATABASE_URL / PG*, APP_*, CORS_ORIGINS
    ├── db.py                # psycopg3: connection, ping()
    ├── main.py              # FastAPI app, CORS, роуты
    ├── schemas.py           # pydantic-модели запросов/ответов
    ├── scoring_service.py   # адаптер к существующему алгоритму src/credit_risk
    └── loan_applications.py # создание заявки, скоринг, авто/ручная проверка
backend/tests/               # unittest: формулы, маршрутизация, интеграция с БД
src/credit_risk/             # существующий алгоритм скоринга (формулы не менялись)
src/data/weight.json         # веса и пороги алгоритма
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
# файл уже содержит рабочие локальные значения; поменяйте PGPASSWORD,
# если у вашего PostgreSQL другой пароль
```

`.env` находится в `.gitignore`; в репозитории лежит только `.env.example`
с плейсхолдерами. Для локального запуска обязательно проверьте:

- **`AUTH_SECRET`** — ключ подписи Bearer-токенов. Без него backend теперь
  запускается с временным секретом процесса, но после рестарта все токены
  становятся недействительными. Для стабильной локальной работы и тем более
  для production задайте свой секрет:
  ```bash
  AUTH_SECRET=$(openssl rand -hex 32)
  echo "AUTH_SECRET=$AUTH_SECRET" >> .env
  ```
- **`PGPASSWORD`** — должен совпадать с паролем вашего локального PostgreSQL.
  Значения по умолчанию (`postgres/postgres`) подходят только для стандартной
  локальной установки; для другой машины задайте реальный пароль в `.env`.

Поддерживаются два способа задать подключение:

1. **`DATABASE_URL`** (приоритетный) — строка вида
   `postgresql://user:password@localhost:5432/alfa-hakaton`;
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

`DB/DB.sql` — **источник истины по схеме**. Для локального демо-запуска
проще одной командой создать БД, схему и демо-данные:

```bash
# из корня репозитория
backend/.venv/bin/python DB/setup_db.py
```

Скрипт пересоздаёт таблицы и добавляет 4 демо-компании, 11 продуктов и логины.
Если БД уже наполнена вашими данными — не запускайте его. Только схему можно
накатить вручную:

```bash
# создать БД (если ещё нет)
createdb alfa-hakaton

# применить схему из корня репозитория
psql -d alfa-hakaton -f ../DB/DB.sql
```

`DB/DB.sql` содержит только DDL и не добавляет демо-данные. Для локальных
проверок компании можно вставить вручную, например:

```sql
INSERT INTO companies (
    inn, company_name, registration_date, company_status,
    industry, region_code, is_simplified_tax, dissolution_flag
) VALUES
    ('7701234567', 'ООО «Ромашка»', '2015-03-12', 'active', '62', '77', FALSE, FALSE),
    ('770123456789', 'ИП Иванов Иван Иванович', '2020-07-01', 'active', '47', '50', TRUE, FALSE);
```

В текущей схеме `loan_applications` добавлено неразрушающее поле
`updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP` (для даты последнего
обновления статуса). В уже существующей БД оно создаётся запросом:

```sql
ALTER TABLE loan_applications
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
```

Поля компании `company_name`, `registration_date`, `company_status`, `industry`,
`region_code`, `is_simplified_tax`, `dissolution_flag` могут быть `NULL` — API
возвращает их как `null`.

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
| POST | `/api/loan-applications` | `201` — заявка с результатом скоринга и статусом | `404` — компания/продукт не найдены, `422` — невалидные данные, `503` — БД недоступна |
| GET | `/api/loan-applications` | `200` — список заявок; по умолчанию `status=manual_review` (очередь сотрудника) | `422` — недопустимый статус, `503` — БД недоступна |
| GET | `/api/loan-applications/{application_id}` | `200` — заявка, рейтинг, причина передачи, решение, история | `404` — заявка не найдена, `503` — БД недоступна |
| POST | `/api/loan-applications/{application_id}/decision` | `200` — решение сотрудника по заявке из `manual_review` | `403` — не сотрудник, `404` — заявка не найдена, `409` — заявка уже решена автоматически, `422` — невалидные данные, `503` — БД недоступна |
| POST | `/api/loan-applications/{application_id}/employee-offer` | `201` — индивидуальное предложение сотрудника, заявка `offer_pending` | `403` — не сотрудник, `404` — заявка/продукт не найдены, `409` — заявка не на ручной проверке, `422` — невалидные сумма/срок/продукт, `503` — БД недоступна |
| POST | `/api/loan-applications/{application_id}/offers/{offer_id}/select` | `200` — выбранный оффер, заявка `approved` | `404` — заявка/оффер не найдены, `409` — заявка/оффер не ожидают выбора, `503` — БД недоступна |
| POST | `/api/loan-applications/{application_id}/offers/{offer_id}/decline` | `200` — отказ от оффера; при отказе от всех — `rejected` | `404` — заявка/оффер не найдены, `409` — заявка/оффер не ожидают выбора, `503` — БД недоступна |

Авторизация: `POST /api/auth/login` возвращает `access_token`. Защищённые действия
(заявки, очередь, решения, предложения, выбор оффера) требуют заголовок
`Authorization: Bearer <access_token>`. Сотрудник определяется по подписанному
токену на сервере, а не по логину из тела запроса. Предприниматель видит только
заявки своей компании (`login.company_inn`).

Правила валидации ИНН: только цифры, длина 10 (ООО) или 12 (ИП). Невалидный
ИНН возвращает `422` с понятным `detail`, например:
`{"detail":"ИНН должен состоять только из цифр и содержать 10 или 12 символов"}`.

Подбор продуктов (`GET /api/loan-products`) учитывает `is_active`, категорию бизнеса,
цель кредитования, сумму, срок и возраст бизнеса (`business_age`, мес.). Необязательный
параметр `credit_rating` — это рассчитанный скоринг заявителя: он сравнивается с
`min_credit_rating` продукта. Клиент его не выбирает, и текущий frontend его не передаёт.
Продукты с `loan_purpose = 'other'` считаются универсальными и подходят под любую цель.

Frontend передаёт `allow_fallback=true`, чтобы не оставлять пользователя без предложений:
если точных совпадений нет, API сначала ослабляет фильтр цели/возраста бизнеса, а затем
возвращает ближайшие продукты по категории, сумме и сроку. В последнем случае API отдаёт
заголовок `X-Loan-Products-Fallback: amount+term`, а frontend показывает предупреждение и
подставляет допустимые сумму/срок продукта при подаче заявки. Без `allow_fallback=true`
поведение прежнее: возвращается только точное совпадение (возможен `[]`).

При сохранении финансовой отчётности (`POST /api/financial-statements`) компания
должна существовать в `companies` (иначе `404`), а на пару `(inn, report_year)`
действует ограничение БД `UNIQUE`, поэтому повторная запись за тот же год
возвращает `409 {"detail":"Отчётность за этот отчётный год уже существует"}`.
Все числовые поля необязательны: незаполненные значения сохраняются как `NULL`.

При недоступной БД `/health` продолжает отвечать `200`, а поиск компании и
сохранение отчётности возвращают `503 {"detail":"База данных недоступна"}`;
подробности пишутся в лог сервера, stack trace клиенту не отдаётся.

## Скоринг и маршрутизация заявок

- `POST /api/loan-applications` сохраняет заявку, вызывает **существующий**
  алгоритм `src/credit_risk` (`Financial_Risk_Score` + `CreditScorer`) и
  сохраняет рейтинг в `applications_checks`.
- Автоматическое решение: продуктовый скоринг ниже нижней границы
  `min_credit_rating/10` → `rejected`, выше верхней границы → `approved`.
- Ручная проверка (`manual_review`), если скоринг в пограничной зоне продукта
  (существующее правило `employee_rout`) или цель кредита `other`.
- Если рейтинг ниже `min_credit_rating` выбранного продукта (или выбранный
  продукт не прошёл существующий порог), backend ищет альтернативы среди
  продуктов, которые были доступны клиенту изначально по сумме, сроку, цели,
  категории и возрасту бизнеса. Подходящие альтернативы сохраняются в
  `application_offers`, заявка получает `offer_pending`; если альтернатив нет —
  финальный `rejected`. Автоматического одобрения/отказа по выбранному продукту
  в этом случае нет.
- Клиент выбирает оффер (`POST .../offers/{offer_id}/select`) или отказывается
  (`POST .../offers/{offer_id}/decline`); при выборе заявка становится `approved`,
  при отказе от всех офферов — `rejected`. Повторный скоринг не выполняется.
- Причина передачи сохраняется в `applications_checks.routing_reason`,
  решение — в `applications_decisions`, история — в `applications_history`.
- Ошибка скоринга не приводит к ложному одобрению/отказу: заявка уходит в
  `manual_review` с `has_error = TRUE`.
- Формулы и веса не изменялись: используются файлы `src/credit_risk/*.py` и
  `src/data/weight.json` как есть.

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

# создать заявку: рейтинг и авто-решение
curl -i -X POST http://127.0.0.1:8000/api/loan-applications \
  -H 'Content-Type: application/json' \
  -d '{"inn":"4217064416","product_id":2,"requested_amount":2000000,
       "requested_term_months":12,"loan_purpose":"working_capital"}'

# очередь ручной проверки и причина передачи
curl -i 'http://127.0.0.1:8000/api/loan-applications?status=manual_review'
curl -i http://127.0.0.1:8000/api/loan-applications/<application_id>

# выбор альтернативного предложения / отказ
curl -i -X POST http://127.0.0.1:8000/api/loan-applications/<application_id>/offers/<offer_id>/select
curl -i -X POST http://127.0.0.1:8000/api/loan-applications/<application_id>/offers/<offer_id>/decline

# решение сотрудника по заявке из manual_review
curl -i -X POST http://127.0.0.1:8000/api/loan-applications/<application_id>/decision \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approved","decided_by":"bank","reason":"Проверено сотрудником"}'

# при остановленной БД
curl -i http://127.0.0.1:8000/health
# {"status":"ok","database":"unavailable"}
curl -i http://127.0.0.1:8000/api/companies/7701234567
# 503 {"detail":"База данных недоступна"}
```

## Ограничения и заметки

- Реализованы `/health`, компании, продукты, финансовая отчётность, авторизация,
  заявки, скоринг и ручная проверка. `offer_pending`/офферы не используются
  в текущем сценарии.
- Для решения сотрудника проверяется, что `decided_by` — пользователь с
  `profile_type='employee'` из `login`. Полноценных токенов/сессий в проекте
  пока нет, поэтому API рассчитан на локальную разработку и демо.
- Тесты: `cd backend && .venv/bin/python -m unittest discover -s tests -t .`
  (без БД) и `RUN_DB_TESTS=1 ...` (с реальной PostgreSQL).
- Пул соединений не используется: на каждый запрос открывается новое
  подключение psycopg с `connect_timeout=5`. Для хакатонного MVP этого
  достаточно.
- Эндпоинты синхронные (`def`), поэтому FastAPI выполняет их в threadpool и не
  блокирует event loop.
- SQL-запросы параметризованы (`%(inn)s`), конкатенация пользовательского ввода
  в SQL не используется.
- CORS по умолчанию разрешает только dev-сервер Vite:
  `http://localhost:5173` и `http://127.0.0.1:5173`.
