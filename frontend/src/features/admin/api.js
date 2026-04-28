import { apiClient } from "../../lib/api/client";

export async function fetchActiveAdminMessage() {
  const { data } = await apiClient.get("/admin/messages");
  return data;
}

export async function fetchAdminUsers({ page = 1, limit = 20, lite = false, role, active, search } = {}) {
  const params = { page, limit, lite };
  if (role) {
    params.role = role;
  }
  if (typeof active === "boolean") {
    params.active = active;
  }
  if (search) {
    params.search = search;
  }
  const response = await apiClient.get("/admin/users", {
    params,
  });
  return response.data;
}

export async function fetchAdminUser(userId, { lite = false } = {}) {
  const { data } = await apiClient.get(`/admin/users/${userId}`, {
    params: { lite },
  });
  return data;
}

export async function fetchAdminGroups({ status, search } = {}) {
  const params = {};
  if (status) {
    params.status = status;
  }
  if (search) {
    params.search = search;
  }
  const { data } = Object.keys(params).length
    ? await apiClient.get("/admin/groups", { params })
    : await apiClient.get("/admin/groups");
  return data;
}

export async function fetchAdminAuctions() {
  const { data } = await apiClient.get("/admin/auctions");
  return data;
}

function occursOnDate(value, dateKey) {
  if (!value || !dateKey) {
    return false;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return false;
  }
  return parsed.toISOString().slice(0, 10) === dateKey;
}

function resolveDashboardDateKey(input) {
  if (input) {
    return input;
  }
  return new Date().toISOString().slice(0, 10);
}

export async function fetchAdminDashboardOverview(dateKey) {
  const resolvedDateKey = resolveDashboardDateKey(dateKey);
  const [users, groups, pendingPayments, auctions] = await Promise.all([
    fetchAdminUsers({ page: 1, limit: 1, lite: true }),
    fetchAdminGroups(),
    fetchAdminPayments({ status: "pending" }),
    fetchAdminAuctions(),
  ]);

  const groupItems = Array.isArray(groups) ? groups : [];
  const paymentItems = Array.isArray(pendingPayments) ? pendingPayments : [];
  const auctionItems = Array.isArray(auctions) ? auctions : [];

  return {
    totalUsers: Number(users?.totalCount ?? 0) || 0,
    activeGroups: groupItems.filter((group) => group?.status === "active").length,
    pendingPayments: paymentItems.length,
    todayAuctions: auctionItems.filter((auction) => occursOnDate(auction?.scheduledAt, resolvedDateKey)).length,
  };
}

export async function fetchAdminPayments({ status, search } = {}) {
  const params = {};
  if (status) {
    params.status = status;
  }
  if (search) {
    params.search = search;
  }
  const { data } = Object.keys(params).length
    ? await apiClient.get("/admin/payments", { params })
    : await apiClient.get("/admin/payments");
  return data;
}
