#!/usr/bin/env python3
"""
Единый скрипт развёртывания БД «alfa-hakaton» для тестирования/демо.

Выполняет всё одним запуском и не падает при повторном прогоне:

    1.  Создаёт БД alfa-hakaton, если её ещё нет (CREATE DATABASE IF NOT EXISTS).
    2.  Сбрасывает предыдущую схему (таблицы удаляются с CASCADE) —
        повторный запуск не ломается.
    3.  Раскатывает схему из DB/DB.sql (таблицы, ключи, индексы).
    4.  Записывает 4 демо-компании (3 ИП + 1 ООО) и их финансовую отчётность —
        это те же компании, что загружаются полным датасетом.
    5.  Записывает 11 кредитных продуктов в loan_catalog.
    6.  Создаёт логины login1..login4, а также client/client и bank/bank.

Полный датасет (127 828 строк) загружается отдельно через
load_companies.py и load_financial.py — этот скрипт создаёт только
демо-набор для быстрого старта.

Использование:
    python DB/setup_db.py

Зависимости: psycopg2-binary, запущенный PostgreSQL на localhost:5432.
"""

# ─────────────────────────── Выбор Python ───────────────────────────
# Автоматически использует Python из venv проекта (backend/.venv),
# если системный Python не имеет psycopg2 — так скрипт работает «из коробки».
try:
    import psycopg2  # noqa: F401
except ImportError:
    import os
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "backend", ".venv", "bin", "python")
    if os.path.exists(venv_python):
        import sys
        sys.path.insert(0, os.path.dirname(venv_python))
        # Поднимаем текущий процесс на python из venv
        os.execv(venv_python, [venv_python] + sys.argv)
    else:
        sys.exit(
            "❌ psycopg2 не найден в системном Python, а venv не обнаружен: "
            "запустите с активным окружением: "
            "source backend/.venv/bin/activate && python DB/setup_db.py"
        )

import hashlib
import os
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import execute_values

