# alfa-hakaton-DVSN

Прототип кредитного конвейера для ИП и ООО: кабинет предпринимателя, подбор кредита,
заявки со статусами, интерфейс сотрудника банка и минимальный backend на FastAPI + PostgreSQL.

## Структура

```
.
├── src/
│   ├── backend/                 # FastAPI + psycopg3 (health, кабинет, заявки, скоринг)
│   │   ├── app/                 # приложение: config, db, auth, main, schemas, ...
│   │   └── tests/               # unittest: формулы, маршрутизация, интеграция с БД
│   ├── credit_risk/             # существующий алгоритм скоринга (формулы не менялись)
│   │   └── data/weight.json     # веса и пороги алгоритма
│   ├── db/                      # DB.sql (DDL, 9 таблиц) — источник истины по схеме,
│   │                            # setup_db.py, docker_init.py, load_*.py, датасеты
│   └── front/                   # React 19 + Vite 8 (кабинет, калькулятор, интерфейс банка)
├── other_info/                  # Roadmap, User Stories, описание модели данных, Схема БД.drawio
├── docker-compose.yml
└── README.md
```

## Быстрый старт

Требования: PostgreSQL 14+ с локальным пользователем `postgres`/`postgres`
(если пароль другой — поправьте `src/backend/.env` и `src/db/setup_db.py`).

1. **Backend и окружение**:

```bash
cd src/backend
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env
```

`.env.example` уже содержит рабочие локальные значения:
`PGDATABASE=alfa-hakaton`, `PGUSER=postgres`, `PGPASSWORD=postgres`,
`AUTH_SECRET` для dev. Если у вас другой пароль PostgreSQL — измените `PGPASSWORD`
в `src/backend/.env`.

2. **База данных + демо-данные** (4 компании, 11 продуктов, логины):

```bash
# из корня репозитория
src/backend/.venv/bin/python src/db/setup_db.py
# Windows: src\backend\.venv\Scripts\python.exe src\db\setup_db.py
```

Скрипт создаёт БД `alfa-hakaton`, накатывает `src/db/DB.sql`, добавляет демо-данные
и логины. Он **пересоздаёт таблицы**, поэтому не запускайте его на БД с вашими
данными.

3. **Запуск backend**:

```bash
cd src/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Проверка: `curl http://127.0.0.1:8000/health` → `{"status":"ok","database":"ok"}`.
Подробнее — [src/backend/README.md](src/backend/README.md).

4. **Frontend**:

```bash
cd src/front
npm install
npm run dev                     # http://localhost:5173
```

`src/front/.env.example` уже содержит `VITE_API_URL=http://localhost:8000`;
при необходимости скопируйте его в `.env`. Подробнее — [src/front/README.md](src/front/README.md).

## Docker: запуск с нуля

Нужен только установленный Docker с Compose plugin.

```bash
docker compose up --build -d
```

- Frontend: <http://localhost:8080>
- Backend API / Swagger: <http://localhost:8000/docs>
- PostgreSQL: внутри сети compose, наружу не публикуется

При первом запуске сервис `db-init` создаёт БД `alfa-hakaton`, применяет
`src/db/DB.sql` и добавляет демо-данные: 4 компании, 11 продуктов и логины
`client/client`, `bank/bank`, `login1…login4`. Повторный запуск данные не
пересоздаёт.

Проверить состояние и логи:

```bash
docker compose ps
docker compose logs -f backend
```

Остановить:

```bash
docker compose down
```

Полностью удалить БД и начать с нуля:

```bash
docker compose down -v
```

Порты и dev-секрет при необходимости можно переопределить через `.env` в корне:

```bash
cp .env.docker.example .env
# FRONTEND_PORT, BACKEND_PORT, PGPASSWORD, AUTH_SECRET
```

В Docker frontend собирается с `VITE_API_URL="/"` и обращается к API через
Nginx reverse proxy (`/api/...`), поэтому не зависит от адреса сервера.
Для production обязательно замените `AUTH_SECRET` и пароль PostgreSQL.

## Демо-учётные записи

| Логин | Пароль | Роль |
|---|---|---|
| `client` | `client` | предприниматель |
| `bank` | `bank` | сотрудник банка |

## Ограничения прототипа

- Backend реализует авторизацию, компании, продукты, финансовую отчётность,
  кредитные заявки, существующий скоринг и ручную проверку; заявки, рейтинг,
  решения и история сохраняются в PostgreSQL.
- Frontend подключён к API заявок: клиент отправляет заявки, видит статус и
  альтернативные предложения; сотрудник банка работает с очередью `manual_review`
  и сохраняет решение в БД.
- Все суммы, ставки и условия не являются офертой банка.