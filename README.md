# Альфа — Бизнес-платформа (хакатон DVSN)

Прототип кредитного конвейера для ИП и ООО: кабинет предпринимателя, подбор кредита,
заявки со статусами, интерфейс сотрудника банка и минимальный backend на FastAPI + PostgreSQL.

## Структура

```
.
├── DB.sql                      # DDL PostgreSQL (9 таблиц) — источник истины по схеме
├── База данных.md              # описание модели данных
├── Roadmap.md                  # бизнес-процесс кредитного конвейера
├── StakeHolders and User Stories.md
├── Схема БД.drawio             # ER-диаграмма
├── backend/                    # FastAPI + psycopg3 (health, компания по ИНН)
├── front/alfa-frontend/        # React 19 + Vite 8 (кабинет, калькулятор, интерфейс банка)
└── front/alfa-frontend/README.md
```

## Быстрый старт

1. **База данных** (PostgreSQL 14+):

```bash
createdb alfa_hakaton
psql -d alfa_hakaton -f DB.sql
```

2. **Backend**:

```bash
cd backend
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env            # укажите PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD или DATABASE_URL
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Проверка: `curl http://127.0.0.1:8000/health` → `{"status":"ok","database":"ok"}`.
Подробнее — [backend/README.md](backend/README.md).

3. **Frontend**:

```bash
cd front/alfa-frontend
npm install
npm run dev                     # http://localhost:5173
```

Если API запущен на другом адресе: `cp .env.example .env` и задайте `VITE_API_URL`.
Подробнее — [front/alfa-frontend/README.md](front/alfa-frontend/README.md).

## Демо-учётные записи

| Логин | Пароль | Роль |
|---|---|---|
| `client` | `client` | предприниматель |
| `bank` | `bank` | сотрудник банка |

## Ограничения прототипа

- Авторизация, заявки, продукты, скоринг и решения — демонстрационные; заявки и решения
  хранятся в mock-данных/`localStorage`, а не в БД.
- Backend реализует только `/health` и `GET /api/companies/{inn}`; бизнес-логика
  кредитования и аутентификация появятся позже.
- Все суммы, ставки и условия не являются офертой банка.
