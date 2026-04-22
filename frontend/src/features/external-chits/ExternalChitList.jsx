import { formatAmount, formatDate } from "./utils";

function ChitCard({
  chit,
  isSelected,
  isDeletePending,
  onSelect,
  onEdit,
  onDelete,
  onCancelDelete,
  onConfirmDelete,
}) {
  return (
    <article
      className={`rounded-lg border p-4 shadow-sm ${isSelected ? "border-teal-500 bg-teal-50" : "border-slate-200 bg-white"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-slate-900">{chit.title}</h3>
          <p className="text-sm text-slate-600">{chit.organizerName}</p>
          <p className="text-sm text-slate-600">
            {formatAmount(chit.chitValue)} · Installment {formatAmount(chit.installmentAmount)}
          </p>
          <p className="text-sm text-slate-600">
            {chit.cycleFrequency || "Unknown"} · Starts {formatDate(chit.startDate)}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
          {chit.status}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="rounded-md border border-slate-300 px-4 py-2" onClick={() => onSelect(chit)} type="button">
          Open ledger
        </button>
        <button className="action-button" onClick={() => onEdit(chit)} type="button">
          Edit chit
        </button>
        {isDeletePending ? (
          <>
            <button className="rounded-md border border-red-300 px-4 py-2 text-red-700" onClick={() => onConfirmDelete(chit)} type="button">
              Confirm delete
            </button>
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={onCancelDelete} type="button">
              Cancel
            </button>
          </>
        ) : (
          <button
            className="rounded-md border border-red-300 px-4 py-2 text-red-700"
            disabled={chit.status === "deleted"}
            onClick={() => onDelete(chit)}
            type="button"
          >
            Delete chit
          </button>
        )}
      </div>
    </article>
  );
}

export default function ExternalChitList({
  chits,
  loading = false,
  error = "",
  onRetry,
  selectedChitId,
  deleteTargetId,
  onSelect,
  onEdit,
  onDelete,
  onCancelDelete,
  onConfirmDelete,
}) {
  const normalizedChits = Array.isArray(chits) ? chits : [];

  return (
    <section className="panel space-y-4">
      <div className="space-y-1">
        <h2>External chit records</h2>
        <p className="text-sm text-slate-600">Review each chit, open its monthly ledger, and manage the record in place.</p>
      </div>

      {loading ? <p aria-live="polite">Loading external chit records...</p> : null}

      {!loading && error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-950" role="alert">
          <p className="font-semibold">We could not load external chit records.</p>
          <p className="text-sm">{error}</p>
          {onRetry ? (
            <button className="action-button mt-3 bg-red-700 hover:bg-red-800" onClick={onRetry} type="button">
              Retry
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && !error && normalizedChits.length === 0 ? <p>No external chits added yet.</p> : null}

      {!loading && !error && normalizedChits.length > 0 ? (
        <div className="grid gap-3">
          {normalizedChits.map((chit) => (
            <ChitCard
              key={chit.id}
              chit={chit}
              isDeletePending={deleteTargetId === chit.id}
              isSelected={selectedChitId === chit.id}
              onCancelDelete={onCancelDelete}
              onConfirmDelete={onConfirmDelete}
              onDelete={onDelete}
              onEdit={onEdit}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
