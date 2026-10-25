"""API и сервис кредитных заявок: скоринг, авто-рассмотрение, ручная проверка."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import db
from .auth import get_current_user, require_business, require_employee
from .schemas import (
    ApplicationDecisionInfo,
    ApplicationOfferInfo,
    ApplicationHistoryInfo,
    ApplicationScoringInfo,
    AuthUser,
    EmployeeOfferCreate,
    ErrorResponse,
    LoanApplicationCreate,
    LoanApplicationDecisionRequest,
    LoanApplicationDetail,
    LoanApplicationSummary,
    LOAN_APPLICATION_STATUSES,
)
from .scoring_service import calculate_application_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/loan-applications", tags=["loan_applications"])

INN_RE = re.compile(r"^(?:\d{10}|\d{12})$")

COMPANY_SELECT = """
    SELECT inn, company_name, registration_date, company_status, industry,
           region_code, is_simplified_tax, dissolution_flag
      FROM companies
     WHERE inn = %s
"""

PRODUCT_SELECT = """
    SELECT product_id,
           product_name,
           description,
           business_category,
           min_amount,
           max_amount,
           min_term_months,
           max_term_months,
           percent,
           loan_purpose,
           is_active,
           business_age,
           min_credit_rating
      FROM loan_catalog
     WHERE product_id = %s
"""

ALTERNATIVE_PRODUCTS_SELECT = """
    SELECT product_id,
           product_name,
           description,
           business_category,
           min_amount,
           max_amount,
           min_term_months,
           max_term_months,
           percent,
           loan_purpose,
           is_active,
           business_age,
           min_credit_rating
      FROM loan_catalog
     WHERE is_active = TRUE
       AND business_category IN (%s, 'both')
       AND (loan_purpose = %s OR loan_purpose = 'other')
       AND min_amount <= %s
       AND max_amount >= %s
       AND min_term_months <= %s
       AND max_term_months >= %s
       AND business_age <= %s
       AND product_id <> %s
     ORDER BY percent ASC, product_id
"""

FINANCIAL_LATEST_SELECT = """
    SELECT financial_id, inn, report_year, revenue, net_profit, assets,
           current_assets, total_equity, longterm_debt, shortterm_debt,
           shortterm_liab, retained_earnings, profit_from_sales, before_tax,
           cash_equivalents, interest_payable, balance_operating
      FROM financial_statements
     WHERE inn = %s
     ORDER BY report_year DESC
     LIMIT 1
