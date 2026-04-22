import React from "react";

function normalizeAmount(value) {
  const amount = Number(value);

  if (!Number.isFinite(amount)) {
    return 0;
  }

  return Math.round(amount);
}

function getFirstDefinedValue(source, keys) {
  for (const key of keys) {
    if (source?.[key] != null && source[key] !== "") {
      return source[key];
    }
  }

  return null;
}

function normalizePaymentStatus(value) {
  if (!value) {
    return null;
  }

  const normalizedValue = String(value).trim().toUpperCase();
  if (["FULL", "PAID", "COMPLETE", "COMPLETED", "SETTLED"].includes(normalizedValue)) {
    return "FULL";
  }
  if (["PARTIAL", "PARTIALLY_PAID"].includes(normalizedValue)) {
    return "PARTIAL";
  }
  if (["PENDING", "DUE", "UNPAID"].includes(normalizedValue)) {
    return "PENDING";
  }

  return normalizedValue;
}

function formatDate(value) {
  if (!value) {
    return null;
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsedDate);
}

export function formatMoney(value, options = {}) {
  const currencyLabel = options.currencyLabel ?? "Rs.";
  const amount = normalizeAmount(value);
  const formattedAmount = new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  }).format(amount);

  return `${currencyLabel} ${formattedAmount}`;
}

function getOptionalAmount(value) {
  if (value == null || value === "") {
    return null;
  }

  const normalized = normalizeAmount(value);
  return Number.isFinite(normalized) ? normalized : null;
}

function getFormattedMoney(value) {
  return value == null ? null : formatMoney(value);
}

function getStatusTone(paymentStatus, balanceState) {
  if (paymentStatus === "FULL" || balanceState === "settled" || balanceState === "credit") {
    return {
      badge: "border-emerald-200 bg-emerald-50 text-emerald-900",
      amount: "text-emerald-700",
      accent: "bg-emerald-500",
      surface: "border-emerald-200 bg-emerald-50/60",
    };
  }

  if (paymentStatus === "PARTIAL") {
    return {
      badge: "border-amber-200 bg-amber-50 text-amber-900",
      amount: "text-amber-700",
      accent: "bg-amber-500",
      surface: "border-amber-200 bg-amber-50/60",
    };
  }

  return {
    badge: "border-rose-200 bg-rose-50 text-rose-900",
    amount: "text-rose-700",
    accent: "bg-rose-500",
    surface: "border-rose-200 bg-rose-50/60",
  };
}

function formatPercent(value) {
  if (!Number.isFinite(value)) {
    return "0%";
  }

  return `${Math.round(value)}%`;
}

function buildProgress(totalDue, totalPaid) {
  const safeDue = Math.max(normalizeAmount(totalDue), 0);
  const safePaid = Math.max(normalizeAmount(totalPaid), 0);
  const percent = safeDue > 0 ? Math.min((safePaid / safeDue) * 100, 100) : safePaid > 0 ? 100 : 0;

  return {
    totalDue: safeDue,
    totalPaid: safePaid,
    remainingAmount: Math.max(safeDue - safePaid, 0),
    percent,
    percentLabel: formatPercent(percent),
  };
}

