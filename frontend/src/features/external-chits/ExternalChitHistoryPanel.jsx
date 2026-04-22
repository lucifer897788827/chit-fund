import { useEffect, useMemo, useState } from "react";

import { AsyncSectionState } from "../../components/page-state";
import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import {
  buildExternalChitEntryDraft,
  buildExternalChitEntryPayload,
  formatAmount,
  formatDate,
  formatDateTime,
  getExternalChitMonthlyEntries,
  getExternalChitOverrideStatus,
} from "./utils";

const winnerTypeOptions = [
  { value: "OTHER", label: "Other member" },
  { value: "SELF", label: "Self" },
];

function SummaryCard({ label, value, detail, status = null }) {
  return (
    <article
      className={`rounded-lg border p-4 shadow-sm ${
        status?.isManual ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
        {status ? <OverrideBadge status={status} /> : null}
      </div>
      <p className="mt-2 text-xl font-semibold text-slate-950">{value}</p>
      {detail ? (
        <p className={`mt-1 text-sm ${status?.isManual ? "text-amber-950" : "text-slate-600"}`}>{detail}</p>
      ) : null}
    </article>
  );
}

function OverrideBadge({ status }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${
        status.isManual ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-700"
      }`}
    >
      {status.badge}
    </span>
  );
}

