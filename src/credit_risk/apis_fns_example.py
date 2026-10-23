"""
Данный файл создан чтобы эмулировать работу с ФНС API.
Доступ к данной API у банка присутствует, но в рамках нашего проекта доступа к нему мы не имеем.

Эмулятор повторяет реальные методы ФНС:
- Поиск наличия ИНН в базе ФНС
- Получение карточки компании по ИНН
- Получение финансовой отчётности компании по ИНН и году
- Получение списка компаний по определённому параметру

Всё остальное (процентили, каталог кредитных продуктов, заявки) — во внутреннем API банка
(internal_api.py). Конфигурация — в config.py.
"""

import os
from pathlib import Path

import asyncpg

if __package__:  # запуск как пакета: python -m src.credit_risk.apis_fns_example
    from .config import COMPANIES_FILTER_COLUMNS, COMPANY_COLUMNS, FINANCIAL_COLUMNS
else:  # запуск из каталога src/credit_risk
    from config import COMPANIES_FILTER_COLUMNS, COMPANY_COLUMNS, FINANCIAL_COLUMNS


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
        columns = ", ".join(COMPANY_COLUMNS)
        conn = await self.get_connection()
        row = await conn.fetchrow(
            f"SELECT {columns} FROM companies WHERE inn = $1",
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
        columns = ", ".join(FINANCIAL_COLUMNS)
        conn = await self.get_connection()
        row = await conn.fetchrow(
            f"""
            SELECT {columns}
            FROM financial_statements
            WHERE inn = $1 AND report_year = $2
            """,
            str(inn),
            int(report_year),
        )
        return dict(row) if row is not None else None

    async def get_companies_by_parameter(
        self,
        parameter: str,
        value=None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Получает информацию о всех компаниях, у которых parameter = value.

        :param parameter: колонка companies (industry, company_status, region_code,
                          is_simplified_tax, dissolution_flag)
        :param value: значение параметра; None — искать компании с NULL в колонке
        :param limit: ограничение количества строк (None — все)
        :return: список словарей с карточками компаний
        """
        if parameter not in COMPANIES_FILTER_COLUMNS:
            raise ValueError(
                f"Недопустимый параметр: {parameter}. "
                f"Допустимые: {', '.join(COMPANIES_FILTER_COLUMNS)}"
            )
        if limit is not None and int(limit) <= 0:
            raise ValueError("limit должен быть положительным числом или None")

        columns = ", ".join(COMPANY_COLUMNS)
        conn = await self.get_connection()
        if value is None:
            query = f"SELECT {columns} FROM companies WHERE {parameter} IS NULL ORDER BY inn"
            params: tuple = ()
        else:
            query = f"SELECT {columns} FROM companies WHERE {parameter} = $1 ORDER BY inn"
            params = (value,)
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]