import { useEffect, useState } from "react";

import PaymentEntryForm from "./PaymentEntryForm";
import PaymentHistoryList from "./PaymentHistoryList";

export default function PaymentPanel({
  ownerId,
  initialPayments = [],
  historyLoading = false,
  historyError = "",
  onRetryHistory,
  onRecorded,
}) {
  const [payments, setPayments] = useState(() => (Array.isArray(initialPayments) ? initialPayments : []));

  useEffect(() => {
    setPayments(Array.isArray(initialPayments) ? initialPayments : []);
  }, [initialPayments]);

  function handleRecordedPayment(recordedPayment, meta = {}) {
    if (meta.type === "rollback") {
      setPayments((currentPayments) => currentPayments.filter((payment) => payment.id !== meta.optimisticId));
      return;
    }
    if (meta.type === "replace") {
      setPayments((currentPayments) =>
        currentPayments.map((payment) => (payment.id === meta.optimisticId ? recordedPayment : payment)),
      );
      if (typeof onRecorded === "function") {
        onRecorded(recordedPayment);
      }
      return;
    }
    setPayments((currentPayments) => [recordedPayment, ...currentPayments]);
    if (!meta.type && typeof onRecorded === "function") {
      onRecorded(recordedPayment);
    }
  }

  return (
    <section className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Collection workflow</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">Record payments and review dues in one place</p>
          <p className="mt-2 text-sm text-slate-600">
            Each card now surfaces installment, arrears, share, and final payable amounts for faster owner review.
          </p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">History snapshot</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{payments.length} recorded payments</p>
          <p className="mt-2 text-sm text-slate-600">
            The latest entries appear first and keep the backend-provided payment state intact.
          </p>
        </article>
      </div>
      <PaymentEntryForm ownerId={ownerId} onRecorded={handleRecordedPayment} />
      <PaymentHistoryList
        error={historyError}
        loading={historyLoading}
        onRetry={onRetryHistory}
        payments={payments}
        title="Recorded payments"
      />
    </section>
  );
}
