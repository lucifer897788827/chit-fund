import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminUsers } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";
import AdminSearchForm from "./AdminSearchForm";
import AdminTablePagination from "./AdminTablePagination";
import { buildAdminListParams, buildAdminPaginationParams, readAdminPagination } from "./admin-pagination";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const { page, limit } = readAdminPagination(searchParams);
  const roleFilter = searchParams.get("role") ?? "";
  const activeFilter = searchParams.get("active") ?? "";
  const searchFilter = searchParams.get("search") ?? "";
  const [searchInput, setSearchInput] = useState(searchFilter);

  useEffect(() => {
    setSearchInput(searchFilter);
  }, [searchFilter]);

  useAppShellHeader({
    title: "Users",
    contextLabel: "Admin user directory",
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users", page, limit, roleFilter, activeFilter, searchFilter],
    queryFn: () =>
      fetchAdminUsers({
        page,
        limit,
        ...(roleFilter ? { role: roleFilter } : {}),
        ...(activeFilter === "active" ? { active: true } : {}),
        ...(activeFilter === "inactive" ? { active: false } : {}),
        ...(searchFilter ? { search: searchFilter } : {}),
      }),
    placeholderData: (previousData) => previousData,
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
  const totalCount = Number(usersQuery.data?.totalCount ?? items.length) || 0;
  const totalPages = Number(usersQuery.data?.totalPages ?? (totalCount > 0 ? Math.ceil(totalCount / limit) : 0)) || 0;
  const isRefreshing = usersQuery.isFetching && Boolean(usersQuery.data);

  function handlePageChange(nextPage) {
    setSearchParams(buildAdminPaginationParams(searchParams, { page: nextPage, limit }));
  }

  function handleFilterChange(key, value) {
    setSearchParams(buildAdminListParams(searchParams, { [key]: value, page: 1, limit }));
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
        <h1>Users</h1>
        <p>Read-only directory across owners, subscribers, and admins.</p>
      </section>

      <section className="panel">
        <div className="mb-4 space-y-3">
          <AdminSearchForm
            onChange={(event) => setSearchInput(event.target.value)}
            onClear={handleSearchClear}
            onSubmit={handleSearchSubmit}
            value={searchInput}
          />
        </div>
        <div className="mb-4 grid gap-3 md:grid-cols-2">
          <label className="space-y-2 text-sm font-semibold text-slate-700">
            Role
            <select
              className="text-input"
              onChange={(event) => handleFilterChange("role", event.target.value)}
              value={roleFilter}
            >
              <option value="">All roles</option>
              <option value="owner">Owner</option>
              <option value="subscriber">Subscriber</option>
            </select>
          </label>
          <label className="space-y-2 text-sm font-semibold text-slate-700">
            Activity
            <select
              className="text-input"
              onChange={(event) => handleFilterChange("active", event.target.value)}
              value={activeFilter}
            >
              <option value="">All users</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>
        {isRefreshing ? <p className="mb-4 text-sm font-semibold text-slate-600">Updating results...</p> : null}
        {items.length === 0 ? (
          <p>No users found</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Active</th>
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
                    <td>{user.name ? <Link to={`/admin/users/${user.id}`}>{user.name}</Link> : "N/A"}</td>
                    <td>{user.role}</td>
                    <td>{user.isActive ? "Active" : "Inactive"}</td>
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
        <AdminTablePagination
          limit={limit}
          onPageChange={handlePageChange}
          page={page}
          totalCount={totalCount}
          totalPages={totalPages}
        />
      </section>
    </main>
  );
}
