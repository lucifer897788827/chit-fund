import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

jest.mock("./api", () => ({
  fetchSubscriberDashboard: jest.fn(),
}));

jest.mock("../auctions/api", () => ({
  acceptGroupInvite: jest.fn(),
  fetchPublicChits: jest.fn(() => Promise.resolve([])),
  rejectGroupInvite: jest.fn(),
  requestGroupMembership: jest.fn(),
  searchChitsByCode: jest.fn(() => Promise.resolve([])),
}));

jest.mock("../../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  getDashboardPath: jest.fn(() => "/subscriber-dashboard"),
  sessionHasRole: jest.fn(() => false),
}));

jest.mock("../auth/api", () => ({
  logoutUser: jest.fn(() => Promise.resolve()),
}));

jest.mock("../owner-requests/api", () => ({
  createOwnerRequest: jest.fn(),
}));

import SubscriberDashboard from "./SubscriberDashboard";
import { fetchSubscriberDashboard } from "./api";
import {
  acceptGroupInvite,
  fetchPublicChits,
  rejectGroupInvite,
  requestGroupMembership,
  searchChitsByCode,
} from "../auctions/api";
import { getCurrentUser } from "../../lib/auth/store";
import { createOwnerRequest } from "../owner-requests/api";

beforeEach(() => {
  jest.clearAllMocks();
});

function renderDashboard() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <SubscriberDashboard />
    </MemoryRouter>,
  );
}

function normalizedText(element) {
  return element?.textContent?.replace(/\s+/g, " ").trim();
}

function hasText(expected) {
  return (_content, element) => normalizedText(element) === expected;
}

test("renders a subscriber-first overview with membership balances, active auctions, and recent outcomes when available", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [
      {
        membershipId: 12,
        groupId: 4,
        groupCode: "APR-004",
        groupTitle: "April Prosperity Chit",
        memberNo: 8,
        membershipStatus: "active",
        prizedStatus: "unprized",
        canBid: true,
        currentCycleNo: 3,
        installmentAmount: 12000,
        totalDue: 25000,
        totalPaid: 10000,
        outstandingAmount: 15000,
        paymentStatus: "PARTIAL",
        penaltyAmount: 1200,
        arrearsAmount: 6000,
        nextDueAmount: 9000,
        nextDueDate: "2026-04-25",
        auctionStatus: "open",
        slotCount: 3,
        wonSlotCount: 1,
        remainingSlotCount: 2,
      },
    ],
    activeAuctions: [
      {
        sessionId: 19,
        groupId: 4,
        groupCode: "APR-004",
        groupTitle: "April Prosperity Chit",
        cycleNo: 3,
        status: "open",
        membershipId: 12,
        canBid: true,
        slotCount: 3,
        wonSlotCount: 1,
        remainingSlotCount: 2,
      },
    ],
    recentAuctionOutcomes: [
      {
        sessionId: 18,
        groupId: 4,
        groupCode: "APR-004",
        groupTitle: "April Prosperity Chit",
        cycleNo: 2,
        status: "closed",
        membershipId: 12,
        winnerMembershipId: 12,
        winnerMemberNo: 8,
        winningBidAmount: 17500,
        finalizedAt: "2026-04-18T10:00:00Z",
      },
    ],
  });
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  expect(await screen.findByRole("heading", { name: /Subscriber Dashboard/i })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /1 active membership/i })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /1 live auction/i })).toBeInTheDocument();
  expect(screen.getByText(/Prize state:/i)).toBeInTheDocument();
  expect(screen.getByText(/Unprized/i)).toBeInTheDocument();
  expect(screen.getAllByText("You own").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Won").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Remaining").length).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("3 chits")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("You can bid 2 more times")).length,
  ).toBeGreaterThan(0);
  expect(screen.getByText(/Outstanding dues/i)).toBeInTheDocument();
  expect(screen.getAllByText("Rs. 15,000").length).toBeGreaterThan(0);
  expect(screen.getByText("PARTIAL")).toBeInTheDocument();
  expect(screen.getByText("Rs. 1,200")).toBeInTheDocument();
  expect(screen.getByText("Rs. 6,000")).toBeInTheDocument();
  expect(screen.getByText("Rs. 9,000")).toBeInTheDocument();
  expect(screen.getByText("25 Apr 2026")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Go to auctions/i })).toHaveAttribute("href", "/auctions/19");
  expect(screen.getByRole("link", { name: /Open external chits/i })).toHaveAttribute(
    "href",
    "/external-chits",
  );
  expect(screen.getByRole("heading", { name: /Recent auction outcomes/i })).toBeInTheDocument();
  expect(screen.getByText(hasText("Winner: Member #8"))).toBeInTheDocument();
  expect(screen.getByText(hasText("Winning bid: Rs. 17,500"))).toBeInTheDocument();
});

test("shows strong empty states when the subscriber has no memberships, no live auctions, and no outcome history", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [],
    activeAuctions: [],
  });
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  expect(await screen.findByText(/No memberships yet/i)).toBeInTheDocument();
  expect(screen.getByText(/No live auctions right now/i)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Recent auction outcomes/i })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Browse external chits/i })[0]).toHaveAttribute(
    "href",
    "/external-chits",
  );
});

