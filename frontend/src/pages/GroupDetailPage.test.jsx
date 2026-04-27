import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import GroupDetailPage from "./GroupDetailPage";
import { getCurrentUser, sessionHasRole } from "../lib/auth/store";
import {
  fetchOwnerDashboard,
  fetchUserDashboard,
  getOwnerDashboardFromUserDashboard,
  getSubscriberDashboardFromUserDashboard,
} from "../features/dashboard/api";
import {
  closeGroupCollection,
  fetchGroupMemberSummary,
  fetchGroups,
  fetchGroupStatus,
  finalizeAuctionSession,
  inviteSubscriberToGroup,
} from "../features/auctions/api";
import { fetchOwnerPayouts, fetchPayments, markOwnerPayoutPaid, settleOwnerPayout } from "../features/payments/api";

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../features/auctions/AuctionRoomPage", () => () => <div data-testid="auction-room" />);
jest.mock("../features/auctions/OwnerAuctionConsole", () => () => <div data-testid="owner-auction-console" />);
jest.mock("../features/subscribers/SubscriberManagementPanel", () => () => <div data-testid="subscriber-management" />);
jest.mock("../features/payments/PaymentPanel", () => () => <div data-testid="payment-panel" />);

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  sessionHasRole: jest.fn(),
}));

jest.mock("../features/dashboard/api", () => ({
  fetchOwnerDashboard: jest.fn(),
  fetchUserDashboard: jest.fn(),
  getOwnerDashboardFromUserDashboard: jest.fn((data) => data?.stats?.owner_dashboard ?? {}),
  getSubscriberDashboardFromUserDashboard: jest.fn((data) => data?.stats?.subscriber_dashboard ?? {}),
}));

jest.mock("../features/auctions/api", () => ({
  closeGroupCollection: jest.fn(),
  fetchGroupMemberSummary: jest.fn(),
  fetchGroups: jest.fn(),
  fetchGroupStatus: jest.fn(),
  finalizeAuctionSession: jest.fn(),
  inviteSubscriberToGroup: jest.fn(),
}));

jest.mock("../features/payments/api", () => ({
  fetchOwnerPayouts: jest.fn(),
  fetchPayments: jest.fn(),
  markOwnerPayoutPaid: jest.fn(),
  settleOwnerPayout: jest.fn(),
}));

const ownerDashboard = {
  groups: [
    {
      groupId: 42,
      title: "May Chit",
      groupCode: "MAY-42",
      currentCycleNo: 1,
      memberCount: 2,
      totalDue: 2000,
      totalPaid: 1000,
      outstandingAmount: 1000,
    },
  ],
  balances: [],
  recentAuctions: [],
};

const groupDetail = {
  id: 42,
  title: "May Chit",
  groupCode: "MAY-42",
  currentCycleNo: 1,
  cycleCount: 2,
  chitValue: 100000,
  installmentAmount: 50000,
  memberCount: 2,
  visibility: "private",
  status: "active",
};

function renderPaymentsTab() {
  return renderGroupTab("payments");
}

function renderGroupTab(tab) {
  return render(
    <MemoryRouter initialEntries={[`/groups/42?tab=${tab}`]}>
      <Routes>
        <Route element={<GroupDetailPage />} path="/groups/:groupId" />
      </Routes>
    </MemoryRouter>,
  );
}

function mockUserDashboard(ownerData = ownerDashboard, subscriberData = { memberships: [], activeAuctions: [] }) {
  fetchUserDashboard.mockReset();
  getOwnerDashboardFromUserDashboard.mockImplementation((data) => data?.stats?.owner_dashboard ?? {});
  getSubscriberDashboardFromUserDashboard.mockImplementation((data) => data?.stats?.subscriber_dashboard ?? {});
  fetchUserDashboard.mockImplementation(() => Promise.resolve({
    role: "owner",
    financial_summary: {},
    stats: {
      owner_dashboard: ownerData,
      subscriber_dashboard: subscriberData,
    },
  }));
}

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  window.confirm = jest.fn(() => true);
  getCurrentUser.mockReturnValue({ owner_id: 1, role: "chit_owner" });
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  mockUserDashboard();
  fetchOwnerDashboard.mockResolvedValue(ownerDashboard);
  fetchGroups.mockResolvedValue([groupDetail]);
  fetchPayments.mockResolvedValue([]);
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchGroupMemberSummary.mockResolvedValue([]);
  markOwnerPayoutPaid.mockResolvedValue({});
  finalizeAuctionSession.mockResolvedValue({ status: "finalized" });
  inviteSubscriberToGroup.mockResolvedValue({});
  settleOwnerPayout.mockResolvedValue({});
});

