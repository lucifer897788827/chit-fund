import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AdminGroupsPage from "./AdminGroupsPage";
import AdminPaymentsPage from "./AdminPaymentsPage";
import UsersPage from "./UsersPage";
import { fetchAdminGroups, fetchAdminPayments, fetchAdminUsers } from "../../features/admin/api";

jest.mock("../../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../../features/admin/api", () => ({
  fetchActiveAdminMessage: jest.fn(),
  fetchAdminAuctions: jest.fn(),
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

function renderAdminPage(route, element, path) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("UsersPage lets admins refine the directory by role", async () => {
  const user = userEvent.setup();

  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 1, role: "subscriber", phone: "9999999999", totalChits: 1, paymentScore: 80, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 2, role: "owner", phone: "7777777777", totalChits: 4, paymentScore: 60, createdAt: "2026-04-02T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });

  renderAdminPage("/admin/users", <UsersPage />, "/admin/users");

  expect(await screen.findByText("9999999999")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Role"), "owner");

  expect(await screen.findByText("7777777777")).toBeInTheDocument();
  expect(fetchAdminUsers).toHaveBeenLastCalledWith({ page: 1, limit: 20, role: "owner" });
});

test("UsersPage lets admins refine the directory by payment score range", async () => {
  const user = userEvent.setup();

  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 1, role: "subscriber", phone: "9999999999", totalChits: 1, paymentScore: 45, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 2, role: "owner", phone: "7777777777", totalChits: 4, paymentScore: 90, createdAt: "2026-04-02T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });

  renderAdminPage("/admin/users", <UsersPage />, "/admin/users");

  expect(await screen.findByText("9999999999")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Payment score"), "high");

  expect(await screen.findByText("7777777777")).toBeInTheDocument();
  expect(fetchAdminUsers).toHaveBeenLastCalledWith({ page: 1, limit: 20, scoreRange: "high" });
});

test("AdminGroupsPage lets admins filter by group status", async () => {
  const user = userEvent.setup();

  fetchAdminGroups
    .mockResolvedValueOnce([
      { id: 1, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 },
    ])
    .mockResolvedValueOnce([
      { id: 2, name: "Beta Group", status: "completed", owner: "Owner Two", membersCount: 18, monthlyAmount: 7000 },
    ]);

  renderAdminPage("/admin/groups", <AdminGroupsPage />, "/admin/groups");

  expect(await screen.findByText("Alpha Group")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Status"), "completed");

  expect(await screen.findByText("Beta Group")).toBeInTheDocument();
  expect(fetchAdminGroups).toHaveBeenLastCalledWith({ status: "completed" });
});

test("AdminPaymentsPage lets admins filter by payment status", async () => {
  const user = userEvent.setup();

  fetchAdminPayments
    .mockResolvedValueOnce([
      { id: 1, user: "Subscriber One", group: "Alpha Group", amount: 9000, status: "paid" },
    ])
    .mockResolvedValueOnce([
      { id: 2, user: "Subscriber Two", group: "Beta Group", amount: 9500, status: "pending" },
    ]);

  renderAdminPage("/admin/payments", <AdminPaymentsPage />, "/admin/payments");

  expect(await screen.findByText("Subscriber One")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Status"), "pending");

  expect(await screen.findByText("Subscriber Two")).toBeInTheDocument();
  expect(fetchAdminPayments).toHaveBeenLastCalledWith({ status: "pending" });
});
