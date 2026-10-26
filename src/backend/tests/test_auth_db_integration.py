"""Интеграционные тесты авторизации: plaintext-пароли, хеши, роли."""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Корень репозитория — ближайший родитель backend/, содержащий src/credit_risk.
PROJECT_ROOT = next(
    (parent for parent in BACKEND_DIR.parents if (parent / "src" / "credit_risk").is_dir()),
    BACKEND_DIR.parent,
)
for path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi import HTTPException  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import login  # noqa: E402
from app.schemas import LoginRequest  # noqa: E402


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Требуется PostgreSQL и RUN_DB_TESTS=1",
)
class AuthDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        try:
            conn = psycopg.connect(**get_settings().connect_kwargs)
        except (psycopg.Error, OSError) as exc:
            raise unittest.SkipTest(f"PostgreSQL недоступен: {exc}") from exc
        conn.close()

    def test_plaintext_password_is_accepted_and_hashed(self):
        import psycopg

        settings = get_settings()
        username = "_test_plain_user"
        password = "plain-secret"
        with psycopg.connect(**settings.connect_kwargs) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO login (username, password, profile_type, company_inn) "
                "VALUES (%s, %s, 'employee', NULL) "
                "ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password",
                (username, password),
            )
            conn.commit()
        try:
            user = login(LoginRequest(username=username, password=password))
            self.assertEqual(user.profile_type, "employee")
            with psycopg.connect(**settings.connect_kwargs) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT password FROM login WHERE username = %s", (username,)
                )
                stored = cur.fetchone()[0]
            self.assertEqual(stored, hashlib.sha256(password.encode()).hexdigest())
        finally:
            with psycopg.connect(**settings.connect_kwargs) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM login WHERE username = %s", (username,))
                conn.commit()

    def test_wrong_password_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username="client", password="definitely-wrong"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_demo_accounts_if_present(self):
        import psycopg

        settings = get_settings()
        with psycopg.connect(**settings.connect_kwargs) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT username FROM login WHERE username IN "
                "('client','bank','login1') ORDER BY username"
            )
            usernames = {row[0] for row in cur.fetchall()}
        for username in ("client", "bank", "login1"):
            if username not in usernames:
                continue
            user = login(LoginRequest(username=username, password=username))
            self.assertEqual(user.username, username)


if __name__ == "__main__":
    unittest.main()
