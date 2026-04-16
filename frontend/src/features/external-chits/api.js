import { apiClient } from "../../lib/api/client";

export async function fetchExternalChits(subscriberId) {
  const { data } = await apiClient.get("/external-chits", {
    params: { subscriberId },
  });
  return data;
}
