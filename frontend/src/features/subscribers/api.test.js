import { apiClient } from "../../lib/api/client";

import { createSubscriber, deactivateSubscriber, fetchSubscribers, updateSubscriber } from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetchSubscribers calls the subscriber list endpoint", async () => {
  apiClient.get.mockResolvedValueOnce({ data: { records: [{ id: 1 }] } });

  await expect(fetchSubscribers()).resolves.toEqual([{ id: 1 }]);

  expect(apiClient.get).toHaveBeenCalledWith("/subscribers");
});

test("createSubscriber posts the new subscriber payload", async () => {
  apiClient.post.mockResolvedValueOnce({ data: { id: 2 } });

  await expect(
    createSubscriber({
      ownerId: 11,
      fullName: "Asha",
      phone: "9000000000",
      email: "asha@example.com",
      password: "starter-pass",
    }),
  ).resolves.toEqual({ id: 2 });

  expect(apiClient.post).toHaveBeenCalledWith("/subscribers", {
    ownerId: 11,
    fullName: "Asha",
    phone: "9000000000",
    email: "asha@example.com",
    password: "starter-pass",
  });
});

test("updateSubscriber patches the targeted subscriber", async () => {
  apiClient.patch.mockResolvedValueOnce({ data: { id: 3 } });

  await expect(
    updateSubscriber(3, {
      ownerId: 11,
      fullName: "Asha Updated",
      phone: "9000000001",
      email: null,
    }),
  ).resolves.toEqual({ id: 3 });

  expect(apiClient.patch).toHaveBeenCalledWith("/subscribers/3", {
    ownerId: 11,
    fullName: "Asha Updated",
    phone: "9000000001",
    email: null,
  });
});

test("deactivateSubscriber deletes the targeted subscriber", async () => {
  apiClient.delete.mockResolvedValueOnce({ data: { id: 4 } });

  await expect(deactivateSubscriber(4)).resolves.toEqual({ id: 4 });

  expect(apiClient.delete).toHaveBeenCalledWith("/subscribers/4");
});
