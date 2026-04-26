import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

export async function fetchGroups() {
  const { data } = await apiClient.get("/groups");
  return extractListItems(data);
}

export async function fetchPublicChits() {
  const { data } = await apiClient.get("/chits/public");
  return extractListItems(data);
}

export async function searchChitsByCode(groupCode) {
  const normalizedGroupCode = String(groupCode ?? "").trim();
  const { data } = await apiClient.get(`/chits/code/${encodeURIComponent(normalizedGroupCode)}`);
  return extractListItems(data);
}

export async function fetchOwnerMembershipRequests() {
  const { data } = await apiClient.get("/chits/owner/requests");
  return extractListItems(data);
}

export async function inviteSubscriberToGroup(groupId, phone) {
  const { data } = await apiClient.post(`/chits/${groupId}/invite`, {
    phone,
  });
  return data;
}

export async function requestGroupMembership(groupId) {
  const { data } = await apiClient.post(`/chits/${groupId}/request`);
  return data;
}

export async function acceptGroupInvite(groupId, membershipId) {
  const { data } = await apiClient.post(`/chits/${groupId}/accept-invite`, {
    membershipId,
  });
  return data;
}

export async function rejectGroupInvite(groupId, membershipId) {
  const { data } = await apiClient.post(`/chits/${groupId}/reject-invite`, {
    membershipId,
  });
  return data;
}

export async function approveGroupMembershipRequest(groupId, membershipId) {
  const { data } = await apiClient.post(`/chits/${groupId}/approve-member`, {
    membershipId,
  });
  return data;
}

export async function rejectGroupMembershipRequest(groupId, membershipId) {
  const { data } = await apiClient.post(`/chits/${groupId}/reject-member`, {
    membershipId,
  });
  return data;
}

export async function createGroup(payload) {
  const { data } = await apiClient.post("/groups", payload);
  return data;
}

export async function fetchGroupStatus(groupId) {
  const { data } = await apiClient.get(`/groups/${groupId}/status`);
  return data;
}

export async function fetchGroupMemberSummary(groupId) {
  const { data } = await apiClient.get(`/groups/${groupId}/member-summary`);
  return Array.isArray(data) ? data : [];
}

export async function closeGroupCollection(groupId) {
  const { data } = await apiClient.post(`/groups/${groupId}/close-collection`);
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

export async function fetchOwnerAuctionConsole(sessionId) {
  const { data } = await apiClient.get(`/auctions/${sessionId}/owner-console`);
  return data;
}

export async function finalizeAuctionSession(sessionId) {
  const { data } = await apiClient.post(`/auctions/${sessionId}/finalize`);
  return data;
}
