import { apiClient } from "../../lib/api/client";

export async function loginUser(payload) {
  const { data } = await apiClient.post("/auth/login", payload);
  return data;
}
