"""Pydantic-модели ответов API."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Literal

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
    min_credit_rating: int | None = None


class LoginRequest(BaseModel):
    """Данные для входа в систему."""

    username: str = Field(min_length=1, max_length=100, examples=["client"])
    password: str = Field(min_length=1, examples=["client"])


class AuthUser(BaseModel):
    """Успешно авторизованный пользователь из таблицы ``login``."""

    username: str
    profile_type: Literal["business", "employee"]
    company_inn: str | None = None
