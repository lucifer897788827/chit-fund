import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { saveSession } from "../../lib/auth/store";

jest.mock("./api", () => ({
  createExternalChitEntry: jest.fn(),
  createExternalChit: jest.fn(),
  deleteExternalChit: jest.fn(),
  fetchExternalChitDetails: jest.fn(),
  fetchExternalChitSummary: jest.fn(),
  fetchExternalChits: jest.fn(),
  updateExternalChitEntry: jest.fn(),
  updateExternalChit: jest.fn(),
}));

jest.mock("../auth/api", () => ({
  logoutUser: jest.fn(() => Promise.resolve()),
}));

import ExternalChitsPage from "./ExternalChitsPage";
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

beforeEach(() => {
  jest.clearAllMocks();
  saveSession({
    access_token: "token-subscriber",
    role: "subscriber",
    subscriber_id: 7,
    has_subscriber_profile: true,
  });
});

afterEach(() => {
  window.localStorage.clear();
});

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <ExternalChitsPage />
    </MemoryRouter>,
  );
}

test("loads external chits without a subscriberId query and opens the first chit history", async () => {
  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 1,
      title: "Neighbourhood Savings Pot",
      organizerName: "Lakshmi",
      chitValue: 120000,
      installmentAmount: 6000,
      cycleFrequency: "monthly",
      startDate: "2026-03-01",
      status: "active",
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 1,
    title: "Neighbourhood Savings Pot",
    organizerName: "Lakshmi",
    chitValue: 120000,
    installmentAmount: 6000,
    cycleFrequency: "monthly",
    startDate: "2026-03-01",
    status: "active",
    entryHistory: [
      {
        id: 9,
        externalChitId: 1,
        entryType: "note",
        entryDate: "2026-04-20",
        amount: null,
        description: "Opened the file for this chit.",
        createdAt: "2026-04-20T10:00:00Z",
      },
    ],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 0,
    totalReceived: 0,
    profit: 0,
    winningMonth: null,
  });

  renderPage();

  expect(await screen.findByRole("heading", { name: /External Chits/i })).toBeInTheDocument();
  expect(fetchExternalChits).toHaveBeenCalledWith();
  await waitFor(() => {
    expect(fetchExternalChitDetails).toHaveBeenCalledWith(1);
  });
  await waitFor(() => {
    expect(fetchExternalChitSummary).toHaveBeenCalledWith(1);
  });
  expect(screen.getByRole("heading", { name: /Monthly ledger/i })).toBeInTheDocument();
  expect(await screen.findByText(/Opened the file for this chit/i)).toBeInTheDocument();
});

test("creates a new external chit and keeps the selected chit and success state updated", async () => {
  const user = userEvent.setup();

  fetchExternalChits.mockResolvedValueOnce([]);
  createExternalChit.mockResolvedValueOnce({
    id: 10,
    title: "Temple Chit",
    organizerName: "Ravi",
    chitValue: 150000,
    installmentAmount: 7500,
    cycleFrequency: "monthly",
    startDate: "2026-05-01",
    status: "active",
  });
  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 10,
      title: "Temple Chit",
      organizerName: "Ravi",
      chitValue: 150000,
      installmentAmount: 7500,
      cycleFrequency: "monthly",
      startDate: "2026-05-01",
      status: "active",
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 10,
    title: "Temple Chit",
    organizerName: "Ravi",
    chitValue: 150000,
    installmentAmount: 7500,
    cycleFrequency: "monthly",
    startDate: "2026-05-01",
    status: "active",
    entryHistory: [],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 0,
    totalReceived: 0,
    profit: 0,
    winningMonth: null,
  });

  renderPage();

  await screen.findByRole("heading", { name: /Add external chit/i });
  await user.type(screen.getByLabelText(/Title/i), "Temple Chit");
  await user.type(screen.getByLabelText(/Organizer name/i), "Ravi");
  await user.type(screen.getByLabelText(/Chit value/i), "150000");
  await user.type(screen.getByLabelText(/Installment amount/i), "7500");
  await user.selectOptions(screen.getByLabelText(/Cycle frequency/i), "monthly");
  await user.type(screen.getByLabelText(/Start date/i), "2026-05-01");
  await user.click(screen.getByRole("button", { name: /Create chit/i }));

  await waitFor(() => {
    expect(createExternalChit).toHaveBeenCalledWith({
      title: "Temple Chit",
      name: "",
      organizerName: "Ravi",
      chitValue: 150000,
      installmentAmount: 7500,
      monthlyInstallment: null,
      totalMembers: null,
      totalMonths: null,
      userSlots: null,
      firstMonthOrganizer: false,
      cycleFrequency: "monthly",
      startDate: "2026-05-01",
      endDate: null,
      notes: "",
      status: "active",
    });
  });

  expect(await screen.findByText(/External chit created/i)).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Temple Chit" })).toBeInTheDocument();
});

