import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

export async function fetchExternalChits() {
  const { data } = await apiClient.get("/external-chits");
  return extractListItems(data);
}

export async function fetchExternalChitDetails(chitId) {
  const { data } = await apiClient.get(`/external-chits/${chitId}`);
  return data;
}

export async function fetchExternalChitSummary(chitId) {
  const { data } = await apiClient.get(`/external-chits/${chitId}/summary`);
  return data;
}

export async function createExternalChit(payload) {
  const { data } = await apiClient.post("/external-chits", payload);
  return data;
}

export async function updateExternalChit(chitId, payload) {
  const { data } = await apiClient.patch(`/external-chits/${chitId}`, payload);
  return data;
}

export async function deleteExternalChit(chitId) {
  const { data } = await apiClient.delete(`/external-chits/${chitId}`);
  return data;
}

export async function createExternalChitEntry(chitId, payload) {
  const { data } = await apiClient.post(`/external-chits/${chitId}/entries`, payload);
  return data;
}

export async function updateExternalChitEntry(chitId, entryId, payload) {
  const { data } = await apiClient.put(`/external-chits/${chitId}/entries/${entryId}`, payload);
  return data;
}
