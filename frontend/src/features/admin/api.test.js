import { apiClient } from "../../lib/api/client";

import { fetchActiveAdminMessage, fetchAdminUser, fetchAdminUsers } from "./api";

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
