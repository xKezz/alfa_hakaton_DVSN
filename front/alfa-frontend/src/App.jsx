import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { checkHealth, getCompany } from "./api.js";
import { ApiStatus, Button, Toast } from "./components/ui.jsx";
import {
  BANK_QUEUE,
  COMPANY_INN,
  ENTREPRENEUR_APPLICATIONS,
  formatMoney,
} from "./data/mock.js";
import ApplicationDetails from "./pages/ApplicationDetails.jsx";
import BankWorkspace from "./pages/BankWorkspace.jsx";
import CreditCalculator from "./pages/CreditCalculator.jsx";
import EntrepreneurDashboard from "./pages/EntrepreneurDashboard.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";

const SESSION_KEY = "alfaSession";
const APPLICATIONS_KEY = "alfaApplications";

function loadSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function loadApplications() {
  try {
    const raw = localStorage.getItem(APPLICATIONS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // игнорируем повреждённые данные
  }
  return ENTREPRENEUR_APPLICATIONS;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function nextApplicationId(applications) {
  const year = new Date().getFullYear();
  const maxNumber = applications.reduce((max, application) => {
    const match = String(application.id).match(/(\d+)$/);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 0);
  return `APP-${year}-${String(maxNumber + 1).padStart(3, "0")}`;
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
  const [applications, setApplications] = useState(loadApplications);
  const [queue, setQueue] = useState(BANK_QUEUE);
  const [selectedApplicationId, setSelectedApplicationId] = useState(null);
  const [company, setCompany] = useState(null);
  const [health, setHealth] = useState(null);
  const [toast, setToast] = useState(null);
  const [isApplicationsLoading, setIsApplicationsLoading] = useState(true);

  const isEmployee = session?.role === "employee";
  const navItems = NAV_ITEMS[isEmployee ? "employee" : "business"];

  const selectedApplication = useMemo(
    () => applications.find((application) => application.id === selectedApplicationId) ?? null,
    [applications, selectedApplicationId]
  );

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setIsApplicationsLoading(false), 350);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(APPLICATIONS_KEY, JSON.stringify(applications));
    } catch {
      // localStorage может быть недоступен
    }
  }, [applications]);

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
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (session?.role !== "business") return undefined;
    const inn = session?.companyInn || COMPANY_INN;
    let active = true;
    getCompany(inn).then((result) => {
      if (active && result.ok) setCompany(result.company);
    });
    return () => {
      active = false;
    };
  }, [session]);

  function showToast(title, text) {
    setToast({ title, text });
  }

  function handleLogin({ login, role, companyInn }) {
    setSession({ login, role, companyInn });
    setView(role === "employee" ? "bank" : "applications");
  }

  function handleLogout() {
    sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
    setView("applications");
    setSelectedApplicationId(null);
    setToast(null);
  }

  function handleOpenApplication(id) {
    setSelectedApplicationId(id);
    setView("application");
  }

  function handleApply(draft) {
    const id = nextApplicationId(applications);
    const application = {
      id,
      date: todayIso(),
      amount: draft.amount,
      termMonths: draft.termMonths,
      productTitle: draft.product.title,
      purpose: draft.purpose,
      status: "processing",
      requested: {
        inn: draft.inn,
        revenue: draft.revenue,
        profit: draft.profit,
        obligations: draft.obligations,
        revenueSource: draft.revenueSource,
      },
      history: [
        {
          title: "Заявка подана",
          date: "только что",
          desc: `Клиент отправил заявку на кредит «${draft.product.title}» на сумму ${formatMoney(
            draft.amount
          )}.`,
        },
        {
          title: "Начата автоматическая проверка",
          date: "только что",
          desc: "Система проверяет данные заявки и рассчитывает скоринг.",
        },
      ],
    };

    setApplications((previous) => [application, ...previous]);
    setSelectedApplicationId(id);
    setView("application");
    showToast("Заявка отправлена", `Номер ${id}. Статус рассмотрения доступен в кабинете.`);
  }

  function handleAcceptOffer(id) {
    setApplications((previous) =>
      previous.map((application) =>
        application.id === id
          ? {
              ...application,
              status: "issued",
              history: [
                {
                  title: "Кредит выдан",
                  date: "только что",
                  desc: "Клиент принял предложение. Средства зачислены на расчётный счёт.",
                },
                ...application.history,
              ],
            }
          : application
      )
    );
    showToast("Кредит оформлен", "Заявка переведена в статус «Кредит выдан».");
  }

  function handleChooseAlternative(id, alternative) {
    setApplications((previous) =>
      previous.map((application) =>
        application.id === id
          ? {
              ...application,
              status: "processing",
              productTitle: alternative.title,
              amount: alternative.amount,
              termMonths: alternative.termMonths,
              offer: null,
              alternatives: undefined,
              declineReason: undefined,
              history: [
                {
                  title: "Клиент выбрал альтернативное предложение",
                  date: "только что",
                  desc: `Выбран продукт «${alternative.title}» на сумму ${formatMoney(
                    alternative.amount
                  )}.`,
                },
                ...application.history,
              ],
            }
          : application
      )
    );
    showToast("Альтернатива выбрана", "Заявка обновлена и отправлена на оформление.");
  }

  function handleDecision(queueId, decision) {
    const application = queue.find((item) => item.id === queueId);
    setQueue((previous) => previous.filter((item) => item.id !== queueId));

    const messages = {
      approve: ["Заявка одобрена", "Решение и обоснование зафиксированы сотрудником."],
      reject: ["Заявка отклонена", "Решение и обоснование зафиксированы сотрудником."],
      alternative: [
        "Альтернативные условия отправлены",
        "Клиенту будет предложено альтернативное решение.",
      ],
    };
    const [title, text] = messages[decision] || ["Решение зафиксировано", ""];
    showToast(title, application ? `${application.id}: ${text}` : text);
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

        {contentView === "application" && selectedApplication && (
          <ApplicationDetails
            application={selectedApplication}
            onBack={() => setView("applications")}
            onAccept={handleAcceptOffer}
            onChooseAlternative={handleChooseAlternative}
          />
        )}

        {contentView === "application" && !selectedApplication && (
          <div className="page">
            <p className="muted">Заявка не найдена.</p>
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
