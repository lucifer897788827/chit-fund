import { apiClient } from "../../lib/api/client";

export async function fetchActiveAdminMessage() {
  const { data } = await apiClient.get("/admin/messages");
  return data;
}
