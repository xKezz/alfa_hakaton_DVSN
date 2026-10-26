"""Интеграционные тесты предложения сотрудника (реальная БД)."""

from __future__ import annotations

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
from app.loan_applications import (  # noqa: E402
    create_employee_offer,
    create_loan_application,
    decline_application_offer,
    decide_loan_application,
    get_loan_application,
    select_application_offer,
)
from app.schemas import (  # noqa: E402
    AuthUser,
    EmployeeOfferCreate,
    LoanApplicationCreate,
    LoanApplicationDecisionRequest,
)

RUN_DB = os.environ.get("RUN_DB_TESTS") == "1"


@unittest.skipUnless(RUN_DB, "Требуется PostgreSQL и RUN_DB_TESTS=1")
class EmployeeOfferFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row

        try:
            conn = psycopg.connect(**get_settings().connect_kwargs, row_factory=dict_row)
        except (psycopg.Error, OSError) as exc:
            raise unittest.SkipTest(f"PostgreSQL недоступен: {exc}") from exc
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, company_inn FROM login "
                    "WHERE profile_type='business' AND company_inn IS NOT NULL "
                    "ORDER BY company_inn, username"
                )
                all_clients = cur.fetchall()
                # Нужны два разных бизнес-пользователя с РАЗНЫМИ компаниями.
                clients = []
                seen_companies = set()
                for item in all_clients:
                    if item["company_inn"] in seen_companies:
                        continue
                    seen_companies.add(item["company_inn"])
                    clients.append(item)
                    if len(clients) == 2:
                        break
                cur.execute(
                    "SELECT username FROM login WHERE profile_type='employee' ORDER BY username LIMIT 1"
                )
                employee = cur.fetchone()
                cur.execute(
                    "SELECT company_status FROM companies WHERE inn = %s",
                    (clients[0]["company_inn"],),
                )
                company_row = cur.fetchone()
                company_status = str((company_row or {}).get("company_status") or "").lower()
                cur.execute(
                    "SELECT * FROM loan_catalog "
                    "WHERE is_active = TRUE AND business_category IN (%s, 'both') "
                    "ORDER BY product_id LIMIT 1",
                    (company_status,),
                )
                product = cur.fetchone()
        finally:
            conn.close()
        if len(clients) < 2 or employee is None or product is None:
            raise unittest.SkipTest("Нет двух бизнес-логинов/сотрудника/продукта")
        cls.client_user = AuthUser(
            username=clients[0]["username"],
            profile_type="business",
            company_inn=clients[0]["company_inn"],
        )
        cls.other_client = AuthUser(
            username=clients[1]["username"],
            profile_type="business",
            company_inn=clients[1]["company_inn"],
        )
        cls.employee = AuthUser(
            username=employee["username"], profile_type="employee", company_inn=None
        )
        cls.product = product
        cls.created: list[str] = []

    @classmethod
    def tearDownClass(cls):
        import psycopg

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

    def _new_manual_application(self) -> dict:
        product = self.product
        amount = max(float(product["min_amount"]), min(1_000_000.0, float(product["max_amount"])))
        term = max(int(product["min_term_months"]), min(12, int(product["max_term_months"])))
        payload = LoanApplicationCreate(
            inn=self.client_user.company_inn,
            product_id=int(product["product_id"]),
            requested_amount=amount,
            requested_term_months=term,
            loan_purpose="other",
            business_age_months=36,
        )
        application = create_loan_application(payload, current_user=self.client_user)
        self.created.append(application.application_id)
        self.assertEqual(application.status, "manual_review")
        return application

    def test_employee_offer_then_client_accepts(self):
        application = self._new_manual_application()
        offered = create_employee_offer(
            application.application_id,
            EmployeeOfferCreate(
                product_id=int(self.product["product_id"]),
                approved_amount=750_000,
                approved_term_months=18,
                reason="Индивидуальные условия сотрудника",
            ),
            current_user=self.employee,
        )
        self.assertEqual(offered.status, "offer_pending")
        self.assertIsNone(offered.decision)
        self.assertEqual(len(offered.offers), 1)
        offer = offered.offers[0]
        self.assertEqual(offer.source, "bank_employee")
        self.assertEqual(offer.created_by, self.employee.username)
        self.assertEqual(offer.status, "offered")
        self.assertEqual(offer.reason, "Индивидуальные условия сотрудника")

        accepted = select_application_offer(
            application.application_id,
            offer.offer_id,
            current_user=self.client_user,
        )
        self.assertEqual(accepted.status, "approved")
        self.assertEqual(accepted.decision.decision_source, "bank_employee")
        self.assertEqual(accepted.decision.decided_by, self.employee.username)
        self.assertEqual(accepted.decision.approved_amount, 750_000.0)
        self.assertEqual(accepted.decision.approved_term_months, 18)
        self.assertEqual(accepted.decision.decision_reason, "Индивидуальные условия сотрудника")
        self.assertEqual(
            next(item for item in accepted.offers if item.offer_id == offer.offer_id).status,
            "selected",
        )

        with self.assertRaises(HTTPException) as ctx:
            select_application_offer(
                application.application_id,
                offer.offer_id,
                current_user=self.client_user,
            )
        self.assertEqual(ctx.exception.status_code, 409)

    def test_employee_offer_then_client_declines(self):
        application = self._new_manual_application()
        offered = create_employee_offer(
            application.application_id,
            EmployeeOfferCreate(
                product_id=int(self.product["product_id"]),
                approved_amount=650_000,
                approved_term_months=9,
                reason="Предложение с другим сроком",
            ),
            current_user=self.employee,
        )
        declined = decline_application_offer(
            application.application_id,
            offered.offers[0].offer_id,
            current_user=self.client_user,
        )
        self.assertEqual(declined.status, "rejected")
        self.assertEqual(declined.offers[0].status, "declined")
        self.assertEqual(
            declined.decision.decision_reason, "Предприниматель отклонил предложение"
        )

    def test_employee_can_approve_with_custom_amount_and_term(self):
        application = self._new_manual_application()
        decided = decide_loan_application(
            application.application_id,
            LoanApplicationDecisionRequest(
                decision="approved",
                approved_amount=800_000,
                approved_term_months=11,
                reason="Одобрено сотрудником банка",
            ),
            current_user=self.employee,
        )
        self.assertEqual(decided.status, "approved")
        self.assertEqual(decided.decision.decision_source, "bank_employee")
        self.assertEqual(decided.decision.decided_by, self.employee.username)
        self.assertEqual(decided.decision.approved_amount, 800_000.0)
        self.assertEqual(decided.decision.approved_term_months, 11)
        self.assertEqual(decided.decision.decision_reason, "Одобрено сотрудником банка")

    def test_employee_can_reject(self):
        application = self._new_manual_application()
        decided = decide_loan_application(
            application.application_id,
            LoanApplicationDecisionRequest(
                decision="rejected", reason="Отказ по кредитной политике"
            ),
            current_user=self.employee,
        )
        self.assertEqual(decided.status, "rejected")
        self.assertEqual(decided.decision.decision_type, "rejected")
        self.assertEqual(decided.decision.decided_by, self.employee.username)

    def test_business_cannot_read_foreign_application_or_act_on_it(self):
        application = self._new_manual_application()
        with self.assertRaises(HTTPException) as ctx:
            get_loan_application(application.application_id, current_user=self.other_client)
        self.assertEqual(ctx.exception.status_code, 403)

        offered = create_employee_offer(
            application.application_id,
            EmployeeOfferCreate(
                product_id=int(self.product["product_id"]),
                approved_amount=500_000,
                approved_term_months=6,
                reason="Предложение для проверки доступа",
            ),
            current_user=self.employee,
        )
        with self.assertRaises(HTTPException) as ctx:
            decline_application_offer(
                application.application_id,
                offered.offers[0].offer_id,
                current_user=self.other_client,
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
