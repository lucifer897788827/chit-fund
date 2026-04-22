import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

export async function fetchSubscribers() {
  const { data } = await apiClient.get("/subscribers");
  return extractListItems(data);
}

export async function createSubscriber(payload) {
  const { data } = await apiClient.post("/subscribers", payload);
  return data;
}

export async function updateSubscriber(subscriberId, payload) {
  const { data } = await apiClient.patch(`/subscribers/${subscriberId}`, payload);
  return data;
}

export async function deactivateSubscriber(subscriberId) {
  const { data } = await apiClient.delete(`/subscribers/${subscriberId}`);
  return data;
}