# ─────────────────────────── Конфигурация ───────────────────────────
DB_NAME = os.environ.get("PGDATABASE", "alfa-hakaton")
DB_USER = os.environ.get("PGUSER", "postgres")
DB_PASSWORD = os.environ.get("PGPASSWORD", "postgres")
DB_HOST = os.environ.get("PGHOST", "localhost")
DB_PORT = int(os.environ.get("PGPORT", "5432"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(BASE_DIR, "DB.sql")

# Таблицы в порядке, обратном зависимостям (для безопасного удаления).
ALL_TABLES = (
    "applications_history",
    "applications_decisions",
    "application_offers",
    "login",
    "applications_checks",
    "loan_applications",
    "loan_catalog",
    "financial_statements",
    "companies",
)

# ─────────────────── Кредитные продукты (loan_catalog) ────────────────
# Порядок колонок: product_name, description, business_category,
#   min_amount, max_amount, min_term_months, max_term_months,
#   percent, loan_purpose, is_active, business_age, min_credit_rating
LOAN_PRODUCTS = [
    # ── ИП: малый бизнес / запуск ──
    ("Микрокредит для запуска ИП",
     "Кредит на старт деятельности ИП: закупка оборудования, аренда, маркетинг",
     "ip",
     100_000, 500_000, 6, 24,
     18.5, "launch_and_start",
     True, 0, 400),

    ("Развитие микробизнеса ИП",
     "Кредит на развитие действующего ИП: расширение ассортимента, найм сотрудников",
     "ip",
     300_000, 2_000_000, 12, 48,
     16.9, "development_and_scaling",
     True, 6, 500),

    # ── ИП: оборотные средства ──
    ("Оборотный кредит для ИП",
     "Пополнение оборотных средств: закупка товаров, покрытие кассовых разрывов",
     "ip",
     200_000, 5_000_000, 6, 36,
     17.5, "operational_activity",
     True, 12, 450),

    ("Сезонный кредит для ИП",
     "Краткосрочный кредит на сезонный подъём продаж",
     "ip",
     100_000, 3_000_000, 3, 12,
     19.0, "operational_activity",
     True, 6, 400),

    # ── ООО: инвестиции и масштабирование ──
    ("Инвестиционный кредит для ООО",
     "Долгосрочный кредит на покупку оборудования, строительство, модернизацию",
     "ooo",
     1_000_000, 50_000_000, 24, 84,
     15.9, "development_and_scaling",
     True, 24, 550),

    ("Кредит на закупку оборудования ООО",
     "Лизинг/кредит на приобретение станков, техники, транспорта",
     "ooo",
     500_000, 30_000_000, 12, 60,
     16.2, "development_and_scaling",
     True, 12, 500),

    # ── Обе категории: универсальные ──
    ("Универсальный бизнес-кредит",
     "Гибкий кредит на любые нужды бизнеса: развитие, оборотка, рефинансирование",
     "both",
     300_000, 10_000_000, 12, 60,
     17.0, "operational_activity",
     True, 6, 450),

    ("Кредит под залог недвижимости",
     "Крупные суммы под залог коммерческой/жилой недвижимости, низкая ставка",
     "both",
     2_000_000, 100_000_000, 36, 180,
     13.5, "strategic_goals",
     True, 12, 600),

    ("Рефинансирование долгов бизнеса",
     "Объединение существующих кредитов в один с пониженной ставкой",
     "both",
     500_000, 20_000_000, 12, 84,
     16.0, "strategic_goals",
     True, 12, 500),

    # ── Специализированные ──
    ("Кредит на защиту бизнеса (страхование рисков)",
     "Кредит на оплату страховых полисов, создание резервного фонда",
     "both",
     200_000, 5_000_000, 12, 36,
     18.0, "business_protection",
     True, 12, 450),

    ("Экспресс-кредит до 500 тыс.",
     "Быстрое решение за 15 минут, минимальные документы, для ИП и ООО",
     "both",
     50_000, 500_000, 3, 18,
     22.0, "operational_activity",
     True, 0, 350),
]

# ─────────────────── Демо-компании (для демонстрации/тестов) ──────────
# 4 компании, отобранные из CSV для демонстрации работы скоринга:
#   3 максимально разношерстных ИП (слабая / средняя / сильная)
#   и 1 небольшое ООО.
#
# ИНН указаны в финальном нормализованном виде (10 цифр):
#   ИП  3662277634 | выручка 0       | убыток -2 143   | очень слабая (P2)
#   ИП  7722344211 | выручка 93 738  | прибыль 2 534   | средняя (P50)
#   ИП  3906398393 | выручка 591 253 | прибыль 123 091 | сильная (P75)
#   ООО 0721013581 | выручка 26 786  | убыток -220     | небольшое ООО
#
# (ИНН: в CSV у ИП 10 цифр, у ООО 9 -> дописываем 1 ноль слева = 10 цифр).

# (inn, company_name, registration_date, company_status, industry,
#  region_code, is_simplified_tax, dissolution_flag)
DEMO_COMPANIES = [
    ("3662277634", "Company3662277634", "2019-07-26", "IP", "G", "3600", "0", "0"),
    ("7722344211", "Company7722344211", "2015-10-28", "IP", "G", "7700", "0", "0"),
    ("3906398393", "Company3906398393", "2021-01-22", "IP", "F", "3900", "0", "0"),
    ("0721013581", "Company721013581", "2005-12-22", "OOO", "L", "700", "0", "0"),
]

# (inn, report_year, revenue, net_profit, assets, current_assets,
#  total_equity, longterm_debt, shortterm_debt, shortterm_liab,
#  retained_earnings, profit_from_sales, before_tax,
#  cash_equivalents, interest_payable, balance_operating)
DEMO_FINANCIAL = [
    ("3662277634", 2025, 0, -2143, 9866, 3576, 2153, 0, 5982, 7676, 2143, -65, -3728, 14, 0, -800),
    ("7722344211", 2025, 93738, 2534, 51226, 50383, 17176, 0, 5, 34050, 17166, 3740, 3377, 0, 0, 1),
    ("3906398393", 2025, 591253, 123091, 2864571, 2036383, 410248, 444912, 85805, 2009411, 410238, 291736, 163473, 56, -137121, 890828),
    ("0721013581", 2025, 26786, -220, 45500, 7646, 13045, 24000, 4135, 8455, 13025, 2772, 228, 1311, 0, 1946),
]

# ─────────────────── Логины для демо (login/catalog) ──────────────────
# Для каждого логина пароль = логин, профиль 'business',
# привязка к демо-компаниям: login1..login3 -> ИП, login4 -> ООО.
#
# (username, password, profile_type, company_inn)
LOGINS = [
    #  ИП: слабая / средняя / сильная
    ("login1", "login1", "business", "3662277634"),
    ("login2", "login2", "business", "7722344211"),
    ("login3", "login3", "business", "3906398393"),
    #  ООО
    ("login4", "login4", "business", "0721013581"),
    #  Демо-аккаунты для входа на сайте
    ("client", "client", "business", "3662277634"),
    ("bank", "bank", "employee", None),
]

# Пароли храним в БД в том же виде, что и в рабочей БД — SHA-256.
LOGINS = [
    (username, hashlib.sha256(password.encode("utf-8")).hexdigest(), profile_type, company_inn)
    for username, password, profile_type, company_inn in LOGINS
]

# ─────────────────────────── Логика скрипта ───────────────────────────
def connect(dbname, autocommit=False):
    conn = psycopg2.connect(
        dbname=dbname,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    if autocommit:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def create_database():
    """Создаёт БД, если она не существует (идемпотентно)."""
    print(f"▶ 1. Проверка/создание БД '{DB_NAME}' ...")
    conn = connect("postgres", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone():
                print(f"   БД '{DB_NAME}' уже существует — пропуск CREATE DATABASE")
            else:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
                print(f"   ✅ БД '{DB_NAME}' создана")
    finally:
        conn.close()


def reset_and_run_schema():
    """Удаляет старые таблицы и накатывает схему из DB.sql (в одной транзакции)."""
    print(f"▶ 2. Сброс старой схемы и раскатка {os.path.basename(SQL_FILE)} ...")

    if not os.path.exists(SQL_FILE):
        sys.exit(f"❌ Файл схемы не найден: {SQL_FILE}")

    with open(SQL_FILE, encoding="utf-8") as f:
        schema_sql = f.read()

    conn = connect(DB_NAME, autocommit=True)
    try:
        with conn.cursor() as cur:
            for table in ALL_TABLES:
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            print("   Старые таблицы удалены (если были)")
            cur.execute(schema_sql)
            print("   ✅ Схема из DB.sql накатана успешно")
    finally:
        conn.close()


def load_loan_products(conn):
    """Записывает 11 кредитных продуктов в loan_catalog."""
    print("▶ 3. Запись кредитных продуктов (loan_catalog) ...")

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO loan_catalog (
                product_name, description, business_category,
                min_amount, max_amount, min_term_months, max_term_months,
                percent, loan_purpose, is_active, business_age, min_credit_rating
            ) VALUES %s
            ON CONFLICT DO NOTHING
        """, LOAN_PRODUCTS)
        conn.commit()
        print(f"   Кредитные продукты вставлено: {cur.rowcount}")


def load_demo_companies(conn):
    """Записывает 4 демо-компании и их финансовую отчётность."""
    print("▶ 4. Запись демо-компаний (companies + financial_statements) ...")

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO companies (inn, company_name, registration_date, company_status,
                industry, region_code, is_simplified_tax, dissolution_flag)
            VALUES %s
            ON CONFLICT (inn) DO NOTHING
        """, DEMO_COMPANIES)
        companies_ins = cur.rowcount

        execute_values(cur, """
            INSERT INTO financial_statements (
                inn, report_year, revenue, net_profit, assets, current_assets,
                total_equity, longterm_debt, shortterm_debt, shortterm_liab,
                retained_earnings, profit_from_sales, before_tax,
                cash_equivalents, interest_payable, balance_operating
            ) VALUES %s
            ON CONFLICT (inn, report_year) DO NOTHING
        """, DEMO_FINANCIAL)
        fin_ins = cur.rowcount

        conn.commit()
        print(f"   Компании вставлено: {companies_ins}, фин. записей: {fin_ins}")


def load_logins(conn):
    """Создаёт логины login1..login4, привязанные к демо-компаниям."""
    print("▶ 5. Создание логинов (login1..login4) ...")

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO login (username, password, profile_type, company_inn)
            VALUES %s
            ON CONFLICT (username) DO NOTHING
        """, LOGINS)
        conn.commit()
        print(f"   Логины вставлено: {cur.rowcount}")


def verify():
    """Контрольная проверка итогового состояния БД."""
    print("▶ 6. Проверка результата ...")
    conn = connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM companies) AS companies,
                    (SELECT COUNT(*) FROM financial_statements) AS financials,
                    (SELECT COUNT(*) FROM loan_catalog) AS products,
                    (SELECT COUNT(*) FROM login) AS logins
            """)
            companies, financials, products, logins = cur.fetchone()
            print(f"   Компании:      {companies}")
            print(f"   Фин. записей:  {financials}")
            print(f"   Кред. продукты:{products}")
            print(f"   Логины:        {logins}")
    finally:
        conn.close()
    print("   ✅ Проверка пройдена")


def main():
    print("=" * 66)
    print("  Развёртывание БД 'alfa-hakaton' (демо: 4 компании + логины + продукты)")
    print("=" * 66)

    try:
        create_database()
        reset_and_run_schema()

        conn = connect(DB_NAME)
        try:
            load_loan_products(conn)
            load_demo_companies(conn)
            load_logins(conn)
        finally:
            conn.close()

        verify()
    except psycopg2.Error as exc:
        print(f"\n❌ Ошибка PostgreSQL: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Неожиданная ошибка: {exc}")
        sys.exit(1)

    print("=" * 66)
    print("  🎉 Готово! БД создана, схема накатана, демо-набор загружен.")
    print("  Логины: login1/login1 .. login4/login4, client/client, bank/bank")
    print("=" * 66)


if __name__ == "__main__":
    main()
