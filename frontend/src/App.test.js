import { render, screen } from "@testing-library/react";

import App from "./App";
import { saveSession } from "./lib/auth/store";

beforeEach(() => {
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
  window.history.pushState({}, "", "/");
});

jest.mock("./features/auctions/api", () => ({
  acceptGroupInvite: jest.fn(),
  approveGroupMembershipRequest: jest.fn(),
  createGroup: jest.fn(),
  createAuctionSession: jest.fn(),
  fetchAuctionRoom: jest.fn(),
  fetchGroups: jest.fn(),
  fetchOwnerMembershipRequests: jest.fn(() => Promise.resolve([])),
  fetchPublicChits: jest.fn(() => Promise.resolve([])),
  inviteSubscriberToGroup: jest.fn(),
  rejectGroupInvite: jest.fn(),
  rejectGroupMembershipRequest: jest.fn(),
  requestGroupMembership: jest.fn(),
  searchChitsByCode: jest.fn(() => Promise.resolve([])),
  submitBid: jest.fn(),
}));

jest.mock("./features/auth/api", () => ({
  confirmPasswordReset: jest.fn(),
  fetchCurrentUser: jest.fn(() => Promise.resolve({})),
  loginUser: jest.fn(),
  logoutUser: jest.fn(() => Promise.resolve()),
  refreshSession: jest.fn(),
  requestPasswordReset: jest.fn(),
  signupUser: jest.fn(),
}));

jest.mock("./features/auctions/AuctionRoomPage", () => {
  const React = require("react");

  const AuctionRoomPage = jest.fn(() =>
    React.createElement(
      React.Fragment,
      null,
      React.createElement("h1", null, "Live Auction"),
      React.createElement("p", null, "Session 5"),
      React.createElement("p", null, "Open"),
    ));

  return {
    __esModule: true,
    default: AuctionRoomPage,
  };
});

jest.mock("./features/external-chits/api", () => ({
  createExternalChit: jest.fn(),
  deleteExternalChit: jest.fn(),
  fetchExternalChitDetails: jest.fn(),
  fetchExternalChits: jest.fn(),
  updateExternalChit: jest.fn(),
}));

jest.mock("./features/notifications/api", () => ({
  fetchNotifications: jest.fn(() => Promise.resolve([])),
  markNotificationRead: jest.fn(),
}));

jest.mock("./features/dashboard/api", () => ({
  fetchOwnerAuditLogs: jest.fn(() => Promise.resolve([])),
  fetchOwnerDashboard: jest.fn(() =>
    Promise.resolve({
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
    }),
  ),
  fetchSubscriberDashboard: jest.fn(() =>
    Promise.resolve({
      memberships: [],
      activeAuctions: [],
      recentAuctionOutcomes: [],
    }),
  ),
}));

jest.mock("./features/payments/api", () => ({
  fetchPaymentBalances: jest.fn(() => Promise.resolve([])),
  fetchPayments: jest.fn(() => Promise.resolve([])),
  fetchOwnerPayouts: jest.fn(() => Promise.resolve([])),
  recordPayment: jest.fn(),
  settleOwnerPayout: jest.fn(),
}));

jest.mock("./features/subscribers/api", () => ({
  createSubscriber: jest.fn(),
  deactivateSubscriber: jest.fn(),
  fetchSubscribers: jest.fn(() => Promise.resolve([])),
  updateSubscriber: jest.fn(),
}));

beforeEach(() => {
  const { fetchPaymentBalances, fetchPayments } = require("./features/payments/api");
  const { fetchSubscribers } = require("./features/subscribers/api");
  const { fetchNotifications } = require("./features/notifications/api");
  const { fetchCurrentUser } = require("./features/auth/api");
  fetchPaymentBalances.mockResolvedValue([]);
  fetchPayments.mockResolvedValue([]);
  fetchSubscribers.mockResolvedValue([]);
  fetchNotifications.mockResolvedValue([]);
  fetchCurrentUser.mockResolvedValue({});
});

test("renders login route shell", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /Sign In/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Create an account/i })).toHaveAttribute("href", "/signup");
  expect(screen.getByRole("link", { name: /Forgot password\?/i })).toHaveAttribute(
    "href",
    "/reset-password",
  );
});

test("renders the signup route shell", async () => {
  window.history.pushState({}, "", "/signup");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Create your account/i })).toBeInTheDocument();
});

test("renders the reset-password route shell", async () => {
  window.history.pushState({}, "", "/reset-password");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Reset your password/i })).toBeInTheDocument();
});

test("redirects unauthenticated users away from the owner route", async () => {
  window.history.pushState({}, "", "/owner");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Sign In/i })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Owner Dashboard/i })).not.toBeInTheDocument();
});

test("allows an owner session to reach the owner route", async () => {
  const { fetchGroups } = require("./features/auctions/api");
  fetchGroups.mockResolvedValue([]);
  saveSession({
    access_token: "token-owner",
    role: "chit_owner",
    ownerId: 4,
    has_subscriber_profile: false,
  });
  window.history.pushState({}, "", "/owner");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Owner Dashboard/i })).toBeInTheDocument();
});

test("blocks an owner-only session from the subscriber route", async () => {
  saveSession({
    access_token: "token-owner",
    role: "chit_owner",
    owner_id: 4,
    has_subscriber_profile: false,
  });
  window.history.pushState({}, "", "/subscriber");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Sign In/i })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /My Managed Chits/i })).not.toBeInTheDocument();
});

test("renders the notifications route for a signed-in user", async () => {
  saveSession({
    access_token: "token-subscriber",
    role: "subscriber",
    subscriber_id: 7,
    has_subscriber_profile: true,
  });
  window.history.pushState({}, "", "/notifications");

  render(<App />);

  expect(await screen.findByRole("heading", { name: /Notifications/i })).toBeInTheDocument();
});
