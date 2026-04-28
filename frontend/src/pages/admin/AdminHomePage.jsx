import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminDashboardOverview } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

function getLocalDateKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

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
    queryKey: ["admin-dashboard-overview", getLocalDateKey()],
    queryFn: () => fetchAdminDashboardOverview(getLocalDateKey()),
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
    todayAuctions: 0,
  };

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
          <AdminOverviewCard label="Today auctions" to="/admin/auctions" value={overview.todayAuctions} />
        </div>
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
