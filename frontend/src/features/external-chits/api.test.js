import { apiClient } from "../../lib/api/client";

import {
  createExternalChitEntry,
  createExternalChit,
  deleteExternalChit,
  fetchExternalChitDetails,
  fetchExternalChitSummary,
  fetchExternalChits,
  updateExternalChitEntry,
  updateExternalChit,
} from "./api";

jest.mock("../../lib/api/client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    put: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("fetchExternalChits calls the secured list endpoint without query params", async () => {
  apiClient.get.mockResolvedValueOnce({ data: [{ id: 1 }] });

  await expect(fetchExternalChits()).resolves.toEqual([{ id: 1 }]);

  expect(apiClient.get).toHaveBeenCalledWith("/external-chits");
});

test("fetchExternalChitDetails loads a selected chit with its history", async () => {
  apiClient.get.mockResolvedValueOnce({ data: { id: 9, entryHistory: [] } });

  await expect(fetchExternalChitDetails(9)).resolves.toEqual({ id: 9, entryHistory: [] });

  expect(apiClient.get).toHaveBeenCalledWith("/external-chits/9");
});

test("fetchExternalChitSummary loads the ledger totals for a chit", async () => {
  apiClient.get.mockResolvedValueOnce({ data: { totalPaid: 1000, totalReceived: 1500, profit: 500 } });

  await expect(fetchExternalChitSummary(9)).resolves.toEqual({ totalPaid: 1000, totalReceived: 1500, profit: 500 });

  expect(apiClient.get).toHaveBeenCalledWith("/external-chits/9/summary");
});

test("createExternalChit posts a new chit payload", async () => {
  apiClient.post.mockResolvedValueOnce({ data: { id: 2 } });

  await expect(
    createExternalChit({
      title: "Temple Chit",
      organizerName: "Ravi",
      chitValue: 150000,
      installmentAmount: 7500,
      cycleFrequency: "monthly",
      startDate: "2026-05-01",
      endDate: null,
      notes: "",
      status: "active",
    }),
  ).resolves.toEqual({ id: 2 });

  expect(apiClient.post).toHaveBeenCalledWith("/external-chits", {
    title: "Temple Chit",
    organizerName: "Ravi",
    chitValue: 150000,
    installmentAmount: 7500,
    cycleFrequency: "monthly",
    startDate: "2026-05-01",
    endDate: null,
    notes: "",
    status: "active",
  });
});

test("updateExternalChit patches the targeted chit", async () => {
  apiClient.patch.mockResolvedValueOnce({ data: { id: 3 } });

  await expect(
    updateExternalChit(3, {
      title: "Village Chit Updated",
      organizerName: "Anita",
      chitValue: 100000,
      installmentAmount: 5500,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      endDate: null,
      notes: "Updated note",
      status: "active",
    }),
  ).resolves.toEqual({ id: 3 });

  expect(apiClient.patch).toHaveBeenCalledWith("/external-chits/3", {
    title: "Village Chit Updated",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5500,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    endDate: null,
    notes: "Updated note",
    status: "active",
  });
});

test("deleteExternalChit deletes the targeted chit", async () => {
  apiClient.delete.mockResolvedValueOnce({ data: { id: 4 } });

  await expect(deleteExternalChit(4)).resolves.toEqual({ id: 4 });

  expect(apiClient.delete).toHaveBeenCalledWith("/external-chits/4");
});

test("createExternalChitEntry posts a month entry payload", async () => {
  apiClient.post.mockResolvedValueOnce({ data: { id: 5 } });

  await expect(
    createExternalChitEntry(4, {
      entryType: "won",
      entryDate: "2026-04-20",
      amount: 20000,
      description: "Month result",
      monthNumber: 2,
      bidAmount: 20000,
      winnerType: "SELF",
      sharePerSlot: 2500,
      myPayable: 15000,
      myPayout: 65000,
    }),
  ).resolves.toEqual({ id: 5 });

  expect(apiClient.post).toHaveBeenCalledWith("/external-chits/4/entries", {
    entryType: "won",
    entryDate: "2026-04-20",
    amount: 20000,
    description: "Month result",
    monthNumber: 2,
    bidAmount: 20000,
    winnerType: "SELF",
    sharePerSlot: 2500,
    myPayable: 15000,
    myPayout: 65000,
  });
});

test("updateExternalChitEntry updates a saved month entry", async () => {
  apiClient.put.mockResolvedValueOnce({ data: { id: 6 } });

  await expect(
    updateExternalChitEntry(4, 6, {
      winnerType: "OTHER",
      sharePerSlot: 2200,
      myPayable: 15600,
      myPayout: 0,
    }),
  ).resolves.toEqual({ id: 6 });

  expect(apiClient.put).toHaveBeenCalledWith("/external-chits/4/entries/6", {
    winnerType: "OTHER",
    sharePerSlot: 2200,
    myPayable: 15600,
    myPayout: 0,
  });
});
