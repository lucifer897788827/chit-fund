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
  approveGroupJoinRequest,
  closeGroupCollection,
  createGroupInvite,
  fetchGroupInvites,
  fetchGroupMemberSummary,
  fetchGroupJoinRequests,
  fetchGroups,
  fetchGroupStatus,
  finalizeAuctionSession,
  removeGroupMember,
  rejectGroupJoinRequest,
  revokeGroupInvite,
  searchGroupInviteCandidates,
  updateGroupSettings,
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
  approveGroupJoinRequest: jest.fn(),
  closeGroupCollection: jest.fn(),
  createGroupInvite: jest.fn(),
  fetchGroupInvites: jest.fn(),
  fetchGroupMemberSummary: jest.fn(),
  fetchGroupJoinRequests: jest.fn(),
  fetchGroups: jest.fn(),
  fetchGroupStatus: jest.fn(),
  finalizeAuctionSession: jest.fn(),
  removeGroupMember: jest.fn(),
  rejectGroupJoinRequest: jest.fn(),
  revokeGroupInvite: jest.fn(),
  searchGroupInviteCandidates: jest.fn(),
  updateGroupSettings: jest.fn(),
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
  commissionType: "NONE",
  auctionType: "LIVE",
  groupType: "STANDARD",
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
  fetchGroupJoinRequests.mockResolvedValue([]);
  fetchGroupInvites.mockResolvedValue([]);
  approveGroupJoinRequest.mockResolvedValue({});
  markOwnerPayoutPaid.mockResolvedValue({});
  finalizeAuctionSession.mockResolvedValue({ status: "finalized" });
  createGroupInvite.mockResolvedValue({});
  searchGroupInviteCandidates.mockResolvedValue([]);
  removeGroupMember.mockResolvedValue({});
  rejectGroupJoinRequest.mockResolvedValue({});
  revokeGroupInvite.mockResolvedValue({});
  updateGroupSettings.mockResolvedValue({});
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
      prizedStatus: "prized",
      lastPaymentDate: "2026-04-27",
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

test("renders member slot usage for owners", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
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
  mockUserDashboard({
    ...ownerDashboard,
    groups: [{ ...ownerDashboard.groups[0], slotsRemaining: 5 }],
    balances: [
      {
        groupId: 42,
        membershipId: 81,
        memberName: "Asha Devi",
        memberNo: 1,
        totalPaid: 10000,
        totalDue: 15000,
        outstandingAmount: 5000,
        slotCount: 3,
        wonSlotCount: 1,
        remainingSlotCount: 2,
        lastPaymentDate: "2026-04-27",
      },
    ],
  });
  fetchGroups.mockResolvedValue([{ ...groupDetail, slotsRemaining: 5 }]);

  renderGroupTab("members");

  expect(await screen.findByText("Asha Devi")).toBeInTheDocument();
  const activeMembersTable = screen.getAllByRole("table")[0];
  expect(activeMembersTable).toHaveTextContent("3 owned");
  expect(activeMembersTable).toHaveTextContent("1 used");
  expect(activeMembersTable).toHaveTextContent("2 remaining");
  expect(activeMembersTable).toHaveTextContent("27 Apr 2026");
  expect(activeMembersTable).toHaveTextContent("Won");
});

test("approves a pending join request from the members tab", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroupMemberSummary.mockResolvedValue([]);
  fetchGroupJoinRequests.mockResolvedValue([
    {
      id: 91,
      groupId: 42,
      subscriberId: 77,
      subscriberName: "Asha Devi",
      requestedSlotCount: 2,
      paymentScore: 88,
      status: "pending",
      createdAt: "2026-04-28T10:00:00Z",
    },
  ]);
  fetchGroups.mockResolvedValue([{ ...groupDetail, slotsRemaining: 6 }]);
  approveGroupJoinRequest.mockResolvedValue({
    id: 81,
    groupId: 42,
    subscriberId: 77,
    memberNo: 3,
    membershipStatus: "active",
    slotCount: 2,
    wonSlotCount: 0,
    remainingSlotCount: 2,
  });

  renderGroupTab("members");

  fireEvent.click(await screen.findByRole("button", { name: "Approve Asha Devi" }));

  await waitFor(() => expect(approveGroupJoinRequest).toHaveBeenCalledWith(42, 91));
  expect(screen.getByRole("table")).toHaveTextContent("88%");
  expect(await screen.findByText("No pending requests")).toBeInTheDocument();
  expect(await screen.findByText("Asha Devi")).toBeInTheDocument();
});

