import { useEffect, useMemo, useState } from "react";
import { ApiStatus, Button, EmptyState, Field, Segmented } from "../components/ui.jsx";
import { getCompany, getLatestFinancialStatement, getLoanProducts } from "../api.js";
import {
  BUSINESS_AGE_TYPES,
  BUSINESS_TYPES,
  LOAN_PURPOSES,
  PURPOSE_ICONS,
  formatDate,
  formatMoney,
  formatRate,
  monthlyPayment,
} from "../data/mock.js";

const AMOUNT_MIN = 50000;
const AMOUNT_MAX = 30000000;
const AMOUNT_STEP = 50000;
const DEFAULT_AMOUNT = 4150000;
const DEFAULT_TERM_YEARS = 3;
const PURPOSE_ALL = "all";

function defaultForm(company) {
  return {
    inn: company?.inn || "",
    revenue: "",
    profit: "",
    obligations: "",
    purpose: LOAN_PURPOSES[0].value,
  };
}

function readStoredProfile() {
  try {
    const raw = localStorage.getItem("ipProfile");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function normalizeProduct(product) {
  return {
    id: product.product_id,
    title: product.product_name,
    subtitle: product.description || "",
    icon: PURPOSE_ICONS[product.loan_purpose] || "💳",
    rate: Number(product.percent),
    minAmount: Number(product.min_amount),
    maxAmount: Number(product.max_amount),
    minTermMonths: product.min_term_months,
    maxTermMonths: product.max_term_months,
    loanPurpose: product.loan_purpose,
    minBusinessAge: product.business_age,
  };
}

export default function CreditCalculator({ defaultCompany, health, onApply }) {
  const [bizType, setBizType] = useState("ip");
  const [bizAge, setBizAge] = useState("more3");
  const [purpose, setPurpose] = useState(PURPOSE_ALL);
  const [amount, setAmount] = useState(DEFAULT_AMOUNT);
  const [termYears, setTermYears] = useState(DEFAULT_TERM_YEARS);

  const [selectedProductId, setSelectedProductId] = useState(null);
  const [detailsProductId, setDetailsProductId] = useState(null);
  const [form, setForm] = useState(() => defaultForm(defaultCompany));
  const [fieldErrors, setFieldErrors] = useState({});
  const [lookup, setLookup] = useState({ state: "idle", company: null, error: null });
  const [fillStatus, setFillStatus] = useState({ state: "idle", message: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [catalog, setCatalog] = useState({ key: null, products: [], error: null });

  const months = termYears * 12;
  const userAgeMonths = bizAge === "more3" ? 36 : 3;

  const queryKey = useMemo(
    () =>
      JSON.stringify({
        amount,
        months,
        bizType,
        purpose,
        userAgeMonths,
      }),
    [amount, months, bizType, purpose, userAgeMonths]
  );

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      getLoanProducts({
        amount,
        termMonths: months,
        businessCategory: bizType,
        purpose,
        businessAgeMonths: userAgeMonths,
      }).then((result) => {
        if (!active) return;
        setCatalog(
          result.ok
            ? { key: queryKey, products: result.products, error: null }
            : { key: queryKey, products: [], error: result.message }
        );
      });
    }, 250);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [queryKey, reloadKey, amount, months, bizType, purpose, userAgeMonths]);

  const isCatalogLoading = catalog.key !== queryKey && !catalog.error;
  const catalogProducts = catalog.key === queryKey ? catalog.products : [];
  const catalogError = catalog.key === queryKey ? catalog.error : null;

  const products = catalogProducts.map(normalizeProduct);

  const selectedProduct = products.find((product) => product.id === selectedProductId) || null;

  function resetForm(product) {
    setSelectedProductId(product.id);
    setDetailsProductId(null);
    setFieldErrors({});
    setLookup({ state: "idle", company: null, error: null });
    setForm((previous) => ({
      ...previous,
      inn: previous.inn || defaultCompany?.inn || "",
      purpose: purpose === PURPOSE_ALL ? previous.purpose : purpose,
    }));
  }

  function updateField(name, value) {
    setFieldErrors((previous) => ({ ...previous, [name]: undefined }));
    setFillStatus({ state: "idle", message: "" });
    setForm((previous) => ({ ...previous, [name]: value }));
  }

  async function handleFillFromProfile() {
    setLookup({ state: "loading", company: null, error: null });
    setFillStatus({ state: "idle", message: "" });

    const profile = readStoredProfile();
    const inn = String(profile.inn || defaultCompany?.inn || form.inn || "").trim();
    if (!inn) {
      setLookup({
        state: "error",
        company: null,
        error: { message: "Профиль не заполнен: укажите ИНН вручную." },
      });
      return;
    }

    const [companyResult, statementResult] = await Promise.all([
      getCompany(inn),
      getLatestFinancialStatement(inn),
    ]);

    const updates = { inn };
    if (statementResult.ok) {
      const statement = statementResult.statement;
      updates.revenue =
        statement.revenue === null || statement.revenue === undefined
          ? ""
          : String(Number(statement.revenue));
      updates.profit =
        statement.net_profit === null || statement.net_profit === undefined
          ? ""
          : String(Number(statement.net_profit));
      updates.obligations =
        statement.shortterm_liab === null || statement.shortterm_liab === undefined
          ? ""
          : String(Number(statement.shortterm_liab));
    } else {
      // если в localStorage профиля когда-то появятся финансовые поля, используем их
      if (profile.revenue !== undefined && profile.revenue !== "") {
        updates.revenue = String(profile.revenue);
      }
      if (profile.profit !== undefined && profile.profit !== "") {
        updates.profit = String(profile.profit);
      }
      if (profile.obligations !== undefined && profile.obligations !== "") {
        updates.obligations = String(profile.obligations);
      }
    }

    setForm((previous) => ({ ...previous, ...updates }));
    setFieldErrors({});

    if (companyResult.ok) {
      setLookup({ state: "ok", company: companyResult.company, error: null });
    } else if (profile.businessName) {
      setLookup({
        state: "ok",
        company: {
          inn,
          company_name: profile.businessName,
          company_status: null,
          registration_date: null,
          is_simplified_tax: null,
        },
        error: null,
      });
    } else {
      setLookup({
        state: "error",
        company: null,
        error: { message: companyResult.message },
      });
    }

    if (statementResult.ok) {
      setFillStatus({
        state: "ok",
        message: `Данные заполнены из профиля. Финансовые показатели — из отчётности за ${statementResult.statement.report_year} год (PostgreSQL).`,
      });
    } else if (statementResult.type === "not_found") {
      setFillStatus({
        state: "warn",
        message:
          "Данные профиля подставлены, но финансовой отчётности в БД нет — заполните показатели вручную.",
      });
    } else {
      setFillStatus({
        state: "warn",
        message: `Данные профиля подставлены. ${statementResult.message}`,
      });
    }
  }

  function handleRetry() {
    setCatalog({ key: null, products: [], error: null });
    setReloadKey((value) => value + 1);
  }

  function resetFilters() {
    setBizType("ip");
    setBizAge("more3");
    setPurpose(PURPOSE_ALL);
    setAmount(DEFAULT_AMOUNT);
    setTermYears(DEFAULT_TERM_YEARS);
    setSelectedProductId(null);
    setDetailsProductId(null);
  }

  function validate() {
    const errors = {};
    if (!/^\d{10}(\d{2})?$/.test(String(form.inn).trim())) {
      errors.inn = "ИНН должен состоять из 10 или 12 цифр";
    }
    const revenue = Number(form.revenue);
    if (!form.revenue || Number.isNaN(revenue) || revenue <= 0) {
      errors.revenue = "Укажите выручку за отчётный год";
    }
    if (form.profit === "" || Number.isNaN(Number(form.profit))) {
      errors.profit = "Укажите чистую прибыль (может быть отрицательной)";
    }
    if (form.obligations === "" || Number.isNaN(Number(form.obligations))) {
      errors.obligations = "Укажите текущие кредитные обязательства";
    }
    return errors;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    if (!selectedProduct) return;

    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 400));

    onApply({
      product: selectedProduct,
      amount,
      termMonths: months,
      purpose: form.purpose,
      inn: String(form.inn).trim(),
      company: lookup.company || defaultCompany,
      revenue: Number(form.revenue),
      profit: Number(form.profit),
      obligations: Number(form.obligations),
      revenueSource: lookup.state === "ok" ? "api" : "manual",
    });
    setIsSubmitting(false);
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Подбор кредита</h1>
          <p className="page-subtitle">
            Активные продукты из каталога банка (таблица loan_catalog). Расчёты демонстрационные.
          </p>
        </div>
        <div className="page-head-actions">
          <ApiStatus health={health} />
        </div>
      </div>

      <div className="calc-layout">
        <aside className="calc-filters">
          <h2 className="calc-filters-title">Рассчитаем кредит под вашу задачу</h2>

          <div className="filter-group">
            <div className="filter-label">Тип регистрации</div>
            <Segmented options={BUSINESS_TYPES} value={bizType} onChange={setBizType} ariaLabel="Тип регистрации" />
          </div>

          <div className="filter-group">
            <label className="filter-label" htmlFor="loanPurpose">
              Цель кредитования
            </label>
            <select
              id="loanPurpose"
              className="input"
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
            >
              <option value={PURPOSE_ALL}>Все цели</option>
              {LOAN_PURPOSES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <div className="filter-label">Срок ведения бизнеса</div>
            <Segmented options={BUSINESS_AGE_TYPES} value={bizAge} onChange={setBizAge} ariaLabel="Срок ведения бизнеса" />
          </div>

          <div className="slider-card">
            <div className="slider-label">Сумма кредита</div>
            <div className="slider-value">{formatMoney(amount)}</div>
            <input
              className="range"
              type="range"
              min={AMOUNT_MIN}
              max={AMOUNT_MAX}
              step={AMOUNT_STEP}
              value={amount}
              aria-label="Сумма кредита"
              onChange={(event) => setAmount(Number(event.target.value))}
            />
            <div className="range-scale">
              <span>50 тыс ₽</span>
              <span>15 млн ₽</span>
              <span>30 млн ₽</span>
            </div>
          </div>

          <div className="slider-card">
            <div className="slider-label">Срок кредита</div>
            <div className="slider-value">
              {termYears} {termYears === 1 ? "год" : termYears < 5 ? "года" : "лет"}
            </div>
            <input
              className="range"
              type="range"
              min={1}
              max={10}
              step={1}
              value={termYears}
              aria-label="Срок кредита"
              onChange={(event) => setTermYears(Number(event.target.value))}
            />
            <div className="range-scale">
              <span>1 год</span>
              <span>5 лет</span>
              <span>10 лет</span>
            </div>
          </div>

          <p className="hint-sm">
            Ставки и условия загружаются из loan_catalog (PostgreSQL) и не являются офертой банка.
          </p>
        </aside>

        <section className="calc-results">
          {isCatalogLoading && (
            <div className="skeleton-list" aria-label="Загрузка кредитных продуктов">
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          )}

          {!isCatalogLoading && catalogError && (
            <>
              <div className="notice notice-warn">{catalogError}</div>
              <div>
                <Button variant="secondary" size="sm" onClick={handleRetry}>
                  Повторить загрузку
                </Button>
              </div>
            </>
          )}

          {!isCatalogLoading && !catalogError && products.length === 0 && (
            <EmptyState
              icon="🔍"
              title="Подходящих продуктов нет"
              text="Измените цель, сумму, срок, категорию или возраст бизнеса."
              action={
                <Button variant="secondary" onClick={resetFilters}>
                  Сбросить фильтры
                </Button>
              }
            />
          )}

          {!isCatalogLoading && !catalogError && products.length > 0 && (
            <p className="hint-sm" style={{ marginBottom: 4 }}>
              Найдено продуктов: {products.length}
            </p>
          )}

          {!isCatalogLoading &&
            !catalogError &&
            products.map((product) => {
              const payment = monthlyPayment(amount, product.rate, months);
              const overpayment = payment ? payment * months - amount : null;
              const isSelected = selectedProductId === product.id;
              const isDetails = detailsProductId === product.id;

              return (
                <article className="card product-card" key={product.id}>
                  <div className="product-head">
                    <div>
                      <h3 className="product-title">{product.title}</h3>
                      <p className="product-subtitle">{product.subtitle}</p>
                    </div>
                    <div className="product-icon" aria-hidden="true">
                      {product.icon}
                    </div>
                  </div>

                  <div className="product-metrics">
                    <div>
                      <div className="metric-label">Ставка</div>
                      <div className="metric-value">{formatRate(product.rate)}</div>
                    </div>
                    <div>
                      <div className="metric-label">Переплата</div>
                      <div className="metric-value">{overpayment ? formatMoney(overpayment) : "—"}</div>
                    </div>
                    <div>
                      <div className="metric-label">Платёж</div>
                      <div className="metric-value">{payment ? formatMoney(payment) : "—"}</div>
                    </div>
                  </div>

                  <div className="product-actions">
                    <Button
                      variant="secondary"
                      onClick={() =>
                        setDetailsProductId((current) => (current === product.id ? null : product.id))
                      }
                    >
                      {isDetails ? "Свернуть" : "Узнать подробнее"}
                    </Button>
                    <Button variant="primary" onClick={() => resetForm(product)}>
                      Заполнить заявку
                    </Button>
                  </div>

                  {isDetails && (
                    <div className="company-result" style={{ marginTop: 16 }}>
                      <div>
                        <div className="company-result-label">Базовая ставка</div>
                        <div className="company-result-value">{formatRate(product.rate)} годовых</div>
                      </div>
                      <div>
                        <div className="company-result-label">Сумма</div>
                        <div className="company-result-value">
                          {formatMoney(product.minAmount)} — {formatMoney(product.maxAmount)}
                        </div>
                      </div>
                      <div>
                        <div className="company-result-label">Срок</div>
                        <div className="company-result-value">
                          {product.minTermMonths} — {product.maxTermMonths} мес.
                        </div>
                      </div>
                      <div>
                        <div className="company-result-label">Возраст бизнеса</div>
                        <div className="company-result-value">от {product.minBusinessAge} мес.</div>
                      </div>
                    </div>
                  )}

                  {isSelected && selectedProduct && (
                    <form className="apply-panel" onSubmit={handleSubmit} noValidate>
                      <h4 className="apply-title">
                        Заявка на «{product.title}» · {formatMoney(amount)} · {months} мес.
                      </h4>

                      <div className="form-grid">
                        <Field label="ИНН компании" htmlFor="applyInn" error={fieldErrors.inn}>
                          <input
                            id="applyInn"
                            className={`input${fieldErrors.inn ? " has-error" : ""}`}
                            value={form.inn}
                            inputMode="numeric"
                            maxLength={12}
                            placeholder="10 или 12 цифр"
                            onChange={(event) => {
                              updateField("inn", event.target.value);
                              setLookup({ state: "idle", company: null, error: null });
                            }}
                          />
                        </Field>
                        <div className="field">
                          <span className="field-label">Данные из профиля</span>
                          <div className="row row-wrap">
                            <Button
                              variant="secondary"
                              onClick={handleFillFromProfile}
                              loading={lookup.state === "loading"}
                            >
                              Заполнить из профиля
                            </Button>
                          </div>
                          <span className="field-hint">
                            ИНН и данные компании — из профиля, финансовые показатели — из
                            последней отчётности в БД.
                          </span>
                        </div>

                        <Field label="Выручка за отчётный год, ₽" htmlFor="applyRevenue" error={fieldErrors.revenue}>
                          <input
                            id="applyRevenue"
                            className={`input${fieldErrors.revenue ? " has-error" : ""}`}
                            inputMode="numeric"
                            placeholder="Например, 10 000 000"
                            value={form.revenue}
                            onChange={(event) => updateField("revenue", event.target.value)}
                          />
                        </Field>
                        <Field label="Чистая прибыль за отчётный год, ₽" htmlFor="applyProfit" error={fieldErrors.profit}>
                          <input
                            id="applyProfit"
                            className={`input${fieldErrors.profit ? " has-error" : ""}`}
                            inputMode="numeric"
                            placeholder="Например, 2 000 000"
                            value={form.profit}
                            onChange={(event) => updateField("profit", event.target.value)}
                          />
                        </Field>
                        <Field
                          label="Текущие кредитные обязательства, ₽"
                          htmlFor="applyObligations"
                          error={fieldErrors.obligations}
                        >
                          <input
                            id="applyObligations"
                            className={`input${fieldErrors.obligations ? " has-error" : ""}`}
                            inputMode="numeric"
                            placeholder="Например, 500 000"
                            value={form.obligations}
                            onChange={(event) => updateField("obligations", event.target.value)}
                          />
                        </Field>
                        <Field label="Цель кредитования" htmlFor="applyPurpose">
                          <select
                            id="applyPurpose"
                            className="input"
                            value={form.purpose}
                            onChange={(event) => updateField("purpose", event.target.value)}
                          >
                            {LOAN_PURPOSES.map((item) => (
                              <option key={item.value} value={item.value}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                        </Field>
                      </div>

                      {fillStatus.state !== "idle" && (
                        <div
                          className={`notice${fillStatus.state === "warn" ? " notice-warn" : ""}`}
                          style={{ marginTop: 16 }}
                        >
                          {fillStatus.message}
                        </div>
                      )}

                      {lookup.state === "error" && (
                        <div className="notice notice-warn" style={{ marginTop: 16 }}>
                          {lookup.error?.message || "Не удалось получить данные компании."}
                        </div>
                      )}

                      {lookup.company && (
                        <div className="company-result">
                          <div>
                            <div className="company-result-label">Компания</div>
                            <div className="company-result-value">{lookup.company.company_name || "—"}</div>
                          </div>
                          <div>
                            <div className="company-result-label">ИНН</div>
                            <div className="company-result-value">{lookup.company.inn}</div>
                          </div>
                          <div>
                            <div className="company-result-label">Статус</div>
                            <div className="company-result-value">{lookup.company.company_status || "—"}</div>
                          </div>
                          <div>
                            <div className="company-result-label">Дата регистрации</div>
                            <div className="company-result-value">{formatDate(lookup.company.registration_date)}</div>
                          </div>
                          <div>
                            <div className="company-result-label">УСН</div>
                            <div className="company-result-value">{lookup.company.is_simplified_tax ? "Да" : "Нет"}</div>
                          </div>
                        </div>
                      )}

                      <div className="form-actions">
                        <Button variant="ghost" onClick={() => setSelectedProductId(null)}>
                          Отмена
                        </Button>
                        <Button type="submit" variant="primary" loading={isSubmitting}>
                          Отправить заявку
                        </Button>
                      </div>
                    </form>
                  )}
                </article>
              );
            })}
        </section>
      </div>
    </div>
  );
}
