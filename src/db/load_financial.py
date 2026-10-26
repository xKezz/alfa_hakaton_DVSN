import csv
import os

import psycopg2
from psycopg2 import extras

# CSV лежит рядом со скриптом (src/db/df_financial.csv).
FIN_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'df_financial.csv')
DB = os.environ.get("PGDATABASE", "alfa-hakaton")
USER = os.environ.get("PGUSER", "postgres")
PASSWORD = os.environ.get("PGPASSWORD", "postgres")
HOST = os.environ.get("PGHOST", "localhost")
PORT = int(os.environ.get("PGPORT", "5432"))

BATCH_SIZE = 5000

def normalize_inn_financial(inn_raw: str) -> str:
    """
    Для финансов статуса нет — определяем по длине после int():
    - 9 цифр → ООО (добавляем 1 ноль слева → 10 цифр)
    - 10 цифр → ИП (оставляем как есть)
    """
    s = inn_raw.strip()
    if not s.isdigit():
        return s
    norm = str(int(s))
    if len(norm) == 9:
        return '0' + norm  # ООО: 9 → 10 цифр
    return norm

conn = psycopg2.connect(dbname=DB, user=USER, password=PASSWORD, host=HOST, port=PORT)
cur = conn.cursor()

# Get set of valid inn from companies (already normalized to 10 digits)
cur.execute("SELECT inn FROM companies")
valid_inns = {row[0] for row in cur.fetchall()}
print(f"Valid inn count: {len(valid_inns)}")

inserted = 0
skipped = 0
batch = []

with open(FIN_CSV, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        inn_raw = row['inn'].strip()
        inn = normalize_inn_financial(inn_raw)
        
        if inn not in valid_inns:
            skipped += 1
            continue

        # CSV: shortterm_dept (typo), SQL: shortterm_debt
        year_val = row['year'].strip()
        if not year_val:
            skipped += 1
            continue

        def to_num(s):
            s = s.strip()
            return float(s) if s else None

        batch.append((
            inn,
            int(year_val),
            to_num(row['revenue']),
            to_num(row['net_profit']),
            to_num(row['assets']),
            to_num(row['current_assets']),
            to_num(row['total_equity']),
            to_num(row['longterm_debt']),
            to_num(row['shortterm_dept']),   # CSV typo: shortterm_dept -> shortterm_debt
            to_num(row['shortterm_liab']),
            to_num(row['retained_earnings']),
            to_num(row['profit_from_sales']),
            to_num(row['before_tax']),
            to_num(row['cash_equivalents']),
            to_num(row['interest_payable']),
            to_num(row['balance_operating']),
        ))

        if len(batch) >= BATCH_SIZE:
            extras.execute_batch(cur, """
                INSERT INTO financial_statements (
                    inn, report_year, revenue, net_profit, assets, current_assets,
                    total_equity, longterm_debt, shortterm_debt, shortterm_liab,
                    retained_earnings, profit_from_sales, before_tax,
                    cash_equivalents, interest_payable, balance_operating
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (inn, report_year) DO NOTHING
            """, batch)
            conn.commit()
            inserted += len(batch)
            print(f"  inserted {inserted} rows (skipped {skipped})")
            batch = []

if batch:
    extras.execute_batch(cur, """
        INSERT INTO financial_statements (
            inn, report_year, revenue, net_profit, assets, current_assets,
            total_equity, longterm_debt, shortterm_debt, shortterm_liab,
            retained_earnings, profit_from_sales, before_tax,
            cash_equivalents, interest_payable, balance_operating
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (inn, report_year) DO NOTHING
    """, batch)
    conn.commit()
    inserted += len(batch)
    print(f"  inserted {inserted} rows (skipped {skipped})")

cur.close()
conn.close()
print(f"\nDone: {inserted} inserted, {skipped} skipped")