test("updates and deletes the selected chit with inline feedback", async () => {
  const user = userEvent.setup();

  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 2,
      title: "Village Chit",
      organizerName: "Anita",
      chitValue: 100000,
      installmentAmount: 5000,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      status: "active",
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 2,
    title: "Village Chit",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5000,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    status: "active",
    entryHistory: [
      {
        id: 20,
        externalChitId: 2,
        entryType: "paid",
        entryDate: "2026-04-20",
        amount: 5000,
        description: "Installment received.",
        createdAt: "2026-04-20T11:15:00Z",
      },
    ],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 5000,
    totalReceived: 0,
    profit: -5000,
    winningMonth: null,
  });
  updateExternalChit.mockResolvedValueOnce({
    id: 2,
    title: "Village Chit Updated",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5500,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    status: "active",
  });
  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 2,
      title: "Village Chit Updated",
      organizerName: "Anita",
      chitValue: 100000,
      installmentAmount: 5500,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      status: "active",
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 2,
    title: "Village Chit Updated",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5500,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    status: "active",
    entryHistory: [],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 5500,
    totalReceived: 0,
    profit: -5500,
    winningMonth: null,
  });
  deleteExternalChit.mockResolvedValueOnce({
    id: 2,
    title: "Village Chit Updated",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5500,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    status: "deleted",
  });
  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 2,
      title: "Village Chit Updated",
      organizerName: "Anita",
      chitValue: 100000,
      installmentAmount: 5500,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      status: "deleted",
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 2,
    title: "Village Chit Updated",
    organizerName: "Anita",
    chitValue: 100000,
    installmentAmount: 5500,
    cycleFrequency: "monthly",
    startDate: "2026-04-01",
    status: "deleted",
    entryHistory: [],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 0,
    totalReceived: 0,
    profit: 0,
    winningMonth: null,
  });

  renderPage();

  await screen.findByRole("button", { name: /Edit chit/i });
  await user.click(screen.getByRole("button", { name: /Edit chit/i }));
  await user.clear(screen.getByLabelText(/Title/i));
  await user.type(screen.getByLabelText(/Title/i), "Village Chit Updated");
  await user.clear(screen.getByLabelText(/Installment amount/i));
  await user.type(screen.getByLabelText(/Installment amount/i), "5500");
  await user.click(screen.getByRole("button", { name: /Save changes/i }));

  await waitFor(() => {
    expect(updateExternalChit).toHaveBeenCalledWith(2, {
      title: "Village Chit Updated",
      name: "",
      organizerName: "Anita",
      chitValue: 100000,
      installmentAmount: 5500,
      monthlyInstallment: null,
      totalMembers: null,
      totalMonths: null,
      userSlots: null,
      firstMonthOrganizer: false,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      endDate: null,
      notes: "",
      status: "active",
    });
  });

  expect(await screen.findByText(/External chit updated/i)).toBeInTheDocument();

  await screen.findByRole("button", { name: /Delete chit/i });
  await user.click(screen.getByRole("button", { name: /Delete chit/i }));
  await user.click(screen.getByRole("button", { name: /Confirm delete/i }));

  await waitFor(() => {
    expect(deleteExternalChit).toHaveBeenCalledWith(2);
  });

  expect(await screen.findByText(/External chit deleted/i)).toBeInTheDocument();
  expect(screen.getByText("deleted", { selector: "span" })).toBeInTheDocument();
});

