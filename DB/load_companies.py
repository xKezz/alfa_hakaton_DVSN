import csv
import psycopg2
from psycopg2 import extras

CSV_PATH = '/home/xkezz/projects/alfa_hakaton_DVSN/DB/df_companies_clean.csv'
DB = "alfa-hakaton"
USER = "postgres"
PASSWORD = "postgres"
HOST = "localhost"
PORT = 5432

BATCH_SIZE = 5000

conn = psycopg2.connect(dbname=DB, user=USER, password=PASSWORD, host=HOST, port=PORT)
cur = conn.cursor()

valid_count = 0
skipped = 0

batch = []
with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        inn = row['inn'].strip()
        if len(inn) not in (10, 12):
            skipped += 1
            continue

        batch.append((
            inn,
            row['company_name'],
            row['registration_date'] or None,
            row['company_status'] or None,
            row['is_simplified_tax'] in ('1', 't', 'true', 'True'),
            row['industry'] or None,
            row['region_code'] or None,
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
