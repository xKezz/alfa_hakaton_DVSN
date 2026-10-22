import asyncio
import datetime
import math
import os
from pathlib import Path

import asyncpg
import pandas as pd
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
COMPANY_CSV_NAME = "df_company.csv"
FINANCIAL_CSV_NAME = "df_financial.csv"
DATABASE = "alpha_hacaton"

COMPANIES_COLUMNS = [
    "inn",
    "company_name",
    "registration_date",
    "company_status",
    "is_simplified_tax",
    "industry",
    "region_code",
    "dissolution_flag",
]

FINANCIAL_COLUMNS = [
    "inn",
    "report_year",
    "revenue",
    "retained_earnings",
    "assets",
    "total_equity",
    "profit_from_sales",
    "before_tax",
    "net_profit",
    "longterm_debt",
    "shortterm_debt",
    "cash_equivalents",
    "interest_payable",
    "current_assets",
    "shortterm_liab",
    "balance_operating",
]


def find_csv(names: tuple[str, ...]) -> Path:
    for name in names:
        path = BASE_DIR / name
        if path.exists():
            return path

    raise SystemExit(
        f"Не найден CSV ({', '.join(names)}) в {BASE_DIR}"
    )


def find_dsn(cli_dsn: str | None = None) -> str:
    if cli_dsn:
        return cli_dsn

    for parent in (BASE_DIR,BASE_DIR.parent,BASE_DIR.parent.parent,):
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            break

    for key in ("DB_CONNECT", "DB_DSN", "DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value.strip().strip("'\"")

    raise SystemExit("DSN не найден: укажи --dsn или переменную""DB_CONNECT/DB_DSN в .env")


def to_str(series: pd.Series) -> pd.Series:
    return (series.astype("string").str.strip().replace("", pd.NA))


def to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series,errors="coerce",).dt.date

def to_bool(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series,errors="coerce",)
    result = numeric.map({1: True,0: False,})
    return result.astype("boolean")


def to_region_code(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series,errors="coerce",)
    valid = numeric.notna() & (numeric % 1 == 0)
    result = pd.Series(pd.NA, index=series.index, dtype="string",)
    result.loc[valid] = (numeric.loc[valid].astype("int64").astype("string"))
    return result


def clean_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (float,)):
        if not math.isfinite(value):
            return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, (str, int, float, datetime.date)):
        return value
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, float) and not math.isfinite(value):
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    return value

def normalize_inn(series: pd.Series) -> pd.Series:
    inn = series.astype("string").str.strip()
    inn = inn.replace("", pd.NA)

    is_nine_digits = inn.str.fullmatch(r"\d{9}", na=False)
    inn.loc[is_nine_digits] = (
        "0" + inn.loc[is_nine_digits]
    )

    return inn

def transform_companies(df: pd.DataFrame) -> pd.DataFrame:
    missing_columns = set(COMPANIES_COLUMNS) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"В CSV отсутствуют обязательные столбцы: "
            f"{sorted(missing_columns)}"
        )

    frame = pd.DataFrame({
        "inn": normalize_inn(df["inn"]),
        "company_name": to_str(df["company_name"]),
        "registration_date": to_date(df["registration_date"]),
        "company_status": to_str(df["company_status"]),
        "is_simplified_tax": to_bool(df["is_simplified_tax"]),
        "industry": to_str(df["industry"]),
        "region_code": to_region_code(df["region_code"]),
        "dissolution_flag": to_bool(df["dissolution_flag"]),
    })

    return frame


def transform_financials(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename_map = {
        "year": "report_year",
        "shortterm_dept": "shortterm_debt",
    }

    df = df.rename(columns=rename_map)
    missing_columns = set(FINANCIAL_COLUMNS) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"В финансовом CSV отсутствуют столбцы: "
            f"{sorted(missing_columns)}"
        )

    df = df[FINANCIAL_COLUMNS].copy()

    df["inn"] = normalize_inn(df["inn"])

    year = pd.to_numeric(
        df["report_year"],
        errors="coerce",
    )

    invalid_year = year.notna() & (year % 1 != 0)

    if invalid_year.any():
        raise ValueError(
            "Обнаружены некорректные значения report_year: "
            f"{df.loc[invalid_year, 'report_year'].head().tolist()}"
        )

    df["report_year"] = year.astype("Int64")

    financial_columns = [
        column
        for column in FINANCIAL_COLUMNS
        if column not in ("inn", "report_year")
    ]

    for column in financial_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).astype("float64")

    df.insert( 0,"financial_id",range(1, len(df) + 1),)
    return df

