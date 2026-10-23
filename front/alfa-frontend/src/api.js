/**
 * Клиент минимального API проекта.
 * Базовый адрес задаётся переменной окружения VITE_API_URL.
 */

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const REQUEST_TIMEOUT_MS = 4000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    return { response, payload };
  } finally {
    clearTimeout(timer);
  }
}

function normalizeDetail(payload) {
  const detail = payload && payload.detail;
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg || "Некорректное значение").join("; ");
  }
  return "Некорректный запрос";
}

export function getApiUrl() {
  return API_URL;
}

/** Проверка доступности backend. */
export async function checkHealth() {
  try {
    const { response, payload } = await request("/health");
    if (!response.ok) {
      return { ok: false, database: "unavailable", error: "Сервис недоступен" };
    }
    return {
      ok: true,
      database: payload?.database || "unknown",
    };
  } catch {
    return { ok: false, database: "unavailable", error: "Сервис недоступен" };
  }
}

/**
 * Авторизация по логину и паролю через API (таблица login в PostgreSQL).
 * Возвращает { ok: true, user } либо { ok: false, type, message }.
 * type: invalid_credentials | invalid | unavailable | error
 */
export async function loginUser(username, password) {
  const credentials = {
    username: String(username || "").trim(),
    password: String(password || ""),
  };

  let result;
  try {
    result = await request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    });
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message: "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload } = result;

  if (response.ok && payload) {
    return { ok: true, user: payload };
  }
  if (response.status === 401) {
    return {
      ok: false,
      type: "invalid_credentials",
      message: normalizeDetail(payload) || "Неверный логин или пароль",
    };
  }
  if (response.status === 422) {
    return {
      ok: false,
      type: "invalid",
      message: normalizeDetail(payload) || "Проверьте логин и пароль",
    };
  }
  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message: normalizeDetail(payload) || "База данных недоступна",
    };
  }
  return {
    ok: false,
    type: "error",
    message: normalizeDetail(payload) || "Не удалось выполнить вход",
  };
}

/**
 * Получение компании по ИНН.
 * Возвращает { ok: true, company } либо { ok: false, type, message }.
 * type: not_found | invalid | unavailable | error
 */
export async function getCompany(inn) {
  const value = String(inn || "").trim();

  if (!/^\d{10}(\d{2})?$/.test(value)) {
    return {
      ok: false,
      type: "invalid",
      message: "ИНН должен состоять из 10 или 12 цифр",
    };
  }

  let result;
  try {
    result = await request(`/api/companies/${value}`);
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message:
        "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload } = result;

  if (response.status === 404) {
    return {
      ok: false,
      type: "not_found",
      message: normalizeDetail(payload) || "Компания с таким ИНН не найдена",
    };
  }

  if (response.status === 422) {
    return {
      ok: false,
      type: "invalid",
      message: normalizeDetail(payload) || "ИНН должен состоять из 10 или 12 цифр",
    };
  }

  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message:
        normalizeDetail(payload) ||
        "База данных недоступна. Проверьте настройки подключения.",
    };
  }

  if (!response.ok || !payload) {
    return {
      ok: false,
      type: "error",
      message:
        normalizeDetail(payload) || "Не удалось получить данные компании",
    };
  }

  return { ok: true, company: payload };
}

/**
 * Сохранение годовой финансовой отчётности в таблицу financial_statements.
 * Возвращает { ok: true, statement } либо { ok: false, type, message }.
 * type: conflict | not_found | invalid | unavailable | error
 */
export async function createFinancialStatement(payload) {
  let result;
  try {
    result = await request("/api/financial-statements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message: "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload: data } = result;

  if (response.status === 201 && data) {
    return { ok: true, statement: data };
  }

  if (response.status === 409) {
    return {
      ok: false,
      type: "conflict",
      message:
        normalizeDetail(data) ||
        "Отчётность за этот отчётный год уже существует",
    };
  }

  if (response.status === 404) {
    return {
      ok: false,
      type: "not_found",
      message: normalizeDetail(data) || "Компания с таким ИНН не найдена",
    };
  }

  if (response.status === 422) {
    return {
      ok: false,
      type: "invalid",
      message: normalizeDetail(data) || "Некорректные данные отчётности",
    };
  }

  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message: normalizeDetail(data) || "База данных недоступна",
    };
  }

  return {
    ok: false,
    type: "error",
    message: normalizeDetail(data) || "Не удалось сохранить отчётность",
  };
}

