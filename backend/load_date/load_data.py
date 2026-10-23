import pandas as pd
from sqlalchemy import create_engine

# Ваши настройки БД
DB_USER = "postgres"
DB_PASSWORD = "1234" # Ваш пароль
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "alfa_hakaton"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

df_companies = pd.read_csv("df_company.csv")

# Загружаем в таблицу companies
df_companies.to_sql('companies', engine, if_exists='append', index=False, chunksize=10000)

print("Компании успешно загружены!")