test("renders the become organizer action for a subscriber", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [],
    activeAuctions: [],
  });
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  expect(await screen.findByRole("button", { name: /Become Organizer/i })).toBeInTheDocument();
});

test("lets a subscriber request to join a public chit from the discovery list", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [],
    activeAuctions: [],
  });
  fetchPublicChits.mockResolvedValue([
    {
      id: 21,
      groupCode: "PUB-001",
      title: "Public Growth Chit",
      visibility: "public",
      chitValue: 500000,
      installmentAmount: 25000,
      memberCount: 20,
      cycleCount: 20,
    },
  ]);
  requestGroupMembership.mockResolvedValue({
    membershipId: 51,
    groupId: 21,
    membershipStatus: "pending",
  });

  renderDashboard();

  expect(await screen.findByText("Public Growth Chit")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Request to join/i }));

  expect(requestGroupMembership).toHaveBeenCalledWith(21);
  expect(await screen.findByText(/Membership request submitted/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Request pending/i })).toBeDisabled();
});

test("lets a subscriber search by group code and request to join a matching chit", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [],
    activeAuctions: [],
  });
  fetchPublicChits.mockResolvedValue([]);
  searchChitsByCode.mockResolvedValue([
    {
      id: 31,
      ownerId: 1,
      groupCode: "JOIN-777",
      title: "Code Search Chit",
      visibility: "private",
      chitValue: 400000,
      installmentAmount: 20000,
      memberCount: 10,
      cycleCount: 20,
    },
  ]);
  requestGroupMembership.mockResolvedValue({
    membershipId: 71,
    groupId: 31,
    membershipStatus: "pending",
  });

  renderDashboard();

  await screen.findByRole("heading", { name: /Subscriber Dashboard/i });
  await user.type(screen.getByLabelText(/Group code/i), "JOIN-777");
  await user.click(screen.getByRole("button", { name: /Search by code/i }));

  expect(searchChitsByCode).toHaveBeenCalledWith("JOIN-777");
  expect(await screen.findByText("Code Search Chit")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Request to join/i }));

  expect(requestGroupMembership).toHaveBeenCalledWith(31);
  expect(await screen.findByText(/Membership request submitted/i)).toBeInTheDocument();
});

test("shows a pending join state for a public chit that is already awaiting approval", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [
      {
        membershipId: 51,
        groupId: 21,
        groupCode: "PUB-001",
        groupTitle: "Public Growth Chit",
        memberNo: 8,
        membershipStatus: "pending",
        prizedStatus: "unprized",
        canBid: false,
        currentCycleNo: 1,
        installmentAmount: 25000,
        totalDue: 0,
        totalPaid: 0,
        outstandingAmount: 0,
        paymentStatus: "FULL",
        arrearsAmount: 0,
        nextDueAmount: 0,
        nextDueDate: null,
        auctionStatus: null,
        slotCount: 1,
        wonSlotCount: 0,
        remainingSlotCount: 1,
      },
    ],
    activeAuctions: [],
  });
  fetchPublicChits.mockResolvedValue([
    {
      id: 21,
      groupCode: "PUB-001",
      title: "Public Growth Chit",
      visibility: "public",
      chitValue: 500000,
      installmentAmount: 25000,
      memberCount: 20,
      cycleCount: 20,
    },
  ]);

  renderDashboard();

  expect(await screen.findByRole("button", { name: /Request pending/i })).toBeDisabled();
});

