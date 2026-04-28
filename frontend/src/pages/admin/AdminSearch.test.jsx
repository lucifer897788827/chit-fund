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

test("UsersPage applies a phone or name search from the admin toolbar", async () => {
  const user = userEvent.setup();

  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 1, role: "subscriber", name: "Subscriber One", isActive: true, phone: "9999999999", totalChits: 1, paymentScore: 80, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 2, role: "owner", name: "Owner Search", isActive: true, phone: "7777777777", totalChits: 4, paymentScore: 60, createdAt: "2026-04-02T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });

  renderAdminPage("/admin/users", <UsersPage />, "/admin/users");

  expect(await screen.findByText("Subscriber One")).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Search"));
  await user.type(screen.getByLabelText("Search"), "owner");
  await user.click(screen.getByRole("button", { name: "Apply search" }));

  expect(await screen.findByText("Owner Search")).toBeInTheDocument();
  expect(fetchAdminUsers).toHaveBeenLastCalledWith({ page: 1, limit: 20, search: "owner" });
});

test("AdminGroupsPage applies a name search from the admin toolbar", async () => {
  const user = userEvent.setup();

  fetchAdminGroups
    .mockResolvedValueOnce([
      { id: 1, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 },
    ])
    .mockResolvedValueOnce([
      { id: 2, name: "Searchable Group", status: "active", owner: "Owner Search", membersCount: 18, monthlyAmount: 7000 },
    ]);

  renderAdminPage("/admin/groups", <AdminGroupsPage />, "/admin/groups");

  expect(await screen.findByText("Alpha Group")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Search"), "search");
  await user.click(screen.getByRole("button", { name: "Apply search" }));

  expect(await screen.findByText("Searchable Group")).toBeInTheDocument();
  expect(fetchAdminGroups).toHaveBeenLastCalledWith({ search: "search" });
});

test("AdminPaymentsPage applies a phone or name search from the admin toolbar", async () => {
  const user = userEvent.setup();

  fetchAdminPayments
    .mockResolvedValueOnce([
      { id: 1, user: "Subscriber One", group: "Alpha Group", amount: 9000, status: "paid" },
    ])
    .mockResolvedValueOnce([
      { id: 2, user: "Subscriber Search", group: "Beta Group", amount: 9500, status: "pending" },
    ]);

  renderAdminPage("/admin/payments", <AdminPaymentsPage />, "/admin/payments");

  expect(await screen.findByText("Subscriber One")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Search"), "search");
  await user.click(screen.getByRole("button", { name: "Apply search" }));

  expect(await screen.findByText("Subscriber Search")).toBeInTheDocument();
  expect(fetchAdminPayments).toHaveBeenLastCalledWith({ search: "search" });
});
