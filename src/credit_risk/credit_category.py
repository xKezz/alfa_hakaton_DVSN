"""Подбор кредитного продукта и формирование заявки (loan_applications).

Класс Credit_category:
1. проверяет пользователя в ФНС (существует ли ИНН) и берёт его карточку;
2. берёт кредитный score (0..1000) и возраст бизнеса из user_param/API;
3. читает каталог продуктов из внутренней БД и фильтрует его по условиям:
   тип бизнеса, возраст, минимальный рейтинг, сумма, срок, цель кредита;
4. если выбранный пользователем продукт есть в подходящих — апрувит его,
   иначе возвращает список всех подходящих предложений;
5. создаёт запись в loan_applications.

Все запросы к БД выполняются через API (apis_fns_example.py, internal_api.py),
константы и справочники — в config.py.
"""

import asyncio
import datetime
import sys

if __package__:  # запуск как пакета: python -m src.credit_risk.credit_category
    from . import config
    from .apis_fns_example import FNSApi
    from .internal_api import InternalApi
else:  # запуск из каталога src/credit_risk
    import config
    from apis_fns_example import FNSApi
    from internal_api import InternalApi

try:  # корректная печать кириллицы в консоли Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # например, при перехвате stdout в тестах
    pass

# Перевод значения в рейтинг (буквенная шкала -> баллы)
rating_to_score = config.RATING_TO_SCORE


def rating_to_score_fast(rating: int) -> str:
    """Быстрая конвертация баллы в рейтинг через словарь."""
    return min(rating_to_score.keys(), key=lambda key: abs(rating_to_score[key] - int(rating)))


async def loan_catalog(sorted_param: list[str] | None = None) -> list[dict]:
    """Получаем список всех доступных предложений, отсортированных по параметрам."""
    async with InternalApi() as api:
        return await api.get_loan_catalog(sorted_param)


