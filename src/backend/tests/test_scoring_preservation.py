"""Тесты сохранности существующих формул скоринга (без БД)."""

from __future__ import annotations

import datetime
import hashlib
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

from src.credit_risk.credit_category import (  # noqa: E402
    CreditScorer,
    product_params,
    product_scoring_threshold,
    rating_to_score_fast,
)
from src.credit_risk.credit_risk_score import Financial_Risk_Score  # noqa: E402

# Хеши зафиксированы до интеграции. Если они изменятся, значит были
# затронуты формулы/веса/пороги, что запрещено условием задачи.
#
# Единственное разрешённое изменение: в config.py после переноса кода в
# src/credit_risk/ поправлен только путь к весам (WEIGHTS_PATH), сами веса,
# пороги и справочники не менялись.
EXPECTED_HASHES = {
    "src/credit_risk/credit_risk_score.py": "420308bd4569f2d0a88e204c54b6fc507c3fc35f7cad5ff3f411a31f12def616",
    "src/credit_risk/credit_category.py": "216a207e7de6c21502effc3570eb4b5754966c60e4389397dbe1918b832f7088",
    "src/credit_risk/config.py": "b5631e3df8066aa4ab2d873b85c98f32493b2f363d272e26fe8d073f292a4bfd",
    "src/credit_risk/data/weight.json": "ac3a8932d68332c886fb4e317b1ba4f89967fd014dc33f0c3b6fa9fc68355d50",
}

FINANCIAL = {
    "financial_id": 1,
    "inn": "4217064416",
    "report_year": 2026,
    "revenue": 10000000,
    "net_profit": 5000000,
    "assets": 23432634434,
    "current_assets": 456534534634,
    "total_equity": 45345234,
    "longterm_debt": 234234,
    "shortterm_debt": 5234534,
    "shortterm_liab": 523423,
    "retained_earnings": 324235,
    "profit_from_sales": 34213342,
    "before_tax": 234234,
    "cash_equivalents": 1232334124,
    "interest_payable": 3456456,
    "balance_operating": 234234,
}

PERCENTILES = {
    "industry": {
        "revenue": (1_000_000.0, 50_000_000.0),
        "net_margin": (0.01, 0.30),
    },
    "dataset": {
        "revenue": (100_000.0, 100_000_000.0),
        "assets": (100_000.0, 1_000_000_000.0),
        "total_equity": (10_000.0, 100_000_000.0),
    },
}

PRODUCT = {
    "product_id": 1,
    "product_name": "Тестовый продукт",
    "business_category": "both",
    "min_amount": 50000,
    "max_amount": 5000000,
    "min_term_months": 3,
    "max_term_months": 36,
    "percent": 29.9,
    "loan_purpose": "other",
    "is_active": True,
    "business_age": 0,
    "min_credit_rating": 400,
    "min_credit_ratings": 400,
}


class FakeAPI:
    async def get_connection(self):
        return object()

    async def close(self):
        return None

    async def get_company_info(self, inn):
        return {
            "inn": inn,
            "company_name": "Test",
            "registration_date": datetime.date(2004, 4, 23),
            "company_status": "IP",
            "industry": "M",
            "region_code": "4200",
            "is_simplified_tax": False,
            "dissolution_flag": False,
        }


class FakeInternalApi:
    async def get_latest_report_year(self, inn):
        return 2026

    async def get_scoring_percentiles(self, inn, year):
        return PERCENTILES


class FormulaPreservationTest(unittest.IsolatedAsyncioTestCase):
    def test_scoring_source_files_and_weights_unchanged(self):
        for relative_path, expected in EXPECTED_HASHES.items():
            actual = hashlib.sha256(
                (PROJECT_ROOT / relative_path).read_bytes()
            ).hexdigest()
            self.assertEqual(actual, expected, f"Файл алгоритма изменён: {relative_path}")

    async def test_financial_rating_baseline(self):
        scorer = Financial_Risk_Score(
            api=FakeAPI(),
            internal_api=FakeInternalApi(),
        )
        result = await scorer.calculate("4217064416", year=2026, financial=FINANCIAL)
        self.assertEqual(result["rating"], 753)
        self.assertEqual(result["fin_score"], 753)
        self.assertEqual(result["fin_params"]["fin_score"], 753)
        self.assertAlmostEqual(result["fin_params"]["net_profit"], 5000000.0)
        self.assertAlmostEqual(result["fin_params"]["total_equity"], 45345234.0)
        self.assertEqual(result["data_quality"], "ok")
        self.assertEqual(result["missing_blocks"], [])

    async def test_product_scoring_baseline(self):
        scorer = Financial_Risk_Score(
            api=FakeAPI(),
            internal_api=FakeInternalApi(),
        )
        fin_result = await scorer.calculate(
            "4217064416", year=2026, financial=FINANCIAL
        )
        params = product_params(PRODUCT)
        scored = CreditScorer(params).calculate_score(fin_result["fin_params"])
        self.assertEqual(scored["score"], 100.0)
        self.assertEqual(
            scored["factors"],
            {"fin_score": 1.0, "net_profit": 1.0, "total_equity": 1.0, "age": 1.0},
        )
        self.assertEqual(
            product_scoring_threshold(PRODUCT),
            {"threshold": 40.0, "margin": 1.2, "low": 38.8, "high": 41.2},
        )
        self.assertEqual(rating_to_score_fast(fin_result["rating"]), "A+")


if __name__ == "__main__":
    unittest.main()
