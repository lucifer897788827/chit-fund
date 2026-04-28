import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import AdminHomePage from "./AdminHomePage";
import { fetchAdminDashboardOverview } from "../../features/admin/api";

jest.mock("../../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../../features/admin/api", () => ({
  fetchActiveAdminMessage: jest.fn(),
  fetchAdminAuctions: jest.fn(),
  fetchAdminDashboardOverview: jest.fn(),
  fetchAdminGroups: jest.fn(),
  fetchAdminPayments: jest.fn(),
  fetchAdminUser: jest.fn(),
  fetchAdminUsers: jest.fn(),
}));

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

beforeEach(() => {
  jest.clearAllMocks();
});

test("AdminHomePage surfaces high-signal overview cards and quick links", async () => {
  fetchAdminDashboardOverview.mockResolvedValue({
    totalUsers: 120,
    activeGroups: 18,
    pendingPayments: 7,
    todayAuctions: 3,
  });

  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AdminHomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("120")).toBeInTheDocument();
  expect(screen.getByText("Total users")).toBeInTheDocument();
  expect(screen.getByText("Active groups")).toBeInTheDocument();
  expect(screen.getByText("Pending payments")).toBeInTheDocument();
  expect(screen.getByText("Today auctions")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Users" })).toHaveAttribute("href", "/admin/users");
  expect(screen.getByRole("link", { name: "Payments" })).toHaveAttribute("href", "/admin/payments");
});
