"""Интеграционные тесты вызова существующего скоринга на реальной БД.

Тесты используют демо-набор из ``src/db/setup_db.py`` (4 компании, 11 продуктов,
логины ``client/bank/login1..login4``).

Запуск: RUN_DB_TESTS=1 python -m unittest discover -s tests -t .
Без переменной RUN_DB_TESTS тесты пропускаются (БД не требуется для CI).
"""

from __future__ import annotations

import asyncio
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

from app.scoring_service import calculate_application_score, decide_application  # noqa: E402

# Демо-компании из src/db/setup_db.py:
#   ИП  3662277634 — слабая, ИП  7722344211 — средняя,
#   ИП  3906398393 — сильная, ООО 0721013581 — небольшое.
DEMO_INNS = ("3662277634", "7722344211", "3906398393", "0721013581")
DEMO_PRODUCTS_TOTAL = 11


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Требуется PostgreSQL и RUN_DB_TESTS=1",
)
def _require_demo_fixtures(testcase: unittest.TestCase) -> None:
    """Проверяет, что в БД загружен демо-набор из src/db/setup_db.py."""
    import psycopg
    from psycopg.rows import dict_row

    from app.config import get_settings

    try:
        conn = psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)
    except (psycopg.Error, OSError) as exc:
        raise unittest.SkipTest(f"PostgreSQL недоступен: {exc}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM companies WHERE inn = ANY(%s)",
                (list(DEMO_INNS),),
            )
            companies = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM loan_catalog WHERE is_active = TRUE")
            products = int(cur.fetchone()["c"])
    finally:
        conn.close()
    if companies < len(DEMO_INNS) or products < DEMO_PRODUCTS_TOTAL:
        raise unittest.SkipTest(
            "Демо-набор src/db/setup_db.py отсутствует в текущей БД "
            f"(найдено компаний: {companies}, продуктов: {products}); "
            "запустите python src/db/setup_db.py"
        )


class RealDatabaseScoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _require_demo_fixtures(cls)

    def _load(self, inn: str, product_id: int):
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings

        try:
            conn = psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)
        except (psycopg.Error, OSError) as exc:
            self.skipTest(f"PostgreSQL недоступен: {exc}")

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM financial_statements WHERE inn = %s "
                    "ORDER BY report_year DESC LIMIT 1",
                    (inn,),
                )
                financial = cur.fetchone()
                cur.execute("SELECT * FROM loan_catalog WHERE product_id = %s", (product_id,))
                product = cur.fetchone()
        conn.close()
        return financial, product

    def test_company_7722344211_product_2_is_approved(self):
        financial, product = self._load("7722344211", 2)
        self.assertIsNotNone(financial)
        self.assertIsNotNone(product)
        result = asyncio.run(
            calculate_application_score(
                inn="7722344211",
                financial=financial,
                product=product,
                requested_amount=500_000.0,
                requested_term_months=12,
                loan_purpose="development_and_scaling",
            )
        )
        self.assertEqual(result["rating"], 738)
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["product_result"]["risk_category"], "A+")
        self.assertEqual(result["product_result"]["scoring"], 55.83)

    def test_no_alternative_products_gives_final_rejection(self):
        """Рейтинг ниже минимума продукта и альтернатив нет → rejected."""
        financial, product = self._load("3662277634", 2)
        self.assertIsNotNone(financial)
        self.assertIsNotNone(product)
        result = asyncio.run(
            calculate_application_score(
                inn="3662277634",
                financial=financial,
                product=product,
                alternative_products=[],
                requested_amount=500_000.0,
                requested_term_months=12,
                loan_purpose="development_and_scaling",
            )
        )
        self.assertEqual(result["rating"], 456)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["offers"], [])
        self.assertIn("альтернатив", result["auto_reason"])

    def test_boundary_scoring_routes_to_manual_review(self):
        """Скоринг точно в пороговой зоне продукта → ручная проверка."""
        financial, product = self._load("3906398393", 9)
        self.assertIsNotNone(financial)
        self.assertIsNotNone(product)
        result = asyncio.run(
            calculate_application_score(
                inn="3906398393",
                financial=financial,
                product=product,
                requested_amount=1_000_000.0,
                requested_term_months=24,
                loan_purpose="strategic_goals",
            )
        )
        self.assertEqual(result["rating"], 683)
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])
        self.assertTrue(result["product_result"]["employee_rout"])
        self.assertEqual(result["product_result"]["scoring"], 51.03)
        self.assertEqual(
            decide_application(
                rating=683,
                product=product,
                product_result=result["product_result"],
                threshold={
                    "threshold": 50.0,
                    "margin": 1.5,
                    "low": 48.5,
                    "high": 51.5,
                },
                loan_purpose="strategic_goals",
            )["status"],
            "manual_review",
        )


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Требуется PostgreSQL и RUN_DB_TESTS=1",
)
class ApplicationPersistenceTest(unittest.TestCase):
    """Проверяет сохранение заявки/рейтинга и маршрутизацию на реальной БД."""

    @classmethod
    def setUpClass(cls):
        _require_demo_fixtures(cls)
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings
        from app.schemas import AuthUser

        with psycopg.connect(
            **get_settings().connect_kwargs, row_factory=dict_row
        ) as conn, conn.cursor() as cur:
            users: dict[str, AuthUser] = {}
            for inn in DEMO_INNS:
                cur.execute(
                    "SELECT username FROM login WHERE company_inn = %s ORDER BY username LIMIT 1",
                    (inn,),
                )
                row = cur.fetchone()
                if row is None:
                    raise unittest.SkipTest(f"Нет бизнес-логина для ИНН {inn}")
                users[inn] = AuthUser(
                    username=row["username"], profile_type="business", company_inn=inn
                )
            cur.execute(
                "SELECT username FROM login WHERE profile_type = 'employee' "
                "ORDER BY username LIMIT 1"
            )
            employee_row = cur.fetchone()
            if employee_row is None:
                raise unittest.SkipTest("Нет логина сотрудника банка")
            users["bank"] = AuthUser(
                username=employee_row["username"], profile_type="employee", company_inn=None
            )
        cls.users = users
        cls.created: list[str] = []

    @classmethod
    def tearDownClass(cls):
        import psycopg

        from app.config import get_settings

        if not cls.created:
            return
        try:
            with psycopg.connect(**get_settings().connect_kwargs) as conn, conn.cursor() as cur:
                for application_id in cls.created:
                    for table in (
                        "applications_history",
                        "applications_checks",
                        "applications_decisions",
                        "application_offers",
                        "loan_applications",
                    ):
                        cur.execute(
                            f"DELETE FROM {table} WHERE application_id = %s",
                            (application_id,),
                        )
                conn.commit()
        except psycopg.Error:
            pass

    @staticmethod
    def _connect():
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings

        return psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)

    def _create(self, inn: str, product_id: int, amount, term: int, purpose: str, **kwargs) -> dict:
        from app.loan_applications import create_loan_application
        from app.schemas import LoanApplicationCreate

        detail = create_loan_application(
            LoanApplicationCreate(
                inn=inn,
                product_id=product_id,
                requested_amount=amount,
                requested_term_months=term,
                loan_purpose=purpose,
                business_age_months=kwargs.pop("business_age_months", 36),
                **kwargs,
            ),
            current_user=self.users[inn],
        )
        self.created.append(detail.application_id)
        return detail

    def test_auto_approved_application_is_persisted(self):
        from fastapi import HTTPException

        from app.loan_applications import decide_loan_application
        from app.schemas import LoanApplicationDecisionRequest

        detail = self._create("7722344211", 2, 500_000, 12, "development_and_scaling")
        self.assertEqual(detail.status, "approved")
        self.assertIsNotNone(detail.scoring)
        self.assertEqual(detail.scoring.rating, 738)
        self.assertEqual(detail.decision.decision_source, "automatic")
        self.assertEqual(detail.decision.decision_type, "approved")
        self.assertEqual(detail.decision.approved_amount, 500_000.0)
        self.assertEqual(detail.decision.approved_term_months, 12)

        with self.assertRaises(HTTPException) as ctx:
            decide_loan_application(
                detail.application_id,
                LoanApplicationDecisionRequest(decision="rejected", reason="Отказ по политике"),
                current_user=self.users["bank"],
            )
        self.assertEqual(ctx.exception.status_code, 409)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT application_status FROM loan_applications WHERE application_id = %s",
                    (detail.application_id,),
                )
                self.assertEqual(cur.fetchone()["application_status"], "approved")
                cur.execute(
                    "SELECT count(*) AS c FROM applications_checks WHERE application_id = %s",
                    (detail.application_id,),
                )
                self.assertEqual(cur.fetchone()["c"], 1)
                cur.execute(
                    "SELECT count(*) AS c FROM applications_decisions WHERE application_id = %s",
                    (detail.application_id,),
                )
                self.assertEqual(cur.fetchone()["c"], 1)

    def test_manual_review_by_other_purpose_has_no_auto_decision(self):
        detail = self._create("7722344211", 2, 500_000, 12, "other")
        self.assertEqual(detail.status, "manual_review")
        self.assertIsNone(detail.decision)
        self.assertTrue(detail.scoring.employee_rout)
        self.assertIn("Другое", detail.scoring.routing_reason or "")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM applications_decisions "
                    "WHERE application_id = %s",
                    (detail.application_id,),
                )
                self.assertEqual(cur.fetchone()["c"], 0)

    def test_manual_review_by_boundary_scoring(self):
        detail = self._create("3906398393", 9, 1_000_000, 24, "strategic_goals")
        self.assertEqual(detail.status, "manual_review")
        self.assertIsNone(detail.decision)
        self.assertTrue(detail.scoring.employee_rout)
        self.assertEqual(detail.scoring.rating, 683)
        self.assertIn("пограничной зоне", detail.scoring.routing_reason or "")

    def test_scoring_error_does_not_create_fake_decision(self):
        from unittest.mock import patch

        async def broken_scoring(**kwargs):
            raise RuntimeError("Тестовая ошибка алгоритма")

        detail = None
        try:
            with patch(
                "app.loan_applications.calculate_application_score",
                new=broken_scoring,
            ):
                detail = self._create(
                    "7722344211", 2, 500_000, 12, "development_and_scaling"
                )
            self.assertEqual(detail.status, "manual_review")
            self.assertIsNone(detail.decision)
            self.assertTrue(detail.scoring.has_error)
            self.assertIsNone(detail.scoring.rating)
            self.assertIn("Ошибка расчёта скоринга", detail.scoring.routing_reason or "")

            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT application_status FROM loan_applications WHERE application_id = %s",
                        (detail.application_id,),
                    )
                    self.assertEqual(cur.fetchone()["application_status"], "manual_review")
                    cur.execute(
                        "SELECT count(*) AS c FROM applications_decisions "
                        "WHERE application_id = %s",
                        (detail.application_id,),
                    )
                    self.assertEqual(cur.fetchone()["c"], 0)
        finally:
            if detail is not None:
                pass

    def test_alternative_offers_created_and_selected(self):
        from app.loan_applications import select_application_offer

        # Выбранный продукт 5 не проходит порог, но подходит альтернатива 6.
        detail = self._create("0721013581", 5, 1_000_000, 24, "development_and_scaling")
        self.assertEqual(detail.status, "offer_pending")
        self.assertIsNone(detail.decision)
        self.assertGreaterEqual(len(detail.offers), 1)
        self.assertTrue(all(offer.status == "offered" for offer in detail.offers))

        selected = select_application_offer(
            detail.application_id,
            detail.offers[0].offer_id,
            current_user=self.users["0721013581"],
        )
        self.assertEqual(selected.status, "approved")
        self.assertEqual(selected.decision.decision_type, "approved")
        self.assertEqual(selected.decision.decision_source, "automatic")
        self.assertEqual(selected.decision.approved_amount, 1_000_000.0)
        self.assertEqual(selected.decision.approved_term_months, 24)
        statuses = {offer.offer_id: offer.status for offer in selected.offers}
        self.assertEqual(statuses[detail.offers[0].offer_id], "selected")
        if len(detail.offers) > 1:
            self.assertTrue(any(status == "superseded" for status in statuses.values()))

    def test_declining_all_offers_leads_to_final_rejection(self):
        from app.loan_applications import decline_application_offer

        detail = self._create("0721013581", 5, 1_000_000, 24, "development_and_scaling")
        self.assertEqual(detail.status, "offer_pending")
        current = detail
        for offer in list(detail.offers):
            current = decline_application_offer(
                detail.application_id,
                offer.offer_id,
                current_user=self.users["0721013581"],
            )
        self.assertEqual(current.status, "rejected")
        self.assertEqual(current.decision.decision_type, "rejected")
        self.assertEqual(current.decision.decision_source, "automatic")
        self.assertTrue(all(offer.status == "declined" for offer in current.offers))

    def test_business_cannot_create_application_for_foreign_company(self):
        from fastapi import HTTPException

        from app.loan_applications import create_loan_application
        from app.schemas import LoanApplicationCreate

        with self.assertRaises(HTTPException) as ctx:
            create_loan_application(
                LoanApplicationCreate(
                    inn="3662277634",
                    product_id=2,
                    requested_amount=500_000,
                    requested_term_months=12,
                    loan_purpose="development_and_scaling",
                ),
                current_user=self.users["7722344211"],
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
