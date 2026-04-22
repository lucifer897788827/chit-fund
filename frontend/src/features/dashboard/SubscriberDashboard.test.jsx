import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

jest.mock("./api", () => ({
  fetchSubscriberDashboard: jest.fn(),
}));

jest.mock("../../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
}));

jest.mock("../auth/api", () => ({
  logoutUser: jest.fn(() => Promise.resolve()),
}));

import SubscriberDashboard from "./SubscriberDashboard";
import { fetchSubscriberDashboard } from "./api";
import { getCurrentUser } from "../../lib/auth/store";

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

  renderDashboard();

  expect(await screen.findByText(/No memberships yet/i)).toBeInTheDocument();
  expect(screen.getByText(/No live auctions right now/i)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Recent auction outcomes/i })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Browse external chits/i })[0]).toHaveAttribute(
    "href",
    "/external-chits",
  );
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

  renderDashboard();

  expect(await screen.findByText(/Unable to load your dashboard right now/i)).toBeInTheDocument();
});