"""

APPLICATION_INSERT = """
    INSERT INTO loan_applications (
        application_id, inn, product_id, requested_amount,
        requested_term_months, loan_purpose, application_status
    ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
"""

HISTORY_INSERT = """
    INSERT INTO applications_history (
        application_id, event_type, actor_username, old_status, new_status,
        event_description
    ) VALUES (%s, %s, %s, %s, %s, %s)
"""

CHECK_INSERT = """
    INSERT INTO applications_checks (
        application_id, product_id, has_error, risk_category, scoring,
        scoring_factors, employee_rout, routing_reason
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

OFFERS_SELECT = """
    SELECT o.offer_id,
           o.product_id,
           p.product_name,
           p.percent::float8 AS percent,
           o.approved_amount,
           o.approved_term_months,
           o.offer_status,
           o.offer_source,
           o.created_by,
           o.created_at,
           o.decided_at
      FROM application_offers AS o
      LEFT JOIN loan_catalog AS p ON p.product_id = o.product_id
     WHERE o.application_id = %s
     ORDER BY o.offer_id
"""

OFFER_INSERT = """
    INSERT INTO application_offers (
        application_id, product_id, approved_amount, approved_term_months,
        offer_source, offer_status
    ) VALUES (%s, %s, %s, %s, 'automatic', 'offered')
    RETURNING offer_id
"""

EMPLOYEE_OFFER_INSERT = """
    INSERT INTO application_offers (
        application_id, product_id, approved_amount, approved_term_months,
        offer_source, created_by, offer_status
    ) VALUES (%s, %s, %s, %s, 'bank_employee', %s, 'offered')
    RETURNING offer_id
"""

DECISION_INSERT = """
    INSERT INTO applications_decisions (
        application_id, product_id, offer_id, decision_type, decision_source,
        decided_by, decision_reason, approved_amount, approved_term_months
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

APPLICATION_DETAIL_SELECT = """
    SELECT la.application_id,
           la.inn,
           c.company_name,
           la.product_id,
           p.product_name,
           la.requested_amount,
           la.requested_term_months,
           la.loan_purpose,
           la.application_status,
           la.created_at,
           la.updated_at
      FROM loan_applications AS la
      LEFT JOIN companies AS c ON c.inn = la.inn
      LEFT JOIN loan_catalog AS p ON p.product_id = la.product_id
     WHERE la.application_id = %s
"""

SUMMARY_BASE_SELECT = """
    SELECT la.application_id,
           la.inn,
           c.company_name,
           la.product_id,
           p.product_name,
           la.requested_amount,
           la.requested_term_months,
           la.loan_purpose,
           la.application_status,
           la.created_at,
           la.updated_at,
           ch.scoring,
           ch.risk_category,
           ch.employee_rout,
           ch.routing_reason
      FROM loan_applications AS la
      LEFT JOIN companies AS c ON c.inn = la.inn
      LEFT JOIN loan_catalog AS p ON p.product_id = la.product_id
      LEFT JOIN LATERAL (
          SELECT scoring, risk_category, employee_rout, routing_reason
            FROM applications_checks
           WHERE application_id = la.application_id
           ORDER BY checked_at DESC, check_id DESC
           LIMIT 1
      ) AS ch ON TRUE
"""


def _company_age_months(company: dict) -> int:
    """Возраст бизнеса в месяцах для подбора альтернатив."""
    registered = company.get("registration_date")
    if registered is None:
        return 0
    from datetime import date

    return max(0, int((date.today() - registered).days / 30.44))


def _validate_inn(inn: str) -> None:
    if not INN_RE.fullmatch(inn):
        raise HTTPException(
            status_code=422,
            detail="ИНН должен состоять только из цифр и содержать 10 или 12 символов",
        )


def _sql_error(exc: Exception, action: str) -> HTTPException:
    logger.error("Ошибка БД при %s: %s", action, exc, exc_info=True)
    return HTTPException(status_code=503, detail="База данных недоступна")


def _validate_product_request(product: dict, payload: LoanApplicationCreate, company: dict) -> None:
    """Проверяет, что заявка допустима для выбранного продукта."""
    if not product.get("is_active"):
        raise HTTPException(status_code=422, detail="Кредитный продукт неактивен")

    amount = Decimal(payload.requested_amount)
    if not (Decimal(product["min_amount"]) <= amount <= Decimal(product["max_amount"])):
        raise HTTPException(
            status_code=422,
            detail="Сумма заявки вне допустимого диапазона продукта",
        )
    term = int(payload.requested_term_months)
    if not (int(product["min_term_months"]) <= term <= int(product["max_term_months"])):
        raise HTTPException(
            status_code=422,
            detail="Срок заявки вне допустимого диапазона продукта",
        )

    company_status = str(company.get("company_status") or "").lower()
    product_category = str(product.get("business_category") or "").lower()
    if product_category not in ("both", company_status):
        raise HTTPException(
            status_code=422,
            detail="Продукт не предназначен для категории заявителя",
        )

    product_purpose = product.get("loan_purpose")
    # loan_purpose = 'other' у продукта означает универсальный продукт.
    # Если клиент выбрал специальную цель «Другое», продукт может иметь
    # собственную цель: такая заявка всё равно уйдёт на ручную проверку.
    if payload.loan_purpose != "other" and product_purpose not in (
        None,
        "other",
        payload.loan_purpose,
    ):
        raise HTTPException(
            status_code=422,
            detail="Цель кредита не соответствует выбранному продукту",
        )


def _set_status(
    application_id: str,
    new_status: str,
    *,
    event_type: str,
    old_status: str,
    description: str | None = None,
    actor_username: str | None = None,
) -> None:
    """Меняет статус заявки и пишет событие в историю в одной транзакции."""
    with db.connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "UPDATE loan_applications "
                "SET application_status = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE application_id = %s",
                (new_status, application_id),
            )
            cur.execute(
                HISTORY_INSERT,
                (application_id, event_type, actor_username, old_status, new_status, description),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _json_safe(value: Any) -> Any:
    """Приводит Decimal/date и прочие значения к JSON-совместимому виду."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _build_scoring_factors(score: dict) -> dict:
    fin_result = score.get("financial_result") or {}
    product_result = score.get("product_result") or {}
    return _json_safe(
        {
            "algorithm": "src.credit_risk (Financial_Risk_Score + CreditScorer)",
            "rating": score.get("rating"),
            "risk_category": score.get("risk_category"),
            "report_year": score.get("report_year"),
            "product_score": product_result.get("scoring"),
            "product_factors": product_result.get("scoring_factors"),
            "threshold": score.get("threshold"),
            "fin_params": fin_result.get("fin_params"),
            "data_quality": fin_result.get("data_quality"),
            "missing_blocks": fin_result.get("missing_blocks"),
            "blocks": fin_result.get("blocks"),
            "manual_review_reasons": score.get("manual_review_reasons"),
            "chosen_status": score.get("chosen_status"),
            "chosen_reasons": score.get("chosen_reasons"),
            "alternatives": score.get("alternatives"),
            "offers": [
                {
                    "product_id": item["product_id"],
                    "product_name": item["product"].get("product_name"),
                    "scoring": item["product_result"].get("scoring"),
                    "risk_category": item["risk_category"],
                }
                for item in score.get("offers") or []
            ],
        }
    )


def _persist_scoring_result(application_id: str, application_row: dict, score: dict) -> None:
    """Сохраняет результат скоринга, офферы/решение и новый статус атомарно."""
    status = score["status"]
    product_result = score.get("product_result") or {}
    reasons = score.get("manual_review_reasons") or []
    auto_reason = score.get("auto_reason")
    is_manual = status == "manual_review"
    is_offer = status == "offer_pending"
    routing_reason = "; ".join(reasons) if is_manual else auto_reason

    with db.connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                CHECK_INSERT,
                (
                    application_id,
                    int(application_row["product_id"]),
                    bool(product_result.get("has_error")),
                    score.get("risk_category"),
                    int(score["rating"]),
                    Jsonb(_build_scoring_factors(score)),
                    is_manual,
                    routing_reason,
                ),
            )

            if is_manual:
                cur.execute(
                    "UPDATE loan_applications "
                    "SET application_status = 'manual_review', updated_at = CURRENT_TIMESTAMP "
                    "WHERE application_id = %s",
                    (application_id,),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "scoring_calculated",
                        None,
                        "processing",
                        "manual_review",
                        f"Рейтинг: {score['rating']}; " + (routing_reason or "требуется сотрудник"),
                    ),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "manual_review_assigned",
                        None,
                        "processing",
                        "manual_review",
                        routing_reason,
                    ),
                )
            elif is_offer:
                offer_names: list[str] = []
                for item in score.get("offers") or []:
                    offer = item["product"]
                    offer_names.append(str(offer.get("product_name") or offer["product_id"]))
                    cur.execute(
                        OFFER_INSERT,
                        (
                            application_id,
                            int(offer["product_id"]),
                            Decimal(application_row["requested_amount"]),
                            int(application_row["requested_term_months"]),
                        ),
                    )
                offer_reason = auto_reason or "Подобраны альтернативные предложения"
                if offer_names:
                    offer_reason = f"{offer_reason}: {', '.join(offer_names)}"
                cur.execute(
                    "UPDATE loan_applications "
                    "SET application_status = 'offer_pending', updated_at = CURRENT_TIMESTAMP "
                    "WHERE application_id = %s",
                    (application_id,),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "scoring_calculated",
                        None,
                        "processing",
                        "offer_pending",
                        f"Рейтинг: {score['rating']}; {offer_reason}",
                    ),
                )
                for item in score.get("offers") or []:
                    cur.execute(
                        HISTORY_INSERT,
                        (
                            application_id,
                            "offer_created",
                            None,
                            "processing",
                            "offer_pending",
                            f"Предложен продукт: {item['product'].get('product_name') or item['product_id']}",
                        ),
                    )
            else:
                decision_type = "approved" if status == "approved" else "rejected"
                if decision_type == "approved":
                    cur.execute(
                        DECISION_INSERT,
                        (
                            application_id,
                            int(application_row["product_id"]),
                            None,
                            decision_type,
                            "automatic",
                            None,
                            auto_reason,
                            Decimal(application_row["requested_amount"]),
                            int(application_row["requested_term_months"]),
                        ),
                    )
                else:
                    cur.execute(
                        DECISION_INSERT,
                        (
                            application_id,
                            int(application_row["product_id"]),
                            None,
                            decision_type,
                            "automatic",
                            None,
                            auto_reason,
                            None,
                            None,
                        ),
                    )
                cur.execute(
                    "UPDATE loan_applications "
                    "SET application_status = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE application_id = %s",
                    (status, application_id),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "scoring_calculated",
                        None,
                        "processing",
                        status,
                        f"Рейтинг: {score['rating']}; {auto_reason or ''}".strip(),
                    ),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "decision_made",
                        None,
                        "processing",
                        status,
                        auto_reason,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

