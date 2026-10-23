"""Финансовый скоринг компании (fin_score) по методике Credit Risk.md.

Класс Financial_Risk_Score (бывш. Credit_Risk_Score) считает финансовые
возможности компании и возвращает fin_params: fin_score, net_profit,
total_equity, age. Эти значения использует credit_category.py при скоринге
компании относительно конкретного кредитного продукта (CreditScorer).
"""

import datetime
import json
import math
from pathlib import Path

if __package__:  # запуск как пакета: python -m src.credit_risk.credit_risk_score
    from . import config
    from .apis_fns_example import FNSApi
    from .internal_api import InternalApi
else:  # запуск из каталога src/credit_risk
    import config
    from apis_fns_example import FNSApi
    from internal_api import InternalApi


def read_weights(path: str | Path = config.WEIGHTS_PATH) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


class Financial_Risk_Score:
    AGE_THRESHOLDS = config.AGE_THRESHOLDS  # возраст, лет
    PROFIT_FROM_SALES_MARGIN = config.PROFIT_FROM_SALES_MARGIN  # 2200 / 2110
    BEFORE_TAX_MARGIN = config.BEFORE_TAX_MARGIN  # 2300 / 2110
    NET_PROFIT_MARGIN = config.NET_PROFIT_MARGIN  # 2400 / 2110
    DEBT_TO_EQUITY = config.DEBT_TO_EQUITY  # Долг / 1300 (a > b: чем меньше, тем лучше)
    NET_DEBT_TO_EBITDA = config.NET_DEBT_TO_EBITDA  # (Долг - 1250) / 2200 (a > b)
    DEBT_SERVICE_COVERAGE = config.DEBT_SERVICE_COVERAGE  # (2300 + 2330) / 2330
    CFO_TO_REVENUE = config.CFO_TO_REVENUE  # 4100 / 2110
    CFO_TO_DEBT = config.CFO_TO_DEBT  # 4100 / Долг

    def __init__(
        self,
        dsn: str | None = None,
        api: FNSApi | None = None,
        internal_api: InternalApi | None = None,
        weights_path: str | Path = config.WEIGHTS_PATH,
    ):
        """
        :param dsn: DSN PostgreSQL (по умолчанию берётся из env DB_CONNECT/DB_DSN)
        :param api: готовый FNSApi (удобно подменять в тестах)
        :param internal_api: готовое InternalApi (по умолчанию использует self.api)
        :param weights_path: путь к weight.json
        """
        self.api = api or FNSApi(dsn=dsn)
        self.internal_api = internal_api or InternalApi(api=self.api)
        self.weights = read_weights(weights_path)

        self.inn: str | None = None
        self.year: int | None = None
        self.company: dict = {}
        self.financial: dict = {}
        self.percentiles: dict = {}

    # ----------------------------- подключение -----------------------------

    async def __aenter__(self) -> "Financial_Risk_Score":
        await self.api.get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Закрывает соединение с БД."""
        await self.api.close()

    # ----------------------------- данные клиента -----------------------------

    async def get_user_type(self, inn: str) -> str | None:
        company = await self.api.get_company_info(inn)
        return None if company is None else company.get("company_status")

    async def _resolve_year(self, inn: str, year: int | None, financial: dict | None = None) -> int:
        """Отчётный год: переданный явно, последний доступный по ИНН или текущий (ручной ввод)."""
        if year is not None:
            return int(year)
        latest = await self.internal_api.get_latest_report_year(inn)
        if latest is not None:
            return int(latest)
        if financial is not None:
            return datetime.date.today().year
        raise ValueError(f"Нет финансовой отчётности ИНН {inn}")

    async def read_from_inn(self, inn: str, year: int | None = None) -> dict:
        company = await self.api.get_company_info(inn)
        if company is None:
            raise ValueError(f"ИНН {inn} не найден в базе ФНС")

        self.inn = str(inn)
        self.year = await self._resolve_year(inn, year)
        self.company = company
        if company.get("company_status") == "IP":
            self.financial = {}
            return dict(company)

        financial = await self.api.get_financial_info(inn, self.year)
        if financial is None:
            raise ValueError(f"Нет финансовой отчётности ИНН {inn} за {self.year} год")
        self.financial = financial
        return {**company, **financial}

    def read_user_data(self, financial: dict) -> dict:
        self.financial = self.normalize_financial(financial)
        return self.financial

    # ----------------------------- основной расчёт -----------------------------

    async def calculate(self, inn: str, year: int | None = None, financial: dict | None = None) -> dict:
        """
        Полный расчёт: проверяем пользователя в API, берём данные, считаем fin_score.

        :param inn: ИНН
        :param year: отчётный год (None — последний доступный по ИНН)
        :param financial: финансовые показатели вручную (обязательно для ИП)
        """
        company = await self.api.get_company_info(inn)
        if company is None:
            raise ValueError(f"ИНН {inn} не найден в базе ФНС")

        self.inn = str(inn)
        self.year = await self._resolve_year(inn, year, financial=financial)
        self.company = company

        if financial is not None:
            self.financial = self.normalize_financial(financial)
        elif company.get("company_status") == "IP":
            raise ValueError(
                "Для ИП финансовые показатели вводятся вручную: передайте financial "
                "в calculate(..., financial={...}) или используйте calculate_manual()"
            )
        else:
            statements = await self.api.get_financial_info(inn, self.year)
            if statements is None:
                raise ValueError(f"Нет финансовой отчётности ИНН {inn} за {self.year} год")
            self.financial = statements

        self.percentiles = await self.internal_api.get_scoring_percentiles(inn, self.year)
        return self.score()

    async def calculate_manual(self, inn: str, year: int | None = None, financial: dict | None = None) -> dict:
        return await self.calculate(inn, year, financial=financial)

    def score(self) -> dict:
        group_key, s_industry, block_weights, industry_matched = self._industry_params()

        blocks: dict[str, dict] = {}

        def add_block(name: str, result: tuple[float | None, str | None]) -> None:
            score, reason = result
            blocks[name] = {"score": score, "weight": block_weights[name], "reason": reason}

        add_block(
            "industry",
            (s_industry, None if s_industry is not None else "нет экспертной оценки s_otr для отрасли в weight.json"),
        )
        add_block("market_position", self.market_pos())
        add_block("business_profile", self.business_profile())
        add_block("size", self.size())
        add_block("profitability", self.profitability())
        add_block("debt_load", self.debt_load())
        add_block("debt_service", self.debt_service())
        add_block("liquidity", self.liquidity())
        add_block("cash_flow", self.cash_flow())

        available = {name: item["score"] for name, item in blocks.items() if item["score"] is not None}
        missing_blocks = [name for name in blocks if blocks[name]["score"] is None]
        financial_blocks = [name for name in available if name in config.FINANCIAL_BLOCK_NAMES]
        total_weight = sum(block_weights[name] for name in available)
        if total_weight > 0 and financial_blocks:
            s_total = sum(block_weights[name] * available[name] for name in available) / total_weight
            weights_used = {name: block_weights[name] / total_weight for name in available}
            data_quality = "ok" if not missing_blocks else "partial"
        else:
            s_total = None
            weights_used = {}
            data_quality = "insufficient"

        rating = int(math.floor(1000.0 * s_total + 0.5)) if s_total is not None else None
        return {
            "inn": self.inn,
            "report_year": self.year,
            "user_type": self.company.get("company_status"),
            "industry": self.company.get("industry"),
            "industry_matched": industry_matched,
            "industry_group": group_key,
            "blocks": blocks,
            "weights_used": weights_used,
            "s_total": s_total,
            "rating": rating,
            # Финансовый показатель компании (0..1000) — для credit_category.py.
            "fin_score": rating,
            # Финансовые параметры компании для CreditScorer (credit_category.py).
            "fin_params": {
                "fin_score": rating,
                "net_profit": self._num(self.financial.get("net_profit")),
                "total_equity": self._num(self.financial.get("total_equity")),
                "age": self._age(),
            },
            "data_quality": data_quality,
            "missing_blocks": missing_blocks,
        }

    # ----------------------------- блоки показателей -----------------------------

    def market_pos(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["market_position"]
        revenue = self._num(self.financial.get("revenue"))
        net_profit = self._num(self.financial.get("net_profit"))
        return self._combine(
            [
                (
                    weights["ln_revenue"],
                    self._scale(self._ln(revenue), self._bounds("industry", "revenue", log=True)),
                    "нет (или <= 0) 2110 или порогов P5/P95 по выручке отрасли",
                ),
                (
                    weights["net_margin"],
                    self._scale(self._ratio(net_profit, revenue), self._bounds("industry", "net_margin")),
                    "нет 2400/2110 (или 2110 <= 0) или порогов P5/P95 по R отрасли",
                ),
            ]
        )

    def business_profile(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["business_profile"]
        revenue = self._num(self.financial.get("revenue"))
        net_profit = self._num(self.financial.get("net_profit"))
        return self._combine(
            [
                (
                    weights["net_margin"],
                    self._scale(self._ratio(net_profit, revenue), self._bounds("industry", "net_margin")),
                    "нет 2400/2110 (или 2110 <= 0) или порогов P5/P95 по R отрасли",
                ),
                (weights["age"], self._scale(self._age(), self.AGE_THRESHOLDS), "нет registration_date"),
                (weights["management"], self._management(), "нет 1300/1370"),
            ]
        )

    def size(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["size"]
        return self._combine(
            [
                (
                    weights["ln_revenue"],
                    self._scale(self._ln(self._num(self.financial.get("revenue"))), self._bounds("dataset", "revenue", log=True)),
                    "нет (или <= 0) 2110 или порогов P5/P95 по датасету",
                ),
                (
                    weights["ln_assets"],
                    self._scale(self._ln(self._num(self.financial.get("assets"))), self._bounds("dataset", "assets", log=True)),
                    "нет (или <= 0) 1600 или порогов P5/P95 по датасету",
                ),
                (
                    weights["ln_equity"],
                    self._scale(self._ln(self._num(self.financial.get("total_equity"))), self._bounds("dataset", "total_equity", log=True)),
                    "нет положительного 1300 или порогов P5/P95 по датасету",
                ),
            ]
        )

    def profitability(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["profitability"]
        revenue = self._num(self.financial.get("revenue"))
        return self._combine(
            [
                (
                    weights["profit_from_sales"],
                    self._scale(self._ratio(self._num(self.financial.get("profit_from_sales")), revenue), self.PROFIT_FROM_SALES_MARGIN),
                    "нет 2200/2110 (или 2110 <= 0)",
                ),
                (
                    weights["before_tax"],
                    self._scale(self._ratio(self._num(self.financial.get("before_tax")), revenue), self.BEFORE_TAX_MARGIN),
                    "нет 2300/2110 (или 2110 <= 0)",
                ),
                (
                    weights["net_profit"],
                    self._scale(self._ratio(self._num(self.financial.get("net_profit")), revenue), self.NET_PROFIT_MARGIN),
                    "нет 2400/2110 (или 2110 <= 0)",
                ),
            ]
        )

    def debt_load(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["debt_load"]
        debt = self._sum(self.financial.get("longterm_debt"), self.financial.get("shortterm_debt"))
        equity = self._num(self.financial.get("total_equity"))
        cash = self._num(self.financial.get("cash_equivalents"))
        ebitda_proxy = self._num(self.financial.get("profit_from_sales"))

        if equity is not None and equity <= 0:
            debt_to_equity = (weights["debt_to_equity"], 0.0, "")
        else:
            debt_to_equity = (
                weights["debt_to_equity"],
                self._scale(self._ratio(debt, equity), self.DEBT_TO_EQUITY),
                "нет (или <= 0) 1300 или нет одной из строк 1410/1510",
            )

        net_debt = debt - cash if debt is not None and cash is not None else None
        if net_debt is not None and net_debt <= 0:
            net_debt_to_ebitda = (weights["net_debt_to_ebitda"], 1.0, "")
        elif net_debt is None:
            net_debt_to_ebitda = (weights["net_debt_to_ebitda"], None, "нет 1250 или одной из строк 1410/1510")
        elif ebitda_proxy is None:
            net_debt_to_ebitda = (weights["net_debt_to_ebitda"], None, "нет 2200")
        elif ebitda_proxy <= 0:
            net_debt_to_ebitda = (weights["net_debt_to_ebitda"], 0.0, "")
        else:
            net_debt_to_ebitda = (
                weights["net_debt_to_ebitda"],
                self._scale(net_debt / ebitda_proxy, self.NET_DEBT_TO_EBITDA),
                "нет 2200 (прокси EBITDA)",
            )
        return self._combine([debt_to_equity, net_debt_to_ebitda])

    def debt_service(self) -> tuple[float | None, str | None]:
        interest = self._num(self.financial.get("interest_payable"))
        before_tax = self._num(self.financial.get("before_tax"))
        debt = self._sum(self.financial.get("longterm_debt"), self.financial.get("shortterm_debt"))

        if interest is None:
            return None, "нет 2330 (interest_payable): блок выбывает"
        if interest == 0:
            if debt is not None and debt == 0:
                return 1.0, None
            return None, "2330 = 0 при ненулевом/неизвестном долге: знаменатель 0"
        if before_tax is None:
            return None, "нет 2300 (before_tax)"
        return self.f(self._ratio(before_tax + interest, interest), *self.DEBT_SERVICE_COVERAGE), None

    def liquidity(self) -> tuple[float | None, str | None]:
        current_assets = self._num(self.financial.get("current_assets"))
        shortterm_liab = self._num(self.financial.get("shortterm_liab"))

        if current_assets is None or shortterm_liab is None:
            return None, "нет 1200/1500 (запасной вариант 1250/1520 недоступен: в БД нет 1520)"
        if shortterm_liab == 0:
            return None, "1500 = 0: коэффициент не рассчитывается"

        ktl = current_assets / shortterm_liab
        if ktl > 1.5:
            return 1.0, None
        if ktl >= 1.25:
            return 0.75, None
        if ktl >= 1.0:
            return 0.5, None
        if ktl >= 0.8:
            return 0.25, None
        return 0.0, None

    def cash_flow(self) -> tuple[float | None, str | None]:
        weights = self.weights["term_weights"]["cash_flow"]
        cash_flow = self._num(self.financial.get("balance_operating"))
        if cash_flow is None:
            return None, "нет 4100 (balance_operating): блок выбывает"

        revenue = self._num(self.financial.get("revenue"))
        debt = self._sum(self.financial.get("longterm_debt"), self.financial.get("shortterm_debt"))
        parts = [
            (
                weights["cfo_to_revenue"],
                self._scale(self._ratio(cash_flow, revenue), self.CFO_TO_REVENUE),
                "нет (или <= 0) 2110",
            )
        ]
        if debt is None:
            parts.append((weights["cfo_to_debt"], None, "нет одной из строк 1410/1510"))
        elif debt == 0:
            parts.append((weights["cfo_to_debt"], 1.0, ""))
        else:
            parts.append((weights["cfo_to_debt"], self.f(self._ratio(cash_flow, debt), *self.CFO_TO_DEBT), ""))
        return self._combine(parts)

    # ----------------------------- служебные расчёты -----------------------------

    def _industry_params(self) -> tuple[str, float | None, dict, bool]:
        groups = self.weights["industry_groups"]
        industry = self.company.get("industry")
        code = None if industry is None else str(industry).strip().upper()[:2]
        group_key = None
        if code:
            section = code[:1]
            for key, group in groups.items():
                if (
                    code in group.get("okved_codes", [])
                    or section in group.get("okved_sections", [])
                    or code in group.get("okved_sections", [])
                ):
                    group_key = key
                    break
        matched = group_key is not None
        if group_key is None:
            group_key = str(self.weights.get("default_industry_group", 10))
        group = groups[group_key]

        w_otr = self._num(group.get("w_otr_pct")) / 100.0
        w_operational = (1.0 - w_otr) / 2.0
        w_financial = (1.0 - w_otr) / 2.0
        alpha = self.weights["block_alpha"]
        block_weights = {
            "industry": w_otr,
            "market_position": w_operational * alpha["operational"]["market_position"],
            "business_profile": w_operational * alpha["operational"]["business_profile"],
            "size": w_financial * alpha["financial"]["size"],
            "profitability": w_financial * alpha["financial"]["profitability"],
            "debt_load": w_financial * alpha["financial"]["debt_load"],
            "debt_service": w_financial * alpha["financial"]["debt_service"],
            "liquidity": w_financial * alpha["financial"]["liquidity"],
            "cash_flow": w_financial * alpha["financial"]["cash_flow"],
        }
        return group_key, self._num(group.get("s_otr")), block_weights, matched

    def _bounds(self, scope: str, key: str, log: bool = False) -> tuple[float, float] | None:
        """Пороги (a, b) из API-процентилей; для ln — логарифмируем."""
        pair = self.percentiles.get(scope, {}).get(key)
        if pair is None:
            return None
        low, high = pair
        if low is None or high is None or low >= high:
            return None
        if log:
            if low <= 0:
                return None
            return math.log(low), math.log(high)
        return low, high

    def _age(self) -> float | None:
        """Возраст по дате регистрации на 31.12 отчётного года."""
        registered = self._as_date(self.company.get("registration_date"))
        if registered is None or self.year is None:
            return None
        return (datetime.date(int(self.year), 12, 31) - registered).days / 365.25

    def _management(self) -> float | None:
        """S_упр: 1, если 1300 > 0 и 1370 >= 0; 0.5, если 1300 > 0 и 1370 < 0; 0, если 1300 <= 0."""
        equity = self._num(self.financial.get("total_equity"))
        retained = self._num(self.financial.get("retained_earnings"))
        if equity is None:
            return None
        if equity <= 0:
            return 0.0
        if retained is None:
            return None
        return 1.0 if retained >= 0 else 0.5

    @staticmethod
    def f(x, a, b) -> float | None:
        """f(x; a, b) = min(1, max(0, (x - a) / (b - a))); при a > b «чем меньше, тем лучше»."""
        if x is None or a is None or b is None or a == b:
            return None
        return min(1.0, max(0.0, (x - a) / (b - a)))

    @staticmethod
    def _scale(value: float | None, bounds: tuple[float, float] | None) -> float | None:
        if value is None or bounds is None:
            return None
        return Financial_Risk_Score.f(value, bounds[0], bounds[1])

    @staticmethod
    def _combine(parts) -> tuple[float | None, str | None]:
        """S = sum(w_i * S_i) / sum(w_i); None-слагаемые выбывают, веса не обнуляются."""
        total_weight = 0.0
        weighted_sum = 0.0
        reasons: list[str] = []
        for weight, value, reason in parts:
            if value is None:
                if reason:
                    reasons.append(reason)
                continue
            total_weight += weight
            weighted_sum += weight * value
        if total_weight == 0.0:
            return None, "; ".join(reasons) if reasons else "нет данных"
        score = weighted_sum / total_weight
        if reasons:
            return score, "не рассчитаны: " + "; ".join(reasons)
        return score, None

    @staticmethod
    def normalize_financial(financial: dict) -> dict:
        normalized = {}
        for key, value in (financial or {}).items():
            key_str = str(key).strip()
            normalized[config.LINE_TO_COLUMN.get(key_str, key_str)] = value
        return normalized

    @staticmethod
    def _num(value) -> float | None:
        """Приводит значение из БД (NUMERIC -> Decimal) или ручного ввода к float, NULL -> None."""
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _ratio(numerator, denominator) -> float | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _ln(value: float | None) -> float | None:
        if value is None or value <= 0:
            return None
        return math.log(value)

    @staticmethod
    def _sum(*values) -> float | None:
        """Сумма; если хотя бы одно слагаемое неизвестно (NULL) — результат неизвестен."""
        total = 0.0
        for value in values:
            number = Financial_Risk_Score._num(value)
            if number is None:
                return None
            total += number
        return total

    @staticmethod
    def _as_date(value) -> datetime.date | None:
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value.strip()[:10])
            except ValueError:
                return None
        return None