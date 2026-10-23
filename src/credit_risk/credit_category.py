import asyncio
import sys
from typing import Dict, Any

if __package__:
    from . import config
    from .apis_fns_example import FNSApi
    from .internal_api import InternalApi
else:
    import config
    from apis_fns_example import FNSApi
    from internal_api import InternalApi

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

RATING_TO_SCORE = config.RATING_TO_SCORE

def rating_to_score_fast(rating: int) -> str:
    return min(RATING_TO_SCORE.keys(), key=lambda k: abs(RATING_TO_SCORE[k] - int(rating)))

async def loan_catalog(sorted_param: list[str] | None = None) -> list[dict]:
    async with InternalApi() as api:
        return await api.get_loan_catalog(sorted_param)
    
async def get_mean_prod_params() -> Dict[str, float]:
    data = await loan_catalog()
    if not data:
        raise ValueError("Каталог кредитных продуктов пуст")
    
    n = float(len(data))
    
    return {
        "amount": float(sum(float(i.get("max_amount", 0)) for i in data) / n),
        "term": float(sum((float(i.get("max_term_months", 0)) + float(i.get("min_term_months", 0))) / 2.0 for i in data) / n),
        "age": float(sum(float(i.get("business_age", 0)) for i in data) / n),
        "percent": float(sum(float(i.get("percent", 0)) for i in data) / n),
        "fin_score": float(sum(float(i.get("min_credit_rating", 0)) for i in data) / n),
    }

class CreditScorer:
    def __init__(self, prod_params: Dict[str, float]):
        self.prod = prod_params

    def _calc_avg_payment(self) -> float:
        r = self.prod["percent"] / (12 * 100)
        n = self.prod["term"]
        if r == 0:
            return self.prod["amount"] / n if n > 0 else 0.0
        return self.prod["amount"] * (r * (1 + r)**n) / ((1 + r)**n - 1)

    @staticmethod
    def scaler(c_val: float, p_val: float, cap: float = 1.0, floor: float = 0.0) -> float:
        """Нормализует показатель клиента относительно базового значения продукта."""
        if p_val == 0:
            return cap if c_val >= 0 else floor
        return max(floor, min(cap, c_val / p_val))

    def calculate_score(self, client: Dict[str, Any]) -> float:
        """Вычисление итогового скорингового балла (0 - 100) через нормализацию scaler'ом."""
        pmt = self._calc_avg_payment()
        
        s1 = self.scaler(client["credit_score"], self.prod["fin_score"])
        s2 = self.scaler(client["net_profit"], pmt)
        s3 = self.scaler(client["total_equity"], self.prod["amount"])
        s4 = self.scaler(client["age"], self.prod["age"])

        return round((0.4 * s1 + 0.2 * s2 + 0.25 * s3 + 0.15 * s4) * 100, 2)

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
        ...
        
    def _search_params(self) -> dict:
        """Разбирает credit_search_param: сумма, срок, цель."""
        ...

    # ----------------------------- подбор продуктов -----------------------------

    async def check_product_requirements(self) -> list[dict]:
        """
        Проверяет обязательные условия и оставляет продукты, подходящие пользователю.
        Возвращает отсортированный список подходящих продуктов.
        """
        ...

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
        ...

async def main():
    try:
        params = await get_mean_prod_params()
        scorer = CreditScorer(params)
        
        client = {
            "credit_score": 750,
            "net_profit": 150000,
            "total_equity": 5000000,
            "age": 5
        }
        
        score = scorer.calculate_score(client)
        print(f"Итоговый скоринг: {score}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())