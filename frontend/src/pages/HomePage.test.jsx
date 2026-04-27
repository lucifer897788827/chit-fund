import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import HomePage from "./HomePage";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { fetchActiveAdminMessage } from "../features/admin/api";
import { fetchPublicChits } from "../features/auctions/api";
import { fetchOwnerDashboard, fetchUserDashboard } from "../features/dashboard/api";
import { fetchMyFinancialSummary } from "../features/users/api";

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  getUserRoles: jest.fn(),
  sessionHasRole: jest.fn(),
}));

jest.mock("../features/admin/api", () => ({
  fetchActiveAdminMessage: jest.fn(),
}));

jest.mock("../features/auctions/api", () => ({
  fetchPublicChits: jest.fn(),
}));

jest.mock("../features/dashboard/api", () => ({
  fetchOwnerDashboard: jest.fn(),
  fetchUserDashboard: jest.fn(),
  getOwnerDashboardFromUserDashboard: jest.fn((data) => data?.stats?.owner_dashboard ?? {}),
  getSubscriberDashboardFromUserDashboard: jest.fn((data) => data?.stats?.subscriber_dashboard ?? {}),
}));

jest.mock("../features/users/api", () => ({
  fetchMyFinancialSummary: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  getCurrentUser.mockReturnValue({ owner_id: 1, role: "chit_owner" });
  getUserRoles.mockReturnValue(["owner"]);
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchOwnerDashboard.mockResolvedValue({ groups: [], balances: [], recentAuctions: [] });
  fetchUserDashboard.mockResolvedValue({
    role: "owner",
    financial_summary: {},
    stats: {
      owner_dashboard: { groups: [], balances: [], recentAuctions: [] },
      subscriber_dashboard: { memberships: [], activeAuctions: [] },
    },
  });
  fetchActiveAdminMessage.mockResolvedValue({
    id: 5,
    message: "Collection window closes tonight",
    type: "warning",
    active: true,
  });
  fetchPublicChits.mockResolvedValue([]);
  fetchMyFinancialSummary.mockResolvedValue({});
});

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
      },
    },
  });
}

function renderHomePage(queryClient = createTestQueryClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}

test("loads the admin message from the backend and keeps dismiss behavior", async () => {
  renderHomePage();

  expect(await screen.findByText(/Collection window closes tonight/)).toBeInTheDocument();
  expect(fetchActiveAdminMessage).toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

  await waitFor(() => expect(screen.queryByText(/Collection window closes tonight/)).not.toBeInTheDocument());
  expect(window.localStorage.getItem("chit-fund-dismissed-admin-message")).toBe("Collection window closes tonight");
});

test("reuses cached dashboard data when home remounts inside the stale window", async () => {
  const queryClient = createTestQueryClient();
  const firstRender = renderHomePage(queryClient);

  expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  firstRender.unmount();

  renderHomePage(queryClient);

  expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  expect(fetchUserDashboard).toHaveBeenCalledTimes(1);
});

test("prefetches groups and profile data after home loads", async () => {
  renderHomePage();

  expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  await waitFor(() => expect(fetchPublicChits).toHaveBeenCalled());
  expect(fetchMyFinancialSummary).toHaveBeenCalled();
});