test("uses backend group status instead of stale local collection state", async () => {
  window.localStorage.setItem("chit-fund-collection-closed:42", "true");
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });

  renderPaymentsTab();

  const button = await screen.findByRole("button", { name: "Close Collection" });
  expect(button).toBeEnabled();
  expect(fetchGroupStatus).toHaveBeenCalledWith(42);
  expect(screen.queryByText(/not synced/i)).not.toBeInTheDocument();
});

test("closes collection through backend and updates the page from the response", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  closeGroupCollection.mockResolvedValue({
    ...groupDetail,
    collectionClosed: true,
    currentMonthStatus: "COLLECTION_CLOSED",
  });

  renderPaymentsTab();

  fireEvent.click(await screen.findByRole("button", { name: "Close Collection" }));

  await waitFor(() => expect(closeGroupCollection).toHaveBeenCalledWith(42));
  expect(await screen.findByRole("button", { name: "Collection closed" })).toBeDisabled();
  expect(screen.queryByText(/not synced/i)).not.toBeInTheDocument();
});

test("disables auction action until backend status is collection closed", async () => {
  const activeAuction = {
    groupId: 42,
    sessionId: 77,
    status: "open",
    auctionMode: "LIVE",
    validBidCount: 0,
  };
  mockUserDashboard({
    ...ownerDashboard,
    recentAuctions: [activeAuction],
  }, { memberships: [], activeAuctions: [activeAuction] });
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 2,
    total_members: 2,
  });

  renderGroupTab("auction");

  expect(await screen.findByRole("button", { name: "Confirm result" })).toBeDisabled();
  expect(screen.getByText("Close collection before starting an auction.")).toBeInTheDocument();
});

test("marks pending payout paid through backend and removes duplicate action", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: true,
    status: "COLLECTION_CLOSED",
    paid_members: 2,
    total_members: 2,
  });
  fetchOwnerPayouts.mockResolvedValue([
    {
      id: 71,
      subscriberName: "Asha Devi",
      subscriberId: 77,
      netAmount: 188000,
      status: "pending",
    },
  ]);
  markOwnerPayoutPaid.mockResolvedValue({
    id: 71,
    subscriberName: "Asha Devi",
    subscriberId: 77,
    netAmount: 188000,
    status: "paid",
    paidAt: "2026-04-26T10:00:00Z",
  });

  renderGroupTab("payout");

  fireEvent.click(await screen.findByRole("button", { name: "Mark as Paid" }));

  await waitFor(() => expect(markOwnerPayoutPaid).toHaveBeenCalledWith(71));
  expect(await screen.findByText("Closed")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Mark as Paid" })).not.toBeInTheDocument();
});

test("renders backend group member summaries in the ledger without approximate messaging", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: true,
    status: "COLLECTION_CLOSED",
    paid_members: 2,
    total_members: 2,
  });
  fetchGroupMemberSummary.mockResolvedValue([
    {
      membershipId: 81,
      subscriberId: 77,
      memberNo: 1,
      memberName: "Asha Devi",
      paid: 10000,
      received: 2500,
      dividend: 500,
      net: -7000,
    },
  ]);

  renderGroupTab("ledger");

  expect(await screen.findByText("Asha Devi")).toBeInTheDocument();
  const ledgerTable = screen.getByRole("table");
  expect(within(ledgerTable).getAllByText("Rs. 10,000").length).toBeGreaterThan(0);
  expect(within(ledgerTable).getAllByText("Rs. 2,500").length).toBeGreaterThan(0);
  expect(within(ledgerTable).getAllByText("Rs. -7,000").length).toBeGreaterThan(0);
  expect(screen.queryByText("Approximate calculation")).not.toBeInTheDocument();
  expect(fetchGroupMemberSummary).toHaveBeenCalledWith(42);
});
