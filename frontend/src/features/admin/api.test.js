import { apiClient } from "../../lib/api/client";

import {
  activateAdminUser,
  bulkDeactivateAdminUsers,
  deactivateAdminUser,
  fetchActiveAdminMessage,
  fetchAdminAuctions,
  fetchAdminDefaulters,
  fetchAdminDashboardOverview,
  fetchAdminGroupDetail,
  fetchAdminGroups,
  fetchAdminInsightsSummary,
  fetchAdminPayments,
  fetchAdminUser,
  fetchAdminUsers,
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

test("fetchActiveAdminMessage loads the current admin banner payload", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      id: 9,
      message: "Collection closes tonight",
      type: "warning",
      active: true,
    },
  });

  await expect(fetchActiveAdminMessage()).resolves.toEqual({
    id: 9,
    message: "Collection closes tonight",
    type: "warning",
    active: true,
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/messages");
});

test("fetchAdminUsers loads the paginated admin user directory", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      items: [{ id: 1, role: "owner", phone: "9999999999", totalChits: 2, paymentScore: 80 }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
    },
  });

  await expect(fetchAdminUsers()).resolves.toEqual({
    items: [{ id: 1, role: "owner", phone: "9999999999", totalChits: 2, paymentScore: 80 }],
    page: 1,
    pageSize: 20,
    totalCount: 1,
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/users", {
    params: { page: 1, limit: 20, lite: false },
  });
});

test("fetchAdminUsers forwards admin list filters without changing the API shape", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      items: [{ id: 8, role: "owner", name: "Owner One", phone: "7777777777", isActive: false, totalChits: 4, paymentScore: 50 }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    },
  });

  await fetchAdminUsers({ page: 1, limit: 20, role: "owner", active: false });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/users", {
    params: { page: 1, limit: 20, lite: false, role: "owner", active: false },
  });
});

test("fetchAdminUsers forwards the score range filter for admin risk review", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      items: [{ id: 8, role: "owner", name: "Owner One", phone: "7777777777", isActive: true, totalChits: 4, paymentScore: 90 }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    },
  });

  await fetchAdminUsers({ page: 1, limit: 20, scoreRange: "high" });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/users", {
    params: { page: 1, limit: 20, lite: false, scoreRange: "high" },
  });
});

test("fetchAdminUser loads one admin user detail payload", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      id: 7,
      role: "subscriber",
      phone: "8888888888",
      financialSummary: { paymentCount: 2, netPosition: -250 },
      participationStats: { totalChits: 3 },
    },
  });

  await expect(fetchAdminUser(7)).resolves.toEqual({
    id: 7,
    role: "subscriber",
    phone: "8888888888",
    financialSummary: { paymentCount: 2, netPosition: -250 },
    participationStats: { totalChits: 3 },
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/users/7", {
    params: { lite: false },
  });
});

test("deactivateAdminUser posts the soft-deactivate action for one user", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: { id: 7, isActive: false },
  });

  await expect(deactivateAdminUser(7)).resolves.toEqual({ id: 7, isActive: false });

  expect(apiClient.post).toHaveBeenCalledWith("/admin/users/7/deactivate");
});

test("activateAdminUser posts the re-activate action for one user", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: { id: 7, isActive: true },
  });

  await expect(activateAdminUser(7)).resolves.toEqual({ id: 7, isActive: true });

  expect(apiClient.post).toHaveBeenCalledWith("/admin/users/7/activate");
});

test("bulkDeactivateAdminUsers posts the selected user ids as one safe batch", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: { deactivatedUserIds: [8, 9], count: 2 },
  });

  await expect(bulkDeactivateAdminUsers([8, 9])).resolves.toEqual({
    deactivatedUserIds: [8, 9],
    count: 2,
  });

  expect(apiClient.post).toHaveBeenCalledWith("/admin/users/bulk-deactivate", {
    userIds: [8, 9],
  });
});

