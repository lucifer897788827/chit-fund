import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminGroups } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";
import AdminSearchForm from "./AdminSearchForm";
import AdminTablePagination from "./AdminTablePagination";
import { buildAdminListParams, buildAdminPaginationParams, paginateAdminItems, readAdminPagination } from "./admin-pagination";

export default function AdminGroupsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { page, limit } = readAdminPagination(searchParams);
  const statusFilter = searchParams.get("status") ?? "";
  const searchFilter = searchParams.get("search") ?? "";
  const [searchInput, setSearchInput] = useState(searchFilter);

  useEffect(() => {
    setSearchInput(searchFilter);
  }, [searchFilter]);

  useAppShellHeader({
    title: "Groups",
    contextLabel: "Read-only group oversight",
  });

  const groupsQuery = useQuery({
    queryKey: ["admin-groups", statusFilter, searchFilter],
    queryFn: () =>
      fetchAdminGroups({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(searchFilter ? { search: searchFilter } : {}),
      }),
    placeholderData: (previousData) => previousData,
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
  const paginatedGroups = paginateAdminItems(groups, { page, limit });
  const isRefreshing = groupsQuery.isFetching && Boolean(groupsQuery.data);

  function handlePageChange(nextPage) {
    setSearchParams(buildAdminPaginationParams(searchParams, { page: nextPage, limit }));
  }

  function handleStatusChange(value) {
    setSearchParams(buildAdminListParams(searchParams, { status: value, page: 1, limit }));
  }

  function handleSearchSubmit(event) {
    event.preventDefault();
    setSearchParams(buildAdminListParams(searchParams, { search: searchInput.trim(), page: 1, limit }));
  }

  function handleSearchClear() {
    setSearchInput("");
    setSearchParams(buildAdminListParams(searchParams, { search: "", page: 1, limit }));
  }

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Groups</h1>
        <p>Read-only oversight across all chit groups without crossing into owner or subscriber flows.</p>
      </section>

      <section className="panel">
        <div className="mb-4 space-y-3">
          <AdminSearchForm
            onChange={(event) => setSearchInput(event.target.value)}
            onClear={handleSearchClear}
            onSubmit={handleSearchSubmit}
            placeholder="Search by group or owner name"
            value={searchInput}
          />
        </div>
        <div className="mb-4 grid gap-3 md:max-w-xs">
          <label className="space-y-2 text-sm font-semibold text-slate-700">
            Status
            <select className="text-input" onChange={(event) => handleStatusChange(event.target.value)} value={statusFilter}>
              <option value="">All groups</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
            </select>
          </label>
        </div>
        {isRefreshing ? <p className="mb-4 text-sm font-semibold text-slate-600">Updating results...</p> : null}
        {paginatedGroups.totalCount === 0 ? (
          <p>No groups found</p>
        ) : (
          <>
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
                  {paginatedGroups.items.map((group) => (
                    <tr key={group.id}>
                      <td>
                        <Link to={`/admin/groups/${group.id}`}>#{group.id}</Link>
                      </td>
                      <td>
                        <Link to={`/admin/groups/${group.id}`}>{group.name}</Link>
                      </td>
                      <td>{group.status}</td>
                      <td>{group.owner}</td>
                      <td>{group.membersCount ?? 0}</td>
                      <td>{group.monthlyAmount ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <AdminTablePagination
              limit={paginatedGroups.limit}
              onPageChange={handlePageChange}
              page={paginatedGroups.page}
              totalCount={paginatedGroups.totalCount}
              totalPages={paginatedGroups.totalPages}
            />
          </>
        )}
      </section>
    </main>
  );
}