/**
 * Последняя годовая отчётность компании (то, что предприниматель заполнил в профиле).
 * Возвращает { ok: true, statement } либо { ok: false, type, message }.
 * type: not_found | invalid | unavailable | error
 */
export async function getLatestFinancialStatement(inn) {
  const value = String(inn || "").trim();

  if (!/^\d{10}(\d{2})?$/.test(value)) {
    return { ok: false, type: "invalid", message: "ИНН должен состоять из 10 или 12 цифр" };
  }

  let result;
  try {
    result = await request(`/api/financial-statements/${value}/latest`);
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message: "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload } = result;

  if (response.ok && payload) return { ok: true, statement: payload };

  if (response.status === 404) {
    return {
      ok: false,
      type: "not_found",
      message: "В профиле нет финансовой отчётности. Заполните её во вкладке «Профиль».",
    };
  }
  if (response.status === 422) {
    return { ok: false, type: "invalid", message: normalizeDetail(payload) || "Некорректный ИНН" };
  }
  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message: normalizeDetail(payload) || "База данных недоступна",
    };
  }
  return {
    ok: false,
    type: "error",
    message: normalizeDetail(payload) || "Не удалось получить отчётность",
  };
}

/**
 * Все годовые отчёты компании (по убыванию года).
 * Возвращает { ok: true, statements } либо { ok: false, type, message }.
 * type: invalid | unavailable | error
 */
export async function getFinancialStatements(inn) {
  const value = String(inn || "").trim();

  if (!/^\d{10}(\d{2})?$/.test(value)) {
    return { ok: false, type: "invalid", message: "ИНН должен состоять из 10 или 12 цифр" };
  }

  let result;
  try {
    result = await request(`/api/financial-statements/${value}`);
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message: "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload } = result;

  if (response.ok && Array.isArray(payload)) {
    return { ok: true, statements: payload };
  }
  if (response.status === 422) {
    return { ok: false, type: "invalid", message: normalizeDetail(payload) || "Некорректный ИНН" };
  }
  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message: normalizeDetail(payload) || "База данных недоступна",
    };
  }
  return {
    ok: false,
    type: "error",
    message: normalizeDetail(payload) || "Не удалось получить отчётность",
  };
}

/**
 * Подбор активных кредитных продуктов из таблицы loan_catalog.
 * Возвращает { ok: true, products } либо { ok: false, type, message }.
 * type: invalid | unavailable | error
 */
export async function getLoanProducts({
  amount,
  termMonths,
  businessCategory,
  purpose,
  businessAgeMonths,
}) {
  const params = new URLSearchParams({
    amount: String(amount),
    term_months: String(termMonths),
    business_category: businessCategory,
  });

  if (purpose && purpose !== "all") params.set("purpose", purpose);
  if (businessAgeMonths !== null && businessAgeMonths !== undefined) {
    params.set("business_age_months", String(businessAgeMonths));
  }

  let result;
  try {
    result = await request(`/api/loan-products?${params.toString()}`);
  } catch {
    return {
      ok: false,
      type: "unavailable",
      message: "API недоступен. Проверьте, запущен ли backend на " + API_URL + ".",
    };
  }

  const { response, payload } = result;

  if (response.status === 422) {
    return {
      ok: false,
      type: "invalid",
      message: normalizeDetail(payload) || "Некорректные параметры подбора",
    };
  }

  if (response.status === 503) {
    return {
      ok: false,
      type: "unavailable",
      message: normalizeDetail(payload) || "База данных недоступна",
    };
  }

  if (!response.ok || !Array.isArray(payload)) {
    return {
      ok: false,
      type: "error",
      message: normalizeDetail(payload) || "Не удалось загрузить кредитные продукты",
    };
  }

  return { ok: true, products: payload };
}
