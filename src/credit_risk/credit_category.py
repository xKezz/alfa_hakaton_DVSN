"""Подбор кредитных продуктов и скоринг компании относительно продукта.

ВХОД (json):
{
    "inn": "0814131130",                      # ИНН пользователя
    "fin_params": {                            # можно не передавать — досчитаем сами
        "fin_score": 563,                      # 0..1000, Financial_Risk_Score (бывш. credit_score)
        "net_profit": 100000,
        "total_equity": 400000,
        "age": 20.5,
    },
    "credit_rating": 42.5,                     # скоринг относительно базового (среднего) продукта;
                                               # можно не передавать — посчитаем через CreditScorer
    "product_id": 13,                          # продукт, выбранный пользователем
    "credit_search_params": {
        "amount": 2000000,
        "term": 12,
        "purpose": "launch_and_start",
    },
}

ВЫХОД (dict для одного продукта, list[dict] для нескольких):
{
    "product_id": 13,
    "has_error": False,
    "risk_category": "BBB",     # rating_to_score_fast(fin_score)
    "scoring": 62.35,           # скоринг относительно продукта (0..100)
    "scoring_factors": {"fin_score": 0.8, "net_profit": 0.5, "total_equity": 0.3, "age": 1.0},
    "employee_rout": False,     # True, если scoring попал в пороговую зону продукта
}

Записи в таблицы applications пока не выполняются — формируются только значения.
"""

import asyncio
import datetime
import sys

if __package__:  # запуск как пакета: python -m src.credit_risk.credit_category
    from . import config
    from .apis_fns_example import FNSApi
    from .credit_risk_score import Financial_Risk_Score
    from .internal_api import InternalApi
else:  # запуск из каталога src/credit_risk
    import config
    from apis_fns_example import FNSApi
    from credit_risk_score import Financial_Risk_Score
    from internal_api import InternalApi

try:  # корректная печать кириллицы в консоли Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # например, при перехвате stdout в тестах
    pass

RATING_TO_SCORE = config.RATING_TO_SCORE

CLIENT_KEYS = ("fin_score", "net_profit", "total_equity", "age")


def rating_to_score_fast(rating: int) -> str:
    """Быстрая конвертация баллов (0..1000) в буквенный рейтинг."""
    return min(RATING_TO_SCORE.keys(), key=lambda key: abs(RATING_TO_SCORE[key] - int(rating)))


async def loan_catalog(sorted_param: list[str] | None = None) -> list[dict]:
    """Получаем список всех доступных предложений, отсортированных по параметрам."""
    async with InternalApi() as api:
        return await api.get_loan_catalog(sorted_param)


def product_params(product: dict) -> dict:
    """Параметры продукта, которые использует CreditScorer."""
    min_term = float(product.get("min_term_months") or 0)
    max_term = float(product.get("max_term_months") or 0)
    return {
        "amount": float(product.get("max_amount") or 0),
        "term": (min_term + max_term) / 2.0,
        "age": float(product.get("business_age") or 0),
        "percent": float(product.get("percent") or 0),
        "fin_score": float(product.get("min_credit_ratings") or 0),
    }


def mean_product_params(products: list[dict]) -> dict:
    """Средние параметры по всем продуктам каталога («базовый» продукт)."""
    if not products:
        raise ValueError("Каталог кредитных продуктов пуст")
    params = [product_params(item) for item in products]
    count = float(len(params))
    return {key: sum(item[key] for item in params) / count for key in params[0]}


async def get_mean_prod_params(products: list[dict] | None = None) -> dict:
    """Средние параметры каталога; products можно передать, чтобы не читать БД повторно."""
    if products is None:
        products = await loan_catalog()
    return mean_product_params(products)


async def get_prod_params(product_id: int | None = None, products: list[dict] | None = None) -> dict:
    """Параметры продукта по id (None — средние параметры «базового» продукта)."""
    if products is None:
        products = await loan_catalog()
    if product_id is None:
        return mean_product_params(products)
    product = next((item for item in products if int(item.get("product_id")) == int(product_id)), None)
    if product is None:
        raise ValueError(f"Кредитный продукт с id={product_id} не найден")
    return product_params(product)