export function buildPaymentRecordSummary(payment = {}) {
  const paymentStatus = normalizePaymentStatus(
    getFirstDefinedValue(payment, [
      "paymentStatus",
      "payment_state",
      "paymentState",
      "collectionStatus",
      "installmentStatus",
    ]),
  );
  const memberName = getFirstDefinedValue(payment, [
    "subscriberName",
    "memberName",
    "membershipName",
  ]) ?? (payment.subscriberId != null ? `Subscriber #${payment.subscriberId}` : "Subscriber");
  const slotCount = getOptionalAmount(
    getFirstDefinedValue(payment, ["slotCount", "slotsCount", "slot_count", "memberSlotCount"]),
  );
  const monthlyInstallmentAmount = getOptionalAmount(
    getFirstDefinedValue(payment, [
      "monthlyInstallment",
      "monthlyInstallmentAmount",
      "installmentAmount",
      "installmentValue",
    ]),
  );
  const shareReceivedAmount = getOptionalAmount(
    getFirstDefinedValue(payment, ["shareReceived", "shareReceivedAmount", "shareAmount", "memberShare"]),
  );
  const arrearsAmount = getOptionalAmount(
    getFirstDefinedValue(payment, ["arrearsAmount", "totalArrearsAmount", "overdueAmount"]),
  ) ?? 0;
  const penaltyAmount = getOptionalAmount(
    getFirstDefinedValue(payment, ["penaltyAmount", "latePenaltyAmount", "appliedPenaltyAmount"]),
  ) ?? 0;
  const basePayableAmount =
    getOptionalAmount(
      getFirstDefinedValue(payment, [
        "finalPayable",
        "finalPayableAmount",
        "memberPayable",
        "memberPayableAmount",
        "payableAmount",
        "netPayableAmount",
        "installmentBalanceAmount",
        "outstandingAmount",
        "balanceAmount",
      ]),
    ) ??
    (monthlyInstallmentAmount != null && shareReceivedAmount != null
      ? normalizeAmount(monthlyInstallmentAmount - shareReceivedAmount)
      : null);
  const totalPayableAmount =
    getOptionalAmount(
      getFirstDefinedValue(payment, [
        "totalPayable",
        "totalPayableAmount",
        "currentDueAmount",
        "outstandingAmount",
        "nextDueAmount",
      ]),
    ) ??
    (basePayableAmount != null ? normalizeAmount(basePayableAmount + arrearsAmount + penaltyAmount) : null);
  const paidAmount =
    getOptionalAmount(getFirstDefinedValue(payment, ["paidAmount", "amountPaid", "totalPaid", "amount"])) ?? 0;
  const progress =
    totalPayableAmount != null ? buildProgress(totalPayableAmount, paidAmount) : buildProgress(Number(payment.amount ?? 0), Number(payment.amount ?? 0));
  const balanceState =
    paymentStatus === "FULL"
      ? "settled"
      : paymentStatus === "PARTIAL"
        ? "partial"
        : totalPayableAmount != null && totalPayableAmount <= 0
          ? "settled"
          : "outstanding";
  const tone = getStatusTone(paymentStatus, balanceState);

  return {
    memberName,
    slotCount,
    monthlyInstallmentAmount,
    shareReceivedAmount,
    finalPayableAmount: basePayableAmount,
    totalPayableAmount,
    arrearsAmount,
    penaltyAmount,
    paidAmount,
    remainingAmount: totalPayableAmount != null ? Math.max(totalPayableAmount - paidAmount, 0) : progress.remainingAmount,
    paymentStatus,
    balanceState,
    tone,
    progress,
    monthlyInstallmentLabel: getFormattedMoney(monthlyInstallmentAmount),
    shareReceivedLabel: getFormattedMoney(shareReceivedAmount),
    finalPayableLabel: getFormattedMoney(basePayableAmount),
    totalPayableLabel: getFormattedMoney(totalPayableAmount),
    paidAmountLabel: getFormattedMoney(paidAmount),
    remainingAmountLabel: getFormattedMoney(
      totalPayableAmount != null ? Math.max(totalPayableAmount - paidAmount, 0) : progress.remainingAmount,
    ),
    arrearsLabel: getFormattedMoney(arrearsAmount),
    penaltyLabel: getFormattedMoney(penaltyAmount),
  };
}

export function buildPayoutBreakdown(payout = {}) {
  const chitValue =
    getOptionalAmount(
      getFirstDefinedValue(payout, ["chitValue", "chitAmount", "auctionChitValue", "grossAmount"]),
    ) ?? 0;
  const bidAmount = getOptionalAmount(
    getFirstDefinedValue(payout, ["bidAmount", "winningBidAmount", "winningBid", "discountAmount"]),
  );
  const commissionAmount = getOptionalAmount(
    getFirstDefinedValue(payout, [
      "commissionAmount",
      "organizerCommission",
      "ownerCommissionAmount",
      "deductionsAmount",
    ]),
  ) ?? 0;
  const monthlyInstallmentAmount = getOptionalAmount(
    getFirstDefinedValue(payout, ["monthlyInstallment", "monthlyInstallmentAmount", "installmentAmount"]),
  );
  const shareReceivedAmount = getOptionalAmount(
    getFirstDefinedValue(payout, [
      "shareReceived",
      "shareReceivedAmount",
      "shareAmount",
      "distributionShare",
      "dividendPerMemberAmount",
    ]),
  );
  const finalPayoutAmount =
    getOptionalAmount(
      getFirstDefinedValue(payout, ["finalPayout", "finalPayoutAmount", "winnerPayoutAmount", "netAmount"]),
    ) ?? 0;
  const winnerName =
    getFirstDefinedValue(payout, ["subscriberName", "winnerName", "memberName"]) ??
    (payout.subscriberId != null ? `Subscriber #${payout.subscriberId}` : "Winner");
  const tone = getStatusTone(normalizePaymentStatus(payout.status), normalizeAmount(finalPayoutAmount) > 0 ? "settled" : "outstanding");

  return {
    winnerName,
    chitValue,
    bidAmount,
    commissionAmount,
    monthlyInstallmentAmount,
    shareReceivedAmount,
    finalPayoutAmount,
    tone,
    chitValueLabel: getFormattedMoney(chitValue),
    bidAmountLabel: getFormattedMoney(bidAmount),
    commissionAmountLabel: getFormattedMoney(commissionAmount),
    monthlyInstallmentLabel: getFormattedMoney(monthlyInstallmentAmount),
    shareReceivedLabel: getFormattedMoney(shareReceivedAmount),
    finalPayoutLabel: getFormattedMoney(finalPayoutAmount),
  };
}

