"""Внутреннее API банка: доступ к внутренней БД (процентили, каталог, заявки).

FNSApi (apis_fns_example.py) эмулирует только методы ФНС. Всё, что относится
к внутренним данным банка (аналитика по датасету, кредитные продукты, заявки),
находится здесь. Все SQL-запросы выполняются в этом файле.

Заглушки на будущее:
- get_credit_rating — расчёт кредитного рейтинга клиента;
- get_loan_offers — подбор кредитных предложений для клиента.
"""

import uuid

if __package__:  # запуск как пакета: python -m src.credit_risk.internal_api
    from .apis_fns_example import FNSApi
    from .config import (
        APPLICATION_STATUSES,
        DATASET_SCOPE,
        INDUSTRY_SCOPE,
        LOAN_APPLICATION_COLUMNS,
        LOAN_CATALOG_COLUMNS,
        LOAN_CATALOG_SORT_COLUMNS,
        LOAN_PURPOSES,
        PERCENTILE_EXPRESSIONS,
        PERCENTILE_HIGH,
        PERCENTILE_LOW,
    )
else:  # запуск из каталога src/credit_risk
    from apis_fns_example import FNSApi
    from config import (
        APPLICATION_STATUSES,
        DATASET_SCOPE,
        INDUSTRY_SCOPE,
        LOAN_APPLICATION_COLUMNS,
        LOAN_CATALOG_COLUMNS,
        LOAN_CATALOG_SORT_COLUMNS,
        LOAN_PURPOSES,
        PERCENTILE_EXPRESSIONS,
        PERCENTILE_HIGH,
        PERCENTILE_LOW,
    )


