import { useEffect, useMemo, useState } from "react";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { toast } from "../../hooks/use-toast";
import { recordPayment } from "./api";
import {
  formatAmount,
  formatPaymentDate,
  getPaymentDuesBreakdown,
  getPaymentStatus,
  todayInputValue,
  toOptionalNumber,
} from "./helpers";

const initialDraft = (ownerId) => ({
  ownerId: ownerId ?? "",
  subscriberId: "",
  membershipId: "",
  installmentId: "",
  paymentType: "membership",
  paymentMethod: "cash",
  amount: "",
  paymentDate: todayInputValue(),
  referenceNo: "",
});

export default function PaymentEntryForm({ ownerId, onRecorded }) {
  const [draft, setDraft] = useState(() => initialDraft(ownerId));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [lastRecordedPayment, setLastRecordedPayment] = useState(null);

  useEffect(() => {
    setDraft((currentDraft) => {
      const nextOwnerId = ownerId ?? "";
      if (currentDraft.ownerId === nextOwnerId) {
        return currentDraft;
      }
      return {
        ...currentDraft,
        ownerId: nextOwnerId,
      };
    });
  }, [ownerId]);

  function updateDraft(field, value) {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
    setError("");
    setSuccess("");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (submitting) {
      return;
    }

    if (!draft.ownerId && draft.ownerId !== 0) {
      setError("An owner id is required to record a payment.");
      return;
    }

    const payload = {
      ownerId: toOptionalNumber(draft.ownerId),
      subscriberId: toOptionalNumber(draft.subscriberId),
      membershipId: toOptionalNumber(draft.membershipId),
      installmentId: toOptionalNumber(draft.installmentId),
      paymentType: draft.paymentType,
      paymentMethod: draft.paymentMethod,
      amount: toOptionalNumber(draft.amount),
      paymentDate: draft.paymentDate,
      referenceNo: draft.referenceNo.trim() || null,
    };

    if (payload.ownerId === null || payload.subscriberId === null || payload.amount === null) {
      setError("Owner, subscriber, and amount are required.");
      return;
    }

    setSubmitting(true);
    setError("");
    setSuccess("");

    try {
      const recordedPayment = await recordPayment(payload);
      setLastRecordedPayment(recordedPayment);
      setSuccess("Payment recorded successfully.");
      toast({
        title: "Payment recorded",
        description: `${formatAmount(recordedPayment.amount ?? payload.amount)} saved successfully.`,
      });
      if (typeof onRecorded === "function") {
        onRecorded(recordedPayment);
      }
    } catch (submitError) {
      const detail = submitError?.response?.data?.detail;
      const message =
        detail ||
        submitError?.response?.data?.message ||
        submitError?.message ||
        "Unable to record this payment right now.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const latestPaymentStatus = getPaymentStatus(lastRecordedPayment);
  const latestDuesBreakdown = getPaymentDuesBreakdown(lastRecordedPayment);
  const latestPaymentNote = [
    latestPaymentStatus ? `Payment status: ${latestPaymentStatus}.` : "",
    latestDuesBreakdown?.installmentBalanceAmount != null
      ? `Installment balance: ${formatAmount(latestDuesBreakdown.installmentBalanceAmount)}.`
      : "",
    latestDuesBreakdown?.penaltyAmount != null
      ? `Penalty: ${formatAmount(latestDuesBreakdown.penaltyAmount)}.`
      : "",
    latestDuesBreakdown?.arrearsAmount != null
      ? `Arrears: ${formatAmount(latestDuesBreakdown.arrearsAmount)}.`
      : "",
    latestDuesBreakdown?.nextDueDate
      ? `Next due date: ${formatPaymentDate(latestDuesBreakdown.nextDueDate)}.`
      : "",
    latestDuesBreakdown?.nextDueAmount != null
      ? `Next due amount: ${formatAmount(latestDuesBreakdown.nextDueAmount)}.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  const draftSummary = useMemo(
    () => ({
      type: draft.paymentType,
      method: draft.paymentMethod,
      amount: draft.amount ? formatAmount(draft.amount) : "Not entered",
      paymentDate: draft.paymentDate || "Not entered",
      reference: draft.referenceNo.trim() || "Not added",
    }),
    [draft],
  );

  return (
    <FormFrame
      description={`Capture a secured payment entry for owner #${ownerId ?? "not set"} and keep the draft ready for the next update.`}
      error={error}
      success={success ? `${success}${draft.amount ? ` ${formatAmount(draft.amount)} saved.` : ""}` : ""}
      title="Record payment"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
          <input aria-hidden="true" hidden name="ownerId" readOnly value={draft.ownerId} />

          <FormField htmlFor="subscriberId" label="Subscriber ID">
            <input
              className="text-input"
              id="subscriberId"
              inputMode="numeric"
              name="subscriberId"
              onChange={(event) => updateDraft("subscriberId", event.target.value)}
              type="number"
              value={draft.subscriberId}
            />
          </FormField>

          <FormField htmlFor="membershipId" label="Membership ID">
            <input
              className="text-input"
              id="membershipId"
              inputMode="numeric"
              name="membershipId"
              onChange={(event) => updateDraft("membershipId", event.target.value)}
              type="number"
              value={draft.membershipId}
            />
          </FormField>

          <FormField htmlFor="installmentId" label="Installment ID (optional)">
            <input
              className="text-input"
              id="installmentId"
              inputMode="numeric"
              name="installmentId"
              onChange={(event) => updateDraft("installmentId", event.target.value)}
              type="number"
              value={draft.installmentId}
            />
            <p className="mt-2 text-xs text-slate-500">
              For installment payments, leave this blank to apply the payment to the next unpaid installment for the
              membership.
            </p>
          </FormField>

          <FormField htmlFor="paymentType" label="Payment type">
            <select
              className="text-input"
              id="paymentType"
              name="paymentType"
              onChange={(event) => updateDraft("paymentType", event.target.value)}
              value={draft.paymentType}
            >
              <option value="membership">Membership</option>
              <option value="installment">Installment</option>
              <option value="advance">Advance</option>
              <option value="other">Other</option>
            </select>
          </FormField>

          <FormField htmlFor="paymentMethod" label="Payment method">
            <select
              className="text-input"
              id="paymentMethod"
              name="paymentMethod"
              onChange={(event) => updateDraft("paymentMethod", event.target.value)}
              value={draft.paymentMethod}
            >
              <option value="cash">Cash</option>
              <option value="upi">UPI</option>
              <option value="bank_transfer">Bank transfer</option>
              <option value="card">Card</option>
            </select>
          </FormField>

          <FormField htmlFor="amount" label="Amount">
            <input
              className="text-input"
              id="amount"
              inputMode="numeric"
              name="amount"
              onChange={(event) => updateDraft("amount", event.target.value)}
              step="1"
              type="number"
              value={draft.amount}
            />
          </FormField>

          <FormField htmlFor="paymentDate" label="Payment date">
            <input
              className="text-input"
              id="paymentDate"
              name="paymentDate"
              onChange={(event) => updateDraft("paymentDate", event.target.value)}
              placeholder="YYYY-MM-DD"
              type="text"
              value={draft.paymentDate}
            />
          </FormField>

          <FormField className="md:col-span-2" htmlFor="referenceNo" label="Reference number">
            <input
              className="text-input"
              id="referenceNo"
              name="referenceNo"
              onChange={(event) => updateDraft("referenceNo", event.target.value)}
              placeholder="Optional UPI or receipt reference"
              type="text"
              value={draft.referenceNo}
            />
          </FormField>

          <FormActions
            className="md:col-span-2"
            note={
              latestPaymentNote ||
              (draft.amount ? `Drafted amount: ${formatAmount(draft.amount)}` : "Fill in the payment details and save.")
            }
          >
            <button className="action-button" disabled={submitting} type="submit">
              {submitting ? "Loading..." : "Record payment"}
            </button>
          </FormActions>
        </form>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Draft summary</p>
            <div className="mt-3 space-y-3">
              <div>
                <p className="text-sm text-slate-500">Amount</p>
                <p className="text-2xl font-semibold text-slate-950">{draftSummary.amount}</p>
              </div>
              <dl className="space-y-2 text-sm text-slate-700">
                <div className="flex items-center justify-between gap-3">
                  <dt>Type</dt>
                  <dd>{draftSummary.type}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Method</dt>
                  <dd>{draftSummary.method}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Date</dt>
                  <dd>{draftSummary.paymentDate}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Reference</dt>
                  <dd>{draftSummary.reference}</dd>
                </div>
              </dl>
            </div>
          </section>

          {lastRecordedPayment ? (
            <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Latest recorded</p>
              <p className="mt-2 text-2xl font-semibold text-emerald-800">
                {formatAmount(lastRecordedPayment.amount)}
              </p>
              <p className="mt-2 text-sm text-emerald-900">
                {latestPaymentStatus ? `Status: ${latestPaymentStatus}` : "Payment saved"}
              </p>
            </section>
          ) : null}
        </aside>
      </div>
    </FormFrame>
  );
}
