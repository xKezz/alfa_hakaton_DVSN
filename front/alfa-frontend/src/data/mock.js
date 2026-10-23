/**
 * Демонстрационные данные прототипа.
 * Все суммы, ставки и решения — тестовые и не являются офертой банка.
 */

export const STEPS = ["Подана", "Проверка", "Скоринг", "Решение", "Выдача"];

export const STATUS_META = {
  submitted: { label: "Подана", badge: "processing", step: 0 },
  processing: { label: "На проверке", badge: "processing", step: 1 },
  manual_review: { label: "На ручной проверке", badge: "manual", step: 2 },
  approved: { label: "Одобрено", badge: "approved", step: 3 },
  issued: { label: "Кредит выдан", badge: "issued", step: 4 },
  declined: { label: "Отказ", badge: "declined", step: 3 },
};

export const STATUS_FILTERS = [
  { value: "all", label: "Все" },
  { value: "active", label: "В работе" },
  { value: "approved", label: "Одобрено" },
  { value: "issued", label: "Выдан" },
  { value: "declined", label: "Отказ" },
];

const moneyFormatter = new Intl.NumberFormat("ru-RU");

export function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${moneyFormatter.format(Math.round(Number(value)))} ₽`;
}

export function formatRate(value) {
  if (value === null || value === undefined) return "—";
  return `${String(value).replace(".", ",")}%`;
}

export function formatDate(isoDate) {
  if (!isoDate) return "—";
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return String(isoDate);
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatDateTime(isoDate) {
  if (!isoDate) return "—";
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return String(isoDate);
  return `${formatDate(isoDate)}, ${date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function formatMonths(months) {
  const value = Number(months);
  if (!value) return "—";
  return `${value} мес.`;
}

/** Аннуитетный платёж; ставка — годовая в процентах. */
export function monthlyPayment(amount, annualRate, months) {
  const sum = Number(amount);
  const rate = Number(annualRate);
  const term = Number(months);
  if (!sum || !term) return null;
  if (!rate) return sum / term;
  const monthRate = rate / 12 / 100;
  return (sum * monthRate) / (1 - Math.pow(1 + monthRate, -term));
}

/** ИНН реальной компании из таблицы companies, используемой в прототипе. */
export const COMPANY_INN = "3257029840";

export const BUSINESS_TYPES = [
  { value: "ip", label: "Для ИП" },
  { value: "ooo", label: "Для ООО" },
];

export const BUSINESS_AGE_TYPES = [
  { value: "more3", label: "Более 3 месяцев" },
  { value: "less3", label: "До 3 месяцев" },
];

export const LOAN_PURPOSES = [
  { value: "working_capital", label: "Пополнение оборотных средств" },
  { value: "equipment", label: "Покупка оборудования" },
  { value: "business_expansion", label: "Развитие бизнеса" },
  { value: "refinancing", label: "Рефинансирование" },
  { value: "other", label: "Другое" },
];

export const PURPOSE_ICONS = {
  working_capital: "💼",
  equipment: "🏭",
  business_expansion: "📈",
  refinancing: "🔄",
  other: "💳",
};

const history001 = [
  {
    title: "Заявка подана",
    date: "15.10.2026 в 10:00",
    desc: "Клиент отправил заявку на кредит «Кредит для бизнеса без залога» на сумму 2 000 000 ₽.",
  },
  {
    title: "Проверка данных",
    date: "15.10.2026 в 10:05",
    desc: "Данные сверены с базой ФНС, противоречий не найдено.",
  },
  {
    title: "Скоринг",
    date: "15.10.2026 в 10:06",
    desc: "Рассчитана скоринговая оценка: 780 баллов. Категория риска: низкая.",
  },
  {
    title: "Принятие решения",
    date: "15.10.2026 в 10:10",
    desc: "Заявка одобрена автоматически, предложены стандартные условия по продукту.",
  },
];

/** Заявки предпринимателя. */
export const ENTREPRENEUR_APPLICATIONS = [
  {
    id: "APP-2026-001",
    date: "2026-10-15",
    amount: 2000000,
    termMonths: 24,
    productTitle: "Кредит для бизнеса без залога",
    purpose: "Развитие и масштабирование",
    status: "approved",
    offer: { amount: 2000000, rate: 13, termMonths: 24 },
    history: history001,
  },
  {
    id: "APP-2026-002",
    date: "2026-10-12",
    amount: 500000,
    termMonths: 12,
    productTitle: "Кредит для бизнеса без залога",
    purpose: "Поддержка операционной деятельности",
    status: "manual_review",
    history: [
      {
        title: "Заявка подана",
        date: "12.10.2026 в 14:25",
        desc: "Клиент отправил заявку на сумму 500 000 ₽.",
      },
      {
        title: "Проверка данных",
        date: "12.10.2026 в 14:28",
        desc: "Данные сверены с базой ФНС.",
      },
      {
        title: "Скоринг завершён",
        date: "12.10.2026 в 14:28",
        desc: "Оценка попала в пограничную зону риска.",
      },
      {
        title: "Заявка передана на ручную проверку",
        date: "12.10.2026 в 14:30",
        desc: "Требуется решение сотрудника банка.",
      },
    ],
  },
  {
    id: "APP-2026-003",
    date: "2026-10-08",
    amount: 1500000,
    termMonths: 18,
    productTitle: "Кредит для бизнеса без залога",
    purpose: "Запуск и старт",
    status: "issued",
    offer: { amount: 1500000, rate: 13, termMonths: 18 },
    history: [
      {
        title: "Заявка подана",
        date: "08.10.2026 в 09:40",
        desc: "Клиент отправил заявку на сумму 1 500 000 ₽.",
      },
      {
        title: "Принятие решения",
        date: "08.10.2026 в 09:47",
        desc: "Заявка одобрена автоматически.",
      },
      {
        title: "Кредит выдан",
        date: "09.10.2026 в 11:12",
        desc: "Клиент принял предложение. Средства зачислены на расчётный счёт.",
      },
    ],
  },
  {
    id: "APP-2026-004",
    date: "2026-10-01",
    amount: 300000,
    termMonths: 6,
    productTitle: "Овердрафт",
    purpose: "Поддержка операционной деятельности",
    status: "declined",
    declineReason:
      "Срок ведения бизнеса и долговая нагрузка не позволяют одобрить продукт на запрошенных условиях (правила демонстрационного прототипа).",
    alternatives: [
      {
        id: 2,
        title: "Возобновляемая кредитная линия без залога",
        rate: 14.5,
        amount: 300000,
        termMonths: 12,
      },
    ],
    history: [
      {
        title: "Заявка подана",
        date: "01.10.2026 в 16:05",
        desc: "Клиент отправил заявку на овердрафт на сумму 300 000 ₽.",
      },
      {
        title: "Решение",
        date: "01.10.2026 в 16:09",
        desc: "Получен отказ по выбранному продукту.",
      },
      {
        title: "Сформированы альтернативные предложения",
        date: "01.10.2026 в 16:09",
        desc: "Система подобрала один альтернативный продукт.",
      },
    ],
  },
];

/** Очередь ручной проверки для сотрудника банка. */
export const BANK_QUEUE = [
  {
    id: "APP-1042",
    date: "2026-10-24",
    amount: 2500000,
    termMonths: 24,
    reason: "Пограничный скоринг",
    status: "manual_review",
    companyInn: COMPANY_INN,
    finance: [
      { label: "Выручка (2025)", value: 10000000, delta: "+15%" },
      { label: "Чистая прибыль (2025)", value: 2000000, delta: "+10%" },
      { label: "Краткосрочные займы", value: 500000, delta: null },
    ],
    chart: [
      { year: "2022", value: 45 },
      { year: "2023", value: 60 },
      { year: "2024", value: 78 },
      { year: "2025", value: 100 },
    ],
    scoring: {
      score: 650,
      category: "Пограничная зона риска",
      level: "mid",
      route: "Ручная проверка",
      positives: ["Стабильная выручка", "Низкая долговая нагрузка"],
      negatives: ["Небольшой срок ведения бизнеса"],
    },
    checks: [
      { ok: true, text: "Формат ИНН корректен" },
      { ok: true, text: "Соответствие ОПФ и ИНН" },
      {
        ok: false,
        text: "Обнаружено несоответствие адреса в анкете и ЕГРЮЛ",
      },
    ],
    history: [
      {
        title: "Заявка передана на ручную проверку",
        date: "24.10.2026 в 14:30",
        desc: "Скоринг 650 из 1000 — пограничная зона риска.",
      },
      {
        title: "Скоринг завершён",
        date: "24.10.2026 в 14:28",
        desc: "Рассчитана скоринговая оценка и факторы риска.",
      },
      {
        title: "Заявка подана",
        date: "24.10.2026 в 14:25",
        desc: "Клиент отправил заявку на сумму 2 500 000 ₽.",
      },
    ],
  },
  {
    id: "APP-1043",
    date: "2026-10-25",
    amount: 1200000,
    termMonths: 18,
    reason: "Цель «Другое»",
    status: "manual_review",
    companyInn: COMPANY_INN,
    finance: [
      { label: "Выручка (2025)", value: 8200000, delta: "+8%" },
      { label: "Чистая прибыль (2025)", value: 1450000, delta: "+6%" },
      { label: "Краткосрочные займы", value: 700000, delta: null },
    ],
    chart: [
      { year: "2022", value: 40 },
      { year: "2023", value: 52 },
      { year: "2024", value: 71 },
      { year: "2025", value: 100 },
    ],
    scoring: {
      score: 720,
      category: "Умеренный риск",
      level: "low",
      route: "Ручная проверка",
      positives: ["Рост выручки", "Положительная чистая прибыль"],
      negatives: ["Цель кредитования «Другое»"],
    },
    checks: [
      { ok: true, text: "Формат ИНН корректен" },
      { ok: true, text: "Соответствие ОПФ и ИНН" },
      { ok: true, text: "Данные ФНС и анкеты согласованы" },
    ],
    history: [
      {
        title: "Заявка передана на ручную проверку",
        date: "25.10.2026 в 09:12",
        desc: "Клиент указал цель кредитования «Другое».",
      },
      {
        title: "Скоринг завершён",
        date: "25.10.2026 в 09:10",
        desc: "Рассчитана скоринговая оценка 720 из 1000.",
      },
      {
        title: "Заявка подана",
        date: "25.10.2026 в 09:05",
        desc: "Клиент отправил заявку на сумму 1 200 000 ₽.",
      },
    ],
  },
  {
    id: "APP-1044",
    date: "2026-10-26",
    amount: 5000000,
    termMonths: 36,
    reason: "Противоречия в данных ФНС",
    status: "manual_review",
    companyInn: COMPANY_INN,
    finance: [
      { label: "Выручка (2025)", value: 12500000, delta: "-4%" },
      { label: "Чистая прибыль (2025)", value: 900000, delta: "-18%" },
      { label: "Краткосрочные займы", value: 2100000, delta: null },
    ],
    chart: [
      { year: "2022", value: 60 },
      { year: "2023", value: 74 },
      { year: "2024", value: 100 },
      { year: "2025", value: 84 },
    ],
    scoring: {
      score: 480,
      category: "Повышенный риск",
      level: "high",
      route: "Ручная проверка",
      positives: ["Длительный срок ведения бизнеса"],
      negatives: [
        "Снижение выручки и прибыли",
        "Высокая долговая нагрузка",
        "Противоречия в данных ФНС",
      ],
    },
    checks: [
      { ok: true, text: "Формат ИНН корректен" },
      {
        ok: false,
        text: "Расхождение адреса в анкете и ЕГРЮЛ",
      },
      {
        ok: false,
        text: "Обороты по данным ФНС ниже заявленной выручки",
      },
    ],
    history: [
      {
        title: "Заявка передана на ручную проверку",
        date: "26.10.2026 в 11:02",
        desc: "Обнаружены противоречия в данных ФНС.",
      },
      {
        title: "Скоринг завершён",
        date: "26.10.2026 в 11:00",
        desc: "Рассчитана скоринговая оценка 480 из 1000.",
      },
      {
        title: "Заявка подана",
        date: "26.10.2026 в 10:55",
        desc: "Клиент отправил заявку на сумму 5 000 000 ₽.",
      },
    ],
  },
];

/** События, доступные кабинету предпринимателя по умолчанию. */
export const DEFAULT_HISTORY = (productTitle, amount) => [
  {
    title: "Заявка подана",
    date: "только что",
    desc: `Клиент отправил заявку на кредит «${productTitle}» на сумму ${formatMoney(amount)}.`,
  },
];
