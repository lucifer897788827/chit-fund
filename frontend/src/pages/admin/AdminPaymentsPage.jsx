import { useQuery } from "@tanstack/react-query";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminPayments } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

export default function AdminPaymentsPage() {
  useAppShellHeader({
    title: "Payments",
    contextLabel: "Read-only payment oversight",
  });

  const paymentsQuery = useQuery({
    queryKey: ["admin-payments"],
    queryFn: () => fetchAdminPayments(),
    staleTime: 30_000,
  });

  if (paymentsQuery.isLoading) {
    return <PageLoadingState description="Loading admin payment oversight." label="Loading payments..." />;
  }

  if (paymentsQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(paymentsQuery.error, { fallbackMessage: "Unable to load admin payments right now." })}
        onRetry={() => paymentsQuery.refetch()}
        title="We could not load payments."
      />
    );
  }

  const payments = Array.isArray(paymentsQuery.data) ? paymentsQuery.data : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Payments</h1>
        <p>Read-only payment summaries across all groups without letting admins record participant activity.</p>
      </section>

      <section className="panel">
        {payments.length === 0 ? (
          <p>No payments are available.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>User</th>
                  <th>Group</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>#{payment.id}</td>
                    <td>{payment.user}</td>
                    <td>{payment.group ?? "Unassigned"}</td>
                    <td>{payment.amount ?? 0}</td>
                    <td>{payment.status}</td>
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
