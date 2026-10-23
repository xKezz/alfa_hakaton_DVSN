import { useEffect } from "react";
import { STATUS_META } from "../data/mock.js";

export function Spinner({ dark = false }) {
  return <span className={`spinner${dark ? " spinner-dark" : ""}`} aria-hidden="true" />;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  block = false,
  loading = false,
  className = "",
  type = "button",
  ...rest
}) {
  const classes = [
    "btn",
    `btn-${variant}`,
    size === "sm" ? "btn-sm" : "",
    size === "lg" ? "btn-lg" : "",
    block ? "btn-block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type={type} className={classes} disabled={loading || rest.disabled} {...rest}>
      {loading && <Spinner dark={variant !== "primary" && variant !== "dark" && variant !== "danger"} />}
      {children}
    </button>
  );
}

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] || { label: "Неизвестно", badge: "neutral" };
  return <span className={`badge badge-${meta.badge}`}>{meta.label}</span>;
}

export function Segmented({ options, value, onChange, ariaLabel }) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value ?? option.id}
          type="button"
          className={`segmented-item${value === option.value ? " is-active" : ""}`}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, htmlFor, hint, error, children, className = "" }) {
  return (
    <div className={`field ${className}`.trim()}>
      {label && (
        <label className="field-label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
      {error ? (
        <span className="field-error">{error}</span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={`tab${active === tab.id ? " is-active" : ""}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({ open, title, children, actions, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2 className="modal-title">{title}</h2>
        <div className="modal-text">{children}</div>
        <div className="modal-actions">{actions}</div>
      </div>
    </div>
  );
}

export function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      <span className="toast-icon">✓</span>
      <div>
        <div className="toast-title">{toast.title}</div>
        {toast.text && <div className="toast-text">{toast.text}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon = "📄", title, text, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      {text && <p className="empty-text">{text}</p>}
      {action}
    </div>
  );
}

export function ScoreGauge({ score, level = "low" }) {
  const safeScore = Math.max(0, Math.min(1000, Number(score) || 0));
  const degrees = Math.round((safeScore / 1000) * 360);
  const color = level === "high" ? "var(--rose)" : level === "mid" ? "var(--orange)" : "var(--green)";
  return (
    <div
      className="gauge"
      style={{ background: `conic-gradient(${color} 0deg ${degrees}deg, #eef0f2 ${degrees}deg 360deg)` }}
      aria-label={`Скоринговый балл ${safeScore} из 1000`}
    >
      <div className="gauge-inner">{safeScore}</div>
    </div>
  );
}

export function Timeline({ events, currentTitle }) {
  if (!events || events.length === 0) {
    return <p className="muted-sm">История обработки пока недоступна.</p>;
  }
  return (
    <div className="timeline">
      {events.map((event, index) => {
        const isLast = index === events.length - 1;
        const isCurrent = currentTitle ? event.title === currentTitle : index === 0;
        return (
          <div className={`timeline-item${isCurrent ? " is-current" : ""}`} key={`${event.title}-${index}`}>
            <div className="timeline-visual">
              <span className="timeline-dot" />
              {!isLast && <span className="timeline-line" />}
            </div>
            <div className="timeline-content">
              <div className="timeline-title">{event.title}</div>
              <div className="timeline-date">{event.date}</div>
              {event.desc && <p className="timeline-desc">{event.desc}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ApiStatus({ health }) {
  if (!health) return null;
  const databaseOk = health.ok && health.database === "ok";
  const label = !health.ok
    ? "API недоступен · демо-данные"
    : databaseOk
      ? "API подключён"
      : "API без БД · демо-данные";
  const dotClass = databaseOk ? "is-ok" : health.ok ? "api-dot" : "is-error";
  return (
    <span className="api-status" title={label}>
      <span className={`api-dot ${dotClass}`} />
      {label}
    </span>
  );
}