function LedgerValueField({ label, value, status, fullWidth = false }) {
  return (
    <div
      className={`rounded-lg border p-3 ${status.isManual ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"} ${
        fullWidth ? "sm:col-span-2 xl:col-span-3" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <dt className="font-medium text-slate-500">{label}</dt>
        <OverrideBadge status={status} />
      </div>
      <dd className="mt-2 text-base font-semibold text-slate-900">{value}</dd>
      <p className={`mt-1 text-xs ${status.isManual ? "text-amber-900" : "text-slate-500"}`}>{status.description}</p>
    </div>
  );
}

function getFieldInputClasses(isManual) {
  return `w-full rounded-md border px-3 py-2 ${
    isManual ? "border-amber-300 bg-amber-50 text-amber-950" : "border-slate-300 bg-white"
  }`;
}

function LedgerEntryCard({ entry, onEdit }) {
  const winnerLabel =
    entry.winnerType === "SELF"
      ? "Self"
      : entry.winnerName
        ? `Other · ${entry.winnerName}`
        : "Other";
  const bidStatus = getExternalChitOverrideStatus(entry, "bid");
  const shareStatus = getExternalChitOverrideStatus(entry, "share");
  const payableStatus = getExternalChitOverrideStatus(entry, "payable");
  const payoutStatus = getExternalChitOverrideStatus(entry, "payout");

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">
              {entry.monthNumber ? `Month ${entry.monthNumber}` : "Unnumbered month"}
            </h3>
            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
              {entry.entryType}
            </span>
          </div>
          <p className="text-sm text-slate-600">{entry.description || "No description provided."}</p>
        </div>

        <div className="text-right text-sm text-slate-600">
          <p>{formatDate(entry.entryDate)}</p>
          <p>{formatDateTime(entry.updatedAt || entry.createdAt)}</p>
        </div>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2 xl:grid-cols-3">
        <LedgerValueField
          label="Bid amount"
          status={bidStatus}
          value={entry.bidAmount === null || entry.bidAmount === undefined ? "Not entered" : formatAmount(entry.bidAmount)}
        />
        <div>
          <dt className="font-medium text-slate-500">Winner</dt>
          <dd className="mt-2 font-semibold text-slate-900">{winnerLabel}</dd>
          <p className="mt-1 text-xs text-slate-500">Recorded winner for this month.</p>
        </div>
        <LedgerValueField
          label="My share"
          status={shareStatus}
          value={entry.myShare === null || entry.myShare === undefined ? "Not available" : formatAmount(entry.myShare)}
        />
        <LedgerValueField
          label="My payable"
          status={payableStatus}
          value={entry.myPayable === null || entry.myPayable === undefined ? "Not available" : formatAmount(entry.myPayable)}
        />
        <LedgerValueField
          label="My payout"
          status={payoutStatus}
          value={entry.myPayout === null || entry.myPayout === undefined ? "Not available" : formatAmount(entry.myPayout)}
        />
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="rounded-md border border-slate-300 px-4 py-2" onClick={() => onEdit(entry.id)} type="button">
          Edit month entry
        </button>
      </div>
    </article>
  );
}

function HistoryItem({ entry }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-slate-900">{entry.entryType}</h3>
          <p className="text-sm text-slate-600">{entry.description}</p>
        </div>
        <div className="text-right text-sm text-slate-600">
          <p>{formatDate(entry.entryDate)}</p>
          <p>{formatDateTime(entry.createdAt)}</p>
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2">
        <div>
          <dt className="font-medium text-slate-500">Amount</dt>
          <dd>{entry.amount === null || entry.amount === undefined ? "Not provided" : formatAmount(entry.amount)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Entry id</dt>
          <dd>{entry.id}</dd>
        </div>
      </dl>
    </article>
  );
}

function OverrideLegend() {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-slate-900">Value source</p>
        <OverrideBadge status={{ isManual: false, badge: "Auto" }} />
        <span className="text-sm text-slate-600">Calculated automatically</span>
        <OverrideBadge status={{ isManual: true, badge: "Manual" }} />
        <span className="text-sm text-slate-600">Manually adjusted</span>
      </div>
    </div>
  );
}

export default function ExternalChitHistoryPanel({
  chit,
  summary,
  loading = false,
  error = "",
  summaryLoading = false,
  summaryError = "",
  onRetry,
  onRetrySummary,
  onCreateEntry,
  onUpdateEntry,
  submitting = { mode: null, id: null },
  feedback = { type: "", message: "" },
}) {
  const history = useMemo(() => (Array.isArray(chit?.entryHistory) ? chit.entryHistory : []), [chit?.entryHistory]);
  const monthlyEntries = useMemo(() => getExternalChitMonthlyEntries(chit), [chit]);
  const otherHistory = useMemo(
    () => history.filter((entry) => entry?.monthNumber === null || entry?.monthNumber === undefined),
    [history],
  );
  const latestMonthlyEntry = monthlyEntries.length > 0 ? monthlyEntries[monthlyEntries.length - 1] : null;
  const [editingEntryId, setEditingEntryId] = useState(null);
  const [draft, setDraft] = useState(() => buildExternalChitEntryDraft(null, chit));

  useEffect(() => {
    setEditingEntryId(null);
    setDraft(buildExternalChitEntryDraft(null, chit));
  }, [chit]);

  const editingEntry = useMemo(
    () => monthlyEntries.find((entry) => entry.id === editingEntryId) ?? null,
    [editingEntryId, monthlyEntries],
  );

  useEffect(() => {
    setDraft(buildExternalChitEntryDraft(editingEntry, chit));
  }, [editingEntry, chit]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!chit) {
      return;
    }
    if (isSubmitting) {
      return;
    }

    const payload = buildExternalChitEntryPayload(draft, chit);
    let succeeded = false;

    if (editingEntry) {
      succeeded = await onUpdateEntry?.(editingEntry.id, payload);
    } else {
      succeeded = await onCreateEntry?.(payload);
    }

    if (succeeded) {
      setEditingEntryId(null);
      setDraft(buildExternalChitEntryDraft(null, chit));
    }
  }

  function updateField(field, value) {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  }

  if (!chit && !error) {
    return (
      <section className="panel space-y-4">
        <div className="space-y-1">
          <h2>Monthly ledger</h2>
          <p className="text-sm text-slate-600">Select a chit to manage month-by-month entries and totals.</p>
        </div>
        <p>No chit selected yet.</p>
      </section>
    );
  }

  const isEditing = Boolean(editingEntry);
  const isSubmitting = submitting.mode === (isEditing ? "edit-entry" : "create-entry") &&
    submitting.id === (isEditing ? editingEntry?.id : chit?.id);
  const draftSourceEntry = editingEntry ?? latestMonthlyEntry;
  const draftBidStatus = getExternalChitOverrideStatus(draftSourceEntry, "bid");
  const draftShareStatus = getExternalChitOverrideStatus(draftSourceEntry, "share");
  const draftPayableStatus = getExternalChitOverrideStatus(draftSourceEntry, "payable");
  const draftPayoutStatus = getExternalChitOverrideStatus(draftSourceEntry, "payout");
  const latestShareStatus = getExternalChitOverrideStatus(latestMonthlyEntry, "share");
  const latestPayableStatus = getExternalChitOverrideStatus(latestMonthlyEntry, "payable");
  const latestPayoutStatus = getExternalChitOverrideStatus(latestMonthlyEntry, "payout");

  return (
    <AsyncSectionState
      className="space-y-5"
      description={
        chit
          ? `${chit.title}${chit.status ? ` · ${chit.status}` : ""} · monthly manual ledger`
          : "Select a chit to manage month-by-month entries."
      }
      empty={false}
      error={error}
      errorTitle="We could not load this chit ledger."
      loading={loading}
      loadingDescription="Fetching the selected chit, saved entries, and summary totals."
      loadingLabel="Loading ledger workspace..."
      onRetry={onRetry}
      retryLabel="Refresh ledger"
      title="Monthly ledger"
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          detail={summaryLoading ? "Refreshing totals..." : "Total you contributed across saved months."}
          label="Total paid"
          value={summaryLoading && !summary ? "Loading..." : formatAmount(summary?.totalPaid)}
        />
        <SummaryCard
          detail="Share plus payout received from all saved months."
          label="Total received"
          value={summaryLoading && !summary ? "Loading..." : formatAmount(summary?.totalReceived)}
        />
        <SummaryCard
          detail="Net result from saved external-chit entries."
          label="Profit"
          value={summaryLoading && !summary ? "Loading..." : formatAmount(summary?.profit)}
        />
        <SummaryCard
          detail={summary?.winningMonth ? "First saved self-win month." : "No self-win saved yet."}
          label="Winning month"
          value={summaryLoading && !summary ? "Loading..." : summary?.winningMonth ? `Month ${summary.winningMonth}` : "Not yet"}
        />
      </div>

      {summaryError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-950" role="alert">
          <p className="font-semibold">Summary totals are unavailable right now.</p>
          <p className="text-sm">{summaryError}</p>
          {onRetrySummary ? (
            <button className="action-button mt-3 bg-amber-700 hover:bg-amber-800" onClick={onRetrySummary} type="button">
              Refresh summary
            </button>
          ) : null}
        </div>
      ) : null}

      <OverrideLegend />

      <div className="space-y-3">
        <div className="space-y-1">
          <h3 className="text-lg font-semibold text-slate-900">Latest month snapshot</h3>
          <p className="text-sm text-slate-600">Your key month-wise numbers stay visible while you add the next entry.</p>
        </div>

        {latestMonthlyEntry ? (
          <div className="grid gap-3 md:grid-cols-3">
            <SummaryCard
              detail={`Month ${latestMonthlyEntry.monthNumber} · ${latestShareStatus.description}`}
              label="My share"
              status={latestShareStatus}
              value={formatAmount(latestMonthlyEntry.myShare)}
            />
            <SummaryCard
              detail={`Month ${latestMonthlyEntry.monthNumber} · ${latestPayableStatus.description}`}
              label="My payable"
              status={latestPayableStatus}
              value={formatAmount(latestMonthlyEntry.myPayable)}
            />
            <SummaryCard
              detail={`Month ${latestMonthlyEntry.monthNumber} · ${latestPayoutStatus.description}`}
              label="My payout"
              status={latestPayoutStatus}
              value={formatAmount(latestMonthlyEntry.myPayout)}
            />
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4">
            <p className="font-semibold text-slate-900">No monthly snapshot yet.</p>
            <p className="mt-1 text-sm text-slate-600">Add the first month entry below to see your share, payable, and payout here.</p>
          </div>
        )}
      </div>

      <FormFrame
        description={
          isEditing
            ? "Update the saved month and keep the ledger totals in sync."
            : "Add each month manually and keep the bid, winner, share, payable, and payout together."
        }
        error={feedback.type === "error" ? feedback.message : ""}
        success={feedback.type === "success" ? feedback.message : ""}
        title={isEditing ? "Edit month entry" : "Add month entry"}
      >
        <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
          <FormField
            helpText="Month number for this saved ledger entry."
            htmlFor="external-entry-month"
            label="Month"
          >
            <input
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2"
              id="external-entry-month"
              min="1"
              onChange={(event) => updateField("monthNumber", event.target.value)}
              required
              step="1"
              type="number"
              value={draft.monthNumber}
            />
          </FormField>

          <FormField
            helpText={
              isEditing
                ? draftBidStatus.description
                : "Leave blank if this month has no bid yet, or enter the saved bid amount."
            }
            htmlFor="external-entry-bid"
            label="Bid amount"
          >
            <input
              className={getFieldInputClasses(isEditing && draftBidStatus.isManual)}
              id="external-entry-bid"
              min="0"
              onChange={(event) => updateField("bidAmount", event.target.value)}
              step="1"
              type="number"
              value={draft.bidAmount}
            />
          </FormField>

          <FormField htmlFor="external-entry-winner-type" label="Winner">
            <select
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2"
              id="external-entry-winner-type"
              onChange={(event) => updateField("winnerType", event.target.value)}
              value={draft.winnerType}
            >
              {winnerTypeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField
            htmlFor="external-entry-share"
            helpText={isEditing ? draftShareStatus.description : "Leave blank to use the backend calculation for your share."}
            label="Share"
          >
            <input
              className={getFieldInputClasses(isEditing && draftShareStatus.isManual)}
              id="external-entry-share"
              min="0"
              onChange={(event) => updateField("myShare", event.target.value)}
              step="1"
              type="number"
              value={draft.myShare}
            />
          </FormField>

          <FormField
            htmlFor="external-entry-payable"
            helpText={isEditing ? draftPayableStatus.description : "Leave blank to keep the calculated payable."}
            label="Payable"
          >
            <input
              className={getFieldInputClasses(isEditing && draftPayableStatus.isManual)}
              id="external-entry-payable"
              min="0"
              onChange={(event) => updateField("myPayable", event.target.value)}
              step="1"
              type="number"
              value={draft.myPayable}
            />
          </FormField>

          <FormField
            htmlFor="external-entry-payout"
            helpText={isEditing ? draftPayoutStatus.description : "Leave blank to keep the calculated payout."}
            label="Payout"
          >
            <input
              className={getFieldInputClasses(isEditing && draftPayoutStatus.isManual)}
              id="external-entry-payout"
              min="0"
              onChange={(event) => updateField("myPayout", event.target.value)}
              step="1"
              type="number"
              value={draft.myPayout}
            />
          </FormField>

          <FormActions
            className="md:col-span-2"
            note="Share, payable, and payout can be entered manually or left blank for the stored calculation."
          >
            <button className="action-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : isEditing ? "Update month entry" : "Add month entry"}
            </button>
            {isEditing ? (
              <button
                className="rounded-md border border-slate-300 px-4 py-2"
                onClick={() => {
                  setEditingEntryId(null);
                  setDraft(buildExternalChitEntryDraft(null, chit));
                }}
                type="button"
              >
                Cancel editing
              </button>
            ) : null}
          </FormActions>
        </form>
      </FormFrame>

      <div className="space-y-3">
        <div className="space-y-1">
          <h3 className="text-lg font-semibold text-slate-900">Saved month entries</h3>
          <p className="text-sm text-slate-600">
            Each card shows the stored month snapshot, including your share, payable, and payout.
          </p>
        </div>

        {monthlyEntries.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4">
            <p className="font-semibold text-slate-900">No month entries recorded yet.</p>
            <p className="mt-1 text-sm text-slate-600">Add the first saved month above to start tracking the external chit.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {monthlyEntries.map((entry) => (
              <LedgerEntryCard key={entry.id} entry={entry} onEdit={setEditingEntryId} />
            ))}
          </div>
        )}
      </div>

      {otherHistory.length > 0 ? (
        <div className="space-y-3">
          <div className="space-y-1">
            <h3 className="text-lg font-semibold text-slate-900">Other saved history</h3>
            <p className="text-sm text-slate-600">Older notes and non-month records remain available below.</p>
          </div>

          <div className="grid gap-3">
            {otherHistory.map((entry) => (
              <HistoryItem key={entry.id} entry={entry} />
            ))}
          </div>
        </div>
      ) : null}
    </AsyncSectionState>
  );
}
