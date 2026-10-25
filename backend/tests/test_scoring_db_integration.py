"""Интеграционный тест вызова существующего скоринга на реальной БД.

Запуск: RUN_DB_TESTS=1 python -m unittest discover -s backend/tests -t backend
Без переменной RUN_DB_TESTS тест пропускается (БД не требуется для CI).
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.scoring_service import calculate_application_score, decide_application  # noqa: E402


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Требуется PostgreSQL и RUN_DB_TESTS=1",
)
def _require_legacy_fixtures(testcase: unittest.TestCase) -> None:
    """Старые демо-ИНН могли исчезнуть после перезаливки БД — тогда skip."""
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
                "SELECT count(*) AS c FROM companies WHERE inn IN "
                "('4217064416','3257029840')"
            )
            companies = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM loan_catalog WHERE product_id IN (1,2,4)")
            products = int(cur.fetchone()["c"])
    finally:
        conn.close()
    if companies < 2 or products < 3:
        raise unittest.SkipTest(
            "Демо-данные 4217064416/3257029840 отсутствуют в текущей БД "
            "(БД перезалита); интеграционный тест старого демо-набора пропущен"
        )


class RealDatabaseScoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _require_legacy_fixtures(cls)

    def test_company_4217064416_product_2(self):
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings

        settings = get_settings()
        try:
            conn = psycopg.connect(**settings.connect_kwargs, row_factory=dict_row)
        except (psycopg.Error, OSError) as exc:
            self.skipTest(f"PostgreSQL недоступен: {exc}")

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM financial_statements WHERE inn = %s "
                    "ORDER BY report_year DESC LIMIT 1",
                    ("4217064416",),
                )
                financial = cur.fetchone()
                cur.execute(
                    "SELECT * FROM loan_catalog WHERE product_id = 2"
                )
                product = cur.fetchone()
        conn.close()

        self.assertIsNotNone(financial)
        self.assertIsNotNone(product)
        result = asyncio.run(
            calculate_application_score(
                inn="4217064416",
                financial=financial,
                product=product,
                requested_amount=2_000_000.0,
                requested_term_months=12,
                loan_purpose="working_capital",
            )
        )
        self.assertEqual(result["rating"], 746)
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["product_result"]["risk_category"], "A+")

    def test_no_alternative_products_gives_final_rejection(self):
        """Рейтинг ниже минимума выбранного продукта и альтернатив нет → rejected."""
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings

        conn = psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM financial_statements WHERE inn = %s "
                    "ORDER BY report_year DESC LIMIT 1",
                    ("3257029840",),
                )
                financial = cur.fetchone()
                cur.execute("SELECT * FROM loan_catalog WHERE product_id = 4")
                product = cur.fetchone()
        finally:
            conn.close()

        result = asyncio.run(
            calculate_application_score(
                inn="3257029840",
                financial=financial,
                product=product,
                alternative_products=[],
                requested_amount=2_000_000.0,
                requested_term_months=12,
                loan_purpose="business_expansion",
            )
        )
        self.assertEqual(result["rating"], 568)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["offers"], [])
        self.assertIn("альтернатив", result["auto_reason"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "Требуется PostgreSQL и RUN_DB_TESTS=1",
)
class ApplicationPersistenceTest(unittest.TestCase):
    """Проверяет сохранение заявки/рейтинга и маршрутизацию на реальной БД."""

    @classmethod
    def setUpClass(cls):
        _require_legacy_fixtures(cls)

    @staticmethod
    def _connect():
        import psycopg
        from psycopg.rows import dict_row

        from app.config import get_settings

        return psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)

    @staticmethod
    def _cleanup(application_id: str) -> None:
        import psycopg

        from app.config import get_settings

        if not application_id:
            return
        try:
            with psycopg.connect(**get_settings().connect_kwargs) as conn:
                with conn.cursor() as cur:
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

    def test_auto_approved_application_is_persisted(self):
        from app.loan_applications import create_loan_application
        from app.schemas import LoanApplicationCreate

        detail = None
        try:
            detail = create_loan_application(
                LoanApplicationCreate(
                    inn="4217064416",
                    product_id=2,
                    requested_amount=2_000_000,
                    requested_term_months=12,
                    loan_purpose="working_capital",
                )
            )
            self.assertEqual(detail.status, "approved")
            self.assertIsNotNone(detail.scoring)
            self.assertEqual(detail.scoring.rating, 746)
            self.assertEqual(detail.decision.decision_source, "automatic")
            self.assertEqual(detail.decision.decision_type, "approved")

            from fastapi import HTTPException

            from app.loan_applications import decide_loan_application
            from app.schemas import LoanApplicationDecisionRequest

            with self.assertRaises(HTTPException) as ctx:
                decide_loan_application(
                    detail.application_id,
                    LoanApplicationDecisionRequest(
                        decision="rejected", decided_by="bank"
                    ),
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
        finally:
            if detail is not None:
                self._cleanup(detail.application_id)

    def test_manual_review_by_other_purpose_has_no_auto_decision(self):
        from app.loan_applications import create_loan_application
        from app.schemas import LoanApplicationCreate

        detail = None
        try:
            detail = create_loan_application(
                LoanApplicationCreate(
                    inn="4217064416",
                    product_id=1,
                    requested_amount=2_000_000,
                    requested_term_months=12,
                    loan_purpose="other",
                )
            )
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
        finally:
            if detail is not None:
                self._cleanup(detail.application_id)

    def test_scoring_error_does_not_create_fake_decision(self):
        from unittest.mock import patch

        from app.loan_applications import create_loan_application
        from app.schemas import LoanApplicationCreate

        async def broken_scoring(**kwargs):
            raise RuntimeError("Тестовая ошибка алгоритма")

        detail = None
        try:
            with patch(
                "app.loan_applications.calculate_application_score",
                new=broken_scoring,
            ):
                detail = create_loan_application(
                    LoanApplicationCreate(
                        inn="4217064416",
                        product_id=2,
                        requested_amount=2_000_000,
                        requested_term_months=12,
                        loan_purpose="working_capital",
                    )
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
                self._cleanup(detail.application_id)


    def test_alternative_offers_created_and_selected(self):
        from app.loan_applications import (
            create_loan_application,
            select_application_offer,
        )
        from app.schemas import LoanApplicationCreate

        detail = None
        try:
            # Рейтинг 568 ниже min_credit_rating 700 у выбранного продукта,
            # но подходят альтернативы с меньшим минимумом.
            detail = create_loan_application(
                LoanApplicationCreate(
                    inn="3257029840",
                    product_id=4,
                    requested_amount=2_000_000,
                    requested_term_months=12,
                    loan_purpose="business_expansion",
                    business_age_months=36,
                )
            )
            self.assertEqual(detail.status, "offer_pending")
            self.assertIsNone(detail.decision)
            self.assertGreaterEqual(len(detail.offers), 1)
            self.assertTrue(all(offer.status == "offered" for offer in detail.offers))

            selected = select_application_offer(
                detail.application_id, detail.offers[0].offer_id
            )
            self.assertEqual(selected.status, "approved")
            self.assertEqual(selected.decision.decision_type, "approved")
            statuses = {offer.offer_id: offer.status for offer in selected.offers}
            self.assertEqual(statuses[detail.offers[0].offer_id], "selected")
            self.assertTrue(
                any(status == "superseded" for status in statuses.values())
            )
        finally:
            if detail is not None:
                self._cleanup(detail.application_id)

    def test_declining_all_offers_leads_to_final_rejection(self):
        from app.loan_applications import (
            create_loan_application,
            decline_application_offer,
        )
        from app.schemas import LoanApplicationCreate

        detail = None
        try:
            detail = create_loan_application(
                LoanApplicationCreate(
                    inn="3257029840",
                    product_id=4,
                    requested_amount=2_000_000,
                    requested_term_months=12,
                    loan_purpose="business_expansion",
                    business_age_months=36,
                )
            )
            self.assertEqual(detail.status, "offer_pending")
            current = detail
            for offer in list(detail.offers):
                current = decline_application_offer(
                    detail.application_id, offer.offer_id
                )
            self.assertEqual(current.status, "rejected")
            self.assertEqual(current.decision.decision_type, "rejected")
            self.assertEqual(current.decision.decision_source, "automatic")
            self.assertTrue(
                all(offer.status == "declined" for offer in current.offers)
            )
        finally:
            if detail is not None:
                self._cleanup(detail.application_id)
