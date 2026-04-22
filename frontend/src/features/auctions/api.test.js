import { apiClient } from "../../lib/api/client";

import { fetchGroups, fetchOwnerAuctionConsole, finalizeAuctionSession } from "./api";

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
