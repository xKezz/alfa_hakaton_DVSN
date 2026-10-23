"""Внутренний API скоринга: выборки из БД для существующего алгоритма.

Модуль отсутствовал в исходной поставке `src/credit_risk`, хотя
`credit_risk_score.py` и `credit_category.py` импортируют из него `InternalApi`.
Этот адаптер не содержит формул: он только отдаёт алгоритму данные из
PostgreSQL (каталог продуктов, последний отчётный год, процентили P5/P95)
через уже существующий `FNSApi` из `apis_fns_example.py`.
"""

from __future__ import annotations

if __package__:  # python -m src.credit_risk...
    from . import config
    from .apis_fns_example import FNSApi
else:  # запуск из каталога src/credit_risk
    import config
    from apis_fns_example import FNSApi


_LOAN_CATALOG_SELECT = """
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
           min_credit_rating,
           min_credit_rating AS min_credit_ratings
      FROM loan_catalog
"""


class InternalApi:
    """Тонкий слой БД-запросов, совместно используемый со скорингом."""

    def __init__(self, api: FNSApi | None = None, dsn: str | None = None):
        self.api = api or FNSApi(dsn=dsn)

    async def __aenter__(self) -> "InternalApi":
        await self.api.get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self.api.close()

    async def get_connection(self):
        return await self.api.get_connection()

    async def get_latest_report_year(self, inn: str) -> int | None:
        """Последний год, за который у компании есть финансовая отчётность."""
        conn = await self.get_connection()
        return await conn.fetchval(
            "SELECT max(report_year) FROM financial_statements WHERE inn = $1",
            str(inn),
        )

    async def get_scoring_percentiles(self, inn: str, report_year: int) -> dict:
        """Пороги P5/P95 для блоков скоринга (делегируется в FNSApi)."""
        return await self.api.get_scoring_percentiles(inn, report_year)

    async def get_loan_catalog(self, sorted_param: list[str] | None = None) -> list[dict]:
        """Каталог продуктов в формате, ожидаемом алгоритмом.

        Ключ `min_credit_ratings` — историческое имя из `config.py`;
        в текущей БД колонка называется `min_credit_rating`.
        """
        allowed = set(config.LOAN_CATALOG_SORT_COLUMNS)
        order_columns = [
            item for item in (sorted_param or []) if item in allowed
        ]
        if not order_columns:
            order_columns = ["product_id"]
        order_by = ", ".join(f"{column} ASC" for column in order_columns)

        conn = await self.get_connection()
        rows = await conn.fetch(f"{_LOAN_CATALOG_SELECT} ORDER BY {order_by}")
        return [dict(row) for row in rows]
