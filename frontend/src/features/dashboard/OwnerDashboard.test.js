import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

jest.mock("../../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("./api", () => ({
  fetchOwnerDashboard: jest.fn(),
}));

jest.mock("../payments/api", () => ({
  fetchOwnerPayouts: jest.fn(),
  settleOwnerPayout: jest.fn(),
}));

jest.mock("../auctions/api", () => ({
  approveGroupMembershipRequest: jest.fn(),
  createGroup: jest.fn(),
  createAuctionSession: jest.fn(),
  fetchOwnerMembershipRequests: jest.fn(),
  inviteSubscriberToGroup: jest.fn(),
  rejectGroupMembershipRequest: jest.fn(),
}));

jest.mock("../auth/api", () => ({
  logoutUser: jest.fn(() => Promise.resolve()),
}));

import OwnerDashboard from "./OwnerDashboard";
import { fetchOwnerDashboard } from "./api";
import { getCurrentUser } from "../../lib/auth/store";
import { fetchOwnerPayouts } from "../payments/api";
import {
  approveGroupMembershipRequest,
  createAuctionSession,
  createGroup,
  fetchOwnerMembershipRequests,
  inviteSubscriberToGroup,
  rejectGroupMembershipRequest,
} from "../auctions/api";

beforeEach(() => {
  jest.clearAllMocks();
});

function normalizedText(element) {
  return element?.textContent?.replace(/\s+/g, " ").trim();
}

