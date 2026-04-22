import { apiClient } from "../../lib/api/client";
import { fetchNotifications, markNotificationRead } from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
    patch: jest.fn(),
    post: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetchNotifications loads and normalizes notification items", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      results: [
        {
          id: 9,
          user_id: 4,
          owner_id: 1,
          channel: "in_app",
          title: "Auction finalized",
          message: "Your round has closed.",
          status: "pending",
          created_at: "2026-04-20T10:00:00Z",
          sent_at: null,
        },
      ],
    },
  });

  await expect(fetchNotifications({ unreadOnly: true })).resolves.toEqual([
    {
      id: 9,
      userId: 4,
      ownerId: 1,
      channel: "in_app",
      title: "Auction finalized",
      message: "Your round has closed.",
      status: "pending",
      createdAt: "2026-04-20T10:00:00Z",
      sentAt: null,
      readAt: null,
      metadata: null,
      notificationType: null,
      deepLink: null,
      sessionId: null,
      groupId: null,
      paymentId: null,
      isRead: false,
    },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/notifications", {
    params: { unreadOnly: true },
  });
});

test("fetchNotifications extracts items from paginated responses", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      items: [
        {
          id: 10,
          userId: 4,
          ownerId: 1,
          channel: "in_app",
          title: "Paged notification",
          message: "Loaded from a paginated feed.",
          status: "delivered",
          createdAt: "2026-04-21T10:00:00Z",
          readAt: null,
        },
      ],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    },
  });

  await expect(fetchNotifications({ page: 1, pageSize: 20 })).resolves.toEqual([
    {
      id: 10,
      userId: 4,
      ownerId: 1,
      channel: "in_app",
      title: "Paged notification",
      message: "Loaded from a paginated feed.",
      status: "delivered",
      createdAt: "2026-04-21T10:00:00Z",
      sentAt: null,
      readAt: null,
      metadata: null,
      notificationType: null,
      deepLink: null,
      sessionId: null,
      groupId: null,
      paymentId: null,
      isRead: true,
    },
  ]);
});

test("markNotificationRead patches the read command for a notification", async () => {
  apiClient.patch.mockResolvedValueOnce({
    data: {
      id: 9,
      status: "read",
      read_at: "2026-04-21T11:15:00Z",
    },
  });

  await expect(markNotificationRead(9, { source: "panel" })).resolves.toEqual({
    id: 9,
    userId: null,
    ownerId: null,
    channel: "in_app",
    title: "",
    message: "",
    status: "read",
    createdAt: null,
    sentAt: null,
    readAt: "2026-04-21T11:15:00Z",
    metadata: null,
    notificationType: null,
    deepLink: null,
    sessionId: null,
    groupId: null,
    paymentId: null,
    isRead: true,
  });

  expect(apiClient.patch).toHaveBeenCalledWith("/notifications/9/read", {
    source: "panel",
  });
});