def product_scoring_threshold(product: dict) -> dict:
    """
    Нижняя граница скоринга продукта и пороговая зона.

    Нижняя граница = min_credit_ratings / 10 (перевод шкалы 0..1000 в 0..100),
    допуск = SCORING_THRESHOLD_PERCENT (3%) от этой границы.
    """
    threshold = float(product.get("min_credit_ratings") or 0) / 10.0
    margin = threshold * config.SCORING_THRESHOLD_PERCENT
    return {
        "threshold": threshold,
        "margin": margin,
        "low": max(0.0, threshold - margin),
        "high": threshold + margin,
    }


class CreditScorer:
    """Скоринг компании относительно параметров конкретного кредитного продукта."""

    def __init__(self, prod: dict):
        self.prod = prod

    def _calc_avg_payment(self) -> float:
        """Средний ежемесячный платёж по продукту (аннуитет)."""
        r = float(self.prod["percent"]) / (12 * 100)
        n = float(self.prod["term"])
        amount = float(self.prod["amount"])
        if n <= 0:
            return 0.0
        if r == 0:
            return amount / n
        return amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    def calculate_score(self, client: dict) -> dict:
        """Скоринг клиента относительно продукта: score 0..100 и факторы."""
        missing = [key for key in CLIENT_KEYS if client.get(key) is None]
        if missing:
            raise ValueError(f"Не хватает данных для скоринга: {', '.join(missing)}")

        pmt = self._calc_avg_payment()
        weights = config.PRODUCT_SCORE_WEIGHTS

        prod_fin_score = float(self.prod["fin_score"])
        s1 = 1.0 if prod_fin_score <= 0 else min(1.0, float(client["fin_score"]) / prod_fin_score)
        s2 = 0.0 if pmt <= 0 else min(1.0, max(0.0, float(client["net_profit"]) / pmt))
        prod_amount = float(self.prod["amount"])
        s3 = 1.0 if prod_amount <= 0 else min(1.0, float(client["total_equity"]) / prod_amount)
        prod_age = float(self.prod["age"])
        s4 = 1.0 if prod_age <= 0 else min(1.0, float(client["age"]) / prod_age)

        factors = {
            "fin_score": s1,
            "net_profit": s2,
            "total_equity": s3,
            "age": s4,
        }
        score = (
            weights["fin_score"] * s1
            + weights["net_profit"] * s2
            + weights["total_equity"] * s3
            + weights["age"] * s4
        ) * config.PRODUCT_SCORE_SCALE
        return {"factors": factors, "score": round(score, 2)}