test("renders the owner dashboard from the reporting summary payload", async () => {
  getCurrentUser.mockReturnValue({
    ownerId: 4,
    has_subscriber_profile: true,
  });
  fetchOwnerDashboard.mockResolvedValue({
    ownerId: 4,
    groupCount: 2,
    auctionCount: 3,
    paymentCount: 4,
    totalDueAmount: 126000,
    totalPaidAmount: 87000,
    totalOutstandingAmount: 39000,
    groups: [
      {
        groupId: 11,
        groupCode: "JUL-001",
        title: "July Chit",
        status: "active",
        currentCycleNo: 3,
        memberCount: 12,
        activeMemberCount: 10,
        totalDue: 84000,
        totalPaid: 57000,
        outstandingAmount: 27000,
        auctionCount: 2,
        openAuctionCount: 1,
        latestPaymentAt: "2026-04-20T10:30:00.000Z",
      },
      {
        groupId: 12,
        groupCode: "AUG-009",
        title: "August Growth",
        status: "active",
        currentCycleNo: 2,
        memberCount: 10,
        activeMemberCount: 9,
        totalDue: 42000,
        totalPaid: 30000,
        outstandingAmount: 12000,
        auctionCount: 1,
        openAuctionCount: 0,
        latestPaymentAt: "2026-04-19T07:15:00.000Z",
      },
    ],
    recentAuctions: [
      {
        sessionId: 91,
        groupId: 11,
        groupCode: "JUL-001",
        groupTitle: "July Chit",
        cycleNo: 3,
        status: "open",
        scheduledStartAt: "2026-04-21T09:30:00.000Z",
        actualStartAt: "2026-04-21T09:31:00.000Z",
        actualEndAt: null,
        createdAt: "2026-04-21T09:00:00.000Z",
      },
    ],
    recentPayments: [
      {
        paymentId: 501,
        groupId: 11,
        groupCode: "JUL-001",
        subscriberId: 77,
        subscriberName: "Asha Devi",
        amount: 15000,
        paymentDate: "2026-04-20",
        paymentMethod: "upi",
        status: "recorded",
        paymentStatus: "PARTIAL",
        penaltyAmount: 1200,
        arrearsAmount: 3000,
        nextDueAmount: 6000,
        nextDueDate: "2026-04-25",
        createdAt: "2026-04-20T10:30:00.000Z",
      },
    ],
    balances: [
      {
        membershipId: 301,
        memberName: "Asha Devi",
        groupTitle: "July Chit",
        totalDue: 45000,
        totalPaid: 30000,
        outstandingAmount: 15000,
        creditAmount: 0,
        balanceState: "outstanding",
        paymentStatus: "PARTIAL",
        penaltyAmount: 1200,
        arrearsAmount: 3000,
        nextDueAmount: 6000,
        nextDueDate: "2026-04-25",
        dueLabel: "Rs. 45,000",
        paidLabel: "Rs. 30,000",
        outstandingLabel: "Rs. 15,000",
        creditLabel: null,
      },
    ],
    recentActivity: [
      {
        kind: "payment_recorded",
        occurredAt: "2026-04-20T10:30:00.000Z",
        groupId: 11,
        groupCode: "JUL-001",
        title: "Payment recorded",
        detail: "Payment of 15000.00 recorded",
        refId: 501,
      },
    ],
    recentAuditLogs: [
      {
        id: 901,
        occurredAt: "2026-04-20T10:30:00.000Z",
        action: "payment.recorded",
        actionLabel: "Payment Recorded",
        entityType: "payment",
        entityId: "501",
        actorId: 4,
        actorName: "Owner One",
        metadata: { paymentId: 501, amount: 15000 },
        before: { status: "pending" },
        after: { status: "recorded" },
      },
    ],
  });
  fetchOwnerPayouts.mockResolvedValue([
    {
      id: 71,
      subscriberName: "Asha Devi",
      subscriberId: 77,
      groupTitle: "July Chit",
      groupCode: "JUL-001",
      auctionResultId: 44,
      grossAmount: 200000,
      deductionsAmount: 12000,
      netAmount: 188000,
      payoutMethod: "auction_settlement",
      payoutDate: "2026-04-21",
      referenceNo: "UPI-9911",
      status: "pending",
    },
  ]);
  fetchOwnerMembershipRequests.mockResolvedValue([]);

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(await screen.findByText("Owner Dashboard")).toBeInTheDocument();
  expect(await screen.findByText("2 groups")).toBeInTheDocument();
  expect(fetchOwnerDashboard).toHaveBeenCalledTimes(1);
  expect(fetchOwnerPayouts).toHaveBeenCalledTimes(1);
  expect(fetchOwnerMembershipRequests).toHaveBeenCalledTimes(1);
  expect(screen.getByText("3 auctions")).toBeInTheDocument();
  expect(screen.getByText("4 payments")).toBeInTheDocument();
  expect(screen.getByText("Rs. 1,26,000")).toBeInTheDocument();
  expect(screen.getByText("Rs. 87,000")).toBeInTheDocument();
  expect(screen.getByText("Rs. 39,000")).toBeInTheDocument();
  expect(screen.getAllByText("July Chit")).toHaveLength(2);
  expect(screen.getByText("August Growth")).toBeInTheDocument();
  expect(screen.getByText("Recent auctions")).toBeInTheDocument();
  expect(screen.getByText("Recent payments")).toBeInTheDocument();
  expect(await screen.findByText("Payouts")).toBeInTheDocument();
  expect(screen.getByText("Pending payouts")).toBeInTheDocument();
  expect(screen.getByText("Outstanding balances")).toBeInTheDocument();
  expect(screen.getByText("Recent activity")).toBeInTheDocument();
  expect(screen.getByText("Audit log")).toBeInTheDocument();
  expect(screen.getAllByText("Asha Devi").length).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("Payment status: Partial")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("Penalty: Rs. 1,200")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("Arrears: Rs. 3,000")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("Next due amount: Rs. 6,000")).length,
  ).toBeGreaterThan(0);
  expect(screen.getAllByText(/Payment recorded/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Actor: Owner One/i)).toBeInTheDocument();
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes('Before: {"status":"pending"}'))
      .length,
  ).toBeGreaterThan(0);
});

test("shows a sign-in message when there is no owner session", () => {
  getCurrentUser.mockReturnValue(null);
  fetchOwnerMembershipRequests.mockResolvedValue([]);

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(screen.getByText(/Sign in as a chit owner/i)).toBeInTheDocument();
  expect(fetchOwnerDashboard).not.toHaveBeenCalled();
  expect(fetchOwnerPayouts).not.toHaveBeenCalled();
  expect(fetchOwnerMembershipRequests).not.toHaveBeenCalled();
});