test("fetchAdminGroups loads read-only admin group oversight data", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 11, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 }],
  });

  await expect(fetchAdminGroups()).resolves.toEqual([
    { id: 11, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/groups");
});

test("fetchAdminGroupDetail loads the admin intelligence view for one group", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      group: { id: 11, name: "Alpha Group" },
      members: [],
      financialSummary: { totalCollected: 10000, totalPaid: 5000, pendingAmount: 2000 },
      auctions: [],
      defaulters: [],
    },
  });

  await expect(fetchAdminGroupDetail(11)).resolves.toEqual({
    group: { id: 11, name: "Alpha Group" },
    members: [],
    financialSummary: { totalCollected: 10000, totalPaid: 5000, pendingAmount: 2000 },
    auctions: [],
    defaulters: [],
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/groups/11");
});

test("fetchAdminGroups forwards status filters for admin oversight", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 12, name: "Closed Group", status: "completed", owner: "Owner Two", membersCount: 20, monthlyAmount: 6000 }],
  });

  await fetchAdminGroups({ status: "completed" });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/groups", {
    params: { status: "completed" },
  });
});

test("fetchAdminAuctions loads read-only admin auction oversight data", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 21, group: "Alpha Group", winner: "Subscriber One", bidAmount: 45000, status: "closed", scheduledAt: "2026-04-28T10:00:00Z" }],
  });

  await expect(fetchAdminAuctions()).resolves.toEqual([
    { id: 21, group: "Alpha Group", winner: "Subscriber One", bidAmount: 45000, status: "closed", scheduledAt: "2026-04-28T10:00:00Z" },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/auctions");
});

test("fetchAdminDefaulters loads admin defaulter insights with the default threshold", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [
      {
        userId: 31,
        name: "Subscriber One",
        phone: "9999999999",
        pendingPaymentsCount: 3,
        pendingAmount: 27000,
      },
    ],
  });

  await expect(fetchAdminDefaulters()).resolves.toEqual([
    {
      userId: 31,
      name: "Subscriber One",
      phone: "9999999999",
      pendingPaymentsCount: 3,
      pendingAmount: 27000,
    },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/insights/defaulters", {
    params: { threshold: 1 },
  });
});

test("fetchAdminDefaulters forwards an explicit threshold for admin risk review", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [],
  });

  await expect(fetchAdminDefaulters({ threshold: 4 })).resolves.toEqual([]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/insights/defaulters", {
    params: { threshold: 4 },
  });
});

test("fetchAdminInsightsSummary loads admin intelligence summary counts", async () => {
  apiClient.get
    .mockResolvedValueOnce({
      data: {
        totalUsers: 12,
        activeGroups: 2,
        pendingPayments: 1,
        defaulters: 4,
      },
    });

  await expect(fetchAdminInsightsSummary()).resolves.toEqual({
    totalUsers: 12,
    activeGroups: 2,
    pendingPayments: 1,
    defaulters: 4,
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/insights/summary");
});

test("fetchAdminDashboardOverview combines summary counts with defaulter details", async () => {
  apiClient.get
    .mockResolvedValueOnce({
      data: {
        totalUsers: 12,
        activeGroups: 2,
        pendingPayments: 1,
        defaulters: 4,
      },
    })
    .mockResolvedValueOnce({
      data: [
        {
          userId: 31,
          name: "Subscriber One",
          phone: "9999999999",
          pendingPaymentsCount: 3,
          pendingAmount: 27000,
        },
      ],
    });

  await expect(fetchAdminDashboardOverview("2026-04-28")).resolves.toEqual({
    totalUsers: 12,
    activeGroups: 2,
    pendingPayments: 1,
    defaultersCount: 4,
    defaulters: [
      {
        userId: 31,
        name: "Subscriber One",
        phone: "9999999999",
        pendingPaymentsCount: 3,
        pendingAmount: 27000,
      },
    ],
  });
});

test("fetchAdminPayments loads read-only admin payment oversight data", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 31, user: "Subscriber One", group: "Alpha Group", amount: 9000, status: "paid" }],
  });

  await expect(fetchAdminPayments()).resolves.toEqual([
    { id: 31, user: "Subscriber One", group: "Alpha Group", amount: 9000, status: "paid" },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/payments");
});

test("fetchAdminPayments forwards payment status filters for admin oversight", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 32, user: "Subscriber Two", group: "Beta Group", amount: 9500, status: "pending" }],
  });

  await fetchAdminPayments({ status: "pending" });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/payments", {
    params: { status: "pending" },
  });
});
