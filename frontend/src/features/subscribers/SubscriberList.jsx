function getStatusLabel(status) {
  if (status === "deleted") {
    return "Deleted";
  }

  if (status === "inactive") {
    return "Inactive";
  }

  return "Active";
}

function isDeactivated(status) {
  return status === "deleted" || status === "inactive";
}

export default function SubscriberList({ subscribers = [], onEdit, onDeactivate }) {
  return (
    <section className="panel space-y-4">
      <div className="space-y-1">
        <h2>Subscribers</h2>
        <p className="text-sm text-slate-600">Keep each subscriber visible while you manage their account status.</p>
      </div>

      {subscribers.length === 0 ? <p>No subscribers have been created yet.</p> : null}

      {subscribers.length > 0 ? (
        <div className="grid gap-3">
          {subscribers.map((subscriber) => (
            <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" key={subscriber.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <h3 className="text-lg font-semibold text-slate-900">{subscriber.fullName}</h3>
                  <p className="text-sm text-slate-600">{subscriber.phone}</p>
                  {subscriber.email ? <p className="text-sm text-slate-500">{subscriber.email}</p> : null}
                </div>

                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    isDeactivated(subscriber.status)
                      ? "bg-slate-100 text-slate-700"
                      : "bg-emerald-50 text-emerald-700"
                  }`}
                >
                  {getStatusLabel(subscriber.status)}
                </span>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                  onClick={() => onEdit?.(subscriber)}
                  type="button"
                >
                  Edit {subscriber.fullName}
                </button>
                <button
                  className="rounded-md border border-red-300 px-3 py-2 text-sm text-red-700 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isDeactivated(subscriber.status)}
                  onClick={() => onDeactivate?.(subscriber)}
                  type="button"
                >
                  Deactivate {subscriber.fullName}
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
