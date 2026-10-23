import pandas as pd
from sqlalchemy import create_engine

DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "alfa_hakaton"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

df = pd.read_csv(r"C:\Users\Lenovo\OneDrive\альфа хакатон\alfa_hakaton_DVSN\backend\load_date\df_financial.txt")

rename_map = {
    "гостиница": "inn",
    "год": "report_year",
    "выручка": "revenue",
    "нераспределенная прибыль": "retained_earnings",
    "активы": "assets",
    "собственный капитал": "total_equity",
    "прибыль от продаж": "profit_from_sales",
    "прибыль до налогообложения": "before_tax",
    "чистая прибыль": "net_profit",
    "долгосрочная задолженность": "longterm_debt",
    "краткосрочная задолженность": "shortterm_dept",
    "денежные эквиваленты": "cash_equivalents",
    "проценты к уплате": "interest_payable",
    "оборотные активы": "current_assets",
    "краткосрочные обязательства": "shortterm_liab",
    "баланс операционной деятельности": "balance_operating"
}

df = df.rename(columns=rename_map)

df.to_sql('financial_statements', engine, if_exists='append', index=False)

print("Данные успешно загружены!")
