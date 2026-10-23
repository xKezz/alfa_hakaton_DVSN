"""Конфигурация проекта: пути, колонки БД, пороги скоринга и справочники.

Все массивы/словари/пороги, которые используются в credit_risk_score.py,
credit_category.py, apis_fns_example.py и internal_api.py, собраны здесь.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # src/
WEIGHTS_PATH = BASE_DIR / "data" / "weight.json"

# ---------------------------------------------------------------------------
# БД: списки колонок
# ---------------------------------------------------------------------------

COMPANY_COLUMNS = (
    "inn",
    "company_name",
    "registration_date",
    "company_status",
    "industry",
    "region_code",
    "is_simplified_tax",
    "dissolution_flag",
)

FINANCIAL_COLUMNS = (
    "financial_id",
    "inn",
    "report_year",
    "revenue",
    "net_profit",
    "assets",
    "current_assets",
    "total_equity",
    "longterm_debt",
    "shortterm_debt",
    "shortterm_liab",
    "retained_earnings",
    "profit_from_sales",
    "before_tax",
    "cash_equivalents",
    "interest_payable",
    "balance_operating",
)

# Колонки companies, по которым разрешено фильтровать get_companies_by_parameter.
COMPANIES_FILTER_COLUMNS = (
    "industry",
    "company_status",
    "region_code",
    "is_simplified_tax",
    "dissolution_flag",
)

LOAN_CATALOG_COLUMNS = (
    "product_id",
    "product_name",
    "description",
    "business_category",
    "min_amount",
    "max_amount",
    "min_term_months",
    "max_term_months",
    "percent",
    "loan_purpose",
    "is_active",
    "business_age",
    "min_credit_ratings",
)

# Колонки, по которым разрешено сортировать каталог продуктов.
LOAN_CATALOG_SORT_COLUMNS = (
    "product_id",
    "product_name",
    "description",
    "business_category",
    "min_amount",
    "max_amount",
    "min_term_months",
    "max_term_months",
    "percent",
    "loan_purpose",
)

LOAN_APPLICATION_COLUMNS = (
    "application_id",
    "inn",
    "product_id",
    "requested_amount",
    "requested_term_months",
    "loan_purpose",
    "application_status",
)

# ---------------------------------------------------------------------------
# Процентили
# ---------------------------------------------------------------------------

# SQL-выражения для процентилей: category -> выражение над financial_statements AS fs.
PERCENTILE_EXPRESSIONS = {
    "revenue": "fs.revenue",
    "net_profit": "fs.net_profit",
    "assets": "fs.assets",
    "current_assets": "fs.current_assets",
    "total_equity": "fs.total_equity",
    "longterm_debt": "fs.longterm_debt",
    "shortterm_debt": "fs.shortterm_debt",
    "shortterm_liab": "fs.shortterm_liab",
    "retained_earnings": "fs.retained_earnings",
    "profit_from_sales": "fs.profit_from_sales",
    "before_tax": "fs.before_tax",
    "cash_equivalents": "fs.cash_equivalents",
    "interest_payable": "fs.interest_payable",
    "balance_operating": "fs.balance_operating",
    # R = net_profit / revenue — замена роста выручки g в одно-годовом режиме
    "net_margin": "fs.net_profit::numeric / NULLIF(fs.revenue, 0)",
}

INDUSTRY_SCOPE = "industry"
DATASET_SCOPE = "dataset"
PERCENTILE_LOW = 0.05
PERCENTILE_HIGH = 0.95

# ---------------------------------------------------------------------------
# Скоринг: блоки, ручной ввод, пороги
# ---------------------------------------------------------------------------

# Блоки, которым нужна финансовая отчётность (S_бп может считаться и по дате регистрации).
FINANCIAL_BLOCK_NAMES = (
    "market_position",
    "size",
    "profitability",
    "debt_load",
    "debt_service",
    "liquidity",
    "cash_flow",
)

# Ручной ввод: коды строк отчётности -> имена колонок БД.
LINE_TO_COLUMN = {
    "line_2110": "revenue",
    "line_1370": "retained_earnings",
    "line_1600": "assets",
    "line_1300": "total_equity",
    "line_2200": "profit_from_sales",
    "line_2300": "before_tax",
    "line_2330": "interest_payable",
    "line_2400": "net_profit",
    "line_1410": "longterm_debt",
    "line_1510": "shortterm_debt",
    "line_1250": "cash_equivalents",
    "line_1200": "current_assets",
    "line_1500": "shortterm_liab",
    "line_4100": "balance_operating",
}

AGE_THRESHOLDS = (1.0, 10.0)  # возраст, лет
PROFIT_FROM_SALES_MARGIN = (0.0, 0.15)  # 2200 / 2110
BEFORE_TAX_MARGIN = (0.0, 0.12)  # 2300 / 2110
NET_PROFIT_MARGIN = (0.0, 0.10)  # 2400 / 2110
DEBT_TO_EQUITY = (3.0, 0.5)  # Долг / 1300 (a > b: чем меньше, тем лучше)
NET_DEBT_TO_EBITDA = (6.0, 1.0)  # (Долг - 1250) / 2200 (a > b)
DEBT_SERVICE_COVERAGE = (1.0, 5.0)  # (2300 + 2330) / 2330
CFO_TO_REVENUE = (0.0, 0.10)  # 4100 / 2110
CFO_TO_DEBT = (0.0, 0.3)  # 4100 / Долг

# ---------------------------------------------------------------------------
# Кредитные продукты и заявки
# ---------------------------------------------------------------------------

# Баллы рейтинга по буквенной шкале (используется для отображения клиенту).
RATING_TO_SCORE = {
    "AAA": 980,
    "AA+": 926, "AA": 871, "AA-": 817,
    "A+": 763, "A": 709, "A-": 654,
    "BBB+": 600, "BBB": 546, "BBB-": 491,
    "BB+": 437, "BB": 383, "BB-": 329,
    "B+": 274, "B": 220, "B-": 166,
    "CCC": 0,
}

APPLICATION_STATUS_SUBMITTED = "submitted"
APPLICATION_STATUS_PROCESSING = "processing"
APPLICATION_STATUS_MANUAL_REVIEW = "manual_review"
APPLICATION_STATUS_APPROVED = "approved"
APPLICATION_STATUS_OFFER_PENDING = "offer_pending"
APPLICATION_STATUS_REJECTED = "rejected"

# Все статусы, допустимые в loan_applications.application_status.
APPLICATION_STATUSES = (
    APPLICATION_STATUS_SUBMITTED,
    APPLICATION_STATUS_PROCESSING,
    APPLICATION_STATUS_MANUAL_REVIEW,
    APPLICATION_STATUS_OFFER_PENDING,
    APPLICATION_STATUS_APPROVED,
    APPLICATION_STATUS_REJECTED,
)

# Допустимые цели кредита (loan_catalog.loan_purpose).
LOAN_PURPOSES = (
    "launch_and_start",
    "operational_activity",
    "development_and_scaling",
    "strategic_goals",
    "business_protection",
)

# ---------------------------------------------------------------------------
# Скоринг относительно кредитного продукта (CreditScorer)
# ---------------------------------------------------------------------------

# Веса факторов в итоговом скоринговом балле продукта (сумма = 1).
PRODUCT_SCORE_WEIGHTS = {
    "fin_score": 0.4,
    "net_profit": 0.2,
    "total_equity": 0.25,
    "age": 0.15,
}

# Множитель перевода скоринга в шкалу 0..100.
PRODUCT_SCORE_SCALE = 100

# Допуск «порогового» скоринга: 3% от нижней границы продукта.
SCORING_THRESHOLD_PERCENT = 0.03