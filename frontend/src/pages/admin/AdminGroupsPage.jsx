import { useQuery } from "@tanstack/react-query";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminGroups } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

export default function AdminGroupsPage() {
  useAppShellHeader({
    title: "Groups",
    contextLabel: "Read-only group oversight",
  });

  const groupsQuery = useQuery({
    queryKey: ["admin-groups"],
    queryFn: () => fetchAdminGroups(),
    staleTime: 30_000,
  });

  if (groupsQuery.isLoading) {
    return <PageLoadingState description="Loading admin group oversight." label="Loading groups..." />;
  }

  if (groupsQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(groupsQuery.error, { fallbackMessage: "Unable to load admin groups right now." })}
        onRetry={() => groupsQuery.refetch()}
        title="We could not load groups."
      />
    );
  }

  const groups = Array.isArray(groupsQuery.data) ? groupsQuery.data : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Groups</h1>
        <p>Read-only oversight across all chit groups without crossing into owner or subscriber flows.</p>
      </section>

      <section className="panel">
        {groups.length === 0 ? (
          <p>No groups are available.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Owner</th>
                  <th>Members</th>
                  <th>Monthly amount</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr key={group.id}>
                    <td>#{group.id}</td>
                    <td>{group.name}</td>
                    <td>{group.status}</td>
                    <td>{group.owner}</td>
                    <td>{group.membersCount ?? 0}</td>
                    <td>{group.monthlyAmount ?? 0}</td>
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
