import { apiClient } from "../../lib/api/client";

export async function fetchActiveAdminMessage() {
  const { data } = await apiClient.get("/admin/messages");
  return data;
}

export async function fetchAdminUsers({ page = 1, limit = 20, lite = false, role, active, search, scoreRange } = {}) {
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
  if (scoreRange) {
    params.scoreRange = scoreRange;
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

export async function deactivateAdminUser(userId) {
  const { data } = await apiClient.post(`/admin/users/${userId}/deactivate`);
  return data;
}

export async function activateAdminUser(userId) {
  const { data } = await apiClient.post(`/admin/users/${userId}/activate`);
  return data;
}

export async function bulkDeactivateAdminUsers(userIds) {
  const { data } = await apiClient.post("/admin/users/bulk-deactivate", {
    userIds,
  });
  return data;
}

export async function fetchAdminDefaulters({ threshold = 1 } = {}) {
  const { data } = await apiClient.get("/admin/insights/defaulters", {
    params: { threshold },
  });
  return data;
}

export async function fetchAdminInsightsSummary() {
  const { data } = await apiClient.get("/admin/insights/summary");
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

export async function fetchAdminGroupDetail(groupId) {
  const { data } = await apiClient.get(`/admin/groups/${groupId}`);
  return data;
}

export async function fetchAdminAuctions() {
  const { data } = await apiClient.get("/admin/auctions");
  return data;
}

export async function fetchAdminDashboardOverview() {
  const [summary, defaulters] = await Promise.all([fetchAdminInsightsSummary(), fetchAdminDefaulters()]);
  const defaulterItems = Array.isArray(defaulters) ? defaulters : [];

  return {
    totalUsers: Number(summary?.totalUsers ?? 0) || 0,
    activeGroups: Number(summary?.activeGroups ?? 0) || 0,
    pendingPayments: Number(summary?.pendingPayments ?? 0) || 0,
    defaultersCount: Number(summary?.defaulters ?? 0) || 0,
    defaulters: defaulterItems,
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
