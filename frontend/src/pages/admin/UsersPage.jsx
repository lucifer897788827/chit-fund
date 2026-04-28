import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { activateAdminUser, bulkDeactivateAdminUsers, deactivateAdminUser, fetchAdminUsers } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser } from "../../lib/auth/store";
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

function getUserDisplayName(user) {
  return user?.name || user?.phone || `User #${user?.id ?? ""}`.trim();
}

function getPaymentScoreBadgeClass(score) {
  if (score >= 80) {
    return "border-emerald-200 bg-emerald-100 text-emerald-900";
  }
  if (score >= 50) {
    return "border-amber-200 bg-amber-100 text-amber-900";
  }
  return "border-red-200 bg-red-100 text-red-900";
}

function renderPaymentScoreBadge(score) {
  const normalizedScore = Number(score ?? 0);
  const badgeClass = getPaymentScoreBadgeClass(normalizedScore);

  return (
    <span
      aria-label={`Payment score: ${normalizedScore} / 100`}
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${badgeClass}`}
    >
      {normalizedScore} / 100
    </span>
  );
}

export default function UsersPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { page, limit } = readAdminPagination(searchParams);
  const roleFilter = searchParams.get("role") ?? "";
  const activeFilter = searchParams.get("active") ?? "";
  const searchFilter = searchParams.get("search") ?? "";
  const scoreRangeFilter = searchParams.get("scoreRange") ?? "";
  const [searchInput, setSearchInput] = useState(searchFilter);
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [pendingAction, setPendingAction] = useState(null);
  const currentUser = getCurrentUser();
  const currentAdminUserId = currentUser?.user?.id ?? currentUser?.userId ?? null;

  useEffect(() => {
    setSearchInput(searchFilter);
  }, [searchFilter]);

  useAppShellHeader({
    title: "Users",
    contextLabel: "Admin user directory",
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users", page, limit, roleFilter, activeFilter, searchFilter, scoreRangeFilter],
    queryFn: () =>
      fetchAdminUsers({
        page,
        limit,
        ...(roleFilter ? { role: roleFilter } : {}),
        ...(activeFilter === "active" ? { active: true } : {}),
        ...(activeFilter === "inactive" ? { active: false } : {}),
        ...(searchFilter ? { search: searchFilter } : {}),
        ...(scoreRangeFilter ? { scoreRange: scoreRangeFilter } : {}),
      }),
    placeholderData: (previousData) => previousData,
    staleTime: 30_000,
  });

  const deactivateUserMutation = useMutation({
    mutationFn: ({ userId }) => deactivateAdminUser(userId),
    onSuccess: async (_result, variables) => {
      setActionSuccess(`${variables.userLabel} deactivated.`);
      setActionError("");
      setSelectedUserIds([]);
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => {
      setActionError(getApiErrorMessage(error, { fallbackMessage: "Unable to deactivate this user right now." }));
      setActionSuccess("");
    },
  });

  const activateUserMutation = useMutation({
    mutationFn: ({ userId }) => activateAdminUser(userId),
    onSuccess: async (_result, variables) => {
      setActionSuccess(`${variables.userLabel} activated.`);
      setActionError("");
      setSelectedUserIds([]);
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => {
      setActionError(getApiErrorMessage(error, { fallbackMessage: "Unable to activate this user right now." }));
      setActionSuccess("");
    },
  });

  const bulkDeactivateMutation = useMutation({
    mutationFn: bulkDeactivateAdminUsers,
    onSuccess: async (result) => {
      const count = Number(result?.count ?? 0) || 0;
      setActionSuccess(count === 1 ? "1 user deactivated." : `${count} users deactivated.`);
      setActionError("");
      setSelectedUserIds([]);
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => {
      setActionError(getApiErrorMessage(error, { fallbackMessage: "Unable to deactivate the selected users right now." }));
      setActionSuccess("");
    },
  });

  const items = Array.isArray(usersQuery.data?.items) ? usersQuery.data.items : [];
  const totalCount = Number(usersQuery.data?.totalCount ?? items.length) || 0;
  const totalPages = Number(usersQuery.data?.totalPages ?? (totalCount > 0 ? Math.ceil(totalCount / limit) : 0)) || 0;
  const isRefreshing = usersQuery.isFetching && Boolean(usersQuery.data);
  const isMutating = activateUserMutation.isPending || deactivateUserMutation.isPending || bulkDeactivateMutation.isPending;
  const selectableUserIds = items
    .filter((user) => {
      const isProtectedAdmin = user.role === "admin";
      const isSelf = currentAdminUserId !== null && user.id === currentAdminUserId;
      return !isProtectedAdmin && !isSelf && user.isActive;
    })
    .map((user) => user.id);
  const allVisibleUsersSelected = selectableUserIds.length > 0 && selectableUserIds.every((userId) => selectedUserIds.includes(userId));

  useEffect(() => {
    setSelectedUserIds((currentIds) => {
      const nextIds = currentIds.filter((userId) => selectableUserIds.includes(userId));
      if (nextIds.length === currentIds.length && nextIds.every((userId, index) => userId === currentIds[index])) {
        return currentIds;
      }
      return nextIds;
    });
  }, [selectableUserIds]);

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

  function toggleSelectedUser(userId) {
    setSelectedUserIds((currentIds) =>
      currentIds.includes(userId) ? currentIds.filter((currentId) => currentId !== userId) : [...currentIds, userId],
    );
  }

  function handleToggleAllVisibleUsers() {
    setSelectedUserIds((currentIds) => {
      if (allVisibleUsersSelected) {
        return currentIds.filter((userId) => !selectableUserIds.includes(userId));
      }
      const nextIds = new Set(currentIds);
      selectableUserIds.forEach((userId) => nextIds.add(userId));
      return Array.from(nextIds);
    });
  }

  function openDeactivateUserConfirmation(user) {
    const userLabel = getUserDisplayName(user);
    setPendingAction({
      kind: "deactivate-user",
      title: "Deactivate user?",
      description: `${userLabel} will stay visible in admin records but will not be able to sign in until reactivated.`,
      confirmLabel: "Deactivate user",
      userId: user.id,
      userLabel,
    });
  }

  function openActivateUserConfirmation(user) {
    const userLabel = getUserDisplayName(user);
    setPendingAction({
      kind: "activate-user",
      title: "Activate user?",
      description: `${userLabel} will regain access to sign in and any linked owner/subscriber profile will be reactivated.`,
      confirmLabel: "Activate user",
      userId: user.id,
      userLabel,
    });
  }

  function openBulkDeactivateConfirmation() {
    if (selectedUserIds.length === 0) {
      return;
    }
    setPendingAction({
      kind: "bulk-deactivate",
      title: "Deactivate selected users?",
      description: `${selectedUserIds.length} selected user${selectedUserIds.length === 1 ? "" : "s"} will stay visible in admin records but will not be able to sign in until reactivated.`,
      confirmLabel: "Deactivate selected",
      userIds: [...selectedUserIds],
    });
  }

  async function handleConfirmAction() {
    if (!pendingAction) {
      return;
    }

    if (pendingAction.kind === "deactivate-user") {
      try {
        await deactivateUserMutation.mutateAsync({
          userId: pendingAction.userId,
          userLabel: pendingAction.userLabel,
        });
        setPendingAction(null);
      } catch {
        return;
      }
      return;
    }

    if (pendingAction.kind === "activate-user") {
      try {
        await activateUserMutation.mutateAsync({
          userId: pendingAction.userId,
          userLabel: pendingAction.userLabel,
        });
        setPendingAction(null);
      } catch {
        return;
      }
      return;
    }

    if (pendingAction.kind === "bulk-deactivate") {
      try {
        await bulkDeactivateMutation.mutateAsync(pendingAction.userIds);
        setPendingAction(null);
      } catch {
        return;
      }
    }
  }

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Users</h1>
        <p>Review users, keep protected admins safe, and deactivate non-admin accounts without deleting records.</p>
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
        <div className="mb-4 grid gap-3 md:grid-cols-3">
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
          <label className="space-y-2 text-sm font-semibold text-slate-700">
            Payment score
            <select
              className="text-input"
              onChange={(event) => handleFilterChange("scoreRange", event.target.value)}
              value={scoreRangeFilter}
            >
              <option value="">All scores</option>
              <option value="high">80-100</option>
              <option value="medium">50-79</option>
              <option value="low">0-49</option>
            </select>
          </label>
        </div>
        {isRefreshing ? <p className="mb-4 text-sm font-semibold text-slate-600">Updating results...</p> : null}
        {selectedUserIds.length > 0 ? (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-sm font-semibold text-slate-800">
              {selectedUserIds.length} user{selectedUserIds.length === 1 ? "" : "s"} selected
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-semibold text-slate-700"
                disabled={isMutating}
                onClick={() => setSelectedUserIds([])}
                type="button"
              >
                Clear selection
              </button>
              <button className="action-button" disabled={isMutating} onClick={openBulkDeactivateConfirmation} type="button">
                {bulkDeactivateMutation.isPending ? "Deactivating..." : "Deactivate selected"}
              </button>
            </div>
          </div>
        ) : null}
        {actionError ? (
          <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
            {actionError}
          </p>
        ) : null}
        {actionSuccess ? (
          <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" role="status">
            {actionSuccess}
          </p>
        ) : null}
        {items.length === 0 ? (
          <p>No users found</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>
                    <input
                      aria-label="Select all eligible users"
                      checked={allVisibleUsersSelected}
                      disabled={selectableUserIds.length === 0 || isMutating}
                      onChange={handleToggleAllVisibleUsers}
                      type="checkbox"
                    />
                  </th>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Active</th>
                  <th>Phone</th>
                  <th>Total chits</th>
                  <th>Payment score</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((user) => {
                  const isProtectedAdmin = user.role === "admin";
                  const isSelf = currentAdminUserId !== null && user.id === currentAdminUserId;
                  const isProtected = isProtectedAdmin || isSelf;
                  const isSelectable = !isProtected && user.isActive;
                  const actionLabel = isSelf ? "Current admin" : isProtectedAdmin ? "Protected admin" : user.isActive ? "Deactivate" : "Activate";
                  const statusBadgeClass = user.isActive
                    ? "border-emerald-200 bg-emerald-100 text-emerald-900"
                    : "border-red-200 bg-red-100 text-red-900";

                  return (
                  <tr key={user.id}>
                    <td>
                      <input
                        aria-label={`Select user ${user.name || user.phone}`}
                        checked={selectedUserIds.includes(user.id)}
                        disabled={!isSelectable || isMutating}
                        onChange={() => toggleSelectedUser(user.id)}
                        type="checkbox"
                      />
                    </td>
                    <td>
                      <Link to={`/admin/users/${user.id}`}>#{user.id}</Link>
                    </td>
                    <td>{user.name ? <Link to={`/admin/users/${user.id}`}>{user.name}</Link> : "N/A"}</td>
                    <td>{user.role}</td>
                    <td>
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusBadgeClass}`}>
                        {user.isActive ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>{user.phone}</td>
                    <td>{user.totalChits ?? 0}</td>
                    <td>{renderPaymentScoreBadge(user.paymentScore)}</td>
                    <td>{formatDateTime(user.createdAt)}</td>
                    <td>
                      <button
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isProtected || isMutating}
                        onClick={() => (user.isActive ? openDeactivateUserConfirmation(user) : openActivateUserConfirmation(user))}
                        type="button"
                      >
                        {actionLabel}
                      </button>
                    </td>
                  </tr>
                  );
                })}
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
      {pendingAction ? (
        <div
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4"
          role="dialog"
        >
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="space-y-3">
              <h2 className="text-lg font-semibold text-slate-950">{pendingAction.title}</h2>
              <p className="text-sm text-slate-700">{pendingAction.description}</p>
            </div>
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-semibold text-slate-700"
                disabled={isMutating}
                onClick={() => setPendingAction(null)}
                type="button"
              >
                Cancel
              </button>
              <button className="action-button mt-0" disabled={isMutating} onClick={handleConfirmAction} type="button">
                {isMutating ? "Saving..." : pendingAction.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