export function buildMemberBalanceSummary(input = {}) {
  const memberName = input.memberName ?? "";
  const groupTitle = input.groupTitle ?? "";
  const totalDue = normalizeAmount(getFirstDefinedValue(input, ["totalDue", "dueAmount"]) ?? 0);
  const totalPaid = normalizeAmount(getFirstDefinedValue(input, ["totalPaid", "paidAmount"]) ?? 0);
  const netBalance = normalizeAmount(totalDue - totalPaid);
  const providedOutstandingAmount = getFirstDefinedValue(input, ["outstandingAmount", "balanceAmount"]);
  const providedCreditAmount = getFirstDefinedValue(input, ["creditAmount", "advanceAmount"]);
  const outstandingAmount =
    providedOutstandingAmount != null
      ? normalizeAmount(providedOutstandingAmount)
      : Math.max(netBalance, 0);
  const creditAmount =
    providedCreditAmount != null ? normalizeAmount(providedCreditAmount) : Math.max(-netBalance, 0);
  const balanceState = creditAmount > 0 ? "credit" : outstandingAmount > 0 ? "outstanding" : "settled";
  const paymentStatus = normalizePaymentStatus(
    getFirstDefinedValue(input, ["paymentStatus", "payment_state", "paymentState", "installmentStatus"]),
  );
  const penaltyAmount = normalizeAmount(getFirstDefinedValue(input, ["penaltyAmount", "latePenaltyAmount"]) ?? 0);
  const arrearsAmount = normalizeAmount(getFirstDefinedValue(input, ["arrearsAmount"]) ?? 0);
  const nextDueAmountValue = getFirstDefinedValue(input, ["nextDueAmount"]);
  const nextDueAmount = nextDueAmountValue != null ? normalizeAmount(nextDueAmountValue) : null;
  const nextDueDate = getFirstDefinedValue(input, ["nextDueDate"]);
  const slotCountValue = getFirstDefinedValue(input, ["slotCount", "slotsCount", "slot_count"]);
  const slotCount = slotCountValue != null ? normalizeAmount(slotCountValue) : null;
  const monthlyInstallmentAmount = getOptionalAmount(
    getFirstDefinedValue(input, [
      "monthlyInstallment",
      "monthlyInstallmentAmount",
      "installmentAmount",
      "installmentValue",
    ]),
  );
  const shareReceivedAmount = getOptionalAmount(
    getFirstDefinedValue(input, ["shareReceived", "shareReceivedAmount", "shareAmount", "memberShare"]),
  );
  const finalPayableAmount =
    getOptionalAmount(
      getFirstDefinedValue(input, [
        "finalPayable",
        "finalPayableAmount",
        "memberPayable",
        "memberPayableAmount",
        "payableAmount",
        "netPayableAmount",
      ]),
    ) ??
    (monthlyInstallmentAmount != null && shareReceivedAmount != null
      ? normalizeAmount(monthlyInstallmentAmount - shareReceivedAmount)
      : outstandingAmount);
  const totalPayableAmount =
    getOptionalAmount(
      getFirstDefinedValue(input, [
        "totalPayable",
        "totalPayableAmount",
        "outstandingAmount",
        "nextDueAmount",
      ]),
    ) ??
    normalizeAmount(finalPayableAmount + arrearsAmount + penaltyAmount);
  const progressBaseAmount = totalPayableAmount > 0 ? totalPayableAmount : totalDue;
  const progress = buildProgress(progressBaseAmount, totalPaid);
  const statusTone = getStatusTone(paymentStatus, balanceState);

  return {
    memberName,
    groupTitle,
    slotCount,
    totalDue,
    totalPaid,
    outstandingAmount,
    creditAmount,
    balanceState,
    paymentStatus,
    penaltyAmount,
    arrearsAmount,
    nextDueAmount,
    nextDueDate,
    monthlyInstallmentAmount,
    shareReceivedAmount,
    finalPayableAmount,
    totalPayableAmount,
    remainingAmount: progress.remainingAmount,
    progress,
    tone: statusTone,
    dueLabel: input.dueLabel ?? formatMoney(totalDue),
    paidLabel: input.paidLabel ?? formatMoney(totalPaid),
    outstandingLabel: input.outstandingLabel ?? formatMoney(outstandingAmount),
    creditLabel: creditAmount > 0 ? input.creditLabel ?? formatMoney(creditAmount) : null,
    penaltyLabel: penaltyAmount > 0 ? input.penaltyLabel ?? formatMoney(penaltyAmount) : null,
    arrearsLabel: input.arrearsLabel ?? formatMoney(arrearsAmount),
    nextDueAmountLabel: nextDueAmount != null ? input.nextDueAmountLabel ?? formatMoney(nextDueAmount) : null,
    nextDueDateLabel: input.nextDueDateLabel ?? formatDate(nextDueDate),
    monthlyInstallmentLabel: monthlyInstallmentAmount != null ? formatMoney(monthlyInstallmentAmount) : null,
    shareReceivedLabel: shareReceivedAmount != null ? formatMoney(shareReceivedAmount) : null,
    finalPayableLabel: finalPayableAmount != null ? formatMoney(finalPayableAmount) : null,
    totalPayableLabel: totalPayableAmount != null ? formatMoney(totalPayableAmount) : null,
    remainingAmountLabel: formatMoney(progress.remainingAmount),
    progressLabel: `${formatMoney(totalPaid)} paid / ${formatMoney(progress.remainingAmount)} remaining`,
  };
}

