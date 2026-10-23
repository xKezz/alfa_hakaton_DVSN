import { useMemo, useState } from "react";
import { Button, EmptyState, Segmented, StatusBadge } from "../components/ui.jsx";
import { STATUS_FILTERS, formatDate, formatMoney, formatMonths } from "../data/mock.js";

const ACTIVE_STATUSES = ["submitted", "processing", "manual_review"];

function matchesFilter(application, filter) {
  if (filter === "all") return true;
  if (filter === "active") return ACTIVE_STATUSES.includes(application.status);
  return application.status === filter;
}

export default function EntrepreneurDashboard({
  applications,
  company,
  isLoading,
  onOpenApplication,
  onNewApplication,
}) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const visibleApplications = useMemo(() => {
    const query = search.trim().toLowerCase();
    return applications.filter((application) => {
      if (!matchesFilter(application, filter)) return false;
      if (!query) return true;
      return (
        application.id.toLowerCase().includes(query) ||
        application.productTitle.toLowerCase().includes(query)
      );
    });
  }, [applications, filter, search]);

  const activeCount = applications.filter((application) =>
    ACTIVE_STATUSES.includes(application.status)
  ).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Мои заявки</h1>
          <p className="page-subtitle">
            {applications.length} заявок · {activeCount} в работе · компания:{" "}
            {company?.company_name || "не указана"}
          </p>
        </div>
        <div className="page-head-actions">
          <Button variant="dark" onClick={onNewApplication}>
            Новая заявка
          </Button>
        </div>
      </div>

      <section className="card card-pad" style={{ marginBottom: 16 }}>
        <div className="spread" style={{ marginBottom: 14 }}>
          <h2 className="section-title">Компания</h2>
          <span className="badge badge-neutral">{company?.company_status || "Данные не загружены"}</span>
        </div>
        <div className="profile-grid">
          <div>
            <div className="readonly-label">Название</div>
            <div className="readonly-value">{company?.company_name || "—"}</div>
          </div>
          <div>
            <div className="readonly-label">ИНН</div>
            <div className="readonly-value">{company?.inn || "—"}</div>
          </div>
          <div>
            <div className="readonly-label">Дата регистрации</div>
            <div className="readonly-value">{formatDate(company?.registration_date)}</div>
          </div>
          <div>
            <div className="readonly-label">Налоговый режим</div>
            <div className="readonly-value">
              {company ? (company.is_simplified_tax ? "УСН" : "ОСНО / не указан") : "—"}
            </div>
          </div>
        </div>
      </section>

      <div className="toolbar">
        <Segmented
          options={STATUS_FILTERS}
          value={filter}
          onChange={setFilter}
          ariaLabel="Фильтр по статусу заявки"
        />
        <input
          className="input search-input"
          type="search"
          placeholder="Поиск по номеру или продукту"
          aria-label="Поиск по заявкам"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="skeleton-list" aria-label="Загрузка заявок">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : applications.length === 0 ? (
        <EmptyState
          icon="📄"
          title="У вас пока нет заявок"
          text="Подберите кредитный продукт и отправьте первую заявку — статус рассмотрения появится здесь."
          action={
            <Button variant="primary" onClick={onNewApplication}>
              Создать первую заявку
            </Button>
          }
        />
      ) : visibleApplications.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="Ничего не найдено"
          text="По выбранному фильтру и поисковому запросу заявок нет."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setFilter("all");
                setSearch("");
              }}
            >
              Сбросить фильтры
            </Button>
          }
        />
      ) : (
        <div className="app-list">
          {visibleApplications.map((application) => (
            <article className="card application-card" key={application.id}>
              <div className="application-fields">
                <div className="application-field">
                  <div className="label">№ заявки</div>
                  <div className="value">{application.id}</div>
                </div>
                <div className="application-field">
                  <div className="label">Дата подачи</div>
                  <div className="value">{formatDate(application.date)}</div>
                </div>
                <div className="application-field">
                  <div className="label">Сумма</div>
                  <div className="value strong">{formatMoney(application.amount)}</div>
                </div>
                <div className="application-field">
                  <div className="label">Срок</div>
                  <div className="value">{formatMonths(application.termMonths)}</div>
                </div>
              </div>
              <div className="application-actions">
                <StatusBadge status={application.status} />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onOpenApplication(application.id)}
                >
                  Открыть
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
