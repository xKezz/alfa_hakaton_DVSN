import { useEffect, useState } from "react";
import {
  Button,
  EmptyState,
  Field,
  ScoreGauge,
  Tabs,
  Timeline,
} from "../components/ui.jsx";
import { getCompany } from "../api.js";
import { formatDate, formatMoney, formatMonths } from "../data/mock.js";

const TABS = [
  { id: "company", label: "Компания" },
  { id: "finance", label: "Финансы" },
  { id: "checks", label: "Проверки" },
  { id: "scoring", label: "Скоринг" },
  { id: "history", label: "История" },
];

const DECISION_OPTIONS = [
  { id: "approve", label: "Одобрить" },
  { id: "reject", label: "Отказать" },
  { id: "alternative", label: "Альтернативные условия" },
];

function BankApplicationPanel({ application, company, companyError, isCompanyLoading, onDecision }) {
  const [activeTab, setActiveTab] = useState("company");
  const [decision, setDecision] = useState("");
  const [reason, setReason] = useState("");
  const [success, setSuccess] = useState("");
  const [formError, setFormError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!decision) {
      setFormError("Выберите решение по заявке");
      return;
    }
    if (reason.trim().length < 5) {
      setFormError("Укажите обоснование решения (минимум 5 символов)");
      return;
    }
    setFormError("");
    const label = DECISION_OPTIONS.find((option) => option.id === decision)?.label;
    setSuccess(`Решение «${label}» зафиксировано. Заявка обновлена.`);
    onDecision(application.id, decision, reason.trim());
  }

  return (
    <section className="card bank-detail" aria-label={`Заявка ${application.id}`}>
      <div className="bank-detail-head">
        <h2 className="bank-detail-title">Заявка {application.id}</h2>
        <p className="bank-detail-sub">
          {company ? company.company_name : "Компания"} • {formatMoney(application.amount)} •{" "}
          {formatMonths(application.termMonths)}
        </p>
      </div>

      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      <div className="bank-detail-body">
        {activeTab === "company" && (
          <>
            {isCompanyLoading && <p className="muted-sm">Загрузка данных компании…</p>}
            {companyError && <div className="notice notice-warn">{companyError}</div>}
            {company && (
              <>
                <h3 className="subsection-title">{company.company_name || "Компания без названия"}</h3>
                <div className="readonly-grid">
                  <div>
                    <div className="readonly-label">ИНН</div>
                    <div className="readonly-value">{company.inn}</div>
                  </div>
                  <div>
                    <div className="readonly-label">Статус компании</div>
                    <div className="readonly-value">{company.company_status || "—"}</div>
                  </div>
                  <div>
                    <div className="readonly-label">Дата регистрации</div>
                    <div className="readonly-value">{formatDate(company.registration_date)}</div>
                  </div>
                  <div>
                    <div className="readonly-label">Отрасль (код)</div>
                    <div className="readonly-value">{company.industry || "—"}</div>
                  </div>
                  <div>
                    <div className="readonly-label">Регион (код)</div>
                    <div className="readonly-value">{company.region_code || "—"}</div>
                  </div>
                  <div>
                    <div className="readonly-label">УСН</div>
                    <div className="readonly-value">{company.is_simplified_tax ? "Да" : "Нет"}</div>
                  </div>
                  <div>
                    <div className="readonly-label">Признак ликвидации</div>
                    <div className="readonly-value">{company.dissolution_flag ? "Есть" : "Нет"}</div>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {activeTab === "finance" && (
          <>
            <h3 className="subsection-title">Финансовые показатели</h3>
            <div className="fin-table-wrap">
              <table className="fin-table">
                <thead>
                  <tr>
                    <th>Показатель</th>
                    <th className="numeric">Значение, ₽</th>
                    <th className="numeric">Динамика</th>
                  </tr>
                </thead>
                <tbody>
                  {application.finance.map((row) => (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td className="numeric">{formatMoney(row.value)}</td>
                      <td className="numeric">
                        {row.delta ? (
                          <span className={row.delta.startsWith("-") ? "delta-neg" : "delta-pos"}>
                            {row.delta}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="chart-card">
              <div className="bar-chart" aria-label="Динамика выручки по годам">
                {application.chart.map((bar) => (
                  <div
                    key={bar.year}
                    className="bar"
                    style={{ height: `${Math.max(12, bar.value)}%` }}
                    title={`${bar.year}: ${bar.value}%`}
                  />
                ))}
              </div>
              <div className="chart-caption">
                <span>{application.chart[0]?.year}</span>
                <span>Динамика выручки, демо-данные</span>
                <span>{application.chart[application.chart.length - 1]?.year}</span>
              </div>
            </div>
          </>
        )}

        {activeTab === "checks" && (
          <>
            <h3 className="subsection-title">Результаты проверок</h3>
            {application.checks.length === 0 ? (
              <p className="muted-sm">Результаты проверок пока недоступны.</p>
            ) : (
              <div className="checks-list">
                {application.checks.map((check) => (
                  <div
                    key={check.text}
                    className={`check-item ${check.ok ? "check-ok" : "check-warn"}`}
                  >
                    <span className="check-icon">{check.ok ? "✓" : "!"}</span>
                    {check.text}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {activeTab === "scoring" && (
          <>
            <h3 className="subsection-title">Скоринговая оценка</h3>
            <div className="score-card">
              <ScoreGauge score={application.scoring.score} level={application.scoring.level} />
              <div>
                <div className={`risk-title risk-${application.scoring.level}`}>
                  {application.scoring.category}
                </div>
                <div className="hint-sm" style={{ marginTop: 4 }}>
                  Маршрут: {application.scoring.route}
                </div>
              </div>
            </div>
            <div className="factors">
              <div className="factor-col is-pos">
                <h4>Факторы +</h4>
                <ul>
                  {application.scoring.positives.map((factor) => (
                    <li key={factor}>{factor}</li>
                  ))}
                </ul>
              </div>
              <div className="factor-col is-neg">
                <h4>Факторы −</h4>
                <ul>
                  {application.scoring.negatives.map((factor) => (
                    <li key={factor}>{factor}</li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        )}

        {activeTab === "history" && (
          <>
            <h3 className="subsection-title">История обработки</h3>
            <Timeline
              events={application.history}
              currentTitle={application.history[0]?.title}
            />
          </>
        )}
      </div>

      <div className="bank-footer">
        {success ? (
          <div className="decision-success">✓ {success}</div>
        ) : (
          <form className="decision-form" onSubmit={handleSubmit}>
            <h3 className="decision-title">Принятие решения</h3>
            <div className="radio-row">
              {DECISION_OPTIONS.map((option) => (
                <label className="radio" key={option.id}>
                  <input
                    type="radio"
                    name={`decision-${application.id}`}
                    value={option.id}
                    checked={decision === option.id}
                    onChange={(event) => {
                      setDecision(event.target.value);
                      setFormError("");
                    }}
                  />
                  {option.label}
                </label>
              ))}
            </div>
            <Field
              label="Обоснование решения (обязательно)"
              htmlFor={`reason-${application.id}`}
              error={formError}
              hint="Минимум 5 символов"
            >
              <textarea
                id={`reason-${application.id}`}
                className={`input${formError ? " has-error" : ""}`}
                placeholder="Укажите обоснование принятого решения"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                  setFormError("");
                }}
              />
            </Field>
            <div className="decision-actions">
              <Button
                type="submit"
                variant="dark"
                disabled={!decision || reason.trim().length < 5}
              >
                Зафиксировать решение
              </Button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

export default function BankWorkspace({ queue, onDecision }) {
  const [selectedId, setSelectedId] = useState(queue[0]?.id ?? null);

  const effectiveSelectedId = queue.some((item) => item.id === selectedId)
    ? selectedId
    : (queue[0]?.id ?? null);
  const selected = queue.find((item) => item.id === effectiveSelectedId) ?? null;
  const selectedCompanyInn = selected?.companyInn ?? null;

  const [companyState, setCompanyState] = useState({ inn: null, company: null, error: "" });

  const company = companyState.inn === selectedCompanyInn ? companyState.company : null;
  const companyError = companyState.inn === selectedCompanyInn ? companyState.error : "";
  const isCompanyLoading =
    Boolean(selectedCompanyInn) && companyState.inn !== selectedCompanyInn && !companyError;

  useEffect(() => {
    if (!selectedCompanyInn) return undefined;
    let active = true;
    getCompany(selectedCompanyInn).then((result) => {
      if (!active) return;
      setCompanyState(
        result.ok
          ? { inn: selectedCompanyInn, company: result.company, error: "" }
          : { inn: selectedCompanyInn, company: null, error: result.message }
      );
    });
    return () => {
      active = false;
    };
  }, [selectedCompanyInn]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Очередь ручной проверки</h1>
          <p className="page-subtitle">
            Заявки, требующие решения сотрудника: {queue.length}
          </p>
        </div>
      </div>

      {queue.length === 0 ? (
        <EmptyState
          icon="✅"
          title="Очередь пуста"
          text="Все заявки, требующие ручной проверки, обработаны. Новые заявки появятся здесь автоматически."
        />
      ) : (
        <div className="bank-layout">
          <section className="card bank-queue" aria-label="Список заявок на проверке">
            <div className="bank-queue-head">Заявки на проверке</div>
            <div className="bank-queue-list">
              {queue.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`queue-item${item.id === effectiveSelectedId ? " is-active" : ""}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="queue-item-top">
                    <span>{item.id}</span>
                    <span>{formatMoney(item.amount)}</span>
                  </div>
                  <div className="queue-item-meta">Дата: {formatDate(item.date)}</div>
                  <div className="queue-item-reason">Причина: {item.reason}</div>
                </button>
              ))}
            </div>
          </section>

          {selected && (
            <BankApplicationPanel
              key={selected.id}
              application={selected}
              company={company}
              companyError={companyError}
              isCompanyLoading={isCompanyLoading}
              onDecision={onDecision}
            />
          )}
        </div>
      )}
    </div>
  );
}
