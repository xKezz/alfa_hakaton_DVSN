# alfa-hakaton-DVSN

Решение для кредитного конвейера ИП/ООО: подбор кредитного продукта, расчёт кредитного риска, подача заявки, автоматическое или ручное рассмотрение, формирование предложений и принятие решения предпринимателем.

Подробные методические материалы: [src/credit_risk/README.md](src/credit_risk/README.md),
описание схемы БД: [src/db/README.md](src/db/README.md),
backend: [src/backend/README.md](src/backend/README.md),
frontend: [src/front/README.md](src/front/README.md).
Сторонние компоненты: [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

## Документация и артефакты

- [Архитектурная схема](docs/ARCHITECTURE.md)
- [Описание API](docs/API.md)
- [статический OpenAPI](docs/openapi.json) - https://alfa-hakaton-dvsn.duckdns.org/docs
- [Коллекция Postman](docs/alfa-hakaton.postman_collection.json)
- [Диаграмма состояний заявки](docs/APPLICATION_STATES.md)
- [Модель данных](docs/DATA_MODEL.md)
- [Тестовые сценарии](docs/TEST_SCENARIOS.md)
- [Индекс документации](docs/README.md)

## Архитектура

```
Браузер (React 19 + Vite)
        │  REST /api, Bearer-token
        ▼
FastAPI backend (Python 3.12)
        │
        ├── PostgreSQL 16: компании, отчётность, продукты, заявки, офферы, решения
        └── src/credit_risk: детерминированный кредитный скоринг
                └── src/credit_risk/data/weight.json: веса и пороги
```

| Компонент         | Назначение                                                                             |
| ----------------- | -------------------------------------------------------------------------------------- |
| `src/front`       | SPA предпринимателя и сотрудника банка; сборка через Vite, раздача через Nginx/Docker  |
| `src/backend`     | FastAPI: авторизация, компании, продукты, заявки, скоринг, ручное рассмотрение, офферы |
| `src/credit_risk` | расчёт рейтинга 0–1000 по финансовым показателям и отраслевым весам                    |
| `src/db`          | DDL, загрузка данных, demo/bootstrap, Docker-инициализация БД                          |
| `other_info`      | бизнес-описание, User Stories                                                          |

Backend не содержит ML/LLM-моделей: скоринг — воспроизводимая формула с
конфигурируемыми весами. Внешние интеграции (ФНС, банковское ядро) не
вызываются; в репозитории используются локальная БД и смоделированный API.

## Требования к окружению и версии

| Компонент            | Требование / фиксация                                       |
| -------------------- | ----------------------------------------------------------- |
| Python               | 3.12 (`python:3.12-slim` в Docker)                          |
| Node.js              | 22 (`src/front/.nvmrc`, `node:22-alpine` в Docker)          |
| PostgreSQL           | 14+; в Docker используется `postgres:16-alpine`             |
| Docker               | Docker Engine + Compose plugin — для запуска всего стека    |
| Python-зависимости   | точные версии в `src/backend/requirements.txt`              |
| Frontend-зависимости | lock-файл `src/front/package-lock.json` (lockfileVersion 3) |
| Nginx                | `nginx:1.27-alpine` в Docker                                |

Полные версии Python-пакетов: `src/backend/requirements.txt`; frontend —
`src/front/package-lock.json`. Для воспроизводимой установки используйте
`pip install -r requirements.txt` и `npm ci`, а не `npm install`.

## Быстрый старт без Docker

```bash
# 1. Зависимости backend
cd src/backend
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env
```

`src/backend/.env.example` уже содержит локальные значения PostgreSQL и
dev-`AUTH_SECRET`; при другом пароле PostgreSQL измените `PGPASSWORD`.

```bash
# 2. Схема и демо-данные (из корня репозитория)
src/backend/.venv/bin/python src/db/setup_db.py
```

Скрипт создаёт БД `alfa-hakaton`, таблицы из `src/db/DB.sql`, 4 демо-компании,
11 кредитных продуктов и тестовые учётные записи. Он **пересоздаёт таблицы** —
не запускайте его на БД с нужными данными.

```bash
# 3. Backend
cd src/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

```bash
# 4. Frontend
cd src/front
npm ci
npm run dev                 # http://localhost:5173
```

## Запуск через Docker

```bash
docker compose up --build -d
```

- приложение: <http://localhost:8080>
- API/Swagger: <http://localhost:8000/docs>
- PostgreSQL: только внутри compose-сети

Сервис `db-init` при первом запуске создаёт схему и демо-данные; при повторном
запуске существующая БД не пересоздаётся. Подробности — в
`docker-compose.yml`. Сброс: `docker compose down -v`.

## Конфигурация и переменные окружения

`.env` не коммитится; в репозитории находятся только примеры.

| Переменная                                                                                                                                                                                | Где используется  | Назначение / default                                                                                                                                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                                                                                                                                                            | backend           | полный DSN PostgreSQL; приоритетнее `PG*`                                                                                                                                                                 |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`                                                                                                                                  | backend, db-init  | параметры PostgreSQL; dev-default: `localhost:5432`, `alfa-hakaton`, `postgres/postgres`                                                                                                                  |
| `AUTH_SECRET`                                                                                                                                                                             | backend           | подпись Bearer-токенов; для production задать случайное значение                                                                                                                                          |
| `APP_HOST`, `APP_PORT`                                                                                                                                                                    | backend           | адрес/порт приложения                                                                                                                                                                                     |
| `CORS_ORIGINS`                                                                                                                                                                            | backend           | список origins через запятую                                                                                                                                                                              |
| `VITE_API_URL`                                                                                                                                                                            | frontend          | адрес API; вне Docker — `http://localhost:8000`; в Docker `/` через Nginx                                                                                                                                 |
| `FRONTEND_PORT`, `BACKEND_PORT`                                                                                                                                                           | Docker Compose    | публикуемые порты; default `8080` и `8000`                                                                                                                                                                |
| `AGE_THRESHOLDS`, `PROFIT_FROM_SALES_MARGIN`, `BEFORE_TAX_MARGIN`, `NET_PROFIT_MARGIN`,  `DEBT_TO_EQUITY`, `NET_DEBT_TO_EBITDA`, `DEBT_SERVICE_COVERAGE`, `CFO_TO_REVENUE`, `CFO_TO_DEBT` | Scoring Algorithm | Переменные хранящие границы возможных значений для вычисления финансового рейтинга компании                                                                                                               |
| `RATING_TO_SCORE`                                                                                                                                                                         | Scoring Algorithm | Нижние пороги для вычисления буквенного рейтинга согласно АКРА «Методология присвоения кредитных рейтингов нефинансовым компаниям по национальной шкале для Российской Федерации» от 17 февраля 2023 года |
| `PRODUCT_SCORE_WEIGHTS`                                                                                                                                                                   | Scoring Algorithm | Веса факторов в итоговом скоринговом балле продукта.                                                                                                                                                      |

Примеры: `src/backend/.env.example`, `src/front/.env.example`,
`.env.docker.example`. Для production обязательно замените `AUTH_SECRET` и
пароль PostgreSQL.

## Синтетические данные и тестовые учётные записи

- `src/db/setup_db.py` создаёт 4 синтетические компании, 11 продуктов и
  учётные записи.
- Полный синтетический датасет: `src/db/df_companies.csv` и
  `src/db/df_financial.csv` — 127 828 записей каждый; загружается скриптами
  `load_companies.py` / `load_financial.py` при необходимости.
- Данные не являются реальной отчётностью и не содержат персональных данных.

| Логин | Пароль | Роль | Компания |
|---|---|---|---|
| `client` | `client` | предприниматель | 3662277634 |
| `login1` | `login1` | предприниматель | 3906398393 |
| `login2` | `login2` | предприниматель | 7722344211 |
| `login3` | `login3` | предприниматель | 3662277634 |
| `login4` | `login4` | предприниматель | 0721013581 |
| `bank` | `bank` | сотрудник банка | — |

`login1` — положительный демонстрационный профиль; `client` и `login3`
оставлены на слабом профиле для проверки отказов и регрессионных сценариев.

## Сквозной сценарий проверки

[Тестовые сценарии](docs/TEST_SCENARIOS.md) - В данном файле описаны основные тестовые сценарии проверки. 

Один из сквозных сценариев: 

1. Запустите стек: `docker compose up --build -d` (или локальные шаги выше).
2. Откройте `http://localhost:8080`, войдите как `client / client`.
3. Нажмите «Подобрать кредит», выберите продукт и цель **«Другое»**
   (этот маршрут передаёт заявку на ручную проверку), заполните профиль и
   финансовые показатели, отправьте заявку. Ожидаемый статус:
   `На ручной проверке`.
4. Выйдите и войдите как `bank / bank`. В очереди ручной проверки откройте
   заявку, выберите «Сформировать предложение», укажите продукт, сумму, срок и
   обоснование, отправьте. Ожидаемый статус заявки: `offer_pending`.
5. Войдите снова как `client / client`, откройте заявку, проверьте условия и
   нажмите «Принять предложение». Ожидаемый статус: `Одобрено`; в карточке
   отображаются сумма и срок предложения.
6. Проверьте результат в БД:

```bash
docker compose exec db psql -U postgres -d alfa-hakaton -c \
  "SELECT application_id, application_status FROM loan_applications ORDER BY created_at DESC LIMIT 1;"
docker compose exec db psql -U postgres -d alfa-hakaton -c \
  "SELECT offer_status, approved_amount, approved_term_months FROM application_offers ORDER BY created_at DESC LIMIT 1;"
docker compose exec db psql -U postgres -d alfa-hakaton -c \
  "SELECT decision_source, decided_by, approved_amount FROM applications_decisions ORDER BY decided_at DESC LIMIT 1;"
```

Ожидается: заявка `approved`, оффер `selected`, решение
`decision_source='bank_employee'` с `decided_by='bank'`.

Дополнительно проверяются ветки «Одобрить»/«Отказать» сотрудником и
автоматический сценарий; повторный выбор/отклонение оффера возвращает `409`.
 
## Тесты

```bash
cd src/backend
.venv/bin/python -m unittest discover -s tests -t .
# интеграционные тесты с PostgreSQL:
RUN_DB_TESTS=1 .venv/bin/python -m unittest discover -s tests -t .
```

```bash
cd src/front
npm ci
npm run lint
npm run build
```

## Принятые решения / Ограничения

* Решение не использовать ML/LLM-алгоритмы и модели было принято ввиду отсутствия размеченного датасета для ООО и ИП. Вместо этого была использована АКРА «Методология присвоения кредитных рейтингов нефинансовым компаниям по национальной шкале для Российской Федерации» от 17 февраля 2023 года, оттуда использовались веса и виды некоторых формул. 
* Аутентификация локальная
- ФНС API и банковское ядро смоделированы; реальные внешние запросы не
  выполняются.
- Кредитные продукты, компании и отчётность в демо-наборе синтетические.