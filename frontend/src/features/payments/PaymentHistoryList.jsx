import { AsyncSectionState } from "../../components/page-state";
import {
  formatPaymentDate,
  formatPaymentMethod,
  formatPaymentType,
  formatStatusText,
  getPaymentStatus,
} from "./helpers";
import { buildPaymentRecordSummary, formatMoney } from "./balances";

function getPaymentStatusStyles(paymentStatus) {
  if (paymentStatus === "FULL") {
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }

  if (paymentStatus === "PARTIAL") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }

  if (paymentStatus === "PENDING") {
    return "border-slate-200 bg-slate-100 text-slate-800";
  }

  return "border-slate-200 bg-slate-50 text-slate-700";
}

function PaymentStatusBadge({ payment }) {
  const paymentStatus = getPaymentStatus(payment);
  if (!paymentStatus) {
    return null;
  }

  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold tracking-wide ${getPaymentStatusStyles(paymentStatus)}`}
    >
      {paymentStatus}
    </span>
  );
}

function HistoryRow({ payment }) {
  const paymentStatus = getPaymentStatus(payment);
  const summary = buildPaymentRecordSummary(payment);
  const amountToneClass =
    paymentStatus === "FULL"
      ? "text-emerald-700"
      : paymentStatus === "PARTIAL"
        ? "text-amber-700"
        : "text-rose-700";

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-slate-900">{formatPaymentType(payment.paymentType)}</h3>
          <p className="text-sm text-slate-600">
            {summary.memberName}
            {payment.membershipId ? ` · Membership #${payment.membershipId}` : ""}
            {payment.installmentId ? ` · Installment #${payment.installmentId}` : ""}
          </p>
          {summary.slotCount != null ? (
            <p className="text-sm text-slate-600">
              {summary.slotCount} {Number(summary.slotCount) === 1 ? "slot" : "slots"}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2">
          <PaymentStatusBadge payment={payment} />
          <p className={`text-2xl font-semibold ${amountToneClass}`}>
            {summary.totalPayableLabel ?? summary.paidAmountLabel}
          </p>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {summary.totalPayableLabel ? "Total payable" : "Recorded payment"}
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monthly installment</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">
            {summary.monthlyInstallmentLabel ?? "Not available"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Share received</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{summary.shareReceivedLabel ?? "Not available"}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Previous due</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{summary.arrearsLabel}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Final payable</p>
          <p className={`mt-1 text-lg font-semibold ${amountToneClass}`}>
            {summary.finalPayableLabel ?? "Not available"}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-900">Partial payment progress</p>
          <p className="text-sm text-slate-600">
            {summary.paidAmountLabel} paid / {summary.remainingAmountLabel} remaining
          </p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
          <div
            className={`h-full rounded-full ${summary.tone.accent}`}
            style={{ width: `${Math.max(summary.progress.percent, 6)}%` }}
          />
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4">
        <p className="text-sm font-semibold text-slate-900">Member breakdown</p>
        <dl className="mt-3 space-y-2 text-sm text-slate-700">
          <div className="flex items-center justify-between gap-3">
            <dt>+ Share</dt>
            <dd>{summary.shareReceivedLabel ?? "Not available"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt>- Installment</dt>
            <dd>{summary.monthlyInstallmentLabel ?? "Not available"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-2 font-semibold text-slate-950">
            <dt>= Final payable</dt>
            <dd>{summary.finalPayableLabel ?? "Not available"}</dd>
          </div>
        </dl>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="font-medium text-slate-500">Method</dt>
          <dd>{formatPaymentMethod(payment.paymentMethod)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Date</dt>
          <dd>{formatPaymentDate(payment.paymentDate)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Record status</dt>
          <dd>{formatStatusText(payment.status || "recorded")}</dd>
        </div>
        {paymentStatus ? (
          <div>
            <dt className="font-medium text-slate-500">Payment status</dt>
            <dd>{paymentStatus}</dd>
          </div>
        ) : null}
        <div>
          <dt className="font-medium text-slate-500">Paid</dt>
          <dd>{summary.paidAmountLabel}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Remaining</dt>
          <dd>{summary.remainingAmountLabel}</dd>
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <dt className="font-medium text-slate-500">Reference</dt>
          <dd>{payment.referenceNo || "Not provided"}</dd>
        </div>
        {summary.totalPayableLabel ? (
          <div className="sm:col-span-2 lg:col-span-3">
            <dt className="font-medium text-slate-500">Dues breakdown</dt>
            <dd className="mt-1 space-y-1">
              {summary.finalPayableLabel ? <p>Installment balance: {summary.finalPayableLabel}</p> : null}
              {summary.penaltyLabel ? <p>Penalty: {summary.penaltyLabel}</p> : null}
              <p>Arrears: {summary.arrearsLabel}</p>
              {payment.nextDueDate ? <p>Next due date: {formatPaymentDate(payment.nextDueDate)}</p> : null}
              {payment.nextDueAmount != null ? <p>Next due amount: {formatMoney(payment.nextDueAmount)}</p> : null}
              <p>Total payable: {summary.totalPayableLabel}</p>
            </dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

export default function PaymentHistoryList({
  payments,
  loading = false,
  error = "",
  onRetry,
  title = "Payment history",
  emptyMessage = "No payments have been recorded yet.",
}) {
  const normalizedPayments = Array.isArray(payments) ? payments : [];

  return (
    <AsyncSectionState
      className="space-y-4"
      description="Review the latest owner-scoped payment entries, their payment state, and any dues context the backend provides."
      empty={normalizedPayments.length === 0}
      emptyActionLabel={onRetry ? "Refresh history" : ""}
      emptyDescription=""
      emptyTitle={emptyMessage}
      error={error}
      errorTitle="We could not load payment history."
      loading={loading}
      loadingDescription="Fetching the latest owner-scoped payment entries."
      loadingLabel="Loading payment history..."
      onEmptyAction={onRetry}
      onRetry={onRetry}
      retryLabel="Refresh history"
      title={title}
    >
      {normalizedPayments.length > 0 ? (
        <div className="grid gap-3">
          {normalizedPayments.map((payment, index) => (
            <HistoryRow key={payment.id ?? `${payment.paymentDate ?? "payment"}-${index}`} payment={payment} />
          ))}
        </div>
      ) : null}
    </AsyncSectionState>
  );
}
