import { useEffect, useState } from "react";
import "./App.css";
import {
  checkHealth,
  createLoanApplication,
  decideLoanApplication,
  declineLoanOffer,
  getCompany,
  getLoanApplication,
  getLoanApplications,
  selectLoanOffer,
} from "./api.js";
import { ApiStatus, Button, Toast } from "./components/ui.jsx";
import { LOAN_PURPOSES, formatDateTime } from "./data/mock.js";
import ApplicationDetails from "./pages/ApplicationDetails.jsx";
import BankWorkspace from "./pages/BankWorkspace.jsx";
import CreditCalculator from "./pages/CreditCalculator.jsx";
import EntrepreneurDashboard from "./pages/EntrepreneurDashboard.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";

const SESSION_KEY = "alfaSession";

const EVENT_TITLES = {
  application_submitted: "Заявка подана",
  processing_started: "Начата автоматическая проверка",
  scoring_calculated: "Скоринг завершён",
  manual_review_assigned: "Заявка передана сотруднику",
  offer_created: "Сформировано альтернативное предложение",
  offer_selected: "Клиент выбрал предложение",
  offer_declined: "Клиент отказался от предложения",
  decision_made: "Принято решение",
  status_changed: "Статус обновлён",
};

function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    // Старые демо-сессии без company_inn не должны подставлять чужой ИНН.
    if (session?.role === "business" && !session.companyInn) return null;
    return session;
  } catch {
    return null;
  }
}

function mapStatus(status) {
  // В старом UI отказ называется declined.
  return status === "rejected" ? "declined" : status;
}

function purposeLabel(code) {
  return LOAN_PURPOSES.find((item) => item.value === code)?.label || code || "—";
}

function mapHistory(history) {
  return (history || []).map((event) => ({
    title: EVENT_TITLES[event.event_type] || event.event_type,
    date: formatDateTime(event.created_at),
    desc: event.event_description || "",
  }));
}

function mapSummary(application) {
  return {
    id: application.application_id,
    date: application.created_at,
    amount: Number(application.requested_amount),
    termMonths: application.requested_term_months,
    productTitle: application.product_name || "Кредитный продукт",
    purpose: application.loan_purpose,
    purposeLabel: purposeLabel(application.loan_purpose),
    status: mapStatus(application.status),
    rawStatus: application.status,
    companyInn: application.inn,
    companyName: application.company_name,
    rating: application.rating,
    riskCategory: application.risk_category,
    routingReason: application.routing_reason,
    employeeRout: application.employee_rout,
  };
}

function mapOffer(offer) {
  return {
    id: offer.offer_id,
    offerId: offer.offer_id,
    productId: offer.product_id,
    title: offer.product_name || "Альтернативный продукт",
    rate: offer.percent,
    amount: Number(offer.approved_amount),
    termMonths: offer.approved_term_months,
    status: offer.status,
  };
}

function mapDetail(detail) {
  const offers = (detail.offers || []).map(mapOffer);
  const selectedOffer = offers.find((offer) => offer.status === "selected");
  const decision = detail.decision || null;
  const scoring = detail.scoring || {};
  return {
    ...mapSummary({
      application_id: detail.application_id,
      created_at: detail.created_at,
      requested_amount: detail.requested_amount,
      requested_term_months: detail.requested_term_months,
      product_name: detail.product_name,
      loan_purpose: detail.loan_purpose,
      status: detail.status,
      inn: detail.inn,
      company_name: detail.company_name,
      rating: scoring.rating,
      risk_category: scoring.risk_category,
      routing_reason: scoring.routing_reason,
      employee_rout: scoring.employee_rout,
    }),
    updatedAt: detail.updated_at,
    productId: detail.product_id,
    scoring,
    offers,
    decision,
    offer: decision && decision.decision_type === "approved"
      ? {
          amount: Number(decision.approved_amount ?? detail.requested_amount),
          termMonths: decision.approved_term_months ?? detail.requested_term_months,
          rate: selectedOffer?.rate ?? null,
        }
      : null,
    declineReason:
      decision && decision.decision_type === "rejected"
        ? decision.decision_reason
        : null,
    history: mapHistory(detail.history),
  };
}

const NAV_ITEMS = {
  business: [
    { id: "applications", label: "Мои заявки" },
    { id: "calculator", label: "Подобрать кредит" },
    { id: "profile", label: "Профиль" },
  ],
  employee: [{ id: "bank", label: "Очередь заявок" }],
};