test("creates an auction session with commission config from the dashboard form", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    ownerId: 4,
  });
  fetchOwnerDashboard
    .mockResolvedValueOnce({
      ownerId: 4,
      groupCount: 1,
      auctionCount: 0,
      paymentCount: 0,
      totalDueAmount: 0,
      totalPaidAmount: 0,
      totalOutstandingAmount: 0,
      groups: [
        {
          groupId: 11,
          groupCode: "JUL-001",
          title: "July Chit",
          status: "active",
          currentCycleNo: 3,
          memberCount: 12,
          activeMemberCount: 10,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          auctionCount: 0,
          openAuctionCount: 0,
          latestPaymentAt: null,
        },
      ],
      recentAuctions: [],
      recentPayments: [],
      balances: [],
      recentActivity: [],
      recentAuditLogs: [],
    })
    .mockResolvedValueOnce({
      ownerId: 4,
      groupCount: 1,
      auctionCount: 1,
      paymentCount: 0,
      totalDueAmount: 0,
      totalPaidAmount: 0,
      totalOutstandingAmount: 0,
      groups: [
        {
          groupId: 11,
          groupCode: "JUL-001",
          title: "July Chit",
          status: "active",
          currentCycleNo: 3,
          memberCount: 12,
          activeMemberCount: 10,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          auctionCount: 1,
          openAuctionCount: 1,
          latestPaymentAt: null,
        },
      ],
      recentAuctions: [
        {
          sessionId: 91,
          groupId: 11,
          groupCode: "JUL-001",
          groupTitle: "July Chit",
          cycleNo: 3,
          auctionMode: "BLIND",
          commissionMode: "PERCENTAGE",
          commissionValue: 5,
          minBid: 5000,
          maxBid: 25000,
          minIncrement: 500,
          status: "open",
          scheduledStartAt: "2026-04-21T09:30:00.000Z",
          actualStartAt: "2026-04-21T09:31:00.000Z",
          actualEndAt: null,
          createdAt: "2026-04-21T09:00:00.000Z",
        },
      ],
      recentPayments: [],
      balances: [],
      recentActivity: [],
      recentAuditLogs: [],
    });
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchOwnerMembershipRequests.mockResolvedValue([]);
  createAuctionSession.mockResolvedValue({
    id: 91,
    groupId: 11,
    cycleNo: 3,
    auctionMode: "BLIND",
    commissionMode: "PERCENTAGE",
    commissionValue: 5,
    minBid: 5000,
    maxBid: 25000,
    minIncrement: 500,
    status: "open",
    biddingWindowSeconds: 180,
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(await screen.findByText("Create Auction Session")).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText(/Auction Mode/i), "BLIND");
  await user.selectOptions(screen.getByLabelText(/Commission Mode/i), "PERCENTAGE");
  await user.clear(screen.getByLabelText(/Commission Value/i));
  await user.type(screen.getByLabelText(/Commission Value/i), "5");
  await user.clear(screen.getByLabelText(/Minimum Bid/i));
  await user.type(screen.getByLabelText(/Minimum Bid/i), "5000");
  await user.clear(screen.getByLabelText(/Maximum Bid/i));
  await user.type(screen.getByLabelText(/Maximum Bid/i), "25000");
  await user.clear(screen.getByLabelText(/Minimum Increment/i));
  await user.type(screen.getByLabelText(/Minimum Increment/i), "500");
  await user.clear(screen.getByLabelText(/Blind Start Time/i));
  await user.type(screen.getByLabelText(/Blind Start Time/i), "2026-04-21T15:30");
  await user.clear(screen.getByLabelText(/Blind End Time/i));
  await user.type(screen.getByLabelText(/Blind End Time/i), "2026-04-21T15:33");
  await user.click(screen.getByRole("button", { name: /Create auction session/i }));

  await waitFor(() => {
    expect(createAuctionSession).toHaveBeenCalledWith(11, {
      cycleNo: 3,
      auctionMode: "BLIND",
      commissionMode: "PERCENTAGE",
      commissionValue: 5,
      biddingWindowSeconds: 180,
      minBidValue: 5000,
      maxBidValue: 25000,
      minIncrement: 500,
      startTime: expect.any(String),
      endTime: expect.any(String),
    });
  });

  expect(await screen.findByText(/Created session #91 with Blind auction and Percentage/i)).toBeInTheDocument();
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("Blind auction · Percentage (5)")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByText(
      (_content, element) => normalizedText(element)?.includes("Bid rules: Min 5,000 · Max 25,000 · Increment 500"),
    ).length,
  ).toBeGreaterThan(0);
});

