# API

## Общие сведения

- Base URL локально: `http://localhost:8000`
- Swagger UI: `/docs`
- OpenAPI: [`docs/openapi.json`](openapi.json) (статический снимок; актуальная
  схема — `GET /openapi.json`)
- Формат ошибок: `{"detail": "..."}`
- Авторизация: `Authorization: Bearer <access_token>`; токен выдаёт
  `POST /api/auth/login`, срок действия 12 ч.

| Роль | Доступ |
|---|---|
| `business` | свои компании/заявки/офферы, создание заявки, выбор/отклонение оффера |
| `employee` | очередь `manual_review`, каталог для оффера, решения и создание офферов |
| без токена | `/`, `/health`, `/api/auth/login`, компании, продукты, отчётность |

## Эндпоинты

| Метод | Путь | Роль | Назначение |
|---|---|---|---|
| GET | `/health` | — | статус API и БД |
| GET | `/` | — | информация о сервисе |
| POST | `/api/auth/login` | — | вход, выдача Bearer-токена |
| GET | `/api/companies/{inn}` | — | компания по ИНН |
| GET | `/api/loan-products` | — | подбор активных продуктов |
| GET | `/api/loan-products/catalog` | employee | полный активный каталог |
| POST | `/api/financial-statements` | — | добавить годовую отчётность |
| GET | `/api/financial-statements/{inn}` | — | отчётность компании по годам |
| GET | `/api/financial-statements/{inn}/latest` | — | последняя отчётность |
| POST | `/api/loan-applications` | business | создать заявку и выполнить скоринг |
| GET | `/api/loan-applications` | business/employee | список своих заявок / очередь `manual_review` |
| GET | `/api/loan-applications/{application_id}` | business/employee | карточка заявки |
| POST | `/api/loan-applications/{application_id}/employee-offer` | employee | индивидуальное предложение |
| POST | `/api/loan-applications/{application_id}/decision` | employee | одобрить/отказать |
| POST | `/api/loan-applications/{application_id}/offers/{offer_id}/select` | business | принять оффер |
| POST | `/api/loan-applications/{application_id}/offers/{offer_id}/decline` | business | отклонить оффер |

## Примеры

### Вход

```http
POST /api/auth/login
Content-Type: application/json

{"username": "client", "password": "client"}
```

```json
{
  "username": "client",
  "profile_type": "business",
  "company_inn": "3662277634",
  "access_token": "<token>"
}
```

### Создание заявки

```http
POST /api/loan-applications
Authorization: Bearer <business-token>
Content-Type: application/json

{
  "inn": "3662277634",
  "product_id": 7,
  "requested_amount": 1000000,
  "requested_term_months": 12,
  "loan_purpose": "other",
  "business_age_months": 36
}
```

### Предложение сотрудника

```http
POST /api/loan-applications/{application_id}/employee-offer
Authorization: Bearer <employee-token>
Content-Type: application/json

{
  "product_id": 7,
  "approved_amount": 1200000,
  "approved_term_months": 18,
  "reason": "Индивидуальные условия для клиента"
}
```

### Принятие оффера

```http
POST /api/loan-applications/{application_id}/offers/{offer_id}/select
Authorization: Bearer <business-token>
```

Готовая последовательность запросов — в
[`docs/alfa-hakaton.postman_collection.json`](alfa-hakaton.postman_collection.json).
