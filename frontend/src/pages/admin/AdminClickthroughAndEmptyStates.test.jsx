import { render, screen } from "@testing-library/react";
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

test("UsersPage makes the user name a direct click-through to the profile view", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
    page: 1,
    pageSize: 20,
    totalCount: 1,
    totalPages: 1,
  });

  renderAdminPage("/admin/users", <UsersPage />, "/admin/users");

  const userLink = await screen.findByRole("link", { name: "Owner Four" });
  expect(userLink).toHaveAttribute("href", "/admin/users/4");
});

test("AdminGroupsPage makes each group name a direct click-through to group detail", async () => {
  fetchAdminGroups.mockResolvedValue([
    { id: 11, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 },
  ]);

  renderAdminPage("/admin/groups", <AdminGroupsPage />, "/admin/groups");

  const groupLink = await screen.findByRole("link", { name: "Alpha Group" });
  expect(groupLink).toHaveAttribute("href", "/admin/groups/11");
});

test("AdminPaymentsPage links the group column into the related group detail flow", async () => {
  fetchAdminPayments.mockResolvedValue([
    { id: 31, user: "Subscriber One", group: "Alpha Group", groupId: 11, amount: 9000, status: "paid" },
  ]);

  renderAdminPage("/admin/payments", <AdminPaymentsPage />, "/admin/payments");

  const groupLink = await screen.findByRole("link", { name: "Alpha Group" });
  expect(groupLink).toHaveAttribute("href", "/admin/groups/11");
});

test("UsersPage shows a precise empty state when no users match", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [],
    page: 1,
    pageSize: 20,
    totalCount: 0,
    totalPages: 0,
  });

  renderAdminPage("/admin/users", <UsersPage />, "/admin/users");

  expect(await screen.findByText("No users found")).toBeInTheDocument();
});

test("AdminPaymentsPage shows a precise empty state when no payments match", async () => {
  fetchAdminPayments.mockResolvedValue([]);

  renderAdminPage("/admin/payments", <AdminPaymentsPage />, "/admin/payments");

  expect(await screen.findByText("No payments")).toBeInTheDocument();
});