test("disables join-request approval when the group is full", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroupJoinRequests.mockResolvedValue([
    {
      id: 91,
      groupId: 42,
      subscriberId: 77,
      subscriberName: "Asha Devi",
      requestedSlotCount: 2,
      paymentScore: 88,
      status: "pending",
    },
  ]);
  fetchGroups.mockResolvedValue([{ ...groupDetail, memberCount: 2, slotsRemaining: 0 }]);

  renderGroupTab("members");

  expect(await screen.findByText("Group full")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Approve Asha Devi" })).toBeDisabled();
  expect(screen.getByText("Group is full.")).toBeInTheDocument();
});

test("rejects a pending join request from the members tab", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroupMemberSummary.mockResolvedValue([]);
  fetchGroupJoinRequests.mockResolvedValue([
    {
      id: 92,
      groupId: 42,
      subscriberId: 78,
      subscriberName: "Latha",
      requestedSlotCount: 1,
      paymentScore: null,
      status: "pending",
      createdAt: "2026-04-28T10:15:00Z",
    },
  ]);
  rejectGroupJoinRequest.mockResolvedValue({
    id: 92,
    status: "rejected",
  });

  renderGroupTab("members");

  expect(await screen.findByText("No history")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Reject Latha" }));

  await waitFor(() => expect(rejectGroupJoinRequest).toHaveBeenCalledWith(42, 92));
  expect(await screen.findByText("No pending requests")).toBeInTheDocument();
});

test("shows clear empty states when there are no members or pending join requests", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 0,
    total_members: 0,
  });
  fetchGroupMemberSummary.mockResolvedValue([]);
  fetchGroupJoinRequests.mockResolvedValue([]);

  renderGroupTab("members");

  expect(await screen.findByText("No members yet")).toBeInTheDocument();
  expect(screen.getByText("No pending requests")).toBeInTheDocument();
});

