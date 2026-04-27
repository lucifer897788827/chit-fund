import { AsyncSectionState } from "../../components/page-state";
import { buildPayoutBreakdown, formatMoney } from "./balances";

function formatDateTime(value) {
  if (!value) {
    return "Not available";
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsedDate);
}

function titleCase(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getPayoutLabel(payout) {
  const pieces = [payout.subscriberName || `Subscriber #${payout.subscriberId ?? "n/a"}`];

  if (payout.groupCode || payout.groupTitle) {
    pieces.push(payout.groupTitle || "Group");
    if (payout.groupCode) {
      pieces.push(payout.groupCode);
    }
  }

  return pieces.join(" · ");
}

function isPendingStatus(status) {
  return String(status ?? "").toLowerCase() === "pending";
}

function isSettledStatus(status) {
  const normalizedStatus = String(status ?? "").toLowerCase();
  return normalizedStatus === "paid" || normalizedStatus === "settled";
}

function PayoutRow({ payout, onSettle, settling }) {
  const isPending = isPendingStatus(payout.status);
  const isSettled = isSettledStatus(payout.status);
  const breakdown = buildPayoutBreakdown(payout);

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3>{getPayoutLabel(payout)}</h3>
          <p className="text-sm text-slate-600">
            Auction result #{payout.auctionResultId ?? "n/a"}
            {payout.membershipId ? ` · Membership #${payout.membershipId}` : ""}
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Final payout</p>
          <p className="mt-1 text-3xl font-semibold text-emerald-700">{breakdown.finalPayoutLabel}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Chit value</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{breakdown.chitValueLabel}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bid amount</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{breakdown.bidAmountLabel ?? "Not available"}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Commission</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">{breakdown.commissionAmountLabel}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monthly installment</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">
            {breakdown.monthlyInstallmentLabel ?? "Not available"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Share received</p>
          <p className="mt-1 text-lg font-semibold text-slate-950">
            {breakdown.shareReceivedLabel ?? "Not available"}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4">
        <p className="text-sm font-semibold text-slate-900">Winner payout breakdown</p>
        <dl className="mt-3 space-y-2 text-sm text-slate-700">
          <div className="flex items-center justify-between gap-3">
            <dt>+ Share</dt>
            <dd>{breakdown.shareReceivedLabel ?? "Not available"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt>- Installment</dt>
            <dd>{breakdown.monthlyInstallmentLabel ?? "Not available"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-2 font-semibold text-slate-950">
            <dt>= Final payout</dt>
            <dd>{breakdown.finalPayoutLabel}</dd>
          </div>
        </dl>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="font-medium text-slate-500">Gross amount</dt>
          <dd>{formatMoney(payout.grossAmount)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Deductions</dt>
          <dd>{formatMoney(payout.deductionsAmount)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Status</dt>
          <dd>{titleCase(payout.status)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Payout method</dt>
          <dd>{titleCase(payout.payoutMethod)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Payout date</dt>
          <dd>{formatDateTime(payout.payoutDate)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Reference</dt>
          <dd>{payout.referenceNo || "Not provided"}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {isPending ? (
          <button className="action-button" disabled={settling} onClick={() => onSettle(payout)} type="button">
            {settling ? "Settling..." : "Mark settled"}
          </button>
        ) : null}
        {isSettled ? <p className="text-sm text-emerald-700">This payout has already been settled.</p> : null}
        {!isPending && !isSettled ? (
          <p className="text-sm text-slate-600">No settlement action is available for this payout status.</p>
        ) : null}
      </div>
    </article>
  );
}

export default function OwnerPayoutsPanel({
  payouts,
  loading = false,
  error = "",
  onRetry,
  onSettle,
  settlingPayoutId = null,
}) {
  const normalizedPayouts = Array.isArray(payouts) ? payouts : [];
  const pendingCount = normalizedPayouts.filter((payout) => isPendingStatus(payout.status)).length;
  const settledCount = normalizedPayouts.filter((payout) => isSettledStatus(payout.status)).length;
  const pendingAmount = normalizedPayouts.reduce(
    (sum, payout) => (isPendingStatus(payout.status) ? sum + Number(payout.netAmount ?? 0) : sum),
    0,
  );

  return (
    <AsyncSectionState
      className="space-y-4"
      description="Review auction payouts and settle any pending winner transfers from one place."
      empty={normalizedPayouts.length === 0}
      emptyDescription="No payouts have been generated yet."
      emptyTitle="No payouts to review yet."
      error={error}
      errorTitle="We could not load payout records."
      loading={loading}
      loadingDescription="Fetching the latest payout records."
      loadingLabel="Loading payouts..."
      onRetry={onRetry}
      retryLabel="Refresh payouts"
      title="Payouts"
    >
      <div className="panel-grid">
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Pending payouts</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{pendingCount}</p>
          <p className="mt-2 text-sm text-slate-600">{formatMoney(pendingAmount)} waiting to be settled.</p>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Settled payouts</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{settledCount}</p>
          <p className="mt-2 text-sm text-slate-600">Confirmed payout transfers already closed out.</p>
        </article>
      </div>

      <div className="grid gap-3">
        {normalizedPayouts.map((payout, index) => (
          <PayoutRow
            key={payout.id ?? `${payout.auctionResultId ?? "payout"}-${index}`}
            onSettle={onSettle}
            payout={payout}
            settling={settlingPayoutId === payout.id}
          />
        ))}
      </div>
    </AsyncSectionState>
  );
}