def _persist_scoring_error(application_id: str, product_id: int, error: str) -> None:
    """Ошибка скоринга: заявка уходит сотруднику без ложного решения."""
    reason = f"Ошибка расчёта скоринга: {error}"[:2000]
    with db.connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                CHECK_INSERT,
                (
                    application_id,
                    product_id,
                    True,
                    None,
                    None,
                    Jsonb({"error": reason}),
                    True,
                    reason,
                ),
            )
            cur.execute(
                "UPDATE loan_applications "
                "SET application_status = 'manual_review', updated_at = CURRENT_TIMESTAMP "
                "WHERE application_id = %s",
                (application_id,),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "manual_review_assigned",
                    None,
                    "processing",
                    "manual_review",
                    reason,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _fetch_application_row(cur, application_id: str) -> dict | None:
    cur.execute(APPLICATION_DETAIL_SELECT, (application_id,))
    return cur.fetchone()


def _fetch_detail(application_id: str) -> LoanApplicationDetail:
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            application = _fetch_application_row(cur, application_id)
            if application is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")

            cur.execute(
                "SELECT check_id, has_error, risk_category, scoring, scoring_factors, "
                "employee_rout, routing_reason, checked_at "
                "FROM applications_checks WHERE application_id = %s "
                "ORDER BY checked_at DESC, check_id DESC LIMIT 1",
                (application_id,),
            )
            check = cur.fetchone()

            cur.execute(
                "SELECT decision_id, decision_type, decision_source, decided_by, "
                "decision_reason, approved_amount, approved_term_months, decided_at "
                "FROM applications_decisions WHERE application_id = %s "
                "ORDER BY decided_at DESC, decision_id DESC LIMIT 1",
                (application_id,),
            )
            decision = cur.fetchone()

            cur.execute(
                "SELECT event_type, actor_username, old_status, new_status, "
                "event_description, created_at "
                "FROM applications_history WHERE application_id = %s "
                "ORDER BY created_at DESC, history_id DESC LIMIT 20",
                (application_id,),
            )
            history_rows = cur.fetchall()

            cur.execute(OFFERS_SELECT, (application_id,))
            offer_rows = cur.fetchall()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "чтении заявки") from exc

    scoring = None
    if check is not None:
        factors = check.get("scoring_factors") or {}
        scoring = ApplicationScoringInfo(
            rating=check.get("scoring"),
            risk_category=check.get("risk_category"),
            product_scoring=(
                float(factors["product_score"])
                if isinstance(factors, dict) and factors.get("product_score") is not None
                else None
            ),
            scoring_factors=factors if isinstance(factors, dict) else None,
            employee_rout=bool(check.get("employee_rout")),
            routing_reason=check.get("routing_reason"),
            has_error=bool(check.get("has_error")),
            checked_at=check.get("checked_at"),
        )

    decision_info = None
    if decision is not None:
        decision_info = ApplicationDecisionInfo(
            decision_type=decision["decision_type"],
            decision_source=decision["decision_source"],
            decided_by=decision.get("decided_by"),
            decision_reason=decision.get("decision_reason"),
            approved_amount=(
                float(decision["approved_amount"])
                if decision.get("approved_amount") is not None
                else None
            ),
            approved_term_months=decision.get("approved_term_months"),
            decided_at=decision["decided_at"],
        )

    # Причина индивидуального предложения сотрудника хранится в
    # applications_history.offer_created (отдельного поля в offers нет).
    employee_offer_reason = next(
        (
            row.get("event_description")
            for row in history_rows
            if row.get("event_type") == "offer_created"
            and row.get("actor_username")
            and row.get("event_description")
        ),
        None,
    )

    offers = [
        ApplicationOfferInfo(
            offer_id=row["offer_id"],
            product_id=row["product_id"],
            product_name=row.get("product_name"),
            percent=row.get("percent"),
            approved_amount=float(row["approved_amount"]),
            approved_term_months=row["approved_term_months"],
            status=row["offer_status"],
            source=row.get("offer_source") or "automatic",
            created_by=row.get("created_by"),
            reason=(
                employee_offer_reason
                if (row.get("offer_source") or "automatic") == "bank_employee"
                else None
            ),
            created_at=row["created_at"],
            decided_at=row.get("decided_at"),
        )
        for row in offer_rows
    ]

    history = [
        ApplicationHistoryInfo(
            event_type=row["event_type"],
            actor_username=row.get("actor_username"),
            old_status=row.get("old_status"),
            new_status=row.get("new_status"),
            event_description=row.get("event_description"),
            created_at=row["created_at"],
        )
        for row in history_rows
    ]

    return LoanApplicationDetail(
        application_id=application["application_id"],
        inn=application["inn"],
        company_name=application.get("company_name"),
        product_id=application["product_id"],
        product_name=application.get("product_name"),
        requested_amount=float(application["requested_amount"]),
        requested_term_months=application["requested_term_months"],
        loan_purpose=application.get("loan_purpose"),
        status=application["application_status"],
        created_at=application["created_at"],
        updated_at=application.get("updated_at") or application["created_at"],
        scoring=scoring,
        decision=decision_info,
        offers=offers,
        history=history,
    )


