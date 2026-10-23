import { useState } from "react";
import { loginUser } from "../api.js";
import { Button, Field } from "../components/ui.jsx";

const DEMO_ACCOUNTS = [
  { login: "client", password: "client", role: "предприниматель", note: "ИНН 4217064416" },
  { login: "bank", password: "bank", role: "сотрудник банка", note: "" },
];

export default function LoginPage({ onLogin }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [info, setInfo] = useState("");

  function clearErrors() {
    setError("");
    setFieldErrors({});
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isLoading) return;

    const nextErrors = {};
    if (!login.trim()) nextErrors.login = "Введите логин";
    if (!password.trim()) nextErrors.password = "Введите пароль";
    setFieldErrors(nextErrors);
    setInfo("");

    if (Object.keys(nextErrors).length > 0) {
      setError("Заполните логин и пароль");
      return;
    }

    setError("");
    setIsLoading(true);

    const result = await loginUser(login, password);
    setIsLoading(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    onLogin({
      login: result.user.username,
      role: result.user.profile_type === "employee" ? "employee" : "business",
      companyInn: result.user.company_inn,
    });
  }

  return (
    <div className="login-page">
      <div className="brand login-brand">
        <div className="brand-logo">А</div>
        <div>
          <div className="brand-name">Альфа</div>
          <div className="brand-subtitle">Бизнес-платформа</div>
        </div>
      </div>

      <main className="login-card">
        <h1 className="login-title">Вход в личный кабинет</h1>
        <p className="login-subtitle">Введите данные для доступа к вашим заявкам</p>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <Field label="Логин" htmlFor="login" error={fieldErrors.login}>
            <input
              id="login"
              className={`input${fieldErrors.login ? " has-error" : ""}`}
              type="text"
              autoComplete="username"
              placeholder="Email, телефон или ИНН"
              value={login}
              disabled={isLoading}
              onChange={(event) => {
                setLogin(event.target.value);
                clearErrors();
              }}
            />
          </Field>

          <Field label="Пароль" htmlFor="password" error={fieldErrors.password}>
            <div className="input-with-action">
              <input
                id="password"
                className={`input${fieldErrors.password ? " has-error" : ""}`}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="Введите пароль"
                value={password}
                disabled={isLoading}
                onChange={(event) => {
                  setPassword(event.target.value);
                  clearErrors();
                }}
              />
              <button
                type="button"
                className="input-action"
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                tabIndex={-1}
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </div>
          </Field>

          <div className="login-aux">
            <button
              type="button"
              className="link-btn"
              onClick={() => setInfo("В демо-режиме восстановление пароля недоступно.")}
            >
              Забыли пароль?
            </button>
          </div>

          {error && <div className="form-error">⚠ {error}</div>}
          {info && <p className="hint-sm">{info}</p>}

          <Button type="submit" variant="primary" size="lg" block loading={isLoading}>
            {isLoading ? "Вход…" : "Войти"}
          </Button>
        </form>

        <div className="login-demo">
          <strong>Деморежим.</strong> Тестовые учётные записи:{" "}
          {DEMO_ACCOUNTS.map((account, index) => (
            <span key={account.login}>
              <code>
                {account.login} / {account.password}
              </code>{" "}
              — {account.role}
              {account.note ? `, ${account.note}` : ""}
              {index < DEMO_ACCOUNTS.length - 1 ? "; " : "."}
            </span>
          ))}{" "}
          Авторизация выполняется без запроса к банку.
        </div>

        <p className="login-footer">Безопасные финансовые решения для вашего бизнеса</p>
      </main>

      <p className="login-page-footer">© 2026 Альфа · Бизнес-платформа · Демонстрационный прототип</p>
    </div>
  );
}