test("creates a chit group with public visibility from the dashboard form", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    ownerId: 4,
  });
  fetchOwnerDashboard.mockResolvedValue({
    ownerId: 4,
    groupCount: 0,
    auctionCount: 0,
    paymentCount: 0,
    totalDueAmount: 0,
    totalPaidAmount: 0,
    totalOutstandingAmount: 0,
    groups: [],
    recentAuctions: [],
    recentPayments: [],
    balances: [],
    recentActivity: [],
    recentAuditLogs: [],
  });
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchOwnerMembershipRequests.mockResolvedValue([]);
  createGroup.mockResolvedValue({
    id: 12,
    ownerId: 4,
    groupCode: "PUB-001",
    title: "Public Group",
    chitValue: 500000,
    installmentAmount: 25000,
    memberCount: 20,
    cycleCount: 20,
    cycleFrequency: "monthly",
    visibility: "public",
    startDate: "2026-05-01",
    firstAuctionDate: "2026-05-10",
    currentCycleNo: 1,
    status: "draft",
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: /Create Chit Group/i });
  await user.type(screen.getByLabelText(/Group code/i), "PUB-001");
  await user.type(screen.getByLabelText(/^Title$/i), "Public Group");
  await user.type(screen.getByLabelText(/Chit value/i), "500000");
  await user.type(screen.getByLabelText(/Installment amount/i), "25000");
  await user.type(screen.getByLabelText(/Member count/i), "20");
  await user.type(screen.getByLabelText(/Cycle count/i), "20");
  await user.selectOptions(screen.getByLabelText(/Visibility/i), "public");
  await user.type(screen.getByLabelText(/^Start date$/i), "2026-05-01");
  await user.type(screen.getByLabelText(/First auction date/i), "2026-05-10");
  await user.click(screen.getByRole("button", { name: /Create chit/i }));

  await waitFor(() => {
    expect(createGroup).toHaveBeenCalledWith({
      ownerId: 4,
      groupCode: "PUB-001",
      title: "Public Group",
      chitValue: 500000,
      installmentAmount: 25000,
      memberCount: 20,
      cycleCount: 20,
      cycleFrequency: "monthly",
      visibility: "public",
      startDate: "2026-05-01",
      firstAuctionDate: "2026-05-10",
    });
  });
});

test("disables bid-rule inputs for fixed auction sessions", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    ownerId: 4,
  });
  fetchOwnerDashboard.mockResolvedValue({
    ownerId: 4,
    groupCount: 1,
    auctionCount: 0,
    paymentCount: 0,
    totalDueAmount: 0,
    totalPaidAmount: 0,
    totalOutstandingAmount: 0,
    groups: [
      {
        groupId: 11,
        groupCode: "JUL-001",
        title: "July Chit",
        status: "active",
        currentCycleNo: 3,
        memberCount: 12,
        activeMemberCount: 10,
        totalDue: 0,
        totalPaid: 0,
        outstandingAmount: 0,
        auctionCount: 0,
        openAuctionCount: 0,
        latestPaymentAt: null,
      },
    ],
    recentAuctions: [],
    recentPayments: [],
    balances: [],
    recentActivity: [],
    recentAuditLogs: [],
  });
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchOwnerMembershipRequests.mockResolvedValue([]);

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(await screen.findByText("Create Auction Session")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText(/Auction Mode/i), "FIXED");

  expect(screen.getByLabelText(/Minimum Bid/i)).toBeDisabled();
  expect(screen.getByLabelText(/Maximum Bid/i)).toBeDisabled();
  expect(screen.getByLabelText(/Minimum Increment/i)).toBeDisabled();
});