export default function App() {
  const [session, setSession] = useState(loadSession);
  const [view, setView] = useState(() =>
    loadSession()?.role === "employee" ? "bank" : "applications"
  );
  const [applications, setApplications] = useState([]);
  const [queue, setQueue] = useState([]);
  const [selectedApplication, setSelectedApplication] = useState(null);
  const [isApplicationLoading, setIsApplicationLoading] = useState(false);
  const [company, setCompany] = useState(null);
  const [health, setHealth] = useState(null);
  const [toast, setToast] = useState(null);
  const [isApplicationsLoading, setIsApplicationsLoading] = useState(true);

  const isEmployee = session?.role === "employee";
  const navItems = NAV_ITEMS[isEmployee ? "employee" : "business"];
  const companyInn = session?.companyInn || "";

  function showToast(title, text) {
    setToast({ title, text });
  }

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!session) return undefined;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch {
      // sessionStorage может быть недоступен
    }
    return undefined;
  }, [session]);

  useEffect(() => {
    if (session?.role !== "business" || !companyInn) return undefined;
    let active = true;
    getCompany(companyInn).then((result) => {
      if (active && result.ok) setCompany(result.company);
    });
    return () => {
      active = false;
    };
  }, [session, companyInn]);

  // Заявки клиента или очередь сотрудника — из API, без mock/localStorage.
  useEffect(() => {
    if (!session) return undefined;
    let active = true;

    if (session.role === "business") {
      if (!companyInn) return undefined;
      getLoanApplications({ inn: companyInn }).then((result) => {
        if (!active) return;
        if (result.ok) {
          setApplications(result.applications.map(mapSummary));
        } else {
          showToast("Не удалось загрузить заявки", result.message);
        }
        setIsApplicationsLoading(false);
      });
    } else {
      getLoanApplications({ status: "manual_review" }).then((result) => {
        if (!active) return;
        if (result.ok) {
          setQueue(
            result.applications.map((application) => ({
              ...mapSummary(application),
              reason: application.routing_reason || "Требуется ручная проверка",
            }))
          );
        } else {
          showToast("Не удалось загрузить очередь", result.message);
        }
        setIsApplicationsLoading(false);
      });
    }

    return () => {
      active = false;
    };
  }, [session, companyInn, view]);

  function handleLogin({ login, role, companyInn: loginCompanyInn }) {
    setSession({ login, role, companyInn: loginCompanyInn });
    setView(role === "employee" ? "bank" : "applications");
    setSelectedApplication(null);
  }

  function handleLogout() {
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
    setApplications([]);
    setQueue([]);
    setSelectedApplication(null);
    setView("applications");
    setToast(null);
  }

  async function handleOpenApplication(id) {
    setView("application");
    setIsApplicationLoading(true);
    const result = await getLoanApplication(id);
    setIsApplicationLoading(false);
    if (!result.ok) {
      setSelectedApplication(null);
      showToast("Не удалось открыть заявку", result.message);
      return;
    }
    setSelectedApplication(mapDetail(result.application));
  }

  async function handleApply(draft) {
    const chosenPurpose =
      draft.product.loanPurpose && draft.product.loanPurpose !== "other"
        ? draft.product.loanPurpose
        : draft.purpose;
    const result = await createLoanApplication({
      inn: draft.inn,
      product_id: draft.product.id,
      requested_amount: draft.amount,
      requested_term_months: draft.termMonths,
      loan_purpose: chosenPurpose,
      business_age_months: draft.businessAgeMonths,
    });
    if (!result.ok) {
      showToast("Заявка не отправлена", result.message);
      throw new Error(result.message);
    }

    const mapped = mapDetail(result.application);
    setApplications((previous) => [mapped, ...previous]);
    setSelectedApplication(mapped);
    setView("application");
    showToast("Заявка отправлена", `Статус: ${mapped.status}. Данные сохранены в БД.`);
    return mapped;
  }

  async function handleSelectOffer(applicationId, offerId) {
    const result = await selectLoanOffer(applicationId, offerId);
    if (!result.ok) {
      showToast("Не удалось выбрать предложение", result.message);
      throw new Error(result.message);
    }
    const mapped = mapDetail(result.application);
    setSelectedApplication(mapped);
    setApplications((previous) =>
      previous.map((application) => (application.id === mapped.id ? mapped : application))
    );
    showToast("Предложение выбрано", "Заявка одобрена на условиях выбранного продукта.");
    return mapped;
  }

  async function handleDeclineOffer(applicationId, offerId) {
    const result = await declineLoanOffer(applicationId, offerId);
    if (!result.ok) {
      showToast("Не удалось отклонить предложение", result.message);
      throw new Error(result.message);
    }
    const mapped = mapDetail(result.application);
    setSelectedApplication(mapped);
    setApplications((previous) =>
      previous.map((application) => (application.id === mapped.id ? mapped : application))
    );
    showToast(
      "Предложение отклонено",
      mapped.status === "declined"
        ? "Отказ от всех альтернатив — по заявке финальный отказ."
        : "Можно выбрать оставшееся предложение."
    );
    return mapped;
  }

  async function handleDecision(queueId, decision, reason) {
    const result = await decideLoanApplication(queueId, {
      decision: decision === "approve" ? "approved" : "rejected",
      decided_by: session?.login,
      reason,
    });
    if (!result.ok) {
      showToast("Решение не сохранено", result.message);
      throw new Error(result.message);
    }
    const mapped = mapDetail(result.application);
    setQueue((previous) => previous.filter((item) => item.id !== queueId));
    if (selectedApplication?.id === queueId) setSelectedApplication(mapped);
    showToast(
      "Решение зафиксировано",
      `Заявка ${queueId}: ${mapped.status}. Изменения сохранены в БД.`
    );
    return mapped;
  }

  if (!session) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const activeNavId = view === "application" ? "applications" : view;
  const contentView = isEmployee ? "bank" : view;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <button
            type="button"
            className="brand"
            style={{ border: "none", background: "none", padding: 0, cursor: "pointer" }}
            onClick={() => setView(isEmployee ? "bank" : "applications")}
          >
            <div className="brand-logo">А</div>
            <div style={{ textAlign: "left" }}>
              <div className="brand-name">Альфа</div>
              <div className="brand-subtitle">
                {isEmployee ? "Интерфейс сотрудника" : "Бизнес-платформа"}
              </div>
            </div>
          </button>

          <nav className="app-nav" aria-label="Основная навигация">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-link${activeNavId === item.id ? " is-active" : ""}`}
                onClick={() => setView(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="app-user">
            <div className="user-chip">
              <span className="user-avatar">{isEmployee ? "С" : "Р"}</span>
              <div>
                <div className="user-name">
                  {isEmployee ? "Сотрудник банка" : company?.company_name || "Компания"}
                </div>
                <div className="user-role">
                  {isEmployee ? "Роль: сотрудник банка" : "Роль: предприниматель"}
                </div>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Выйти
            </Button>
          </div>
        </div>
      </header>

      <main>
        {contentView === "calculator" && (
          <CreditCalculator defaultCompany={company} health={health} onApply={handleApply} />
        )}

        {contentView === "profile" && <ProfilePage company={company} health={health} />}

        {contentView === "application" && isApplicationLoading && (
          <div className="page">
            <p className="muted">Загружаем заявку из базы данных…</p>
          </div>
        )}

        {contentView === "application" && !isApplicationLoading && selectedApplication && (
          <ApplicationDetails
            application={selectedApplication}
            onBack={() => setView("applications")}
            onSelectOffer={handleSelectOffer}
            onDeclineOffer={handleDeclineOffer}
          />
        )}

        {contentView === "application" && !isApplicationLoading && !selectedApplication && (
          <div className="page">
            <p className="muted">Заявка не найдена или не загружена.</p>
            <Button variant="secondary" onClick={() => setView("applications")}>
              К списку заявок
            </Button>
          </div>
        )}

        {contentView === "bank" && <BankWorkspace queue={queue} onDecision={handleDecision} />}

        {contentView === "applications" && (
          <EntrepreneurDashboard
            applications={applications}
            company={company}
            isLoading={isApplicationsLoading}
            onOpenApplication={handleOpenApplication}
            onNewApplication={() => setView("calculator")}
          />
        )}
      </main>

      <footer className="app-footer">
        <div className="app-footer-inner">
          <span>© 2026 Альфа · Бизнес-платформа · Демонстрационный прототип</span>
          <span className="row" style={{ gap: 12 }}>
            <span>Данные и условия не являются офертой банка</span>
            <ApiStatus health={health} />
          </span>
        </div>
      </footer>

      <Toast toast={toast} />
    </div>
  );
}