class Credit_category:
    """Подбор кредитных продуктов и скоринг компании относительно каждого продукта."""

    def __init__(
        self,
        user_param: dict,
        product_id: int | None = None,
        api: FNSApi | None = None,
        internal_api: InternalApi | None = None,
        financial_scorer: Financial_Risk_Score | None = None,
    ):
        """
        :param user_param: входной json пользователя (см. пример в начале файла)
        :param product_id: выбранный продукт (если не передан — берётся из user_param)
        :param api: готовый FNSApi (для тестов); по умолчанию создаётся
        :param internal_api: готовое InternalApi; по умолчанию использует self.api
        :param financial_scorer: готовый Financial_Risk_Score; по умолчанию создаётся
        """
        self.user_param = user_param or {}
        raw_product_id = product_id if product_id is not None else self.user_param.get("product_id")
        if raw_product_id is None:
            raise ValueError("Не указан product_id (ни в аргументе, ни в user_param)")
        self.product_id = int(raw_product_id)

        self.api = api or FNSApi()
        self.internal_api = internal_api or InternalApi(api=self.api)
        self.financial_scorer = financial_scorer or Financial_Risk_Score(
            api=self.api, internal_api=self.internal_api
        )

        self.company_info: dict | None = None
        self.user_type: str | None = None
        self.report_year: int | None = None
        self.fin_params: dict = {}
        self.credit_rating: float | None = None
        self.catalog_loans: list[dict] = []
        self.matching_products: list[dict] = []
        self.scoring_details: dict[int, dict] = {}
        self.errors: list[str] = []

    # ----------------------------- подключение -----------------------------

    async def __aenter__(self) -> "Credit_category":
        await self.api.get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Закрывает соединение с БД."""
        await self.api.close()

    # ----------------------------- данные пользователя -----------------------------

    async def read_user_data(self) -> dict:
        """
        Дочитывает недостающие данные пользователя:
        * карточку компании — из FNS API;
        * fin_params (fin_score/net_profit/total_equity/age) — из Financial_Risk_Score,
          если они не переданы во входном json;
        * credit_rating — скоринг «базового» (среднего) продукта через CreditScorer.
        """
        inn = self.user_param.get("inn")
        if not inn:
            raise ValueError("В user_param не указан ИНН (inn)")

        company = await self.api.get_company_info(inn)
        if company is None:
            raise ValueError("Такого пользователя не существует")
        self.company_info = company
        self.user_type = company.get("company_status")

        if not self.catalog_loans:
            self.catalog_loans = await self.internal_api.get_loan_catalog()

        year = self.user_param.get("report_year")
        provided = dict(self.user_param.get("fin_params") or {})
        if any(provided.get(key) is None for key in CLIENT_KEYS):
            try:
                computed = await self.financial_scorer.calculate(
                    inn,
                    year,
                    financial=self.user_param.get("financial"),
                )
                computed_params = computed.get("fin_params") or {}
                self.report_year = computed.get("report_year")
            except Exception as exc:  # ошибку покажем через has_error в итоговых json
                self.errors.append(f"financial_score: {exc}")
                computed_params = {}
            for key in CLIENT_KEYS:
                if provided.get(key) is None:
                    provided[key] = computed_params.get(key)

        if provided.get("age") is None:
            provided["age"] = self._age_from_company(company)
        self.fin_params = provided
        if self.report_year is None and year is not None:
            self.report_year = int(year)

        if self.user_param.get("credit_rating") is not None:
            self.credit_rating = float(self.user_param["credit_rating"])
        else:
            try:
                base_params = mean_product_params(self.catalog_loans)
                self.credit_rating = CreditScorer(base_params).calculate_score(self._client())["score"]
            except Exception as exc:
                self.errors.append(f"credit_rating: {exc}")

        return self.fin_params

    def _client(self) -> dict:
        """Клиентские параметры для CreditScorer."""
        return {key: self.fin_params.get(key) for key in CLIENT_KEYS}

    def _age_from_company(self, company: dict) -> float | None:
        """Возраст бизнеса по дате регистрации, если age не передан."""
        registered = self._as_date(company.get("registration_date"))
        if registered is None:
            return None
        reference_year = self.user_param.get("report_year")
        end_date = (
            datetime.date(int(reference_year), 12, 31)
            if reference_year is not None
            else datetime.date.today()
        )
        return (end_date - registered).days / 365.25

    def _search_params(self) -> dict:
        """Разбирает credit_search_params: сумма, срок, цель."""
        search = self.user_param.get("credit_search_params") or self.user_param.get("credit_search_param") or {}
        amount = search.get("amount")
        term = search.get("term")
        if amount is None or term is None:
            raise ValueError("В credit_search_params нужны amount и term")
        if float(amount) <= 0:
            raise ValueError("amount должен быть больше 0")
        if int(term) <= 0:
            raise ValueError("term должен быть больше 0")

        purpose = search.get("purpose", search.get("descript"))
        if purpose is not None and purpose not in config.LOAN_PURPOSES:
            raise ValueError(
                f"Недопустимая цель кредита: {purpose}. "
                f"Допустимые: {', '.join(config.LOAN_PURPOSES)}"
            )
        return {"amount": float(amount), "term": int(term), "purpose": purpose}

    # ----------------------------- фильтрация продуктов -----------------------------

    def check_product_requirements(self) -> list[dict]:
        """
        Фильтрует каталог по обязательным условиям: business_category, цель,
        попадание суммы и срока в рамки продукта.
        """
        if self.company_info is None:
            raise RuntimeError("Сначала вызовите read_user_data()")

        search = self._search_params()
        company_status = str(self.user_type or "").lower()  # 'ip'/'ooo'
        matching: list[dict] = []
        for product in self.catalog_loans:
            if not product.get("is_active"):
                continue
            if str(product.get("business_category") or "").lower() not in (company_status, "both"):
                continue
            # loan_purpose = NULL у продукта означает «любая цель»
            if search["purpose"] is not None and product.get("loan_purpose") not in (None, search["purpose"]):
                continue
            min_amount = float(product.get("min_amount") or 0)
            max_amount = float(product.get("max_amount") or 0)
            if not min_amount <= search["amount"] <= max_amount:
                continue
            min_term = int(product.get("min_term_months") or 0)
            max_term = int(product.get("max_term_months") or 0)
            if not min_term <= search["term"] <= max_term:
                continue
            matching.append(dict(product))

        self.matching_products = matching
        return matching

    def calculate_product_score(self, product: dict) -> dict:
        """Скоринг компании относительно продукта (score + факторы)."""
        scorer = CreditScorer(product_params(product))
        scored = scorer.calculate_score(self._client())
        self.scoring_details[int(product["product_id"])] = {
            "threshold": product_scoring_threshold(product),
            "result": scored,
        }
        return scored

    # ----------------------------- итоговые json -----------------------------

    def _build_product_result(self, product: dict) -> dict:
        """Формирует итоговый json по одному продукту."""
        product_id = int(product["product_id"])
        result = {
            "product_id": product_id,
            "has_error": False,
            "risk_category": None,
            "scoring": None,
            "scoring_factors": {},
            "employee_rout": False,
        }
        try:
            fin_score = self.fin_params.get("fin_score")
            if fin_score is None:
                raise ValueError("не рассчитан fin_score")
            result["risk_category"] = rating_to_score_fast(int(round(float(fin_score))))

            scored = self.calculate_product_score(product)
            result["scoring"] = scored["score"]
            result["scoring_factors"] = scored["factors"]

            threshold = self.scoring_details[product_id]["threshold"]
            result["employee_rout"] = threshold["low"] <= scored["score"] <= threshold["high"]
        except Exception as exc:
            self.errors.append(f"product_id={product_id}: {exc}")
            result["has_error"] = True
            result["employee_rout"] = True

        result["has_error"] = result["has_error"] or bool(self.errors)
        return result

    async def process(self) -> dict | list[dict]:
        """
        Полный расчёт: досчитывает данные, фильтрует продукты, скорит их.

        Возвращает один json, если подходящий/выбранный продукт один,
        и список json-ов, если продуктов несколько.
        """
        if not self.catalog_loans:
            self.catalog_loans = await self.internal_api.get_loan_catalog()

        await self.read_user_data()

        catalog_ids = {int(product["product_id"]) for product in self.catalog_loans}
        if self.product_id not in catalog_ids:
            raise ValueError(f"Продукт {self.product_id} не найден в каталоге")

        matching = self.check_product_requirements()
        if not matching:
            return []

        chosen = next(
            (product for product in matching if int(product["product_id"]) == self.product_id),
            None,
        )
        targets = [chosen] if chosen is not None else matching

        results = [self._build_product_result(product) for product in targets]
        return results[0] if len(results) == 1 else results

    async def process_application(self) -> dict | list[dict]:
        """Совместимость со старым именем метода (заявки пока не создаются)."""
        return await self.process()

    @staticmethod
    def _as_date(value) -> datetime.date | None:
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value.strip()[:10])
            except ValueError:
                return None
        return None