test("lets an owner approve and reject pending membership requests", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    ownerId: 4,
  });
  fetchOwnerDashboard
    .mockResolvedValueOnce({
      ownerId: 4,
      groupCount: 1,
      auctionCount: 0,
      paymentCount: 0,
      totalDueAmount: 0,
      totalPaidAmount: 0,
      totalOutstandingAmount: 0,
      groups: [
        {
          groupId: 11,
          groupCode: "JUL-001",
          title: "July Chit",
          status: "active",
          currentCycleNo: 3,
          memberCount: 12,
          activeMemberCount: 10,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          auctionCount: 0,
          openAuctionCount: 0,
          latestPaymentAt: null,
        },
      ],
      recentAuctions: [],
      recentPayments: [],
      balances: [],
      recentActivity: [],
      recentAuditLogs: [],
    })
    .mockResolvedValue({
      ownerId: 4,
      groupCount: 1,
      auctionCount: 0,
      paymentCount: 0,
      totalDueAmount: 0,
      totalPaidAmount: 0,
      totalOutstandingAmount: 0,
      groups: [
        {
          groupId: 11,
          groupCode: "JUL-001",
          title: "July Chit",
          status: "active",
          currentCycleNo: 3,
          memberCount: 12,
          activeMemberCount: 11,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          auctionCount: 0,
          openAuctionCount: 0,
          latestPaymentAt: null,
        },
      ],
      recentAuctions: [],
      recentPayments: [],
      balances: [],
      recentActivity: [],
      recentAuditLogs: [],
    });
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchOwnerMembershipRequests.mockResolvedValue([
    {
      membershipId: 51,
      groupId: 11,
      groupCode: "JUL-001",
      groupTitle: "July Chit",
      subscriberId: 7,
      subscriberName: "Asha Devi",
      memberNo: 8,
      membershipStatus: "pending",
      requestedAt: "2026-04-23T10:00:00.000Z",
    },
    {
      membershipId: 52,
      groupId: 11,
      groupCode: "JUL-001",
      groupTitle: "July Chit",
      subscriberId: 8,
      subscriberName: "Meena Devi",
      memberNo: 9,
      membershipStatus: "pending",
      requestedAt: "2026-04-23T10:05:00.000Z",
    },
  ]);
  approveGroupMembershipRequest.mockResolvedValue({
    membershipId: 51,
    membershipStatus: "active",
  });
  rejectGroupMembershipRequest.mockResolvedValue({
    membershipId: 52,
    membershipStatus: "rejected",
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: /Membership requests/i })).toBeInTheDocument();
  expect(screen.getByText("Asha Devi")).toBeInTheDocument();
  expect(screen.getByText("Meena Devi")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Approve request for Asha Devi/i }));

  await waitFor(() => {
    expect(approveGroupMembershipRequest).toHaveBeenCalledWith(11, 51);
  });
  expect(await screen.findByText(/Approved Asha Devi for July Chit/i)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Reject request for Meena Devi/i }));

  await waitFor(() => {
    expect(rejectGroupMembershipRequest).toHaveBeenCalledWith(11, 52);
  });
  expect(await screen.findByText(/Rejected Meena Devi for July Chit/i)).toBeInTheDocument();
});

test("lets an owner send a phone invite to a private chit group", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    ownerId: 4,
  });
  fetchOwnerDashboard.mockResolvedValue({
    ownerId: 4,
    groupCount: 2,
    auctionCount: 0,
    paymentCount: 0,
    totalDueAmount: 0,
    totalPaidAmount: 0,
    totalOutstandingAmount: 0,
    groups: [
      {
        groupId: 11,
        groupCode: "PRI-001",
        title: "Private Group",
        visibility: "private",
        status: "active",
        currentCycleNo: 1,
        memberCount: 12,
        activeMemberCount: 4,
        totalDue: 0,
        totalPaid: 0,
        outstandingAmount: 0,
        auctionCount: 0,
        openAuctionCount: 0,
        latestPaymentAt: null,
      },
      {
        groupId: 12,
        groupCode: "PUB-001",
        title: "Public Group",
        visibility: "public",
        status: "active",
        currentCycleNo: 1,
        memberCount: 12,
        activeMemberCount: 4,
        totalDue: 0,
        totalPaid: 0,
        outstandingAmount: 0,
        auctionCount: 0,
        openAuctionCount: 0,
        latestPaymentAt: null,
      },
    ],
    recentAuctions: [],
    recentPayments: [],
    balances: [],
    recentActivity: [],
    recentAuditLogs: [],
  });
  fetchOwnerPayouts.mockResolvedValue([]);
  fetchOwnerMembershipRequests.mockResolvedValue([]);
  inviteSubscriberToGroup.mockResolvedValue({
    membershipId: 61,
    groupId: 11,
    memberNo: 5,
    membershipStatus: "invited",
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <OwnerDashboard />
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: /Send Private Invite/i })).toBeInTheDocument();
  await user.type(screen.getByLabelText(/Subscriber phone/i), "8888888888");
  await user.click(screen.getByRole("button", { name: /Send invite/i }));

  expect(inviteSubscriberToGroup).toHaveBeenCalledWith(11, "8888888888");
  expect(await screen.findByText(/Invite sent for Private Group/i)).toBeInTheDocument();
});
