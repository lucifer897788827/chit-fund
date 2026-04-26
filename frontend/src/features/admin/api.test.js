import { apiClient } from "../../lib/api/client";

import { fetchActiveAdminMessage } from "./api";

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