class Credit_category:
    """Подбор продуктов и оформление заявки на кредит."""

    def __init__(
        self,
        user_param: dict,
        product_id: int,
        api: FNSApi | None = None,
        internal_api: InternalApi | None = None,
    ):
        """
        :param user_param: данные пользователя (см. пример в начале файла)
        :param product_id: продукт, который выбрал пользователь
        :param api: готовый FNSApi (для тестов); по умолчанию создаётся
        :param internal_api: готовое InternalApi; по умолчанию использует self.api
        """
        self.user_param = user_param or {}
        self.product_id = int(product_id)
        self.api = api or FNSApi()
        self.internal_api = internal_api or InternalApi(api=self.api)

        self.company_info: dict | None = None
        self.catalog_loans: list[dict] = []
        self.matching_products: list[dict] = []
        self.credit_score: float | None = None
        self.business_age: float | None = None
        self.application: dict | None = None

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
        Дочитывает данные пользователя: карточку компании из ФНС, кредитный балл
        и возраст бизнеса. Балл берётся из user_param['credit_score'], а если его
        нет — запрашивается у внутреннего API (пока заглушка).
        """
        inn = self.user_param.get("inn")
        if not inn:
            raise ValueError("В user_param не указан ИНН (inn)")

        company = await self.api.get_company_info(inn)
        if company is None:
            raise ValueError("Такого пользователя не существует")
        self.company_info = company

        credit_score = self.user_param.get("credit_score")
        if credit_score is None:
            report_year = self.user_param.get("report_year")
            if report_year is None:
                raise ValueError(
                    "Не указан credit_score. Пока API расчёта рейтинга — заглушка, "
                    "передайте балл (0..1000) в user_param['credit_score']"
                )
            rating = await self.internal_api.get_credit_rating(inn, int(report_year))
            credit_score = rating["rating"]
        self.credit_score = float(credit_score)
        if not 0 <= self.credit_score <= 1000:
            raise ValueError("credit_score должен быть в диапазоне 0..1000")

        age = self.user_param.get("age")
        if age is not None:
            self.business_age = float(age)
        else:
            registered = self._as_date(company.get("registration_date"))
            if registered is not None:
                reference_year = self.user_param.get("report_year")
                end_date = (
                    datetime.date(int(reference_year), 12, 31)
                    if reference_year is not None
                    else datetime.date.today()
                )
                self.business_age = (end_date - registered).days / 365.25

        return self.user_param

    def _search_params(self) -> dict:
        """Разбирает credit_search_param: сумма, срок, цель."""
        search = self.user_param.get("credit_search_param") or {}
        amount = search.get("amount")
        term = search.get("term")
        if amount is None or term is None:
            raise ValueError("В credit_search_param нужны amount и term")
        if float(amount) <= 0:
            raise ValueError("amount должен быть больше 0")
        if int(term) <= 0:
            raise ValueError("term должен быть больше 0")

        purpose = search.get("descript")
        if purpose is not None and purpose not in config.LOAN_PURPOSES:
            raise ValueError(
                f"Недопустимая цель кредита: {purpose}. "
                f"Допустимые: {', '.join(config.LOAN_PURPOSES)}"
            )
        return {"amount": float(amount), "term": int(term), "purpose": purpose}

    # ----------------------------- подбор продуктов -----------------------------

    async def check_product_requirements(self) -> list[dict]:
        """
        Проверяет обязательные условия и оставляет продукты, подходящие пользователю.
        Возвращает отсортированный список подходящих продуктов.
        """
        if self.company_info is None or self.credit_score is None:
            await self.read_user_data()
        if not self.catalog_loans:
            self.catalog_loans = await self.internal_api.get_loan_catalog()

        search = self._search_params()
        # company_status в БД: 'IP'/'OOO'; в каталоге: 'ip'/'ooo'/'both'
        company_status = str(self.company_info.get("company_status") or "").lower()

        matching: list[dict] = []
        for product in self.catalog_loans:
            if not product.get("is_active"):
                continue
            if str(product.get("business_category") or "").lower() not in (company_status, "both"):
                continue
            if self.business_age is not None and float(product.get("business_age") or 0) > self.business_age:
                continue
            if float(product.get("min_credit_ratings") or 0) > self.credit_score:
                continue
            if not (float(product.get("min_amount") or 0) <= search["amount"] <= float(product.get("max_amount") or 0)):
                continue
            if not (int(product.get("min_term_months") or 0) <= search["term"] <= int(product.get("max_term_months") or 0)):
                continue
            # loan_purpose = NULL у продукта означает «любая цель»
            if search["purpose"] is not None and product.get("loan_purpose") not in (None, search["purpose"]):
                continue
            matching.append(dict(product))

        self.matching_products = matching
        return self.rank_loan_products()

    def calculate_product_score(self, product: dict) -> float:
        """Оценка продукта для клиента: пока по ставке (меньше — лучше)."""
        return float(product.get("percent") or 0.0)

    def rank_loan_products(self) -> list[dict]:
        """Сортировка подходящих предложений (сначала с лучшей ставкой)."""
        return sorted(self.matching_products, key=self.calculate_product_score)

    # ----------------------------- заявка -----------------------------

    async def process_application(self) -> dict:
        """
        Формирует заявку на выбранный продукт.

        Если выбранный продукт подошёл — статус 'approved' и продукт апрувится.
        Если нет — статус 'offer_pending', а в ответе список подходящих продуктов.
        """
        matching = await self.check_product_requirements()
        search = self._search_params()
        catalog_ids = {int(product["product_id"]) for product in self.catalog_loans}
        if self.product_id not in catalog_ids:
            raise ValueError(f"Продукт {self.product_id} не найден в каталоге")
        approved_product = next(
            (product for product in matching if int(product.get("product_id")) == self.product_id),
            None,
        )
        status = (
            config.APPLICATION_STATUS_APPROVED
            if approved_product is not None
            else config.APPLICATION_STATUS_OFFER_PENDING
        )

        self.application = await self.internal_api.create_loan_application(
            inn=self.user_param["inn"],
            product_id=self.product_id,
            requested_amount=search["amount"],
            requested_term_months=search["term"],
            loan_purpose=search["purpose"],
            application_status=status,
        )

        return {
            "application_id": self.application["application_id"],
            "status": status,
            "user_type": self.company_info.get("company_status"),
            "credit_score": self.credit_score,
            "rating": rating_to_score_fast(int(round(self.credit_score))),
            "requested_amount": search["amount"],
            "requested_term_months": search["term"],
            "loan_purpose": search["purpose"],
            "approved_product": approved_product,
            "offers": [] if approved_product is not None else matching,
            "application": self.application,
        }

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


if __name__ == "__main__":
    print(asyncio.run(loan_catalog()))
