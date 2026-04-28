import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import ProfilePage from "./ProfilePage";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
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

jest.mock("../features/auth/api", () => ({
  logoutUser: jest.fn(),
}));

jest.mock("../features/owner-requests/api", () => ({
  createOwnerRequest: jest.fn(),
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
  getCurrentUser.mockReturnValue({
    user: {
      id: 1,
      name: "Owner One",
      phone: "9999999999",
      email: "owner@example.com",
    },
    owner_id: 1,
    role: "chit_owner",
  });
  getUserRoles.mockReturnValue(["owner"]);
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchUserDashboard.mockResolvedValue({
    role: "owner",
    financial_summary: {},
    stats: {
      owner_dashboard: {
        totalPaidAmount: 1000,
        recentPayouts: [],
      },
      subscriber_dashboard: {
        memberships: [
          {
            groupId: 42,
            installmentAmount: 5000,
            slotCount: 1,
            membershipStatus: "active",
            wonSlotCount: 1,
            prizedStatus: "prized",
          },
        ],
      },
    },
  });
  fetchOwnerDashboard.mockResolvedValue({ totalPaidAmount: 1000, recentPayouts: [] });
  fetchMyFinancialSummary.mockResolvedValue({
    total_paid: 1000,
    total_received: 4000,
    dividend: 100,
    net: 3100,
  });
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

function renderProfilePage(queryClient = createTestQueryClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <ProfilePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}

test("uses backend financial summary instead of approximate local totals", async () => {
  renderProfilePage();

  await waitFor(() => expect(fetchMyFinancialSummary).toHaveBeenCalled());
  const totalPaidCard = (await screen.findAllByText("Total paid"))[0].closest("article");
  const totalDividendCard = screen.getByText("Total dividend").closest("article");
  const totalReceivedCard = screen.getByText("Total received").closest("article");
  const netProfitCard = screen.getByText("Net profit").closest("article");

  expect(within(totalPaidCard).getByText("Rs. 1,000")).toBeInTheDocument();
  expect(within(totalDividendCard).getByText("Rs. 100")).toBeInTheDocument();
  expect(within(totalReceivedCard).getByText("Rs. 4,000")).toBeInTheDocument();
  expect(within(netProfitCard).getByText("Rs. 3,100")).toBeInTheDocument();
  expect(screen.queryByText("Approximate calculation")).not.toBeInTheDocument();
});

test("prefers dashboard net position and uses positive tone when provided", async () => {
  fetchUserDashboard.mockResolvedValueOnce({
    role: "owner",
    financial_summary: {
      total_paid: 1500,
      total_received: 4100,
      dividend: 100,
      net: 2700,
      netPosition: 900,
    },
    stats: {
      owner_dashboard: {
        totalPaidAmount: 1000,
        recentPayouts: [],
      },
      subscriber_dashboard: {
        memberships: [],
      },
    },
  });
  fetchMyFinancialSummary.mockResolvedValueOnce({
    total_paid: 1000,
    total_received: 4000,
    dividend: 100,
    net: 3100,
    netPosition: -300,
  });

  renderProfilePage();

  const netPositionCard = (await screen.findAllByText("Net position"))[0].closest("article");
  const metricValue = within(netPositionCard).getByText("Rs. 900");
  expect(metricValue).toHaveClass("text-emerald-700");
});

test("shows negative net position in red when the dashboard reports a loss", async () => {
  fetchUserDashboard.mockResolvedValueOnce({
    role: "owner",
    financial_summary: {
      total_paid: 1500,
      total_received: 1000,
      dividend: 0,
      net: -500,
      netPosition: -500,
    },
    stats: {
      owner_dashboard: {
        totalPaidAmount: 1500,
        recentPayouts: [],
      },
      subscriber_dashboard: {
        memberships: [],
      },
    },
  });
  fetchMyFinancialSummary.mockResolvedValueOnce({
    total_paid: 1500,
    total_received: 1000,
    dividend: 0,
    net: -500,
    netPosition: -500,
  });

  renderProfilePage();

  const netPositionCard = (await screen.findAllByText("Net position"))[0].closest("article");
  const metricValue = within(netPositionCard).getByText("Rs. -500");
  expect(metricValue).toHaveClass("text-red-700");
});

test("shows zero net position with neutral tone when neither source provides a signed value", async () => {
  fetchUserDashboard.mockResolvedValueOnce({
    role: "owner",
    financial_summary: {
      total_paid: 1000,
      total_received: 1000,
      dividend: 0,
      net: 0,
    },
    stats: {
      owner_dashboard: {
        totalPaidAmount: 1000,
        recentPayouts: [],
      },
      subscriber_dashboard: {
        memberships: [],
      },
    },
  });
  fetchMyFinancialSummary.mockResolvedValueOnce({
    total_paid: 1000,
    total_received: 1000,
    dividend: 0,
    net: 0,
  });

  renderProfilePage();

  const netPositionCard = (await screen.findAllByText("Net position"))[0].closest("article");
  const metricValue = within(netPositionCard).getByText("Rs. 0");
  expect(metricValue).toHaveClass("text-slate-700");
});

test("reuses cached profile dashboard and financial summary on remount", async () => {
  const queryClient = createTestQueryClient();
  const firstRender = renderProfilePage(queryClient);

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  firstRender.unmount();

  renderProfilePage(queryClient);

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  expect(fetchUserDashboard).toHaveBeenCalledTimes(1);
  expect(fetchMyFinancialSummary).toHaveBeenCalledTimes(1);
});
