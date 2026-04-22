import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

jest.mock("../../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
}));

jest.mock("../auth/api", () => ({
  logoutUser: jest.fn(() => Promise.resolve()),
}));

jest.mock("./api", () => ({
  fetchNotifications: jest.fn(),
  markNotificationRead: jest.fn(),
}));

import NotificationsPage from "./NotificationsPage";
import { fetchNotifications, markNotificationRead } from "./api";
import { getCurrentUser } from "../../lib/auth/store";

beforeEach(() => {
  jest.clearAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <NotificationsPage />
    </MemoryRouter>,
  );
}

test("loads notifications and marks an unread item as read", async () => {
  const user = userEvent.setup();

  getCurrentUser.mockReturnValue({
    access_token: "token-subscriber",
    role: "subscriber",
    subscriber_id: 7,
  });
  fetchNotifications.mockResolvedValueOnce([
    {
      id: 11,
      title: "Payment received",
      message: "Your installment was recorded.",
      channel: "in_app",
      status: "pending",
      createdAt: "2026-04-20T10:00:00Z",
      readAt: null,
      isRead: false,
    },
    {
      id: 12,
      title: "Auction started",
      message: "The latest round is now live.",
      channel: "in_app",
      status: "read",
      createdAt: "2026-04-19T08:00:00Z",
      readAt: "2026-04-19T09:00:00Z",
      isRead: true,
      sessionId: 55,
    },
  ]);
  fetchNotifications.mockResolvedValueOnce([
    {
      id: 11,
      title: "Payment received",
      message: "Your installment was recorded.",
      channel: "in_app",
      status: "read",
      createdAt: "2026-04-20T10:00:00Z",
      readAt: "2026-04-21T09:30:00Z",
      isRead: true,
    },
    {
      id: 12,
      title: "Auction started",
      message: "The latest round is now live.",
      channel: "in_app",
      status: "read",
      createdAt: "2026-04-19T08:00:00Z",
      readAt: "2026-04-19T09:00:00Z",
      isRead: true,
      sessionId: 55,
    },
  ]);
  markNotificationRead.mockResolvedValueOnce({
    id: 11,
    title: "Payment received",
    message: "Your installment was recorded.",
    channel: "in_app",
    status: "read",
    createdAt: "2026-04-20T10:00:00Z",
    readAt: "2026-04-21T09:30:00Z",
    isRead: true,
  });

  renderPage();

  expect(await screen.findByRole("heading", { name: /Notifications/i })).toBeInTheDocument();
  expect(fetchNotifications).toHaveBeenCalledTimes(1);
  expect(await screen.findByRole("button", { name: /Mark read/i })).toBeInTheDocument();
  expect(screen.getByText("Payment received")).toBeInTheDocument();
  expect(screen.getAllByText("Auction started").length).toBeGreaterThan(1);
  expect(screen.getByText("Payment recorded")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open payments/i })).toHaveAttribute("href", "/subscriber#payments");
  expect(screen.getByRole("link", { name: /Open auction/i })).toHaveAttribute("href", "/auctions/55");

  await user.click(screen.getByRole("button", { name: /Mark read/i }));

  await waitFor(() => {
    expect(markNotificationRead).toHaveBeenCalledWith(11);
  });

  expect(await screen.findByText(/Notification marked as read/i)).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /Marked read/i })).toHaveLength(2);
});

test("shows a sign-in prompt when there is no session", async () => {
  getCurrentUser.mockReturnValue(null);

  renderPage();

  expect(await screen.findByText(/Sign in to view your notifications/i)).toBeInTheDocument();
  expect(fetchNotifications).not.toHaveBeenCalled();
});