@router.post(
    "",
    response_model=LoanApplicationDetail,
    status_code=201,
    summary="Создать кредитную заявку и выполнить скоринг",
    responses={
        404: {"model": ErrorResponse, "description": "Компания или продукт не найдены"},
        422: {"model": ErrorResponse, "description": "Некорректные данные заявки"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def create_loan_application(
    payload: LoanApplicationCreate,
    current_user: AuthUser = Depends(require_business),
) -> LoanApplicationDetail:
    """Сохраняет заявку, вызывает существующий скоринг и маршрутизирует её."""
    _validate_inn(payload.inn)
    if payload.inn != current_user.company_inn:
        raise HTTPException(
            status_code=403,
            detail="Нельзя создать заявку от имени чужой компании",
        )
    application_id = str(uuid.uuid4())

    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(COMPANY_SELECT, (payload.inn,))
            company = cur.fetchone()
            if company is None:
                raise HTTPException(status_code=404, detail="Компания с таким ИНН не найдена")

            cur.execute(PRODUCT_SELECT, (payload.product_id,))
            product = cur.fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Кредитный продукт не найден")
            _validate_product_request(product, payload, company)

            cur.execute(FINANCIAL_LATEST_SELECT, (payload.inn,))
            financial = cur.fetchone()
            if financial is None:
                raise HTTPException(
                    status_code=422,
                    detail="Нет финансовой отчётности — заполните её в профиле",
                )

            age_months = (
                payload.business_age_months
                if payload.business_age_months is not None
                else _company_age_months(company)
            )
            company_category = str(company.get("company_status") or "").lower()
            cur.execute(
                ALTERNATIVE_PRODUCTS_SELECT,
                (
                    company_category,
                    payload.loan_purpose,
                    payload.requested_amount,
                    payload.requested_amount,
                    payload.requested_term_months,
                    payload.requested_term_months,
                    age_months,
                    payload.product_id,
                ),
            )
            alternative_products = cur.fetchall()

            cur.execute(
                APPLICATION_INSERT,
                (
                    application_id,
                    payload.inn,
                    payload.product_id,
                    payload.requested_amount,
                    payload.requested_term_months,
                    payload.loan_purpose,
                ),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "application_submitted",
                    None,
                    None,
                    "submitted",
                    "Заявка создана через API",
                ),
            )
            cur.execute(
                "UPDATE loan_applications "
                "SET application_status = 'processing', updated_at = CURRENT_TIMESTAMP "
                "WHERE application_id = %s",
                (application_id,),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "processing_started",
                    None,
                    "submitted",
                    "processing",
                    "Запущен расчёт кредитного рейтинга",
                ),
            )
            cur.execute(
                "SELECT application_id, inn, product_id, requested_amount, "
                "requested_term_months, loan_purpose "
                "FROM loan_applications WHERE application_id = %s",
                (application_id,),
            )
            application_row = cur.fetchone()
            conn.commit()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "создании заявки") from exc

    try:
        # Ограничиваем время расчёта, чтобы зависший scoring-запрос не
        # оставлял заявку в processing навсегда.
        score = asyncio.run(
            asyncio.wait_for(
                calculate_application_score(
                    inn=payload.inn,
                    financial=financial,
                    product=product,
                    alternative_products=alternative_products,
                    requested_amount=float(payload.requested_amount),
                    requested_term_months=int(payload.requested_term_months),
                    loan_purpose=payload.loan_purpose,
                ),
                timeout=30.0,
            )
        )
    except Exception as exc:  # noqa: BLE001 - любая ошибка скоринга не должна давать ложный результат
        logger.exception("Ошибка скоринга заявки %s: %s", application_id, exc)
        try:
            _persist_scoring_error(application_id, int(product["product_id"]), str(exc))
        except (psycopg.Error, OSError) as db_exc:
            raise _sql_error(db_exc, "сохранении ошибки скоринга") from db_exc
        return _fetch_detail(application_id)

    try:
        _persist_scoring_result(application_id, application_row, score)
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "сохранении результата скоринга") from exc

    return _fetch_detail(application_id)


