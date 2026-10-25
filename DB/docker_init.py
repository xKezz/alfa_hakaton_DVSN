#!/usr/bin/env python3
"""Инициализация демо-БД для docker compose.

Запускается один раз перед backend. Если в БД уже есть логины и продукты,
ничего не делает; иначе создаёт схему и демо-данные через setup_db.py.
"""

from __future__ import annotations

import os
import subprocess
import sys

import psycopg2

DB_NAME = os.environ.get("PGDATABASE", "alfa-hakaton")
DB_USER = os.environ.get("PGUSER", "postgres")
DB_PASSWORD = os.environ.get("PGPASSWORD", "postgres")
DB_HOST = os.environ.get("PGHOST", "db")
DB_PORT = int(os.environ.get("PGPORT", "5432"))


def already_seeded() -> bool:
    try:
        with psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT to_regclass('public.login'), "
                    "       to_regclass('public.loan_catalog')"
                )
                login_table, catalog_table = cur.fetchone()
                if login_table is None or catalog_table is None:
                    return False
                cur.execute("SELECT count(*) FROM login")
                logins = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM loan_catalog")
                products = cur.fetchone()[0]
                return logins > 0 and products > 0
    except psycopg2.Error:
        return False


def main() -> None:
    if already_seeded():
        print("DB already seeded — skip.")
        return
    setup_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_db.py")
    print("Seeding demo database...")
    subprocess.run([sys.executable, setup_script], check=True)


if __name__ == "__main__":
    main()