test("shows a clear history panel error state", async () => {
  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 3,
      title: "Samudaya Chit",
      organizerName: "Kumar",
      chitValue: 90000,
      installmentAmount: 4500,
      cycleFrequency: "monthly",
      startDate: "2026-04-01",
      status: "active",
    },
  ]);
  fetchExternalChitDetails.mockRejectedValueOnce({
    response: {
      status: 500,
      data: {
        detail: "History is temporarily unavailable.",
      },
    },
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 0,
    totalReceived: 0,
    profit: 0,
    winningMonth: null,
  });

  renderPage();

  await screen.findByText(/Samudaya Chit/i);
  expect(await screen.findByText(/We could not load this chit ledger/i)).toBeInTheDocument();
});

test("adds and edits a monthly entry while showing summary totals", async () => {
  const user = userEvent.setup();

  fetchExternalChits.mockResolvedValueOnce([
    {
      id: 4,
      title: "Temple Ledger",
      name: "Temple Ledger",
      organizerName: "Ravi",
      chitValue: 100000,
      installmentAmount: 5000,
      monthlyInstallment: 10000,
      totalMembers: 10,
      totalMonths: 20,
      userSlots: 2,
      firstMonthOrganizer: false,
      cycleFrequency: "monthly",
      startDate: "2026-01-01",
      status: "active",
      entryHistory: [],
    },
  ]);
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 4,
    title: "Temple Ledger",
    name: "Temple Ledger",
    organizerName: "Ravi",
    chitValue: 100000,
    installmentAmount: 5000,
    monthlyInstallment: 10000,
    totalMembers: 10,
    totalMonths: 20,
    userSlots: 2,
    firstMonthOrganizer: false,
    cycleFrequency: "monthly",
    startDate: "2026-01-01",
    status: "active",
    entryHistory: [],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 0,
    totalReceived: 0,
    profit: 0,
    winningMonth: null,
  });

  createExternalChitEntry.mockResolvedValueOnce({ id: 40 });
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 4,
    title: "Temple Ledger",
    name: "Temple Ledger",
    organizerName: "Ravi",
    chitValue: 100000,
    installmentAmount: 5000,
    monthlyInstallment: 10000,
    totalMembers: 10,
    totalMonths: 20,
    userSlots: 2,
    firstMonthOrganizer: false,
    cycleFrequency: "monthly",
    startDate: "2026-01-01",
    status: "active",
    entryHistory: [
      {
        id: 40,
        externalChitId: 4,
        entryType: "won",
        entryDate: "2026-02-01",
        amount: 20000,
        description: "Month 2 ledger entry",
        monthNumber: 2,
        bidAmount: 20000,
        winnerType: "SELF",
        sharePerSlot: 2500,
        myShare: 5000,
        myPayable: 15000,
        myPayout: 65000,
        isBidOverridden: false,
        isShareOverridden: true,
        isPayableOverridden: false,
        isPayoutOverridden: true,
        createdAt: "2026-04-20T10:00:00Z",
        updatedAt: "2026-04-20T10:00:00Z",
      },
    ],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 15000,
    totalReceived: 70000,
    profit: 55000,
    winningMonth: 2,
  });

  updateExternalChitEntry.mockResolvedValueOnce({ id: 40 });
  fetchExternalChitDetails.mockResolvedValueOnce({
    id: 4,
    title: "Temple Ledger",
    name: "Temple Ledger",
    organizerName: "Ravi",
    chitValue: 100000,
    installmentAmount: 5000,
    monthlyInstallment: 10000,
    totalMembers: 10,
    totalMonths: 20,
    userSlots: 2,
    firstMonthOrganizer: false,
    cycleFrequency: "monthly",
    startDate: "2026-01-01",
    status: "active",
    entryHistory: [
      {
        id: 40,
        externalChitId: 4,
        entryType: "paid",
        entryDate: "2026-02-01",
        amount: 20000,
        description: "Month 2 ledger entry",
        monthNumber: 2,
        bidAmount: 20000,
        winnerType: "OTHER",
        sharePerSlot: 2500,
        myShare: 5000,
        myPayable: 15000,
        myPayout: 0,
        isBidOverridden: false,
        isShareOverridden: true,
        isPayableOverridden: false,
        isPayoutOverridden: true,
        createdAt: "2026-04-20T10:00:00Z",
        updatedAt: "2026-04-20T10:30:00Z",
      },
    ],
  });
  fetchExternalChitSummary.mockResolvedValueOnce({
    totalPaid: 15000,
    totalReceived: 5000,
    profit: -10000,
    winningMonth: null,
  });

  renderPage();

  expect(await screen.findByText(/Total paid/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Latest month snapshot/i })).toBeInTheDocument();

  await user.clear(screen.getByLabelText(/^Month$/i));
  await user.type(screen.getByLabelText(/^Month$/i), "2");
  await user.type(screen.getByLabelText(/Bid amount/i), "20000");
  await user.selectOptions(screen.getByLabelText(/^Winner$/i), "SELF");
  await user.type(screen.getByLabelText(/^Share$/i), "5000");
  await user.type(screen.getByLabelText(/Payable/i), "15000");
  await user.type(screen.getByLabelText(/Payout/i), "65000");
  await user.click(screen.getByRole("button", { name: /Add month entry/i }));

  await waitFor(() => {
    expect(createExternalChitEntry).toHaveBeenCalledWith(4, {
      entryType: "won",
      entryDate: "2026-02-01",
      amount: 20000,
      description: "Month 2 ledger entry",
      monthNumber: 2,
      bidAmount: 20000,
      winnerType: "SELF",
      winnerName: null,
      myShare: 5000,
      myPayable: 15000,
      myPayout: 65000,
    });
  });

  expect(await screen.findByText(/Month entry added/i)).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Month 2" })).toBeInTheDocument();
  expect(await screen.findByText(/Rs. 70,000/i)).toBeInTheDocument();
  expect(screen.getAllByText(/Month 2 · Manually adjusted/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText("Manual").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Calculated automatically").length).toBeGreaterThan(0);

  await user.click(screen.getByRole("button", { name: /Edit month entry/i }));
  await screen.findByRole("button", { name: /Update month entry/i });
  expect(screen.getAllByText("Manually adjusted").length).toBeGreaterThan(0);
  await user.selectOptions(screen.getByLabelText(/^Winner$/i), "OTHER");
  await user.clear(screen.getByLabelText(/Payout/i));
  await user.type(screen.getByLabelText(/Payout/i), "0");
  await user.click(screen.getByRole("button", { name: /Update month entry/i }));

  await waitFor(() => {
    expect(updateExternalChitEntry).toHaveBeenCalledWith(4, 40, {
      entryType: "paid",
      entryDate: "2026-02-01",
      amount: 20000,
      description: "Month 2 ledger entry",
      monthNumber: 2,
      bidAmount: 20000,
      winnerType: "OTHER",
      winnerName: "",
      myShare: 5000,
      myPayable: 15000,
      myPayout: 0,
    });
  });

  expect(await screen.findByText(/Month entry updated/i)).toBeInTheDocument();
  expect(await screen.findByText(/Rs. -10,000/i)).toBeInTheDocument();
});