test("lets a subscriber accept and reject private-group invites", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard
    .mockResolvedValueOnce({
      subscriberId: 7,
      memberships: [
        {
          membershipId: 61,
          groupId: 31,
          groupCode: "PRI-001",
          groupTitle: "Private Growth Chit",
          memberNo: 5,
          membershipStatus: "invited",
          prizedStatus: "unprized",
          canBid: false,
          currentCycleNo: 1,
          installmentAmount: 18000,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          paymentStatus: "FULL",
          arrearsAmount: 0,
          nextDueAmount: 0,
          nextDueDate: null,
          auctionStatus: null,
          slotCount: 1,
          wonSlotCount: 0,
          remainingSlotCount: 1,
        },
        {
          membershipId: 62,
          groupId: 32,
          groupCode: "PRI-002",
          groupTitle: "Private Savings Chit",
          memberNo: 6,
          membershipStatus: "invited",
          prizedStatus: "unprized",
          canBid: false,
          currentCycleNo: 1,
          installmentAmount: 19000,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          paymentStatus: "FULL",
          arrearsAmount: 0,
          nextDueAmount: 0,
          nextDueDate: null,
          auctionStatus: null,
          slotCount: 1,
          wonSlotCount: 0,
          remainingSlotCount: 1,
        },
      ],
      activeAuctions: [],
    })
    .mockResolvedValueOnce({
      subscriberId: 7,
      memberships: [
        {
          membershipId: 61,
          groupId: 31,
          groupCode: "PRI-001",
          groupTitle: "Private Growth Chit",
          memberNo: 5,
          membershipStatus: "active",
          prizedStatus: "unprized",
          canBid: true,
          currentCycleNo: 1,
          installmentAmount: 18000,
          totalDue: 18000,
          totalPaid: 0,
          outstandingAmount: 18000,
          paymentStatus: "PENDING",
          arrearsAmount: 0,
          nextDueAmount: 18000,
          nextDueDate: "2026-06-01",
          auctionStatus: null,
          slotCount: 1,
          wonSlotCount: 0,
          remainingSlotCount: 1,
        },
        {
          membershipId: 62,
          groupId: 32,
          groupCode: "PRI-002",
          groupTitle: "Private Savings Chit",
          memberNo: 6,
          membershipStatus: "invited",
          prizedStatus: "unprized",
          canBid: false,
          currentCycleNo: 1,
          installmentAmount: 19000,
          totalDue: 0,
          totalPaid: 0,
          outstandingAmount: 0,
          paymentStatus: "FULL",
          arrearsAmount: 0,
          nextDueAmount: 0,
          nextDueDate: null,
          auctionStatus: null,
          slotCount: 1,
          wonSlotCount: 0,
          remainingSlotCount: 1,
        },
      ],
      activeAuctions: [],
    })
    .mockResolvedValueOnce({
      subscriberId: 7,
      memberships: [
        {
          membershipId: 61,
          groupId: 31,
          groupCode: "PRI-001",
          groupTitle: "Private Growth Chit",
          memberNo: 5,
          membershipStatus: "active",
          prizedStatus: "unprized",
          canBid: true,
          currentCycleNo: 1,
          installmentAmount: 18000,
          totalDue: 18000,
          totalPaid: 0,
          outstandingAmount: 18000,
          paymentStatus: "PENDING",
          arrearsAmount: 0,
          nextDueAmount: 18000,
          nextDueDate: "2026-06-01",
          auctionStatus: null,
          slotCount: 1,
          wonSlotCount: 0,
          remainingSlotCount: 1,
        },
      ],
      activeAuctions: [],
    });
  fetchPublicChits.mockResolvedValue([]);
  acceptGroupInvite.mockResolvedValue({
    membershipId: 61,
    membershipStatus: "active",
  });
  rejectGroupInvite.mockResolvedValue({
    membershipId: 62,
    membershipStatus: "rejected",
  });

  renderDashboard();

  expect(await screen.findByRole("heading", { name: /Private group invites/i })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Accept invite to Private Growth Chit/i }));

  expect(acceptGroupInvite).toHaveBeenCalledWith(31, 61);
  expect(await screen.findByText(/Accepted your invite for Private Growth Chit/i)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Reject invite to Private Savings Chit/i }));

  expect(rejectGroupInvite).toHaveBeenCalledWith(32, 62);
  expect(await screen.findByText(/Rejected your invite for Private Savings Chit/i)).toBeInTheDocument();
});

test("shows a pending owner request state after submit", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [],
    activeAuctions: [],
  });
  createOwnerRequest.mockResolvedValue({
    id: 41,
    status: "pending",
  });
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  await screen.findByRole("button", { name: /Become Organizer/i });
  await user.click(screen.getByRole("button", { name: /Become Organizer/i }));

  expect(createOwnerRequest).toHaveBeenCalledTimes(1);
  expect(await screen.findByText(/Organizer request submitted/i)).toBeInTheDocument();
});

test("maps non-open auction states into clearer membership status text", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockResolvedValue({
    subscriberId: 7,
    memberships: [
      {
        membershipId: 12,
        groupId: 4,
        groupCode: "APR-004",
        groupTitle: "April Prosperity Chit",
        memberNo: 8,
        membershipStatus: "active",
        prizedStatus: "unprized",
        canBid: true,
        currentCycleNo: 3,
        installmentAmount: 12000,
        totalDue: 0,
        totalPaid: 0,
        outstandingAmount: 0,
        paymentStatus: "FULL",
        arrearsAmount: 0,
        nextDueAmount: 0,
        nextDueDate: null,
        auctionStatus: "ended",
        slotCount: 1,
        wonSlotCount: 0,
        remainingSlotCount: 1,
      },
    ],
    activeAuctions: [],
    recentAuctionOutcomes: [],
  });
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  expect(await screen.findByText(/The latest auction round for this membership has ended\./i)).toBeInTheDocument();
});

test("shows a sign-in message when there is no subscriber session", () => {
  getCurrentUser.mockReturnValue(null);

  renderDashboard();

  expect(screen.getByText(/Sign in as a subscriber to load your dashboard/i)).toBeInTheDocument();
  expect(fetchSubscriberDashboard).not.toHaveBeenCalled();
});

test("shows a load failure message when the dashboard request fails", async () => {
  getCurrentUser.mockReturnValue({
    role: "subscriber",
    subscriberId: 7,
  });
  fetchSubscriberDashboard.mockRejectedValue(new Error("network"));
  fetchPublicChits.mockResolvedValue([]);

  renderDashboard();

  expect(await screen.findByText(/Unable to load your dashboard right now/i)).toBeInTheDocument();
});
