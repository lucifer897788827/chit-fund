import { apiClient } from "../../lib/api/client";

import {
  acceptGroupInvite,
  approveGroupMembershipRequest,
  createGroup,
  fetchGroups,
  fetchOwnerAuctionConsole,
  fetchOwnerMembershipRequests,
  fetchPublicChits,
  searchChitsByCode,
  inviteSubscriberToGroup,
  finalizeAuctionSession,
  rejectGroupInvite,
  rejectGroupMembershipRequest,
  requestGroupMembership,
} from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetchGroups uses the auth-scoped backend endpoint without owner filters", async () => {
  apiClient.get.mockResolvedValue({
    data: { groups: [{ id: 11, title: "July Chit" }] },
  });

  await expect(fetchGroups()).resolves.toEqual([{ id: 11, title: "July Chit" }]);

  expect(apiClient.get).toHaveBeenCalledWith("/groups");
});

test("fetchPublicChits requests the global public chit listing", async () => {
  apiClient.get.mockResolvedValue({
    data: [{ id: 21, title: "Public Chit" }],
  });

  await expect(fetchPublicChits()).resolves.toEqual([{ id: 21, title: "Public Chit" }]);

  expect(apiClient.get).toHaveBeenCalledWith("/chits/public");
});

test("searchChitsByCode requests exact group-code matches from the backend", async () => {
  apiClient.get.mockResolvedValue({
    data: [{ id: 31, title: "Code Match Chit" }],
  });

  await expect(searchChitsByCode("JOIN-777")).resolves.toEqual([{ id: 31, title: "Code Match Chit" }]);

  expect(apiClient.get).toHaveBeenCalledWith("/chits/code/JOIN-777");
});

test("fetchOwnerMembershipRequests loads the pending owner review queue", async () => {
  apiClient.get.mockResolvedValue({
    data: [{ membershipId: 41, groupId: 21, subscriberName: "Asha Devi" }],
  });

  await expect(fetchOwnerMembershipRequests()).resolves.toEqual([
    { membershipId: 41, groupId: 21, subscriberName: "Asha Devi" },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/chits/owner/requests");
});

test("requestGroupMembership submits a join request for a public chit", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 51, groupId: 21, membershipStatus: "pending" },
  });

  await expect(requestGroupMembership(21)).resolves.toEqual({
    membershipId: 51,
    groupId: 21,
    membershipStatus: "pending",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/21/request");
});

test("inviteSubscriberToGroup posts a private-group phone invite", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 61, groupId: 22, membershipStatus: "invited" },
  });

  await expect(inviteSubscriberToGroup(22, "8888888888")).resolves.toEqual({
    membershipId: 61,
    groupId: 22,
    membershipStatus: "invited",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/22/invite", {
    phone: "8888888888",
  });
});

test("acceptGroupInvite posts the subscriber acceptance decision", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 61, membershipStatus: "active" },
  });

  await expect(acceptGroupInvite(22, 61)).resolves.toEqual({
    membershipId: 61,
    membershipStatus: "active",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/22/accept-invite", {
    membershipId: 61,
  });
});

test("rejectGroupInvite posts the subscriber rejection decision", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 61, membershipStatus: "rejected" },
  });

  await expect(rejectGroupInvite(22, 61)).resolves.toEqual({
    membershipId: 61,
    membershipStatus: "rejected",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/22/reject-invite", {
    membershipId: 61,
  });
});

test("approveGroupMembershipRequest posts the owner approval decision", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 51, membershipStatus: "active" },
  });

  await expect(approveGroupMembershipRequest(21, 51)).resolves.toEqual({
    membershipId: 51,
    membershipStatus: "active",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/21/approve-member", {
    membershipId: 51,
  });
});

test("rejectGroupMembershipRequest posts the owner rejection decision", async () => {
  apiClient.post.mockResolvedValue({
    data: { membershipId: 51, membershipStatus: "rejected" },
  });

  await expect(rejectGroupMembershipRequest(21, 51)).resolves.toEqual({
    membershipId: 51,
    membershipStatus: "rejected",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/chits/21/reject-member", {
    membershipId: 51,
  });
});

test("createGroup posts a new group payload", async () => {
  const payload = {
    ownerId: 1,
    groupCode: "PUB-001",
    title: "Public Group",
    chitValue: 500000,
    installmentAmount: 25000,
    memberCount: 20,
    cycleCount: 20,
    cycleFrequency: "monthly",
    visibility: "public",
    startDate: "2026-05-01",
    firstAuctionDate: "2026-05-10",
  };
  apiClient.post.mockResolvedValue({
    data: { id: 11, ...payload },
  });

  await expect(createGroup(payload)).resolves.toEqual({ id: 11, ...payload });

  expect(apiClient.post).toHaveBeenCalledWith("/groups", payload);
});

test("fetchOwnerAuctionConsole requests the owner console payload for a session", async () => {
  apiClient.get.mockResolvedValue({
    data: {
      sessionId: 44,
    },
  });

  await expect(fetchOwnerAuctionConsole(44)).resolves.toEqual({ sessionId: 44 });

  expect(apiClient.get).toHaveBeenCalledWith("/auctions/44/owner-console");
});

test("finalizeAuctionSession posts the owner finalize command for a session", async () => {
  apiClient.post.mockResolvedValue({
    data: {
      status: "finalized",
    },
  });

  await expect(finalizeAuctionSession(44)).resolves.toEqual({ status: "finalized" });

  expect(apiClient.post).toHaveBeenCalledWith("/auctions/44/finalize");
});
