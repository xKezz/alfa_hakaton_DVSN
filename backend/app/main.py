"""FastAPI-приложение: health-check и поиск компании по ИНН."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Annotated, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from . import db
from .config import get_settings
from .schemas import (
    AuthUser,
    Company,
    ErrorResponse,
    FinancialStatement,
    FinancialStatementCreate,
    HealthResponse,
    LoanProduct,
    LoginRequest,
    ServiceInfo,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# ООО — 10 цифр, ИП — 12 цифр.
INN_RE = re.compile(r"^(?:\d{10}|\d{12})$")

COMPANY_SELECT = """
    SELECT inn,
           company_name,
           registration_date,
           company_status,
           industry,
           region_code,
           is_simplified_tax,
           dissolution_flag
      FROM companies
     WHERE inn = %(inn)s
"""

# Поля таблицы financial_statements, которые заполняются через API.
FINANCIAL_FIELDS = (
    "revenue",
    "net_profit",
    "assets",
    "current_assets",
    "total_equity",
    "longterm_debt",
    "shortterm_debt",
    "shortterm_liab",
    "retained_earnings",
    "profit_from_sales",
    "before_tax",
    "cash_equivalents",
    "interest_payable",
    "balance_operating",
)
_FINANCIAL_COLUMNS = ", ".join(FINANCIAL_FIELDS)
_FINANCIAL_VALUES = ", ".join(f"%({name})s" for name in FINANCIAL_FIELDS)

FINANCIAL_INSERT = f"""
    INSERT INTO financial_statements (inn, report_year, {_FINANCIAL_COLUMNS})
    VALUES (%(inn)s, %(report_year)s, {_FINANCIAL_VALUES})
    RETURNING financial_id, inn, report_year, {_FINANCIAL_COLUMNS}
"""

COMPANY_EXISTS_SQL = "SELECT 1 FROM companies WHERE inn = %(inn)s"

LOGIN_SELECT = """
    SELECT username,
           password,
           profile_type,
           company_inn
      FROM login
     WHERE username = %(username)s
"""


def _hash_password(password: str) -> str:
    """SHA-256-хеш пароля (пароли в БД хранятся только в виде хеша)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

LOAN_PRODUCTS_SELECT = """
    SELECT product_id,
           product_name,
           description,
           business_category,
           min_amount::float8 AS min_amount,
           max_amount::float8 AS max_amount,
           min_term_months,
           max_term_months,
           percent::float8 AS percent,
           loan_purpose,
           is_active,
           business_age
      FROM loan_catalog
     WHERE is_active = TRUE
       AND business_category IN (%(business_category)s, 'both')
       AND (
            CAST(%(purpose)s AS varchar) IS NULL
            OR loan_purpose = %(purpose)s
            OR loan_purpose = 'other'
       )
       AND min_amount <= %(amount)s
       AND max_amount >= %(amount)s
       AND min_term_months <= %(term_months)s
       AND max_term_months >= %(term_months)s
       AND (
            CAST(%(business_age_months)s AS integer) IS NULL
            OR business_age <= %(business_age_months)s
       )
       AND (
            CAST(%(credit_rating)s AS integer) IS NULL
            OR min_credit_rating <= %(credit_rating)s
       )
     ORDER BY percent ASC, product_id
"""

FINANCIAL_SELECT = f"""
    SELECT financial_id, inn, report_year, {_FINANCIAL_COLUMNS}
      FROM financial_statements
     WHERE inn = %(inn)s
     ORDER BY report_year DESC
"""

app = FastAPI(
    title="Alfa Hakaton Backend",
    version="0.1.0",
    description=(
        "Минимальный backend для кредитования ИП/ООО: проверка состояния сервиса, "
        "карточка компании по ИНН, подбор кредитных продуктов и сохранение годовой "
        "финансовой отчётности."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=ServiceInfo, summary="Информация о сервисе", tags=["service"])
def root() -> ServiceInfo:
    """Короткая информация о сервисе и ссылка на Swagger UI."""
    return ServiceInfo(service="alfa-hakaton-backend", docs="/docs")


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка состояния сервиса и БД",
    tags=["service"],
)
def health() -> HealthResponse:
    """Всегда отвечает 200; доступность БД отражается в поле ``database``."""
    return HealthResponse(
        status="ok",
        database="ok" if db.ping() else "unavailable",
    )


