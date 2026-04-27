import { apiClient } from "../../lib/api/client";
import { fetchUserDashboard } from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetches the universal user dashboard", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      role: "owner",
      financial_summary: { total_paid: 0, total_received: 0, dividend: 0, net: 0 },
      stats: {},
    },
  });

  await expect(fetchUserDashboard()).resolves.toMatchObject({ role: "owner" });

  expect(apiClient.get).toHaveBeenCalledWith("/users/me/dashboard");
});
