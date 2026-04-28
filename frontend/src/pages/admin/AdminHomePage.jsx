import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminDashboardOverview } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

function AdminOverviewCard({ label, to, value }) {
  return (
    <Link className="quiet-card-link panel" to={to}>
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <h2 className="mt-2 text-3xl font-semibold text-slate-950">{value}</h2>
    </Link>
  );
}

export default function AdminHomePage() {
  useAppShellHeader({
    title: "Dashboard",
    contextLabel: "System-level control",
  });

  const overviewQuery = useQuery({
    queryKey: ["admin-dashboard-overview"],
    queryFn: () => fetchAdminDashboardOverview(),
    staleTime: 30_000,
  });

  if (overviewQuery.isLoading) {
    return <PageLoadingState description="Loading the admin control overview." label="Loading dashboard..." />;
  }

  if (overviewQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(overviewQuery.error, { fallbackMessage: "Unable to load the admin dashboard right now." })}
        onRetry={() => overviewQuery.refetch()}
        title="We could not load the dashboard."
      />
    );
  }

  const overview = overviewQuery.data ?? {
    totalUsers: 0,
    activeGroups: 0,
    pendingPayments: 0,
    defaultersCount: 0,
    defaulters: [],
  };
  const defaulters = Array.isArray(overview.defaulters) ? overview.defaulters : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Dashboard</h1>
        <p>Admin is a control layer only. These counts stay read-only and help you move quickly into the right oversight surface.</p>
      </section>

      <section className="panel">
        <div className="panel-grid md:grid-cols-2">
          <AdminOverviewCard label="Total users" to="/admin/users" value={overview.totalUsers} />
          <AdminOverviewCard label="Active groups" to="/admin/groups" value={overview.activeGroups} />
          <AdminOverviewCard label="Pending payments" to="/admin/payments?status=pending" value={overview.pendingPayments} />
          <AdminOverviewCard label="Defaulters" to="/admin/users" value={overview.defaultersCount} />
        </div>
      </section>

      <section className="panel">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>Defaulters requiring action</h2>
            <p className="text-sm text-slate-600">Members with more than one unpaid installment are surfaced here so you can intervene early.</p>
          </div>
          <span className="inline-flex rounded-full border border-red-200 bg-red-50 px-3 py-1 text-sm font-semibold text-red-900">
            {defaulters.length} flagged
          </span>
        </div>
        {defaulters.length === 0 ? (
          <p className="mt-4 text-sm text-slate-700">No defaulters crossed the current threshold.</p>
        ) : (
          <div className="mt-4 space-y-3">
            {defaulters.map((defaulter) => (
              <div className="flex items-center justify-between gap-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3" key={defaulter.userId}>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-950">{defaulter.name}</p>
                  <p className="text-sm text-slate-700">{defaulter.phone}</p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-sm font-semibold text-red-900">{defaulter.pendingPaymentsCount} pending payments</p>
                    <p className="text-sm text-red-800">Rs. {new Intl.NumberFormat("en-IN").format(defaulter.pendingAmount ?? 0)}</p>
                  </div>
                  <Link
                    aria-label={`Review ${defaulter.name}`}
                    className="rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-semibold text-red-900"
                    to={`/admin/users/${defaulter.userId}`}
                  >
                    Review
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-grid md:grid-cols-3">
          <Link className="action-button" to="/admin/users">
            Users
          </Link>
          <Link className="action-button" to="/admin/groups">
            Groups
          </Link>
          <Link className="action-button" to="/admin/auctions">
            Auctions
          </Link>
          <Link className="action-button" to="/admin/payments">
            Payments
          </Link>
          <Link className="action-button" to="/admin/owner-requests">
            Owner requests
          </Link>
          <Link className="action-button" to="/admin/system">
            System
          </Link>
        </div>
      </section>
    </main>
  );
}
