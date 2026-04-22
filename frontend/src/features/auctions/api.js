import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

export async function fetchGroups() {
  const { data } = await apiClient.get("/groups");
  return extractListItems(data);
}

export async function createAuctionSession(groupId, payload) {
  const { data } = await apiClient.post(`/groups/${groupId}/auction-sessions`, payload);
  return data;
}

export async function fetchAuctionRoom(sessionId) {
  const { data } = await apiClient.get(`/auctions/${sessionId}/room`);
  return data;
}

export async function submitBid(sessionId, payload) {
  const { data } = await apiClient.post(`/auctions/${sessionId}/bids`, payload);
  return data;
}

export async function fetchOwnerAuctionConsole(sessionId) {
  const { data } = await apiClient.get(`/auctions/${sessionId}/owner-console`);
  return data;
}

export async function finalizeAuctionSession(sessionId) {
  const { data } = await apiClient.post(`/auctions/${sessionId}/finalize`);
  return data;
}
