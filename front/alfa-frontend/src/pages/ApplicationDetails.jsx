import { useState } from "react";
import { Button, Modal, StatusBadge, Timeline } from "../components/ui.jsx";
import {
  STEPS,
  STATUS_META,
  formatDate,
  formatMoney,
  formatMonths,
  formatRate,
} from "../data/mock.js";

const FINAL_STATUSES = ["approved", "issued", "declined"];

function stepperState(status) {
  const meta = STATUS_META[status] || STATUS_META.submitted;
  const isFinal = FINAL_STATUSES.includes(status);
  const reached = isFinal ? (status === "issued" ? 4 : 3) : meta.step;
  return { meta, isFinal, reached };
}

export default function ApplicationDetails({ application, onBack, onAccept, onChooseAlternative }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { meta, isFinal, reached } = stepperState(application.status);
  const lineProgress = reached / (STEPS.length - 1);

  const isApproved = application.status === "approved";
  const isIssued = application.status === "issued";
  const isDeclined = application.status === "declined";

  return (
    <div className="page">
      <div className="detail-wrap">
        <button type="button" className="back-link" onClick={onBack}>
          ← К списку заявок
        </button>

        <section className="card detail-card">
          <div className="detail-head">
            <div>
              <h1 className="detail-title">Заявка № {application.id}</h1>
              <p className="detail-subtitle">
                Дата подачи: {formatDate(application.date)} · {application.productTitle}
              </p>
              <div className="detail-amount">{formatMoney(application.amount)}</div>
            </div>
            <StatusBadge status={application.status} />
          </div>

          <div className="stepper">
            <span className="stepper-line" />
            <span
              className="stepper-line-active"
              style={{ width: `calc((100% - 36px) * ${lineProgress})` }}
            />
            {STEPS.map((step, index) => {
              const isDone = isFinal ? index <= reached : index < meta.step;
              const isCurrent = !isFinal && index === meta.step;
              return (
                <div className="stepper-step" key={step}>
                  <span
                    className={`stepper-dot${isDone ? " is-done" : ""}${
                      isCurrent ? " is-current" : ""
                    }`}
                  >
                    {isDone ? "✓" : index + 1}
                  </span>
                  <span className={`stepper-label${isCurrent || isDone ? " is-active" : ""}`}>
                    {step}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card detail-card">
          {isApproved && (
            <>
              <h2 className="result-title">Предложение одобрено</h2>
              <p className="result-text">
                Продукт уже проверен по правилам прототипа. Подтвердите условия, чтобы оформить
                кредит — повторный скоринг не потребуется.
              </p>
              <div className="conditions-grid">
                <div>
                  <div className="condition-label">Сумма</div>
                  <div className="condition-value">
                    {formatMoney(application.offer?.amount ?? application.amount)}
                  </div>
                </div>
                <div>
                  <div className="condition-label">Ставка</div>
                  <div className="condition-value">{formatRate(application.offer?.rate ?? 13)}</div>
                </div>
                <div>
                  <div className="condition-label">Срок</div>
                  <div className="condition-value">
                    {formatMonths(application.offer?.termMonths ?? application.termMonths)}
                  </div>
                </div>
              </div>
              <div className="detail-actions">
                <Button variant="dark" onClick={() => setIsModalOpen(true)}>
                  Принять предложение
                </Button>
              </div>
            </>
          )}

          {isIssued && (
            <>
              <h2 className="result-title">Кредит успешно оформлен</h2>
              <p className="result-text">
                Условия зафиксированы, денежные средства будут перечислены на расчётный счёт в
                течение 1 рабочего дня.
              </p>
              <div className="conditions-grid">
                <div>
                  <div className="condition-label">Сумма</div>
                  <div className="condition-value">
                    {formatMoney(application.offer?.amount ?? application.amount)}
                  </div>
                </div>
                <div>
                  <div className="condition-label">Ставка</div>
                  <div className="condition-value">{formatRate(application.offer?.rate ?? 13)}</div>
                </div>
                <div>
                  <div className="condition-label">Срок</div>
                  <div className="condition-value">
                    {formatMonths(application.offer?.termMonths ?? application.termMonths)}
                  </div>
                </div>
              </div>
            </>
          )}

          {isDeclined && (
            <>
              <h2 className="result-title">По заявке получен отказ</h2>
              <p className="result-text">
                {application.declineReason ||
                  "Продукт не прошёл проверки по правилам демонстрационного прототипа."}
              </p>
              {application.alternatives && application.alternatives.length > 0 ? (
                <>
                  <h3 className="result-title" style={{ fontSize: 15, marginTop: 20 }}>
                    Доступные альтернативы
                  </h3>
                  <div className="alternatives">
                    {application.alternatives.map((alternative) => (
                      <div className="alternative-card" key={alternative.id}>
                        <div>
                          <div className="alternative-title">{alternative.title}</div>
                          <div className="alternative-meta">
                            {formatMoney(alternative.amount)} · {formatRate(alternative.rate)} ·{" "}
                            {formatMonths(alternative.termMonths)}
                          </div>
                        </div>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onChooseAlternative(application.id, alternative)}
                        >
                          Выбрать
                        </Button>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="notice" style={{ marginTop: 18 }}>
                  Подходящих альтернативных продуктов не найдено.
                </p>
              )}
            </>
          )}

          {!isApproved && !isIssued && !isDeclined && (
            <>
              <h2 className="result-title">Заявка находится на рассмотрении</h2>
              <p className="result-text">
                {application.status === "manual_review"
                  ? "Заявка передана сотруднику банка на ручную проверку. Результат появится в кабинете после принятия решения."
                  : application.status === "processing"
                    ? "Система проверяет данные и рассчитывает скоринг. Информация обновится автоматически."
                    : "Заявка получена и ожидает начала автоматической обработки."}
              </p>
              <div className="conditions-grid">
                <div>
                  <div className="condition-label">Сумма</div>
                  <div className="condition-value">{formatMoney(application.amount)}</div>
                </div>
                <div>
                  <div className="condition-label">Срок</div>
                  <div className="condition-value">{formatMonths(application.termMonths)}</div>
                </div>
                <div>
                  <div className="condition-label">Статус</div>
                  <div className="condition-value" style={{ fontSize: 15 }}>
                    {meta.label}
                  </div>
                </div>
              </div>
            </>
          )}
        </section>

        <section className="card detail-card">
          <h2 className="result-title" style={{ marginBottom: 18 }}>
            История обработки
          </h2>
          <Timeline events={application.history} />
        </section>
      </div>

      <Modal
        open={isModalOpen}
        title="Подтверждение"
        onClose={() => setIsModalOpen(false)}
        actions={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setIsModalOpen(false);
                onAccept(application.id);
              }}
            >
              Подтвердить
            </Button>
          </>
        }
      >
        Вы соглашаетесь с условиями кредитования и подтверждаете оформление кредита на сумму{" "}
        {formatMoney(application.offer?.amount ?? application.amount)} сроком{" "}
        {formatMonths(application.offer?.termMonths ?? application.termMonths)} по ставке{" "}
        {formatRate(application.offer?.rate ?? 13)}. Условия демонстрационные.
      </Modal>
    </div>
  );
}
