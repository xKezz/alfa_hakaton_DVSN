import csv
import psycopg2
from psycopg2 import extras

FIN_CSV = '/home/xkezz/projects/alfa_hakaton_DVSN/DB/df_financial_clean.csv'
DB = "alfa-hakaton"
USER = "postgres"
PASSWORD = "postgres"
HOST = "localhost"
PORT = 5432

BATCH_SIZE = 5000

conn = psycopg2.connect(dbname=DB, user=USER, password=PASSWORD, host=HOST, port=PORT)
cur = conn.cursor()

# Get set of valid inn from companies
cur.execute("SELECT inn FROM companies")
valid_inns = {row[0] for row in cur.fetchall()}
print(f"Valid inn count: {len(valid_inns)}")

inserted = 0
skipped = 0
batch = []

with open(FIN_CSV, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        inn = row['inn'].strip()
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
            to_num(row['shortterm_dept']),   # CSV typo
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