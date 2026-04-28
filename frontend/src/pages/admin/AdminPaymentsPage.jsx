import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminPayments } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";
import AdminSearchForm from "./AdminSearchForm";
import AdminTablePagination from "./AdminTablePagination";
import { buildAdminListParams, buildAdminPaginationParams, paginateAdminItems, readAdminPagination } from "./admin-pagination";

export default function AdminPaymentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { page, limit } = readAdminPagination(searchParams);
  const statusFilter = searchParams.get("status") ?? "";
  const searchFilter = searchParams.get("search") ?? "";
  const [searchInput, setSearchInput] = useState(searchFilter);

  useEffect(() => {
    setSearchInput(searchFilter);
  }, [searchFilter]);

  useAppShellHeader({
    title: "Payments",
    contextLabel: "Read-only payment oversight",
  });

  const paymentsQuery = useQuery({
    queryKey: ["admin-payments", statusFilter, searchFilter],
    queryFn: () =>
      fetchAdminPayments({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(searchFilter ? { search: searchFilter } : {}),
      }),
    placeholderData: (previousData) => previousData,
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
  const paginatedPayments = paginateAdminItems(payments, { page, limit });
  const isRefreshing = paymentsQuery.isFetching && Boolean(paymentsQuery.data);

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
        <h1>Payments</h1>
        <p>Read-only payment summaries across all groups without letting admins record participant activity.</p>
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
        <div className="mb-4 grid gap-3 md:max-w-xs">
          <label className="space-y-2 text-sm font-semibold text-slate-700">
            Status
            <select className="text-input" onChange={(event) => handleStatusChange(event.target.value)} value={statusFilter}>
              <option value="">All payments</option>
              <option value="paid">Paid</option>
              <option value="pending">Pending</option>
            </select>
          </label>
        </div>
        {isRefreshing ? <p className="mb-4 text-sm font-semibold text-slate-600">Updating results...</p> : null}
        {paginatedPayments.totalCount === 0 ? (
          <p>No payments</p>
        ) : (
          <>
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
                  {paginatedPayments.items.map((payment) => (
                    <tr key={payment.id}>
                      <td>#{payment.id}</td>
                      <td>{payment.user}</td>
                      <td>
                        {payment.groupId ? (
                          <Link to={`/admin/groups/${payment.groupId}`}>{payment.group ?? "Unassigned"}</Link>
                        ) : (
                          payment.group ?? "Unassigned"
                        )}
                      </td>
                      <td>{payment.amount ?? 0}</td>
                      <td>{payment.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <AdminTablePagination
              limit={paginatedPayments.limit}
              onPageChange={handlePageChange}
              page={paginatedPayments.page}
              totalCount={paginatedPayments.totalCount}
              totalPages={paginatedPayments.totalPages}
            />
          </>
        )}
      </section>
    </main>
  );
}
