import { apiClient } from "../../lib/api/client";

export async function fetchGroups(ownerId) {
  const { data } = await apiClient.get("/groups", {
    params: { ownerId },
  });
  return data;
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
