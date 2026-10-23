import { useState } from "react";
import { Button, StatusBadge, Timeline } from "../components/ui.jsx";
import {
  STEPS,
  STATUS_META,
  formatDate,
  formatMoney,
  formatMonths,
  formatRate,
} from "../data/mock.js";

const FINAL_STATUSES = ["approved", "declined", "issued"];

function stepperState(status) {
  const meta = STATUS_META[status] || STATUS_META.submitted;
  const isFinal = FINAL_STATUSES.includes(status);
  const reached = isFinal ? (status === "issued" ? 4 : 3) : meta.step;
  return { meta, isFinal, reached };
}

function RateValue({ value }) {
  return <>{value === null || value === undefined ? "по продукту" : formatRate(value)}</>;
}

export default function ApplicationDetails({
  application,
  onBack,
  onSelectOffer,
  onDeclineOffer,
}) {
  const [busyOfferId, setBusyOfferId] = useState(null);
  const [actionError, setActionError] = useState("");

  const { meta, isFinal, reached } = stepperState(application.status);
  const lineProgress = reached / (STEPS.length - 1);

  const isOfferPending = application.status === "offer_pending";
  const isApproved = application.status === "approved";
  const isIssued = application.status === "issued";
  const isDeclined = application.status === "declined";
  const isManual = application.status === "manual_review";
  const pendingOffers = (application.offers || []).filter(
    (offer) => offer.status === "offered"
  );

  async function handleOffer(action, offerId) {
    setActionError("");
    setBusyOfferId(offerId);
    try {
      if (action === "select") await onSelectOffer(application.id, offerId);
      else await onDeclineOffer(application.id, offerId);
    } catch (error) {
      setActionError(error.message || "Не удалось обновить предложение");
    } finally {
      setBusyOfferId(null);
    }
  }

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
          {isOfferPending && (
            <>
              <h2 className="result-title">Доступны альтернативные предложения</h2>
              <p className="result-text">
                Выбранный продукт не подошёл по рейтингу. Система подобрала продукты из
                доступных вам вариантов. Выберите одно предложение или откажитесь от него.
              </p>
              <div className="alternatives">
                {pendingOffers.map((offer) => (
                  <div className="alternative-card" key={offer.id}>
                    <div>
                      <div className="alternative-title">{offer.title}</div>
                      <div className="alternative-meta">
                        {formatMoney(offer.amount)} · <RateValue value={offer.rate} /> ·{" "}
                        {formatMonths(offer.termMonths)}
                      </div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={busyOfferId === offer.id}
                        onClick={() => handleOffer("select", offer.id)}
                      >
                        Выбрать
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={busyOfferId === offer.id}
                        onClick={() => handleOffer("decline", offer.id)}
                      >
                        Отказаться
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              {actionError && (
                <div className="notice notice-warn" style={{ marginTop: 16 }}>
                  {actionError}
                </div>
              )}
            </>
          )}

          {isApproved && (
            <>
              <h2 className="result-title">Заявка одобрена</h2>
              <p className="result-text">
                Решение зафиксировано по правилам банка. Повторный скоринг не требуется.
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
                  <div className="condition-value"><RateValue value={application.offer?.rate} /></div>
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
                  <div className="condition-value"><RateValue value={application.offer?.rate} /></div>
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
                  "Подходящих альтернативных продуктов не найдено, заявка отклонена."}
              </p>
              {application.offers && application.offers.length > 0 && (
                <p className="hint-sm" style={{ marginTop: 12 }}>
                  Предложения:{" "}
                  {application.offers
                    .map((offer) => `${offer.title} (${offer.status === "declined" ? "отказ" : offer.status})`)
                    .join("; ")}
                </p>
              )}
            </>
          )}

          {!isApproved && !isIssued && !isDeclined && !isOfferPending && (
            <>
              <h2 className="result-title">Заявка находится на рассмотрении</h2>
              <p className="result-text">
                {isManual
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
              {isManual && application.routingReason && (
                <p className="hint-sm" style={{ marginTop: 12 }}>
                  Причина передачи сотруднику: {application.routingReason}
                </p>
              )}
            </>
          )}
        </section>

        {application.scoring && application.scoring.rating !== null && (
          <section className="card detail-card">
            <h2 className="result-title" style={{ marginBottom: 14 }}>
              Результат скоринга
            </h2>
            <div className="conditions-grid">
              <div>
                <div className="condition-label">Кредитный рейтинг</div>
                <div className="condition-value">{application.scoring.rating} / 1000</div>
              </div>
              <div>
                <div className="condition-label">Категория риска</div>
                <div className="condition-value">{application.scoring.risk_category || "—"}</div>
              </div>
              <div>
                <div className="condition-label">Скоринг по продукту</div>
                <div className="condition-value">
                  {application.scoring.product_scoring !== null &&
                  application.scoring.product_scoring !== undefined
                    ? application.scoring.product_scoring
                    : "—"}
                </div>
              </div>
            </div>
            {application.scoring.routing_reason && (
              <p className="hint-sm" style={{ marginTop: 12 }}>
                Маршрут: {application.scoring.routing_reason}
              </p>
            )}
          </section>
        )}

        <section className="card detail-card">
          <h2 className="result-title" style={{ marginBottom: 18 }}>
            История обработки
          </h2>
          <Timeline events={application.history} />
        </section>
      </div>
    </div>
  );
}
