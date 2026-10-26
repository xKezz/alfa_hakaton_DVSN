"""Pydantic-модели ответов API."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ServiceInfo(BaseModel):
    """Короткая информация о сервисе (GET /)."""

    service: str = Field(examples=["alfa-hakaton-backend"])
    docs: str = Field(examples=["/docs"])


class HealthResponse(BaseModel):
    """Статус сервиса и БД (GET /health). HTTP-код всегда 200."""

    status: Literal["ok"] = "ok"
    database: Literal["ok", "unavailable"]


class Company(BaseModel):
    """Компания из таблицы ``companies`` (все поля, кроме inn, могут быть NULL)."""

    inn: str
    company_name: str | None = None
    registration_date: date | None = None
    company_status: str | None = None
    industry: str | None = None
    region_code: str | None = None
    is_simplified_tax: bool | None = None
    dissolution_flag: bool | None = None


class ErrorResponse(BaseModel):
    """Единый формат ошибки."""

    detail: str


INN_PATTERN = r"^(?:\d{10}|\d{12})$"


class FinancialStatementCreate(BaseModel):
    """Данные годовой финансовой отчётности для таблицы ``financial_statements``.

    Числовые показатели необязательны: отсутствующие значения сохраняются как NULL,
    как и предусмотрено схемой БД.
    """

    inn: str = Field(examples=["3257029840"], description="ИНН компании: 10 или 12 цифр")
    report_year: int = Field(ge=1900, examples=[2025], description="Отчётный год")

    revenue: Decimal | None = None
    net_profit: Decimal | None = None
    assets: Decimal | None = None
    current_assets: Decimal | None = None
    total_equity: Decimal | None = None
    longterm_debt: Decimal | None = None
    shortterm_debt: Decimal | None = None
    shortterm_liab: Decimal | None = None
    retained_earnings: Decimal | None = None
    profit_from_sales: Decimal | None = None
    before_tax: Decimal | None = None
    cash_equivalents: Decimal | None = None
    interest_payable: Decimal | None = None
    balance_operating: Decimal | None = None

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value: str) -> str:
        if not re.fullmatch(INN_PATTERN, value):
            raise ValueError(
                "ИНН должен состоять только из цифр и содержать 10 или 12 символов"
            )
        return value


class FinancialStatement(FinancialStatementCreate):
    """Сохранённая запись ``financial_statements``."""

    financial_id: int


class LoanProduct(BaseModel):
    """Кредитный продукт из таблицы ``loan_catalog``."""

    product_id: int
    product_name: str
    description: str | None = None
    business_category: str
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    percent: float
    loan_purpose: str | None = None
    is_active: bool
    business_age: int
    min_credit_rating: int


class LoginRequest(BaseModel):
    """Данные для входа в систему."""

    username: str = Field(min_length=1, max_length=100, examples=["client"])
    password: str = Field(min_length=1, examples=["client"])


class AuthUser(BaseModel):
    """Успешно авторизованный пользователь из таблицы ``login``."""

    username: str
    profile_type: Literal["business", "employee"]
    company_inn: str | None = None
    access_token: str | None = Field(default=None, description="Bearer-токен для защищённых действий")


# ---------------------------------------------------------------------------
# Кредитные заявки и скоринг
# ---------------------------------------------------------------------------

LOAN_APPLICATION_STATUSES = (
    "submitted",
    "processing",
    "manual_review",
    "offer_pending",
    "approved",
    "rejected",
)

# Пять целей из документации (StakeHolders and User Stories, US-04).
LOAN_PURPOSES = (
    "launch_and_start",
    "operational_activity",
    "development_and_scaling",
    "strategic_goals",
    "business_protection",
    # Специальная цель «Другое» не входит в пять целей, но используется
    # правилом ручной проверки.
    "other",
)


class LoanApplicationCreate(BaseModel):
    """Заявка клиента на кредитный продукт из `loan_catalog`."""

    inn: str = Field(examples=["4217064416"], description="ИНН заявителя")
    product_id: int = Field(gt=0, examples=[2])
    requested_amount: Decimal = Field(gt=0, examples=[2000000])
    requested_term_months: int = Field(gt=0, examples=[12])
    loan_purpose: str = Field(
        examples=["working_capital"],
        description="Код цели кредита из loan_catalog.loan_purpose",
    )
    business_age_months: int | None = Field(
        default=None,
        ge=0,
        description="Возраст бизнеса в месяцах на момент подбора (для альтернатив)",
    )

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value: str) -> str:
        if not re.fullmatch(INN_PATTERN, value):
            raise ValueError("ИНН должен состоять только из цифр и содержать 10 или 12 символов")
        return value

    @field_validator("loan_purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        if value not in LOAN_PURPOSES:
            raise ValueError(
                "Недопустимая цель кредита. Допустимые: " + ", ".join(LOAN_PURPOSES)
            )
        return value


class LoanApplicationDecisionRequest(BaseModel):
    """Решение сотрудника по заявке, ожидающей ручной проверки."""

    decision: Literal["approved", "rejected"]
    decided_by: str | None = Field(
        default=None,
        max_length=100,
        description="Устаревшее поле; сервер использует логин из Bearer-токена",
    )
    reason: str = Field(min_length=5, max_length=2000)
    approved_amount: Decimal | None = Field(default=None, gt=0)
    approved_term_months: int | None = Field(default=None, gt=0)


class EmployeeOfferCreate(BaseModel):
    """Индивидуальное предложение сотрудника банка."""

    product_id: int = Field(gt=0)
    approved_amount: Decimal = Field(gt=0)
    approved_term_months: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=2000)


class ApplicationScoringInfo(BaseModel):
    """Сохранённый результат скоринга заявки (applications_checks)."""

    rating: int | None = None
    risk_category: str | None = None
    product_scoring: float | None = None
    scoring_factors: dict[str, Any] | None = None
    employee_rout: bool = False
    routing_reason: str | None = None
    has_error: bool = False
    checked_at: datetime | None = None


class ApplicationDecisionInfo(BaseModel):
    """Решение по заявке (applications_decisions)."""

    decision_type: str
    decision_source: str
    decided_by: str | None = None
    decision_reason: str | None = None
    approved_amount: float | None = None
    approved_term_months: int | None = None
    decided_at: datetime


class ApplicationHistoryInfo(BaseModel):
    """Событие истории заявки (applications_history)."""

    event_type: str
    actor_username: str | None = None
    old_status: str | None = None
    new_status: str | None = None
    event_description: str | None = None
    created_at: datetime


class ApplicationOfferInfo(BaseModel):
    """Предложение по заявке (application_offers)."""

    offer_id: int
    product_id: int
    product_name: str | None = None
    percent: float | None = None
    approved_amount: float
    approved_term_months: int
    status: str
    source: str = "automatic"
    created_by: str | None = None
    reason: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class LoanApplicationDetail(BaseModel):
    """Полная карточка заявки для клиента/сотрудника."""

    application_id: str
    inn: str
    company_name: str | None = None
    product_id: int
    product_name: str | None = None
    requested_amount: float
    requested_term_months: int
    loan_purpose: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    scoring: ApplicationScoringInfo | None = None
    decision: ApplicationDecisionInfo | None = None
    offers: list[ApplicationOfferInfo] = Field(default_factory=list)
    history: list[ApplicationHistoryInfo] = Field(default_factory=list)


class LoanApplicationSummary(BaseModel):
    """Краткая строка очереди заявок (в т.ч. на ручную проверку)."""

    application_id: str
    inn: str
    company_name: str | None = None
    product_id: int
    product_name: str | None = None
    requested_amount: float
    requested_term_months: int
    loan_purpose: str | None = None
    status: str
    rating: int | None = None
    risk_category: str | None = None
    employee_rout: bool = False
    routing_reason: str | None = None
    created_at: datetime
    updated_at: datetime
