"""
Данный файл создан чтобы эмулировать работу с ФНС API.
Доступ к данной API у банка присутствует, но в рамках нашего проекта доступа к нему мы не имеем.

В данном файле реализованы стандартные функции, которые используются в проекте для работы с ФНС API:
- Поиск наличия ИНН в базе ФНС
- Получение информации о компании по ИНН
- Получение финансовой информации о компании по ИНН (для ООО)
- Процентили P5/P95 по показателю: по отрасли клиента или по всему датасету

Все взаимодействия с БД выполняются только в этом файле; credit_risk_score.py БД не трогает.
"""

import os
from pathlib import Path

import asyncpg

# SQL-выражения для процентилей: category -> выражение над financial_statements AS fs.
_PERCENTILE_EXPRESSIONS = {
    "revenue": "fs.revenue",
    "net_profit": "fs.net_profit",
    "assets": "fs.assets",
    "current_assets": "fs.current_assets",
    "total_equity": "fs.total_equity",
    "longterm_debt": "fs.longterm_debt",
    "shortterm_debt": "fs.shortterm_debt",
    "shortterm_liab": "fs.shortterm_liab",
    "retained_earnings": "fs.retained_earnings",
    "profit_from_sales": "fs.profit_from_sales",
    "before_tax": "fs.before_tax",
    "cash_equivalents": "fs.cash_equivalents",
    "interest_payable": "fs.interest_payable",
    "balance_operating": "fs.balance_operating",
    # R = net_profit / revenue — замена роста выручки g в одно-годовом режиме
    "net_margin": "fs.net_profit::numeric / NULLIF(fs.revenue, 0)",
}

_INDUSTRY_SCOPE = "industry"
_DATASET_SCOPE = "dataset"


class FNSApi:
    def __init__(self, dsn: str | None = None):
        """
        :param dsn: строка подключения к PostgreSQL; если не задана, берётся из env
                    DB_CONNECT (как в .env проекта) или DB_DSN
        """
        self._dsn = dsn or os.environ.get("DB_CONNECT") or os.environ.get("DB_DSN")
        if not self._dsn:
            self._dsn = self._load_dotenv_dsn()
        if not self._dsn:
            raise RuntimeError(
                "Не задан DSN базы данных: установите переменную окружения DB_CONNECT "
                "или передайте dsn в FNSApi(dsn=...)"
            )
        self._conn: asyncpg.Connection | None = None
        self._scoring_percentiles_cache: dict = {}

    @staticmethod
    def _load_dotenv_dsn() -> str | None:
        """Пробует подхватить .env из корня проекта (если установлен python-dotenv)."""
        try:
            from dotenv import load_dotenv
        except ImportError:
            return None
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()
        return os.environ.get("DB_CONNECT") or os.environ.get("DB_DSN")

    async def get_connection(self) -> asyncpg.Connection:
        """Ленивое подключение к БД (одно соединение на экземпляр)."""
        if self._conn is None:
            self._conn = await asyncpg.connect(self._dsn)
        return self._conn

    async def close(self) -> None:
        """Закрывает соединение с БД."""
        if self._conn is not None:
            await self._conn.close()
        self._conn = None

    async def __aenter__(self) -> "FNSApi":
        await self.get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def check_inn_exists(self, inn: str) -> bool:
        """
        Проверяет наличие ИНН в базе ФНС.
        :param inn: ИНН компании
        :return: True если ИНН найден, False если не найден
        """
        conn = await self.get_connection()
        return await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM companies WHERE inn = $1)", str(inn)
        )

    async def get_company_info(self, inn: str) -> dict | None:
        """
        Получает информацию о компании по ИНН.
        :param inn: ИНН компании
        :return: Словарь с информацией о компании или None, если ИНН не найден
        """
        conn = await self.get_connection()
        row = await conn.fetchrow(
            """
            SELECT inn, company_name, registration_date, company_status,
                   industry, region_code, is_simplified_tax, dissolution_flag
            FROM companies
            WHERE inn = $1
            """,
            str(inn),
        )
        return dict(row) if row is not None else None

    async def get_financial_info(self, inn: str, report_year: int) -> dict | None:
        """
        Получает финансовую информацию о компании по ИНН (для ООО) за отчётный год.
        :param inn: ИНН компании
        :param report_year: отчётный год
        :return: Словарь с финансовой информацией или None, если записи за год нет
        """
        conn = await self.get_connection()
        row = await conn.fetchrow(
            """
            SELECT financial_id, inn, report_year, revenue, net_profit, assets,
                   current_assets, total_equity, longterm_debt, shortterm_debt,
                   shortterm_liab, retained_earnings, profit_from_sales, before_tax,
                   cash_equivalents, interest_payable, balance_operating
            FROM financial_statements
            WHERE inn = $1 AND report_year = $2
            """,
            str(inn),
            int(report_year),
        )
        return dict(row) if row is not None else None

    async def procentil_from_client_category(
        self,
        inn: str,
        report_year: int,
        low_: float = 0.05,
        high_: float = 0.95,
        category: str | None = None,
        scope: str = _INDUSTRY_SCOPE,
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
        if category not in _PERCENTILE_EXPRESSIONS:
            raise ValueError(f"Недопустимый столбец: {category}")
        if scope not in (_INDUSTRY_SCOPE, _DATASET_SCOPE):
            raise ValueError(f"Недопустимый scope: {scope} (ожидается industry или dataset)")
        if not 0 <= low_ <= high_ <= 1:
            raise ValueError("Процентили должны удовлетворять условию 0 <= low_ <= high_ <= 1")

        expression = _PERCENTILE_EXPRESSIONS[category]
        # У R знаменатель — выручка, поэтому отрицательные/нулевые не берём.
        extra_filter = " AND fs.revenue > 0" if category == "net_margin" else ""
        if positive_only:
            extra_filter += f" AND ({expression}) > 0"

        conn = await self.get_connection()
        if scope == _INDUSTRY_SCOPE:
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
            inn, report_year, category="revenue", scope=_DATASET_SCOPE, positive_only=True
        )
        dataset_assets = await self.procentil_from_client_category(
            inn, report_year, category="assets", scope=_DATASET_SCOPE, positive_only=True
        )
        dataset_equity = await self.procentil_from_client_category(
            inn, report_year, category="total_equity", scope=_DATASET_SCOPE, positive_only=True
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