async def insert_dataframe(
    dsn: str,
    database: str,
    table: str,
    df: pd.DataFrame,
    columns: list[str],
    batch_size: int = 5000,
) -> None:
    """Загружает DataFrame в указанную таблицу PostgreSQL пакетами."""

    if df.empty:
        print(f"[{database}.{table}] Нет данных для загрузки.")
        return

    missing_columns = set(columns) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Для таблицы {table} отсутствуют столбцы: "
            f"{sorted(missing_columns)}"
        )

    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(f"${i}" for i in range(1, len(columns) + 1))

    query = (
        f'INSERT INTO "{table}" ({column_sql}) '
        f"VALUES ({placeholders})"
    )

    conn = await asyncpg.connect(dsn=dsn,database=database,)

    try:
        async with conn.transaction():
            total = len(df)

            for start in range(0, total, batch_size):
                batch_df = df.iloc[start:start + batch_size]

                records = [
                    tuple(clean_value(value) for value in row)
                    for row in batch_df[columns].itertuples(
                        index=False,
                        name=None,
                    )
                ]

                await conn.executemany(query, records)

                print(
                    f"[{database}.{table}] "
                    f"Загружено {min(start + len(records), total)} "
                    f"из {total} записей"
                )

        print(f"[{database}.{table}] Загрузка завершена.")

    finally:
        await conn.close()


async def load_data_to_postgres() -> None:
    """Обрабатывает CSV и загружает данные в две базы PostgreSQL."""

    dsn = find_dsn()

    # 1. Загружаем и трансформируем компании
    company_path = find_csv((COMPANY_CSV_NAME,))
    raw_companies = pd.read_csv(company_path, dtype={"inn": "string"})
    companies_df = transform_companies(raw_companies)
    
    print(f"[INFO] Загружено компаний из CSV: {len(companies_df)}")
    print(f"[INFO] Примеры ИНН компаний: {companies_df['inn'].head(10).tolist()}")

    # 2. Загружаем и трансформируем финансовые отчеты
    financial_path = find_csv((FINANCIAL_CSV_NAME,))
    raw_financials = pd.read_csv(financial_path, dtype={"inn": "string"})
    financial_df = transform_financials(raw_financials)
    
    print(f"[INFO] Загружено финансовых отчетов из CSV: {len(financial_df)}")
    
    # 3. ФИЛЬТРАЦИЯ: оставляем только те отчеты, где компания существует
    valid_inns = set(companies_df['inn'].dropna())
    missing_inns = set(financial_df['inn'].dropna()) - valid_inns
    
    if missing_inns:
        print(f"[WARNING] Найдено {len(missing_inns)} ИНН в financial, которых нет в companies")
        print(f"[WARNING] Примеры отсутствующих ИНН: {list(missing_inns)[:10]}")
        
        # Фильтруем financial_df, оставляя только существующие компании
        financial_df = financial_df[financial_df['inn'].isin(valid_inns)]
        print(f"[INFO] После фильтрации осталось отчетов: {len(financial_df)}")

    # 4. Загружаем данные
    await insert_dataframe(
        dsn=dsn,
        database=DATABASE,
        table="companies",
        df=companies_df,
        columns=COMPANIES_COLUMNS,
    )

    await insert_dataframe(
        dsn=dsn,
        database=DATABASE,
        table="financial_statements",
        df=financial_df,
        columns=["financial_id"] + FINANCIAL_COLUMNS,
    )

if __name__ == "__main__":
    asyncio.run(load_data_to_postgres())