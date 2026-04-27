import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminUsers } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

function formatDateTime(value) {
  if (!value) {
    return "N/A";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export default function UsersPage() {
  useAppShellHeader({
    title: "Users",
    contextLabel: "Admin user directory",
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => fetchAdminUsers(),
    staleTime: 30_000,
  });

  if (usersQuery.isLoading) {
    return <PageLoadingState description="Loading the admin user directory." label="Loading users..." />;
  }

  if (usersQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(usersQuery.error, { fallbackMessage: "Unable to load admin users right now." })}
        onRetry={() => usersQuery.refetch()}
        title="We could not load users."
      />
    );
  }

  const items = Array.isArray(usersQuery.data?.items) ? usersQuery.data.items : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Users</h1>
        <p>Read-only directory across owners, subscribers, and admins.</p>
      </section>

      <section className="panel">
        {items.length === 0 ? (
          <p>No users are available.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Role</th>
                  <th>Phone</th>
                  <th>Total chits</th>
                  <th>Payment score</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <Link to={`/admin/users/${user.id}`}>#{user.id}</Link>
                    </td>
                    <td>{user.role}</td>
                    <td>{user.phone}</td>
                    <td>{user.totalChits ?? 0}</td>
                    <td>{user.paymentScore ?? 0}</td>
                    <td>{formatDateTime(user.createdAt)}</td>
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
