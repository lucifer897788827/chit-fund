import { apiClient } from "../../lib/api/client";

export async function fetchActiveAdminMessage() {
  const { data } = await apiClient.get("/admin/messages");
  return data;
}

export async function fetchAdminUsers({ page = 1, limit = 20, lite = false } = {}) {
  const response = await apiClient.get("/admin/users", {
    params: { page, limit, lite },
  });
  return response.data;
}

export async function fetchAdminUser(userId, { lite = false } = {}) {
  const { data } = await apiClient.get(`/admin/users/${userId}`, {
    params: { lite },
  });
  return data;
}
