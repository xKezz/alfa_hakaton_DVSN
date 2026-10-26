"""Тесты маршрутизации заявки без изменения формул скоринга."""

from __future__ import annotations

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

from app.scoring_service import (  # noqa: E402
    REASON_BOUNDARY,
    REASON_BELOW_MIN,
    REASON_PURPOSE_OTHER,
    decide_application,
    manual_review_reasons,
)

PRODUCT = {
    "product_id": 2,
    "min_credit_rating": 400,
}
BASE = {
    "has_error": False,
    "risk_category": "A+",
    "scoring": 100.0,
    "scoring_factors": {
        "fin_score": 1.0,
        "net_profit": 1.0,
        "total_equity": 1.0,
        "age": 1.0,
    },
    "employee_rout": False,
}
THRESHOLD = {"threshold": 40.0, "margin": 1.2, "low": 38.8, "high": 41.2}


class RoutingRulesTest(unittest.TestCase):
    def route(self, *, rating=746, score=100.0, employee_rout=False, has_error=False, purpose="working_capital"):
        result = dict(BASE)
        result["scoring"] = score
        result["employee_rout"] = employee_rout
        result["has_error"] = has_error
        return decide_application(
            rating=rating,
            product=PRODUCT,
            product_result=result,
            threshold=THRESHOLD,
            loan_purpose=purpose,
        )

    def test_standard_purpose_high_rating_auto_approved(self):
        result = self.route()
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["reasons"], [])

    def test_product_score_below_low_threshold_auto_rejected(self):
        result = self.route(score=10.0)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["decision"], "rejected")

    def test_rating_below_product_minimum_goes_to_employee(self):
        result = self.route(rating=300)
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])
        self.assertIn(
            REASON_BELOW_MIN.format(rating=300, min_rating=400), result["reasons"]
        )

    def test_purpose_other_goes_to_employee_even_with_high_rating(self):
        result = self.route(purpose="other")
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])
        self.assertEqual(result["reasons"], [REASON_PURPOSE_OTHER])

    def test_both_conditions_go_to_employee_once(self):
        result = self.route(rating=300, purpose="other")
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])
        self.assertIn(
            REASON_BELOW_MIN.format(rating=300, min_rating=400), result["reasons"]
        )
        self.assertIn(REASON_PURPOSE_OTHER, result["reasons"])

    def test_existing_boundary_rule_is_preserved(self):
        result = self.route(score=40.0, employee_rout=True)
        self.assertEqual(result["status"], "manual_review")
        self.assertIn(REASON_BOUNDARY, result["reasons"])

    def test_scoring_error_goes_to_employee_without_decision(self):
        result = self.route(has_error=True)
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])

    def test_missing_product_score_goes_to_employee(self):
        result = self.route(score=None)
        self.assertEqual(result["status"], "manual_review")
        self.assertIsNone(result["decision"])

    def test_manual_review_reasons_are_deduplicated(self):
        result = dict(BASE)
        result["employee_rout"] = True
        reasons = manual_review_reasons(
            rating=746,
            product=PRODUCT,
            product_result=result,
            loan_purpose="other",
        )
        self.assertEqual(len(reasons), len(set(reasons)))
        self.assertIn(REASON_BOUNDARY, reasons)
        self.assertIn(REASON_PURPOSE_OTHER, reasons)


if __name__ == "__main__":
    unittest.main()