export function MemberBalanceSummary({ summary }) {
  if (!summary) {
    return null;
  }

  return (
    <article aria-label="Member balance summary" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-slate-950">{summary.memberName || "Member balance"}</h2>
          {summary.groupTitle ? <p className="text-sm text-slate-600">{summary.groupTitle}</p> : null}
          {summary.slotCount != null ? (
            <p className="text-sm text-slate-600">
              {summary.slotCount} {Number(summary.slotCount) === 1 ? "slot" : "slots"}
            </p>
          ) : null}
        </div>
        <div className="space-y-2 text-right">
          {summary.paymentStatus ? (
            <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${summary.tone.badge}`}>
              {summary.paymentStatus}
            </span>
          ) : null}
          <div className={`rounded-2xl border px-4 py-3 ${summary.tone.surface}`}>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Final payable</p>
            <p className={`mt-1 text-2xl font-semibold ${summary.tone.amount}`}>
              {summary.finalPayableLabel ?? summary.outstandingLabel}
            </p>
          </div>
        </div>
      </header>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-900">Payment progress</p>
          <p className="text-sm text-slate-600">{summary.progressLabel}</p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
          <div
            className={`h-full rounded-full ${summary.tone.accent}`}
            style={{ width: `${Math.max(summary.progress.percent, 6)}%` }}
          />
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monthly installment</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">
            {summary.monthlyInstallmentLabel ?? summary.dueLabel}
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
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total payable</p>
          <p className={`mt-1 text-lg font-semibold ${summary.tone.amount}`}>
            {summary.totalPayableLabel ?? summary.outstandingLabel}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-sm font-semibold text-slate-900">Breakdown</p>
        <dl className="mt-3 space-y-2 text-sm text-slate-700">
          <div className="flex items-center justify-between gap-3">
            <dt>+ Share</dt>
            <dd>{summary.shareReceivedLabel ?? "Not available"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt>- Installment</dt>
            <dd>{summary.monthlyInstallmentLabel ?? summary.dueLabel}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-2 font-semibold text-slate-950">
            <dt>= Final payable</dt>
            <dd>{summary.finalPayableLabel ?? summary.outstandingLabel}</dd>
          </div>
        </dl>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2">
        <div>
          <dt className="font-medium text-slate-500">Paid</dt>
          <dd>{summary.paidLabel}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Remaining</dt>
          <dd>{summary.remainingAmountLabel}</dd>
        </div>
        {summary.penaltyLabel ? (
          <div>
            <dt className="font-medium text-slate-500">Penalty</dt>
            <dd>{summary.penaltyLabel}</dd>
          </div>
        ) : null}
        {summary.nextDueAmountLabel ? (
          <div>
            <dt className="font-medium text-slate-500">Next due</dt>
            <dd>{summary.nextDueAmountLabel}</dd>
          </div>
        ) : null}
        {summary.nextDueDateLabel ? (
          <div className="sm:col-span-2">
            <dt className="font-medium text-slate-500">Next due date</dt>
            <dd>{summary.nextDueDateLabel}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}