@router.get(
    "",
    response_model=list[LoanApplicationSummary],
    summary="Список заявок (по умолчанию — очередь ручной проверки)",
    responses={503: {"model": ErrorResponse, "description": "База данных недоступна"}},
)
def list_loan_applications(
    status: str | None = Query(
        default=None,
        description="Статус заявки; без параметров — очередь ручной проверки",
    ),
    inn: str | None = Query(default=None, description="ИНН клиента для его личного кабинета"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthUser = Depends(get_current_user),
) -> list[LoanApplicationSummary]:
    """Очередь сотрудника (manual_review) или только свои заявки предпринимателя."""
    if status is not None and status not in LOAN_APPLICATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Недопустимый статус. Допустимые: " + ", ".join(LOAN_APPLICATION_STATUSES),
        )
    if current_user.profile_type == "business":
        own_inn = current_user.company_inn
        if not own_inn:
            raise HTTPException(status_code=403, detail="У пользователя не привязана компания")
        if inn is not None and inn != own_inn:
            raise HTTPException(status_code=403, detail="Доступ только к заявкам своей компании")
        inn = own_inn
    elif inn is not None:
        _validate_inn(inn)

    conditions: list[str] = []
    params: list[object] = []
    if status is not None:
        conditions.append("la.application_status = %s")
        params.append(status)
    elif inn is None:
        # Обратная совместимость: сотрудник без параметров получает очередь.
        conditions.append("la.application_status = 'manual_review'")
    if inn is not None:
        conditions.append("la.inn = %s")
        params.append(inn)

    where_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        SUMMARY_BASE_SELECT
        + where_sql
        + " ORDER BY la.created_at DESC LIMIT %s"
    )
    params.append(limit)
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "получении списка заявок") from exc

    return [
        LoanApplicationSummary(
            application_id=row["application_id"],
            inn=row["inn"],
            company_name=row.get("company_name"),
            product_id=row["product_id"],
            product_name=row.get("product_name"),
            requested_amount=float(row["requested_amount"]),
            requested_term_months=row["requested_term_months"],
            loan_purpose=row.get("loan_purpose"),
            status=row["application_status"],
            rating=row.get("scoring"),
            risk_category=row.get("risk_category"),
            employee_rout=bool(row.get("employee_rout")),
            routing_reason=row.get("routing_reason"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at") or row["created_at"],
        )
        for row in rows
    ]


@router.get(
    "/{application_id}",
    response_model=LoanApplicationDetail,
    summary="Получить заявку, статус, скоринг и решение",
    responses={
        404: {"model": ErrorResponse, "description": "Заявка не найдена"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def get_loan_application(
    application_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> LoanApplicationDetail:
    """Карточка заявки: предприниматель видит только заявки своей компании."""
    detail = _fetch_detail(application_id)
    if (
        current_user.profile_type == "business"
        and detail.inn != current_user.company_inn
    ):
        raise HTTPException(status_code=403, detail="Доступ только к заявкам своей компании")
    return detail


@router.post(
    "/{application_id}/employee-offer",
    response_model=LoanApplicationDetail,
    status_code=201,
    summary="Сотрудник формирует индивидуальное предложение предпринимателю",
    responses={
        403: {"model": ErrorResponse, "description": "Нет прав сотрудника"},
        404: {"model": ErrorResponse, "description": "Заявка или продукт не найдены"},
        409: {"model": ErrorResponse, "description": "Заявка не находится на ручной проверке"},
        422: {"model": ErrorResponse, "description": "Некорректные данные предложения"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def create_employee_offer(
    application_id: str,
    payload: EmployeeOfferCreate,
    current_user: AuthUser = Depends(require_employee),
) -> LoanApplicationDetail:
    """Создаёт предложение сотрудника; заявка ждёт решения предпринимателя."""
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT application_id, product_id, application_status "
                "FROM loan_applications WHERE application_id = %s FOR UPDATE",
                (application_id,),
            )
            application = cur.fetchone()
            if application is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            if application["application_status"] != "manual_review":
                raise HTTPException(
                    status_code=409,
                    detail="Индивидуальное предложение можно создать только на ручной проверке",
                )

            cur.execute(
                "SELECT product_id FROM loan_catalog WHERE product_id = %s AND is_active = TRUE",
                (payload.product_id,),
            )
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=422,
                    detail="Выбранный кредитный продукт не найден или неактивен",
                )

            cur.execute(
                EMPLOYEE_OFFER_INSERT,
                (
                    application_id,
                    payload.product_id,
                    payload.approved_amount,
                    payload.approved_term_months,
                    current_user.username,
                ),
            )
            offer_id = cur.fetchone()["offer_id"]

            cur.execute(
                "UPDATE loan_applications SET application_status = 'offer_pending', "
                "updated_at = CURRENT_TIMESTAMP WHERE application_id = %s",
                (application_id,),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "offer_created",
                    current_user.username,
                    "manual_review",
                    "offer_pending",
                    payload.reason,
                ),
            )
            conn.commit()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "создании индивидуального предложения") from exc

    logger.info(
        "Сотрудник %s создал предложение %s по заявке %s",
        current_user.username,
        offer_id,
        application_id,
    )
    return _fetch_detail(application_id)


@router.post(
    "/{application_id}/decision",
    response_model=LoanApplicationDetail,
    summary="Решение сотрудника по заявке из очереди ручной проверки",
    responses={
        403: {"model": ErrorResponse, "description": "Нет прав сотрудника"},
        404: {"model": ErrorResponse, "description": "Заявка не найдена"},
        409: {"model": ErrorResponse, "description": "Заявка не ожидает ручного решения"},
        422: {"model": ErrorResponse, "description": "Некорректное решение"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def decide_loan_application(
    application_id: str,
    payload: LoanApplicationDecisionRequest,
    current_user: AuthUser = Depends(require_employee),
) -> LoanApplicationDetail:
    """Принимает окончательное решение сотрудника; автоматические решения не перепроверяются."""
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT application_id, product_id, requested_amount, "
                "requested_term_months, application_status "
                "FROM loan_applications WHERE application_id = %s FOR UPDATE",
                (application_id,),
            )
            application = cur.fetchone()
            if application is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            if application["application_status"] != "manual_review":
                raise HTTPException(
                    status_code=409,
                    detail="Заявка не находится на ручной проверке; автоматические решения окончательны",
                )

            if payload.decision == "approved":
                if payload.approved_amount is None or payload.approved_term_months is None:
                    raise HTTPException(
                        status_code=422,
                        detail="Для одобрения обязательно укажите сумму и срок",
                    )
                approved_amount = payload.approved_amount
                approved_term = payload.approved_term_months
                if Decimal(approved_amount) <= 0 or int(approved_term) <= 0:
                    raise HTTPException(
                        status_code=422,
                        detail="Для одобрения нужны положительные сумма и срок",
                    )
            else:
                approved_amount = None
                approved_term = None

            cur.execute(
                DECISION_INSERT,
                (
                    application_id,
                    int(application["product_id"]),
                    None,
                    payload.decision,
                    "bank_employee",
                    current_user.username,
                    payload.reason,
                    approved_amount,
                    approved_term,
                ),
            )
            cur.execute(
                "UPDATE loan_applications "
                "SET application_status = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE application_id = %s",
                (payload.decision, application_id),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "decision_made",
                    current_user.username,
                    "manual_review",
                    payload.decision,
                    payload.reason or "Решение сотрудника банка",
                ),
            )
            conn.commit()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "сохранении решения сотрудника") from exc

    return _fetch_detail(application_id)


@router.post(
    "/{application_id}/offers/{offer_id}/select",
    response_model=LoanApplicationDetail,
    summary="Клиент выбирает альтернативное предложение",
    responses={
        404: {"model": ErrorResponse, "description": "Заявка или предложение не найдены"},
        409: {"model": ErrorResponse, "description": "Заявка/предложение не ожидают выбора"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def select_application_offer(
    application_id: str,
    offer_id: int,
    current_user: AuthUser = Depends(require_business),
) -> LoanApplicationDetail:
    """Фиксирует выбранный оффер и переводит заявку в approved без повторного скоринга."""
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT application_id, inn, product_id, application_status, "
                "requested_amount, requested_term_months "
                "FROM loan_applications WHERE application_id = %s FOR UPDATE",
                (application_id,),
            )
            application = cur.fetchone()
            if application is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            if application["inn"] != current_user.company_inn:
                raise HTTPException(status_code=403, detail="Доступ только к заявкам своей компании")
            if application["application_status"] != "offer_pending":
                raise HTTPException(
                    status_code=409,
                    detail="Заявка не ожидает выбора альтернативного предложения",
                )

            cur.execute(
                "SELECT offer_id, product_id, approved_amount, approved_term_months, "
                "offer_status, offer_source, created_by FROM application_offers "
                "WHERE offer_id = %s AND application_id = %s FOR UPDATE",
                (offer_id, application_id),
            )
            offer = cur.fetchone()
            if offer is None:
                raise HTTPException(status_code=404, detail="Предложение не найдено")
            if offer["offer_status"] != "offered":
                raise HTTPException(status_code=409, detail="Предложение уже обработано")

            # Обоснование индивидуального предложения сотрудника хранится в
            # applications_history.offer_created — отдельного поля в offers нет.
            cur.execute(
                "SELECT event_description FROM applications_history "
                "WHERE application_id = %s AND event_type = 'offer_created' "
                "ORDER BY created_at DESC, history_id DESC LIMIT 1",
                (application_id,),
            )
            offer_event = cur.fetchone()
            employee_offer_reason = offer_event["event_description"] if offer_event else None
            is_employee_offer = offer["offer_source"] == "bank_employee"
            decision_source = "bank_employee" if is_employee_offer else "automatic"
            decided_by = offer["created_by"] if is_employee_offer else None
            decision_reason = (
                employee_offer_reason
                if is_employee_offer and employee_offer_reason
                else "Клиент выбрал альтернативное предложение"
            )

            cur.execute(
                "UPDATE application_offers SET offer_status = 'selected', "
                "decided_at = CURRENT_TIMESTAMP WHERE offer_id = %s",
                (offer_id,),
            )
            cur.execute(
                "UPDATE application_offers SET offer_status = 'superseded', "
                "decided_at = CURRENT_TIMESTAMP "
                "WHERE application_id = %s AND offer_id <> %s AND offer_status = 'offered'",
                (application_id, offer_id),
            )
            cur.execute(
                "UPDATE loan_applications SET application_status = 'approved', "
                "updated_at = CURRENT_TIMESTAMP WHERE application_id = %s",
                (application_id,),
            )
            cur.execute(
                DECISION_INSERT,
                (
                    application_id,
                    int(offer["product_id"]),
                    offer_id,
                    "approved",
                    decision_source,
                    decided_by,
                    decision_reason,
                    offer["approved_amount"],
                    int(offer["approved_term_months"]),
                ),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "offer_selected",
                    current_user.username,
                    "offer_pending",
                    "approved",
                    f"Предприниматель выбрал предложение offer_id={offer_id}",
                ),
            )
            cur.execute(
                HISTORY_INSERT,
                (
                    application_id,
                    "decision_made",
                    current_user.username,
                    "offer_pending",
                    "approved",
                    "Предложение принято; повторный скоринг не требуется",
                ),
            )
            conn.commit()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "выборе альтернативного предложения") from exc

    return _fetch_detail(application_id)


@router.post(
    "/{application_id}/offers/{offer_id}/decline",
    response_model=LoanApplicationDetail,
    summary="Клиент отказывается от альтернативного предложения",
    responses={
        404: {"model": ErrorResponse, "description": "Заявка или предложение не найдены"},
        409: {"model": ErrorResponse, "description": "Заявка/предложение не ожидают выбора"},
        503: {"model": ErrorResponse, "description": "База данных недоступна"},
    },
)
def decline_application_offer(
    application_id: str,
    offer_id: int,
    current_user: AuthUser = Depends(require_business),
) -> LoanApplicationDetail:
    """Отмечает отказ; если отказ от всех офферов — финальный отказ по заявке."""
    try:
        with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT application_id, inn, product_id, application_status "
                "FROM loan_applications WHERE application_id = %s FOR UPDATE",
                (application_id,),
            )
            application = cur.fetchone()
            if application is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            if application["inn"] != current_user.company_inn:
                raise HTTPException(status_code=403, detail="Доступ только к заявкам своей компании")
            if application["application_status"] != "offer_pending":
                raise HTTPException(
                    status_code=409,
                    detail="Заявка не ожидает выбора альтернативного предложения",
                )

            cur.execute(
                "SELECT offer_id, offer_status, offer_source, created_by "
                "FROM application_offers "
                "WHERE offer_id = %s AND application_id = %s FOR UPDATE",
                (offer_id, application_id),
            )
            offer = cur.fetchone()
            if offer is None:
                raise HTTPException(status_code=404, detail="Предложение не найдено")
            if offer["offer_status"] != "offered":
                raise HTTPException(status_code=409, detail="Предложение уже обработано")

            cur.execute(
                "UPDATE application_offers SET offer_status = 'declined', "
                "decided_at = CURRENT_TIMESTAMP WHERE offer_id = %s",
                (offer_id,),
            )
            cur.execute(
                "SELECT count(*) AS c FROM application_offers "
                "WHERE application_id = %s AND offer_status = 'offered'",
                (application_id,),
            )
            remaining = int(cur.fetchone()["c"])

            if remaining > 0:
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "offer_declined",
                        current_user.username,
                        "offer_pending",
                        "offer_pending",
                        f"Предприниматель отклонил предложение offer_id={offer_id}",
                    ),
                )
            else:
                cur.execute(
                    "UPDATE loan_applications SET application_status = 'rejected', "
                    "updated_at = CURRENT_TIMESTAMP WHERE application_id = %s",
                    (application_id,),
                )
                cur.execute(
                    DECISION_INSERT,
                    (
                        application_id,
                        int(application["product_id"]),
                        offer_id,
                        "rejected",
                        "automatic",
                        None,
                        (
                            "Предприниматель отклонил предложение"
                            if offer["offer_source"] == "bank_employee"
                            else "Клиент отказался от всех альтернативных предложений"
                        ),
                        None,
                        None,
                    ),
                )
                decline_reason = (
                    "Предприниматель отклонил предложение"
                    if offer["offer_source"] == "bank_employee"
                    else "Клиент отказался от всех альтернативных предложений"
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "offer_declined",
                        current_user.username,
                        "offer_pending",
                        "rejected",
                        f"Предприниматель отклонил предложение offer_id={offer_id}",
                    ),
                )
                cur.execute(
                    HISTORY_INSERT,
                    (
                        application_id,
                        "decision_made",
                        current_user.username,
                        "offer_pending",
                        "rejected",
                        decline_reason,
                    ),
                )
            conn.commit()
    except HTTPException:
        raise
    except (psycopg.Error, OSError) as exc:
        raise _sql_error(exc, "отказе от альтернативного предложения") from exc

    return _fetch_detail(application_id)