class InternalApi:
    """Внутреннее API банка (работает через соединение FNSApi-эмулятора)."""

    def __init__(self, api: FNSApi | None = None, dsn: str | None = None):
        """
        :param api: готовый FNSApi (общее соединение); если не передан — создаётся
        :param dsn: DSN PostgreSQL (используется, если api не передан)
        """
        self.api = api or FNSApi(dsn=dsn)
        self._scoring_percentiles_cache: dict = {}

    # ----------------------------- подключение -----------------------------

    async def get_connection(self):
        """Соединение с БД (переиспользует соединение FNSApi)."""
        return await self.api.get_connection()

    async def close(self) -> None:
        """Закрывает соединение."""
        await self.api.close()

    async def __aenter__(self) -> "InternalApi":
        await self.get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ----------------------------- процентили -----------------------------

    async def procentil_from_client_category(
        self,
        inn: str,
        report_year: int,
        low_: float = PERCENTILE_LOW,
        high_: float = PERCENTILE_HIGH,
        category: str | None = None,
        scope: str = INDUSTRY_SCOPE,
        positive_only: bool = False,
    ) -> dict | None:
        """
        Считает процентили показателя в БД за отчётный год.

        :param inn: ИНН клиента (по нему определяется отрасль для scope="industry")
        :param report_year: отчётный год
        :param low_: нижний процентиль (по умолчанию 0.05)
        :param high_: верхний процентиль (по умолчанию 0.95)
        :param category: показатель — колонка financial_statements или "net_margin"
        :param scope: "industry" — только отрасль клиента, "dataset" — весь датасет
        :param positive_only: учитывать только значения > 0 (нужно для ln)
        :return: словарь с count/low_percentile/high_percentile или None, если данных нет
        """
        if category is None:
            raise ValueError("Не указан столбец для вычисления процентилей")
        if category not in PERCENTILE_EXPRESSIONS:
            raise ValueError(f"Недопустимый столбец: {category}")
        if scope not in (INDUSTRY_SCOPE, DATASET_SCOPE):
            raise ValueError(f"Недопустимый scope: {scope} (ожидается industry или dataset)")
        if not 0 <= low_ <= high_ <= 1:
            raise ValueError("Процентили должны удовлетворять условию 0 <= low_ <= high_ <= 1")

        expression = PERCENTILE_EXPRESSIONS[category]
        # У R знаменатель — выручка, поэтому отрицательные/нулевые не берём.
        extra_filter = " AND fs.revenue > 0" if category == "net_margin" else ""
        if positive_only:
            extra_filter += f" AND ({expression}) > 0"

        conn = await self.get_connection()
        if scope == INDUSTRY_SCOPE:
            row = await conn.fetchrow(
                f"""
                SELECT count(*) AS count,
                       percentile_cont($3) WITHIN GROUP (ORDER BY {expression}) AS low_percentile,
                       percentile_cont($4) WITHIN GROUP (ORDER BY {expression}) AS high_percentile
                FROM financial_statements AS fs
                JOIN companies AS c ON c.inn = fs.inn
                WHERE fs.report_year = $2
                  AND c.industry = (SELECT industry FROM companies WHERE inn = $1)
                  AND ({expression}) IS NOT NULL{extra_filter}
                """,
                str(inn),
                int(report_year),
                float(low_),
                float(high_),
            )
        else:
            row = await conn.fetchrow(
                f"""
                SELECT count(*) AS count,
                       percentile_cont($2) WITHIN GROUP (ORDER BY {expression}) AS low_percentile,
                       percentile_cont($3) WITHIN GROUP (ORDER BY {expression}) AS high_percentile
                FROM financial_statements AS fs
                WHERE fs.report_year = $1
                  AND ({expression}) IS NOT NULL{extra_filter}
                """,
                int(report_year),
                float(low_),
                float(high_),
            )

        count = int(row["count"] or 0)
        if count == 0:
            return None
        low_value = row["low_percentile"]
        high_value = row["high_percentile"]
        return {
            "category": category,
            "scope": scope,
            "report_year": int(report_year),
            "count": count,
            "low_percentile": None if low_value is None else float(low_value),
            "high_percentile": None if high_value is None else float(high_value),
        }

    @staticmethod
    def _percentile_pair(result: dict | None) -> tuple[float, float] | None:
        """Превращает результат процентилей в пару (P5, P95) или None."""
        if result is None:
            return None
        low = result["low_percentile"]
        high = result["high_percentile"]
        if low is None or high is None or low >= high:
            return None
        return low, high

    async def get_scoring_percentiles(self, inn: str, report_year: int) -> dict:
        """
        Возвращает пороги P5/P95 для скоринга:
        * industry — выручка и R = net_profit/revenue по отрасли клиента;
        * dataset — выручка, активы и капитал по всему датасету.

        Результат кешируется в рамках экземпляра API.
        """
        cache_key = (str(inn), int(report_year))
        cached = self._scoring_percentiles_cache.get(cache_key)
        if cached is not None:
            return cached

        industry_revenue = await self.procentil_from_client_category(
            inn, report_year, category="revenue", positive_only=True
        )
        industry_margin = await self.procentil_from_client_category(
            inn, report_year, category="net_margin"
        )
        dataset_revenue = await self.procentil_from_client_category(
            inn, report_year, category="revenue", scope=DATASET_SCOPE, positive_only=True
        )
        dataset_assets = await self.procentil_from_client_category(
            inn, report_year, category="assets", scope=DATASET_SCOPE, positive_only=True
        )
        dataset_equity = await self.procentil_from_client_category(
            inn, report_year, category="total_equity", scope=DATASET_SCOPE, positive_only=True
        )

        result = {
            "industry": {
                "revenue": self._percentile_pair(industry_revenue),
                "net_margin": self._percentile_pair(industry_margin),
            },
            "dataset": {
                "revenue": self._percentile_pair(dataset_revenue),
                "assets": self._percentile_pair(dataset_assets),
                "total_equity": self._percentile_pair(dataset_equity),
            },
        }
        self._scoring_percentiles_cache[cache_key] = result
        return result

    # ----------------------------- каталог продуктов -----------------------------

    async def get_loan_catalog(self, sorted_param: list[str] | None = None) -> list[dict]:
        """
        Возвращает список всех активных кредитных предложений.

        :param sorted_param: список колонок для ORDER BY (из LOAN_CATALOG_SORT_COLUMNS),
                             по умолчанию — product_id
        """
        if sorted_param is not None:
            if not sorted_param:
                raise ValueError("Список параметров сортировки пуст")
            invalid = [param for param in sorted_param if param not in LOAN_CATALOG_SORT_COLUMNS]
            if invalid:
                raise ValueError(
                    f"Недопустимые параметры сортировки: {invalid}. "
                    f"Допустимые: {', '.join(LOAN_CATALOG_SORT_COLUMNS)}"
                )
            order_by = ", ".join(sorted_param)
        else:
            order_by = "product_id"

        columns = ", ".join(LOAN_CATALOG_COLUMNS)
        conn = await self.get_connection()
        rows = await conn.fetch(
            f"SELECT {columns} FROM loan_catalog WHERE is_active = TRUE ORDER BY {order_by}"
        )
        return [dict(row) for row in rows]

    # ----------------------------- заявки -----------------------------

    async def create_loan_application(
        self,
        inn: str,
        product_id: int,
        requested_amount: float,
        requested_term_months: int,
        loan_purpose: str | None = None,
        application_status: str = "submitted",
    ) -> dict:
        """
        Создаёт заявку в loan_applications и возвращает её данные.

        :param inn: ИНН заявителя
        :param product_id: выбранный продукт
        :param requested_amount: запрашиваемая сумма
        :param requested_term_months: запрашиваемый срок, месяцев
        :param loan_purpose: цель кредита (код из LOAN_PURPOSES или None)
        :param application_status: статус заявки (из APPLICATION_STATUSES)
        :return: словарь с полями заявки, включая application_id
        """
        if float(requested_amount) <= 0:
            raise ValueError("requested_amount должен быть больше 0")
        if int(requested_term_months) <= 0:
            raise ValueError("requested_term_months должен быть больше 0")
        if application_status not in APPLICATION_STATUSES:
            raise ValueError(
                f"Недопустимый статус заявки: {application_status}. "
                f"Допустимые: {', '.join(APPLICATION_STATUSES)}"
            )
        if loan_purpose is not None and loan_purpose not in LOAN_PURPOSES:
            raise ValueError(
                f"Недопустимая цель кредита: {loan_purpose}. "
                f"Допустимые: {', '.join(LOAN_PURPOSES)}"
            )

        application_id = str(uuid.uuid4())
        columns = ", ".join(LOAN_APPLICATION_COLUMNS)
        placeholders = ", ".join(f"${index + 1}" for index in range(len(LOAN_APPLICATION_COLUMNS)))
        conn = await self.get_connection()
        row = await conn.fetchrow(
            f"""
            INSERT INTO loan_applications ({columns})
            VALUES ({placeholders})
            RETURNING {columns}, created_at
            """,
            application_id,
            str(inn),
            int(product_id),
            float(requested_amount),
            int(requested_term_months),
            loan_purpose,
            application_status,
        )
        return dict(row)

    # ----------------------------- заглушки -----------------------------

    async def get_credit_rating(self, inn: str, report_year: int, financial: dict | None = None) -> dict:
        """
        ЗАГЛУШКА: расчёт кредитного рейтинга клиента.
        Позже будет вызывать Credit_Risk_Score.calculate().
        """
        raise NotImplementedError("InternalApi.get_credit_rating пока не реализован (заглушка)")

    async def get_loan_offers(self, user_param: dict) -> list[dict]:
        """
        ЗАГЛУШКА: подбор кредитных предложений для клиента.
        Позже будет вызывать Credit_category.
        """
        raise NotImplementedError("InternalApi.get_loan_offers пока не реализован (заглушка)")
