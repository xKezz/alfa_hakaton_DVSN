import { useState } from "react";
import { loginUser } from "../api.js";
import { Button, Field } from "../components/ui.jsx";

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
      token: result.user.access_token,
    });
  }

  return (
    <div className="login-page">
      <div className="brand login-brand">
        <div className="brand-logo">А</div>
        <div>
          <div className="brand-name">alfa-hakaton-DVSN</div>
          <div className="brand-subtitle">Кредитная платформа</div>
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
              onClick={() => setInfo("Для восстановления доступа обратитесь к администратору.")}
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

        <p className="login-footer">Кредитование для вашего бизнеса</p>
      </main>

      <p className="login-page-footer">alfa-hakaton-DVSN</p>
    </div>
  );
}
