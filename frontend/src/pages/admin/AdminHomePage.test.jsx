import { render, screen, within } from "@testing-library/react";
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
    defaultersCount: 3,
    defaulters: [
      {
        userId: 42,
        name: "Subscriber One",
        phone: "9999999999",
        pendingPaymentsCount: 3,
        pendingAmount: 27000,
      },
      {
        userId: 43,
        name: "Subscriber Two",
        phone: "8888888888",
        pendingPaymentsCount: 2,
        pendingAmount: 18000,
      },
    ],
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
  expect(screen.getByText("Defaulters")).toBeInTheDocument();
  expect(screen.getByText("Defaulters requiring action")).toBeInTheDocument();
  const reviewLink = screen.getByRole("link", { name: /review subscriber one/i });
  const riskCard = reviewLink.closest("div.rounded-2xl");
  expect(within(riskCard).getByText("Subscriber One")).toBeInTheDocument();
  expect(within(riskCard).getByText("9999999999")).toBeInTheDocument();
  expect(riskCard).toHaveTextContent("Rs. 27,000");
  expect(reviewLink).toHaveAttribute("href", "/admin/users/42");
  expect(screen.getByRole("link", { name: "Users" })).toHaveAttribute("href", "/admin/users");
  expect(screen.getByRole("link", { name: "Payments" })).toHaveAttribute("href", "/admin/payments");
});
