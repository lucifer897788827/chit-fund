import { apiClient } from "../../lib/api/client";

export async function fetchSubscriberDashboard() {
  const { data } = await apiClient.get("/subscribers/dashboard");
  return data;
}

export async function fetchOwnerDashboard() {
  const { data } = await apiClient.get("/reporting/owner/dashboard");
  return data;
}

export async function fetchOwnerAuditLogs(params = {}) {
  const { data } = await apiClient.get("/reporting/owner/audit-logs", { params });
  return data;
}
