import { apiClient } from "../../lib/api/client";

export async function createOwnerRequest() {
  const { data } = await apiClient.post("/users/request-owner", {});
  return data;
}

export async function fetchAdminOwnerRequests() {
  const { data } = await apiClient.get("/admin/owner-requests");
  return data;
}

export async function approveOwnerRequest(requestId) {
  const { data } = await apiClient.post(`/admin/owner-requests/${requestId}/approve`);
  return data;
}

export async function rejectOwnerRequest(requestId) {
  const { data } = await apiClient.post(`/admin/owner-requests/${requestId}/reject`);
  return data;
}
