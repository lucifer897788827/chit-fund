import { apiClient } from "../../lib/api/client";

import { fetchOwnerPayouts, fetchPaymentBalances, fetchPayments, markOwnerPayoutPaid, recordPayment, settleOwnerPayout } from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("recordPayment posts a secured payment payload to the payments endpoint", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: {
      id: 91,
      status: "recorded",
    },
  });

  await expect(
    recordPayment({
      ownerId: 17,
      subscriberId: 42,
      membershipId: 8,
      installmentId: 3,
      paymentType: "installment",
      paymentMethod: "upi",
      amount: 1250,
      paymentDate: "2026-04-20",
      referenceNo: "UPI-7788",
    }),
  ).resolves.toEqual({
    id: 91,
    status: "recorded",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/payments", {
    ownerId: 17,
    subscriberId: 42,
    membershipId: 8,
    installmentId: 3,
    paymentType: "installment",
    paymentMethod: "upi",
    amount: 1250,
    paymentDate: "2026-04-20",
    referenceNo: "UPI-7788",
  });
});

test("fetchPayments loads owner-scoped payment history with filters", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      results: [{ id: 11, amount: 500 }],
    },
  });

  await expect(fetchPayments({ subscriberId: 7, groupId: 3 })).resolves.toEqual([
    { id: 11, amount: 500 },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/payments", {
    params: { subscriberId: 7, groupId: 3 },
  });
});

test("fetchPaymentBalances loads owner-scoped member balances", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      balances: [{ membershipId: 12, outstandingAmount: 250 }],
    },
  });

  await expect(fetchPaymentBalances()).resolves.toEqual([
    { membershipId: 12, outstandingAmount: 250 },
  ]);

  expect(apiClient.get).toHaveBeenCalledWith("/payments/balances", {
    params: {},
  });
});

test("fetchOwnerPayouts loads owner-scoped payouts with filters", async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      payouts: [{ id: 71, status: "pending" }],
    },
  });

  await expect(fetchOwnerPayouts({ status: "pending" })).resolves.toEqual([{ id: 71, status: "pending" }]);

  expect(apiClient.get).toHaveBeenCalledWith("/payments/payouts", {
    params: { status: "pending" },
  });
});

test("settleOwnerPayout posts the payout settlement command", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: { id: 71, status: "settled" },
  });

  await expect(settleOwnerPayout(71, { referenceNo: "NEFT-9911" })).resolves.toEqual({
    id: 71,
    status: "settled",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/payments/payouts/71/settle", {
    referenceNo: "NEFT-9911",
  });
});

test("markOwnerPayoutPaid posts the canonical mark-paid command", async () => {
  apiClient.post.mockResolvedValueOnce({
    data: { id: 71, status: "paid", paidAt: "2026-04-26T10:00:00Z" },
  });

  await expect(markOwnerPayoutPaid(71)).resolves.toEqual({
    id: 71,
    status: "paid",
    paidAt: "2026-04-26T10:00:00Z",
  });

  expect(apiClient.post).toHaveBeenCalledWith("/payouts/71/mark-paid");
});
