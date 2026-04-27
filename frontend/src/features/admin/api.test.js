import { apiClient } from "../../lib/api/client";

import {
  fetchActiveAdminMessage,
  fetchAdminAuctions,
  fetchAdminGroups,
  fetchAdminPayments,
  fetchAdminUser,
  fetchAdminUsers,
} from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
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

test("fetchAdminUser loads one admin user detail payload", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      id: 7,
      role: "subscriber",
      phone: "8888888888",
      financialSummary: { paymentCount: 2 },
      participationStats: { totalChits: 3 },
    },
  });

  await expect(fetchAdminUser(7)).resolves.toEqual({
    id: 7,
    role: "subscriber",
    phone: "8888888888",
    financialSummary: { paymentCount: 2 },
    participationStats: { totalChits: 3 },
  });

  expect(apiClient.get).toHaveBeenCalledWith("/admin/users/7", {
    params: { lite: false },
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

test("fetchAdminAuctions loads read-only admin auction oversight data", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: [{ id: 21, group: "Alpha Group", winner: "Subscriber One", bidAmount: 45000, status: "closed" }],
  });

  await expect(fetchAdminAuctions()).resolves.toEqual([
    { id: 21, group: "Alpha Group", winner: "Subscriber One", bidAmount: 45000, status: "closed" },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/admin/auctions");
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
