import { apiClient } from "../../lib/api/client";

import { fetchMyFinancialSummary } from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetchMyFinancialSummary loads the authenticated financial summary", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      total_paid: 1000,
      total_received: 4000,
      dividend: 100,
      net: 3100,
    },
  });

  await expect(fetchMyFinancialSummary()).resolves.toEqual({
    total_paid: 1000,
    total_received: 4000,
    dividend: 100,
    net: 3100,
  });

  expect(apiClient.get).toHaveBeenCalledWith("/users/me/financial-summary");
});