@app.post(
    "/api/auth/login",
    response_model=AuthUser,
    summary="Авторизация по логину и паролю",
    responses={
        401: {"model": ErrorResponse, "description": "Неверный логин или пароль"},
        422: {"model": ErrorResponse, "description": "Некорректные данные запроса"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["auth"],
)
def login(payload: LoginRequest) -> AuthUser:
    """Проверяет логин и пароль по таблице ``login`` и возвращает профиль пользователя."""
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(LOGIN_SELECT, {"username": payload.username})
            row = cur.fetchone()
    except (psycopg.Error, OSError) as exc:
        logger.error("Ошибка БД при авторизации пользователя: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc

    if row is None or not hmac.compare_digest(row["password"], _hash_password(payload.password)):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    return AuthUser(
        username=row["username"],
        profile_type=row["profile_type"],
        company_inn=row["company_inn"],
    )


@app.get(
    "/api/companies/{inn}",
    response_model=Company,
    summary="Компания по ИНН",
    responses={
        404: {"model": ErrorResponse, "description": "Компания не найдена"},
        422: {"model": ErrorResponse, "description": "Некорректный ИНН"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["companies"],
)
def get_company(
    inn: Annotated[
        str,
        Path(description="ИНН: 10 цифр (ООО) или 12 цифр (ИП)", examples=["7701234567"]),
    ],
) -> Company:
    """Ищет компанию по ИНН.

    ИНН валидируется вручную, чтобы вернуть понятный ``detail`` (а не
    стандартный список ошибок FastAPI). Запрос к БД параметризован.
    """
    if not INN_RE.fullmatch(inn):
        raise HTTPException(
            status_code=422,
            detail="ИНН должен состоять только из цифр и содержать 10 или 12 символов",
        )

    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(COMPANY_SELECT, {"inn": inn})
            row = cur.fetchone()
    except (psycopg.Error, OSError) as exc:
        # Клиенту не отдаём stack trace, детали пишем в лог.
        logger.error("Ошибка БД при поиске компании по ИНН %s: %s", inn, exc, exc_info=True)
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    return Company(**row)


@app.get(
    "/api/loan-products",
    response_model=list[LoanProduct],
    summary="Подбор активных кредитных продуктов",
    responses={
        422: {"model": ErrorResponse, "description": "Некорректные параметры подбора"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["loan_products"],
)
def get_loan_products(
    amount: Annotated[
        float,
        Query(gt=0, description="Запрашиваемая сумма кредита"),
    ],
    term_months: Annotated[
        int,
        Query(gt=0, description="Запрашиваемый срок кредита в месяцах"),
    ],
    business_category: Annotated[
        Literal["ip", "ooo", "both"],
        Query(description="Категория бизнеса заявителя"),
    ] = "both",
    purpose: Annotated[
        Literal[
            "working_capital",
            "equipment",
            "business_expansion",
            "refinancing",
            "other",
        ]
        | None,
        Query(description="Код цели кредитования из loan_catalog, например working_capital"),
    ] = None,
    business_age_months: Annotated[
        int | None,
        Query(ge=0, description="Возраст бизнеса в месяцах"),
    ] = None,
    credit_rating: Annotated[
        int | None,
        Query(
            ge=0,
            le=1000,
            description="Рассчитанный скоринг заявителя 0–1000 (не выбирается клиентом)",
        ),
    ] = None,
) -> list[LoanProduct]:
    """Возвращает активные продукты из ``loan_catalog``, подходящие под параметры.

    Универсальные продукты с ``loan_purpose = 'other'`` подходят под любую цель.
    Если ничего не подходит, возвращается пустой список.
    """
    params = {
        "amount": amount,
        "term_months": term_months,
        "business_category": business_category,
        "purpose": purpose,
        "business_age_months": business_age_months,
        "credit_rating": credit_rating,
    }

    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(LOAN_PRODUCTS_SELECT, params)
            rows = cur.fetchall()
    except (psycopg.Error, OSError) as exc:
        logger.error("Ошибка БД при подборе кредитных продуктов: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc

    return [LoanProduct(**row) for row in rows]


@app.post(
    "/api/financial-statements",
    response_model=FinancialStatement,
    status_code=201,
    summary="Добавить годовую финансовую отчётность",
    responses={
        404: {"model": ErrorResponse, "description": "Компания не найдена"},
        409: {"model": ErrorResponse, "description": "Отчётность за этот год уже существует"},
        422: {"model": ErrorResponse, "description": "Некорректные данные отчётности"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["financial_statements"],
)
def create_financial_statement(payload: FinancialStatementCreate) -> FinancialStatement:
    """Сохраняет годовую финансовую отчётность компании в ``financial_statements``.

    Одна компания может иметь только одну запись за отчётный год
    (ограничение ``UNIQUE (inn, report_year)`` в БД).
    """
    params = payload.model_dump()

    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(COMPANY_EXISTS_SQL, {"inn": payload.inn})
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Компания не найдена")

            cur.execute(FINANCIAL_INSERT, params)
            row = cur.fetchone()
            conn.commit()
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        logger.warning(
            "Отчётность за %s год для ИНН %s уже существует",
            payload.report_year,
            payload.inn,
        )
        raise HTTPException(
            status_code=409,
            detail="Отчётность за этот отчётный год уже существует",
        ) from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(status_code=404, detail="Компания не найдена") from exc
    except (psycopg.Error, OSError) as exc:
        logger.error(
            "Ошибка БД при сохранении отчётности (ИНН %s, год %s): %s",
            payload.inn,
            payload.report_year,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc

    if row is None:  # pragma: no cover - защита от неожиданного поведения БД
        raise HTTPException(status_code=500, detail="Не удалось сохранить отчётность")

    return FinancialStatement(**row)


def _validate_inn(inn: str) -> None:
    if not INN_RE.fullmatch(inn):
        raise HTTPException(
            status_code=422,
            detail="ИНН должен состоять только из цифр и содержать 10 или 12 символов",
        )


def _fetch_statements(inn: str, limit: int | None = None) -> list[dict]:
    sql = FINANCIAL_SELECT + (" LIMIT %(limit)s" if limit else "")
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"inn": inn, "limit": limit})
            return cur.fetchall()
    except (psycopg.Error, OSError) as exc:
        logger.error("Ошибка БД при чтении отчётности (ИНН %s): %s", inn, exc, exc_info=True)
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc


@app.get(
    "/api/financial-statements/{inn}/latest",
    response_model=FinancialStatement,
    summary="Последняя годовая отчётность компании",
    responses={
        404: {"model": ErrorResponse, "description": "Отчётность не найдена"},
        422: {"model": ErrorResponse, "description": "Некорректный ИНН"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["financial_statements"],
)
def get_latest_financial_statement(inn: str) -> FinancialStatement:
    """Отчётность за самый свежий год: используется для автозаполнения заявки."""
    _validate_inn(inn)
    rows = _fetch_statements(inn, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Финансовая отчётность не найдена")
    return FinancialStatement(**rows[0])


@app.get(
    "/api/financial-statements/{inn}",
    response_model=list[FinancialStatement],
    summary="Вся годовая отчётность компании",
    responses={
        422: {"model": ErrorResponse, "description": "Некорректный ИНН"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
    tags=["financial_statements"],
)
def list_financial_statements(inn: str) -> list[FinancialStatement]:
    """Все годы по убыванию. Пустой список, если отчётности нет."""
    _validate_inn(inn)
    return [FinancialStatement(**row) for row in _fetch_statements(inn)]


if __name__ == "__main__":  # pragma: no cover - ручной запуск
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)
