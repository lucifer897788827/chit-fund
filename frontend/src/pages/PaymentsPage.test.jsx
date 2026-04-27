import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import PaymentsPage from "./PaymentsPage";
import { fetchUserDashboard } from "../features/dashboard/api";
import { fetchPayments } from "../features/payments/api";
import { getCurrentUser, sessionHasRole } from "../lib/auth/store";

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  sessionHasRole: jest.fn(),
}));

jest.mock("../features/dashboard/api", () => ({
  fetchUserDashboard: jest.fn(),
  getOwnerDashboardFromUserDashboard: jest.fn((data) => data?.stats?.owner_dashboard ?? {}),
  getSubscriberDashboardFromUserDashboard: jest.fn((data) => data?.stats?.subscriber_dashboard ?? {}),
}));

jest.mock("../features/payments/api", () => ({
  fetchPayments: jest.fn(),
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

function renderPaymentsPage(queryClient = createTestQueryClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PaymentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}

beforeEach(() => {
  jest.clearAllMocks();
  getCurrentUser.mockReturnValue({ role: "chit_owner", owner_id: 4 });
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchPayments.mockResolvedValue([{ id: 5, groupId: 42, groupCode: "APR-42", paymentDate: "2026-04-01", amount: 1200 }]);
  fetchUserDashboard.mockResolvedValue({
    role: "owner",
    stats: {
      owner_dashboard: {
        balances: [],
      },
    },
  });
});

test("reuses cached payments and dashboard data on remount", async () => {
  const queryClient = createTestQueryClient();
  const firstRender = renderPaymentsPage(queryClient);

  expect(await screen.findByRole("heading", { name: "Payments" })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "APR-42" })).toBeInTheDocument();
  firstRender.unmount();

  renderPaymentsPage(queryClient);

  expect(await screen.findByRole("link", { name: "APR-42" })).toBeInTheDocument();
  expect(fetchPayments).toHaveBeenCalledTimes(1);
  expect(fetchUserDashboard).toHaveBeenCalledTimes(1);
});
