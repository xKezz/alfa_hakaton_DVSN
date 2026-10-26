import csv
import os

import psycopg2
from psycopg2 import extras

# CSV лежит рядом со скриптом (src/db/df_companies.csv).
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'df_companies.csv')
DB = os.environ.get("PGDATABASE", "alfa-hakaton")
USER = os.environ.get("PGUSER", "postgres")
PASSWORD = os.environ.get("PGPASSWORD", "postgres")
HOST = os.environ.get("PGHOST", "localhost")
PORT = int(os.environ.get("PGPORT", "5432"))

BATCH_SIZE = 5000

def normalize_inn(inn_raw: str, status: str) -> str:
    """
    Простое правило:
    - 10 цифр после int() → ИП (оставляем 10)
    - 9 цифр после int() → ООО (дописываем 1 ноль слева → 10 цифр)
    """
    s = inn_raw.strip()
    if not s.isdigit():
        return s
    norm = str(int(s))  # убираем все ведущие нули
    if len(norm) == 9:
        # ООО: 9 цифр → добавляем 1 ноль слева = 10 цифр
        return '0' + norm
    # ИП: 10 цифр (или другие случаи) — оставляем как есть
    return norm


def clean_company_name(name: str) -> str:
    """
    Убирает нереалистичный суффикс '.0' в конце названия,
    оставшийся от float-экспорта CSV: 'Company4217066710.0' -> 'Company4217066710'.
    """
    name = (name or '').strip()
    if name.endswith('.0'):
        name = name[:-2]
    return name


conn = psycopg2.connect(dbname=DB, user=USER, password=PASSWORD, host=HOST, port=PORT)
cur = conn.cursor()

valid_count = 0
skipped = 0

batch = []
with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        inn_raw = row['inn'].strip()
        status = (row['company_status'] or '').strip()
        
        inn = normalize_inn(inn_raw, status)
        
        if len(inn) not in (10, 12):
            skipped += 1
            continue

        region_code = row['region_code']
        if region_code and region_code.endswith('.0'):
            region_code = region_code[:-2]

        batch.append((
            inn,
            clean_company_name(row['company_name']),
            row['registration_date'] or None,
            row['company_status'] or None,
            row['is_simplified_tax'] in ('1', 't', 'true', 'True'),
            row['industry'] or None,
            region_code,
            row['dissolution_flag'] in ('1', 't', 'true', 'True'),
        ))

        if len(batch) >= BATCH_SIZE:
            extras.execute_batch(cur, """
                INSERT INTO companies (inn, company_name, registration_date, company_status,
                    is_simplified_tax, industry, region_code, dissolution_flag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (inn) DO NOTHING
            """, batch)
            conn.commit()
            valid_count += len(batch)
            print(f"  inserted {valid_count} rows (skipped {skipped})")
            batch = []

if batch:
    extras.execute_batch(cur, """
        INSERT INTO companies (inn, company_name, registration_date, company_status,
            is_simplified_tax, industry, region_code, dissolution_flag)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (inn) DO NOTHING
    """, batch)
    conn.commit()
    valid_count += len(batch)
    print(f"  inserted {valid_count} rows (skipped {skipped})")

cur.close()
conn.close()
print(f"\nDone: {valid_count} inserted, {skipped} skipped")
