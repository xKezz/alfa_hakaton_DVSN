# alfa-hakaton-DVSN

Прототип кредитного конвейера для ИП и ООО: кабинет предпринимателя, подбор кредита,
заявки со статусами, интерфейс сотрудника банка и минимальный backend на FastAPI + PostgreSQL.

## Структура

```
.
├── DB/DB.sql                   # DDL PostgreSQL (9 таблиц) — источник истины по схеме
├── База данных.md              # описание модели данных
├── Roadmap.md                  # бизнес-процесс кредитного конвейера
├── StakeHolders and User Stories.md
├── Схема БД.drawio             # ER-диаграмма
├── backend/                    # FastAPI + psycopg3 (health, компания по ИНН)
├── front/alfa-frontend/        # React 19 + Vite 8 (кабинет, калькулятор, интерфейс банка)
└── front/alfa-frontend/README.md
```

## Быстрый старт

Требования: PostgreSQL 14+ с локальным пользователем `postgres`/`postgres`
(если пароль другой — поправьте `backend/.env` и `DB/setup_db.py`).

1. **Backend и окружение**:

```bash
cd backend
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env
```

`.env.example` уже содержит рабочие локальные значения:
`PGDATABASE=alfa-hakaton`, `PGUSER=postgres`, `PGPASSWORD=postgres`,
`AUTH_SECRET` для dev. Если у вас другой пароль PostgreSQL — измените `PGPASSWORD`
в `backend/.env`.

2. **База данных + демо-данные** (4 компании, 11 продуктов, логины):

```bash
# из корня репозитория
backend/.venv/bin/python DB/setup_db.py
```

Скрипт создаёт БД `alfa-hakaton`, накатывает `DB/DB.sql`, добавляет демо-данные
и логины. Он **пересоздаёт таблицы**, поэтому не запускайте его на БД с вашими
данными.

3. **Запуск backend**:

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Проверка: `curl http://127.0.0.1:8000/health` → `{"status":"ok","database":"ok"}`.
Подробнее — [backend/README.md](backend/README.md).

4. **Frontend**:

```bash
cd front/alfa-frontend
npm install
npm run dev                     # http://localhost:5173
```

`front/alfa-frontend/.env.example` уже содержит `VITE_API_URL=http://localhost:8000`;
при необходимости скопируйте его в `.env`. Подробнее — [front/alfa-frontend/README.md](front/alfa-frontend/README.md).

## Docker: запуск с нуля

Нужен только установленный Docker с Compose plugin.

```bash
docker compose up --build -d
```

- Frontend: <http://localhost:8080>
- Backend API / Swagger: <http://localhost:8000/docs>
- PostgreSQL: внутри сети compose, наружу не публикуется

При первом запуске сервис `db-init` создаёт БД `alfa-hakaton`, применяет
`DB/DB.sql` и добавляет демо-данные: 4 компании, 11 продуктов и логины
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
