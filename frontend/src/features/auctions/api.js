import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

export async function fetchGroups() {
  const { data } = await apiClient.get("/groups");
  return extractListItems(data);
}

export async function fetchPublicChits() {
  const { data } = await apiClient.get("/groups/public");
  return extractListItems(data);
}

export async function searchChitsByCode(groupCode) {
  const normalizedGroupCode = String(groupCode ?? "").trim();
  const { data } = await apiClient.get(`/groups/code/${encodeURIComponent(normalizedGroupCode)}`);
  return extractListItems(data);
}

export async function fetchOwnerMembershipRequests() {
  const { data } = await apiClient.get("/groups/owner/requests");
  return extractListItems(data);
}

export async function inviteSubscriberToGroup(groupId, phone) {
  const { data } = await apiClient.post(`/groups/${groupId}/invite-by-phone`, {
    phone,
  });
  return data;
}

export async function requestGroupMembership(groupId) {
  const { data } = await apiClient.post(`/groups/${groupId}/request`);
  return data;
}

export async function acceptGroupInvite(groupId, membershipId) {
  const { data } = await apiClient.post(`/groups/${groupId}/accept-invite`, {
    membershipId,
  });
  return data;
}

export async function rejectGroupInvite(groupId, membershipId) {
  const { data } = await apiClient.post(`/groups/${groupId}/reject-invite`, {
    membershipId,
  });
  return data;
}

export async function approveGroupMembershipRequest(groupId, membershipId) {
  const { data } = await apiClient.post(`/groups/${groupId}/approve-membership-request`, {
    membershipId,
  });
  return data;
}

export async function rejectGroupMembershipRequest(groupId, membershipId) {
  const { data } = await apiClient.post(`/groups/${groupId}/reject-membership-request`, {
    membershipId,
  });
  return data;
}

export async function createGroup(payload) {
  const { data } = await apiClient.post("/groups", payload);
  return data;
}

export async function updateGroupSettings(groupId, payload) {
  const { data } = await apiClient.patch(`/groups/${groupId}`, payload);
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

export async function fetchGroupJoinRequests(groupId) {
  const { data } = await apiClient.get(`/groups/${groupId}/join-requests`);
  return Array.isArray(data) ? data : [];
}

export async function searchGroupInviteCandidates(groupId, query) {
  const normalizedQuery = String(query ?? "").trim();
  const { data } = await apiClient.get(`/groups/${groupId}/search-users`, {
    params: { q: normalizedQuery },
  });
  return Array.isArray(data) ? data : [];
}

export async function createGroupInvite(groupId, subscriberId) {
  const { data } = await apiClient.post(`/groups/${groupId}/invite`, {
    subscriberId,
  });
  return data;
}

export async function fetchGroupInvites(groupId) {
  const { data } = await apiClient.get(`/groups/${groupId}/invites`);
  return Array.isArray(data) ? data : [];
}

export async function revokeGroupInvite(groupId, inviteId) {
  const { data } = await apiClient.post(`/groups/${groupId}/invites/${inviteId}/revoke`);
  return data;
}

export async function removeGroupMember(groupId, membershipId) {
  const { data } = await apiClient.post(`/groups/${groupId}/memberships/${membershipId}/remove`);
  return data;
}

export async function approveGroupJoinRequest(groupId, joinRequestId) {
  const { data } = await apiClient.post(`/groups/${groupId}/approve-member`, {
    joinRequestId,
  });
  return data;
}

export async function rejectGroupJoinRequest(groupId, joinRequestId) {
  const { data } = await apiClient.post(`/groups/${groupId}/reject-member`, {
    joinRequestId,
  });
  return data;
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
