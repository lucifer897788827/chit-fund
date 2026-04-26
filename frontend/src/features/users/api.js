import { apiClient } from "../../lib/api/client";

export async function fetchMyFinancialSummary() {
  const { data } = await apiClient.get("/users/me/financial-summary");
  return data;
}