test("searches subscribers and sends an invite from the invites tab", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  searchGroupInviteCandidates.mockResolvedValue([
    {
      subscriberId: 77,
      userId: 501,
      fullName: "Asha Devi",
      phone: "8888888888",
      subscriberStatus: "active",
      membershipStatus: null,
      inviteEligible: true,
      note: null,
    },
  ]);
  createGroupInvite.mockResolvedValue({
    inviteId: 71,
    membershipId: 91,
    groupId: 42,
    subscriberId: 77,
    subscriberName: "Asha Devi",
    memberNo: 3,
    membershipStatus: "invited",
    inviteStatus: "pending",
    inviteExpiresAt: "2026-05-05T10:30:00Z",
    requestedAt: "2026-04-28T10:30:00Z",
  });

  renderGroupTab("invites");

  fireEvent.change(await screen.findByPlaceholderText("Search subscribers by name or phone"), {
    target: { value: "asha" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search subscribers" }));

  expect(await screen.findByText("Asha Devi")).toBeInTheDocument();
  expect(searchGroupInviteCandidates).toHaveBeenCalledWith(42, "asha");

  fireEvent.click(screen.getByRole("button", { name: "Invite Asha Devi" }));

  await waitFor(() => expect(createGroupInvite).toHaveBeenCalledWith(42, 77));
  expect(await screen.findByText("Invite sent to Asha Devi. Member #3 is waiting for acceptance.")).toBeInTheDocument();
  const inviteResultsTable = screen.getAllByRole("table")[0];
  expect(inviteResultsTable).toHaveTextContent("Invited");
  expect(inviteResultsTable).toHaveTextContent("Invite sent as member #3");
  const inviteAuditTable = screen.getAllByRole("table")[1];
  expect(inviteAuditTable).toHaveTextContent("Pending");
});

test("lists and revokes a pending invite from the invites tab", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroupInvites.mockResolvedValue([
    {
      inviteId: 71,
      groupId: 42,
      subscriberId: 77,
      subscriberName: "Asha Devi",
      membershipId: 91,
      memberNo: 3,
      membershipStatus: "invited",
      status: "pending",
      issuedAt: "2026-04-28T10:30:00Z",
      expiresAt: "2026-05-05T10:30:00Z",
      acceptedAt: null,
      revokedAt: null,
    },
  ]);
  revokeGroupInvite.mockResolvedValue({
    inviteId: 71,
    groupId: 42,
    subscriberId: 77,
    subscriberName: "Asha Devi",
    membershipId: 91,
    memberNo: 3,
    membershipStatus: "rejected",
    status: "revoked",
    issuedAt: "2026-04-28T10:30:00Z",
    expiresAt: "2026-05-05T10:30:00Z",
    acceptedAt: null,
    revokedAt: "2026-04-28T11:00:00Z",
  });

  renderGroupTab("invites");

  expect(await screen.findByText("Asha Devi")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

  await waitFor(() => expect(revokeGroupInvite).toHaveBeenCalledWith(42, 71));
  expect(await screen.findByText("Invite for Asha Devi was revoked.")).toBeInTheDocument();
  expect(await screen.findByText("Revoked")).toBeInTheDocument();
});

test("removes a removable member from the members tab and releases slots", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroupMemberSummary.mockResolvedValue([
    {
      membershipId: 81,
      subscriberId: 77,
      memberNo: 1,
      memberName: "Asha Devi",
      membershipStatus: "active",
      prizedStatus: "unprized",
      canBid: true,
      slotCount: 2,
      wonSlotCount: 0,
      remainingSlotCount: 2,
      removeEligible: true,
      removeBlockedReason: null,
      paid: 0,
      received: 0,
      dividend: 0,
      net: 0,
    },
  ]);
  mockUserDashboard({
    ...ownerDashboard,
    groups: [{ ...ownerDashboard.groups[0], slotsRemaining: 4 }],
    balances: [
      {
        groupId: 42,
        membershipId: 81,
        memberName: "Asha Devi",
        memberNo: 1,
        totalPaid: 0,
        totalDue: 10000,
        outstandingAmount: 10000,
        slotCount: 2,
        wonSlotCount: 0,
        remainingSlotCount: 2,
      },
    ],
  });
  fetchGroups.mockResolvedValue([{ ...groupDetail, slotsRemaining: 4 }]);
  removeGroupMember.mockResolvedValue({
    membershipId: 81,
    groupId: 42,
    subscriberId: 77,
    membershipStatus: "removed",
    slotsReleased: 2,
    removedAt: "2026-04-28T11:00:00Z",
  });

  renderGroupTab("members");

  fireEvent.click(await screen.findByRole("button", { name: "Remove member" }));

  await waitFor(() => expect(removeGroupMember).toHaveBeenCalledWith(42, 81));
  expect(await screen.findByText("Asha Devi was removed and 2 slots were released.")).toBeInTheDocument();
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Slots remaining: 6");
  expect(screen.queryByText("Asha Devi")).not.toBeInTheDocument();
});

test("saves commission and auction settings from the settings tab", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: false,
    status: "OPEN",
    paid_members: 1,
    total_members: 2,
  });
  updateGroupSettings.mockResolvedValue({
    ...groupDetail,
    commissionType: "FIRST_MONTH",
    auctionType: "BLIND",
  });

  renderGroupTab("settings");

  const commissionTypeSelect = await screen.findByLabelText("Commission type");
  const auctionTypeSelect = screen.getByLabelText("Auction type");
  expect(commissionTypeSelect).toHaveValue("NONE");
  expect(auctionTypeSelect).toHaveValue("LIVE");

  fireEvent.change(commissionTypeSelect, { target: { value: "FIRST_MONTH" } });
  fireEvent.change(auctionTypeSelect, { target: { value: "BLIND" } });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

  await waitFor(() =>
    expect(updateGroupSettings).toHaveBeenCalledWith(42, {
      commissionType: "FIRST_MONTH",
      auctionType: "BLIND",
    }),
  );
  expect(await screen.findByText("Group settings saved.")).toBeInTheDocument();
  expect(screen.getByText("Current commission").nextSibling).toHaveTextContent("First Month");
  expect(screen.getByText("Current auction mode").nextSibling).toHaveTextContent("Blind");
});

test("locks settings after the group has started", async () => {
  fetchGroupStatus.mockResolvedValue({
    collection_closed: true,
    status: "COLLECTION_CLOSED",
    paid_members: 1,
    total_members: 2,
  });
  fetchGroups.mockResolvedValue([
    {
      ...groupDetail,
      collectionClosed: true,
      currentMonthStatus: "COLLECTION_CLOSED",
    },
  ]);

  renderGroupTab("settings");

  expect(await screen.findByText(/Settings are locked because this group has already started/i)).toBeInTheDocument();
  expect(screen.getByLabelText("Commission type")).toBeDisabled();
  expect(screen.getByLabelText("Auction type")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
});
