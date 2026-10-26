"""Интеграция существующего алгоритма скоринга с backend.

Все формулы, веса и пороги остаются в `src/credit_risk/*` и
`src/credit_risk/data/weight.json`. Здесь выполняется только преобразование
данных API/БД в формат алгоритма, вызов его функций и маршрутизация заявки.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.parse import quote

from .config import get_settings

logger = logging.getLogger(__name__)

# Корень, от которого импортируется пакет `src.credit_risk`.
#
# Раскладка репозитория: <repo_root>/src/backend/app/scoring_service.py,
# поэтому self-parents[3] — корень репозитория. В Docker backend лежит в
# /app/backend, и корнем импорта становится /app. Чтобы не зависеть от
# конкретной раскладки, ищем ближайший родительский каталог, содержащий
# `src/credit_risk`.
def _detect_import_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "credit_risk").is_dir():
            return parent
    # Фолбэк: <repo_root>/src/backend/app/scoring_service.py -> <repo_root>
    return here.parents[3]


PROJECT_ROOT = _detect_import_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.credit_risk.apis_fns_example import FNSApi  # noqa: E402
from src.credit_risk.credit_category import (  # noqa: E402
    Credit_category,
    product_scoring_threshold,
    rating_to_score_fast,
)
from src.credit_risk.credit_risk_score import Financial_Risk_Score  # noqa: E402
from src.credit_risk.internal_api import InternalApi  # noqa: E402

MANUAL_PURPOSE_VALUES = {"other", "другое"}

REASON_BOUNDARY = "Скоринг в пограничной зоне продукта (существующее правило)"
REASON_BELOW_MIN = "Кредитный рейтинг {rating} ниже минимального рейтинга продукта {min_rating}"
REASON_PURPOSE_OTHER = "Цель кредита «Другое»"
REASON_SCORING_ERROR = "Ошибка расчёта скоринга: {error}"
REASON_NO_ALTERNATIVES = (
    "Рейтинг недостаточен для выбранного продукта, подходящих альтернатив не найдено"
)
REASON_ALTERNATIVES_FOUND = "Подобраны альтернативные продукты с подходящим рейтингом"


def build_dsn() -> str:
    """Строка подключения для asyncpg из настроек backend."""
    settings = get_settings()
    if settings.database_url:
        dsn = settings.database_url
        if dsn.startswith("postgres://"):
            dsn = "postgresql://" + dsn[len("postgres://") :]
        if dsn.startswith("postgresql+"):
            dsn = "postgresql://" + dsn.split("://", 1)[1]
        return dsn

    user = quote(settings.pguser or "", safe="")
    password = quote(settings.pgpassword or "", safe="")
    auth = user if not password else f"{user}:{password}"
    database = quote(settings.pgdatabase or "", safe="")
    return f"postgresql://{auth}@{settings.pghost}:{settings.pgport}/{database}"


def manual_review_reasons(
    *,
    rating: int,
    product: dict,
    product_result: dict,
    loan_purpose: str | None,
) -> list[str]:
    """Причины ручной проверки для конкретного продукта.

    Сохраняется существующее правило алгоритма `employee_rout` (пограничная
    зона), плюс условия задачи: рейтинг ниже `min_credit_rating` продукта
    или цель «Другое». Условия объединяются через OR.
    """
    reasons: list[str] = []

    if product_result.get("has_error"):
        reasons.append(REASON_SCORING_ERROR.format(error="см. scoring_factors"))
    if product_result.get("employee_rout"):
        reasons.append(REASON_BOUNDARY)

    min_rating = int(product.get("min_credit_rating") or 0)
    if rating < min_rating:
        reasons.append(REASON_BELOW_MIN.format(rating=rating, min_rating=min_rating))

    if str(loan_purpose or "").strip().lower() in MANUAL_PURPOSE_VALUES:
        reasons.append(REASON_PURPOSE_OTHER)

    return list(dict.fromkeys(reasons))


def decide_application(
    *,
    rating: int,
    product: dict,
    product_result: dict,
    threshold: dict,
    loan_purpose: str | None,
) -> dict:
    """Статус для одного продукта по существующим порогам.

    Приоритет: ручная проверка → автоматический отказ ниже нижней границы →
    автоматическое одобрение выше верхней границы.
    """
    reasons = manual_review_reasons(
        rating=rating,
        product=product,
        product_result=product_result,
        loan_purpose=loan_purpose,
    )
    if reasons:
        return {
            "status": "manual_review",
            "decision": None,
            "reasons": reasons,
            "auto_reason": None,
        }

    score = product_result.get("scoring")
    if score is None:
        return {
            "status": "manual_review",
            "decision": None,
            "reasons": [REASON_SCORING_ERROR.format(error="product_score не рассчитан")],
            "auto_reason": None,
        }

    score = float(score)
    if score < float(threshold["low"]):
        return {
            "status": "rejected",
            "decision": "rejected",
            "reasons": [],
            "auto_reason": (
                f"Автоматический отказ: скоринг {score:.2f} ниже нижней границы "
                f"{float(threshold['low']):.2f}"
            ),
        }
    if score > float(threshold["high"]):
        return {
            "status": "approved",
            "decision": "approved",
            "reasons": [],
            "auto_reason": (
                f"Автоматическое одобрение: скоринг {score:.2f} выше верхней границы "
                f"{float(threshold['high']):.2f}"
            ),
        }

    return {
        "status": "manual_review",
        "decision": None,
        "reasons": [REASON_BOUNDARY],
        "auto_reason": None,
    }


def _scoring_product(product: dict) -> dict:
    """Копия продукта с ключом, который ожидает существующий алгоритм."""
    result = dict(product)
    result["min_credit_ratings"] = int(product.get("min_credit_rating") or 0)
    return result


async def _evaluate_product(
    *,
    product: dict,
    rating: int,
    financial_result: dict,
    requested_amount: float,
    requested_term_months: int,
    loan_purpose: str | None,
    api: FNSApi,
    internal_api: InternalApi,
    financial_scorer: Financial_Risk_Score,
) -> dict:
    """Оценивает один продукт существующим `Credit_category` (без новых формул)."""
    scoring_product = _scoring_product(product)
    product_id = int(product["product_id"])
    try:
        category = Credit_category(
            user_param={
                "inn": financial_result["inn"],
                "report_year": financial_result["report_year"],
                "fin_params": financial_result["fin_params"],
                # Цель уже проверена API; алгоритм не фильтрует каталог по цели.
                "credit_search_params": {
                    "amount": float(requested_amount),
                    "term": int(requested_term_months),
                    "purpose": None,
                },
            },
            product_id=product_id,
            api=api,
            internal_api=internal_api,
            financial_scorer=financial_scorer,
        )
        category.catalog_loans = [scoring_product]
        product_result = await category.process()
        if isinstance(product_result, list):
            product_result = product_result[0] if product_result else None
        if not product_result:
            raise ValueError("продукт не прошёл обязательные условия")
    except Exception as exc:  # noqa: BLE001 - ошибка продукта не роняет всю заявку
        logger.warning("Ошибка оценки продукта %s: %s", product_id, exc)
        product_result = {
            "product_id": product_id,
            "has_error": True,
            "risk_category": None,
            "scoring": None,
            "scoring_factors": {},
            "employee_rout": True,
            "error": str(exc),
        }

    threshold = product_scoring_threshold(scoring_product)
    reasons = manual_review_reasons(
        rating=rating,
        product=product,
        product_result=product_result,
        loan_purpose=loan_purpose,
    )
    routing = decide_application(
        rating=rating,
        product=product,
        product_result=product_result,
        threshold=threshold,
        loan_purpose=loan_purpose,
    )
    return {
        "product": product,
        "product_id": product_id,
        "scoring_product": scoring_product,
        "product_result": product_result,
        "threshold": threshold,
        "risk_category": (
            product_result.get("risk_category") or rating_to_score_fast(rating)
        ),
        "reasons": reasons,
        "status": routing["status"],
        "decision": routing["decision"],
        "auto_reason": routing["auto_reason"],
    }


def _alternative_summary(evaluation: dict) -> dict:
    product = evaluation["product"]
    product_result = evaluation["product_result"]
    return {
        "product_id": evaluation["product_id"],
        "product_name": product.get("product_name"),
        "percent": float(product.get("percent") or 0),
        "min_credit_rating": int(product.get("min_credit_rating") or 0),
        "scoring": product_result.get("scoring"),
        "risk_category": evaluation["risk_category"],
        "threshold": evaluation["threshold"],
        "status": evaluation["status"],
        "reasons": evaluation["reasons"],
    }


async def calculate_application_score(
    *,
    inn: str,
    financial: dict,
    product: dict,
    alternative_products: list[dict] | None = None,
    requested_amount: float,
    requested_term_months: int,
    loan_purpose: str | None,
) -> dict:
    """Один раз считает рейтинг и оценивает выбранный + альтернативные продукты.

    Возвращает:
    * `status` — итоговый маршрут заявки: approved | rejected | manual_review | offer_pending;
    * `offers` — альтернативы, которые прошли существующие пороги (для offer_pending);
    * `product_result`/`threshold`/`manual_review_reasons` — результат выбранного продукта.
    """
    dsn = build_dsn()
    api = FNSApi(dsn=dsn)
    internal_api = InternalApi(api=api)
    try:
        financial_scorer = Financial_Risk_Score(api=api, internal_api=internal_api)
        report_year = int(financial["report_year"])
        financial_result = await financial_scorer.calculate(
            inn,
            year=report_year,
            financial=financial,
        )
        rating = int(round(float(financial_result["rating"])))

        chosen = await _evaluate_product(
            product=product,
            rating=rating,
            financial_result=financial_result,
            requested_amount=requested_amount,
            requested_term_months=requested_term_months,
            loan_purpose=loan_purpose,
            api=api,
            internal_api=internal_api,
            financial_scorer=financial_scorer,
        )

        alternatives: list[dict] = []
        for alternative_product in alternative_products or []:
            if int(alternative_product["product_id"]) == int(product["product_id"]):
                continue
            alternatives.append(
                await _evaluate_product(
                    product=alternative_product,
                    rating=rating,
                    financial_result=financial_result,
                    requested_amount=requested_amount,
                    requested_term_months=requested_term_months,
                    loan_purpose=loan_purpose,
                    api=api,
                    internal_api=internal_api,
                    financial_scorer=financial_scorer,
                )
            )

        # Выбранный продукт одобрен — альтернативы не нужны.
        if chosen["status"] == "approved":
            final_status = "approved"
            decision = "approved"
            manual_reasons: list[str] = []
            auto_reason = chosen["auto_reason"]
            offers: list[dict] = []
        else:
            has_hard_manual_reason = any(
                reason == REASON_PURPOSE_OTHER
                or reason == REASON_BOUNDARY
                or reason.startswith("Ошибка расчёта")
                for reason in chosen["reasons"]
            )
            # Существующие ручные правила (цель «Другое», пограничная зона,
            # ошибка) имеют приоритет над подбором альтернатив.
            if has_hard_manual_reason:
                final_status = "manual_review"
                decision = None
                manual_reasons = chosen["reasons"]
                auto_reason = None
                offers = []
            else:
                # Рейтинг ниже минимума выбранного продукта (или выбранный
                # продукт не прошёл существующий порог): ищем альтернативы
                # среди продуктов, которые были доступны клиенту изначально.
                offers = [
                    item for item in alternatives if item["status"] == "approved"
                ]
                if offers:
                    final_status = "offer_pending"
                    decision = None
                    manual_reasons = []
                    auto_reason = REASON_ALTERNATIVES_FOUND
                else:
                    final_status = "rejected"
                    decision = "rejected"
                    manual_reasons = []
                    auto_reason = REASON_NO_ALTERNATIVES

        return {
            "rating": rating,
            "risk_category": chosen["risk_category"],
            "report_year": report_year,
            "financial_result": financial_result,
            "product_result": chosen["product_result"],
            "threshold": chosen["threshold"],
            "status": final_status,
            "decision": decision,
            "manual_review_reasons": manual_reasons,
            "auto_reason": auto_reason,
            "chosen_status": chosen["status"],
            "chosen_reasons": chosen["reasons"],
            "alternatives": [_alternative_summary(item) for item in alternatives],
            "offers": offers,
        }
    finally:
        await api.close()
