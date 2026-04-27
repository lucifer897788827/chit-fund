import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminUser } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

function StatCard({ label, value }) {
  return (
    <article className="panel">
      <h3>{value ?? 0}</h3>
      <p>{label}</p>
    </article>
  );
}

function formatValue(value) {
  return value ?? "N/A";
}

export default function UserDetailPage() {
  const { id } = useParams();

  useAppShellHeader({
    title: `User ${id}`,
    contextLabel: "Admin user detail",
  });

  const userQuery = useQuery({
    queryKey: ["admin-user", id],
    queryFn: () => fetchAdminUser(id),
    enabled: Boolean(id),
    staleTime: 30_000,
  });

  if (userQuery.isLoading) {
    return <PageLoadingState description="Loading admin user detail." label="Loading user..." />;
  }

  if (userQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(userQuery.error, { fallbackMessage: "Unable to load admin user detail right now." })}
        onRetry={() => userQuery.refetch()}
        title="We could not load this user."
      />
    );
  }

  const user = userQuery.data;
  const financialSummary = user?.financialSummary ?? {};
  const participationStats = user?.participationStats ?? {};
  const chits = Array.isArray(user?.chits) ? user.chits : [];
  const payments = Array.isArray(user?.payments) ? user.payments : [];
  const externalChits = Array.isArray(user?.externalChitsData) ? user.externalChitsData : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>User #{id}</h1>
        <p>Role: {user?.role ?? "unknown"}</p>
        <p>Phone: {user?.phone ?? "N/A"}</p>
        <p>Email: {user?.email ?? "N/A"}</p>
        <p>Active: {user?.isActive ? "Yes" : "No"}</p>
        <p>Owner profile: {user?.ownerId ?? "None"}</p>
        <p>Subscriber profile: {user?.subscriberId ?? "None"}</p>
        <Link className="action-button" to="/admin/users">
          Back to users
        </Link>
      </section>

      <section className="panel">
        <h2>Participation</h2>
        <div className="panel-grid md:grid-cols-3">
          <StatCard label="Total chits" value={participationStats.totalChits} />
          <StatCard label="Owned chits" value={participationStats.ownedChits} />
          <StatCard label="Joined chits" value={participationStats.joinedChits} />
          <StatCard label="External chits" value={participationStats.externalChits} />
          <StatCard label="Memberships" value={participationStats.membershipCount} />
          <StatCard label="Active memberships" value={participationStats.activeMemberships} />
          <StatCard label="Prized memberships" value={participationStats.prizedMemberships} />
        </div>
      </section>

      <section className="panel">
        <h2>Financial summary</h2>
        <div className="panel-grid md:grid-cols-3">
          <StatCard label="Payments" value={financialSummary.paymentCount} />
          <StatCard label="Total paid" value={financialSummary.totalPaid} />
          <StatCard label="Payouts" value={financialSummary.payoutCount} />
          <StatCard label="Total received" value={financialSummary.totalReceived} />
          <StatCard label="Net cashflow" value={financialSummary.netCashflow} />
          <StatCard label="Payment score" value={financialSummary.paymentScore} />
        </div>
      </section>

      <section className="panel">
        <h2>All chits</h2>
        {chits.length === 0 ? (
          <p>No chit relationships found.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Kind</th>
                  <th>Group code</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Cycle</th>
                </tr>
              </thead>
              <tbody>
                {chits.map((chit) => (
                  <tr key={`${chit.kind}-${chit.id}`}>
                    <td>#{chit.id}</td>
                    <td>{formatValue(chit.kind)}</td>
                    <td>{formatValue(chit.groupCode)}</td>
                    <td>{formatValue(chit.title)}</td>
                    <td>{formatValue(chit.status)}</td>
                    <td>{formatValue(chit.currentCycleNo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Payments</h2>
        {payments.length === 0 ? (
          <p>No payments found.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Date</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Method</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>#{payment.id}</td>
                    <td>{formatValue(payment.paymentDate)}</td>
                    <td>{formatValue(payment.amount)}</td>
                    <td>{formatValue(payment.status)}</td>
                    <td>{formatValue(payment.paymentType)}</td>
                    <td>{formatValue(payment.paymentMethod)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>External chits</h2>
        {externalChits.length === 0 ? (
          <p>No external chits found.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Title</th>
                  <th>Organizer</th>
                  <th>Chit value</th>
                  <th>Installment</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {externalChits.map((chit) => (
                  <tr key={chit.id}>
                    <td>#{chit.id}</td>
                    <td>{formatValue(chit.title)}</td>
                    <td>{formatValue(chit.organizerName)}</td>
                    <td>{formatValue(chit.chitValue)}</td>
                    <td>{formatValue(chit.installmentAmount)}</td>
                    <td>{formatValue(chit.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
