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
  const queryClient = createTestQueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function expectPageLabel(page, totalPages) {
  expect(
    screen.getByText((_content, element) => element?.textContent === `Page ${page} of ${totalPages}`),
  ).toBeInTheDocument();
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("UsersPage reads page and limit from the URL for admin directory requests", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [{ id: 2, role: "subscriber", phone: "8888888888", totalChits: 1, paymentScore: 75, createdAt: "2026-04-01T10:00:00Z" }],
    page: 2,
    pageSize: 1,
    totalCount: 3,
    totalPages: 3,
  });

  renderAdminPage("/admin/users?page=2&limit=1", <UsersPage />, "/admin/users");

  expect(await screen.findByText("8888888888")).toBeInTheDocument();
  expect(fetchAdminUsers).toHaveBeenCalledWith({ page: 2, limit: 1 });
  expectPageLabel(2, 3);
});

test("AdminGroupsPage paginates the fetched group list from the URL state", async () => {
  fetchAdminGroups.mockResolvedValue([
    { id: 1, name: "Alpha Group", status: "active", owner: "Owner One", membersCount: 20, monthlyAmount: 5000 },
    { id: 2, name: "Beta Group", status: "completed", owner: "Owner Two", membersCount: 15, monthlyAmount: 7000 },
    { id: 3, name: "Gamma Group", status: "active", owner: "Owner Three", membersCount: 10, monthlyAmount: 9000 },
  ]);

  renderAdminPage("/admin/groups?page=2&limit=1", <AdminGroupsPage />, "/admin/groups");

  expect(await screen.findByText("Beta Group")).toBeInTheDocument();
  expect(screen.queryByText("Alpha Group")).not.toBeInTheDocument();
  expect(screen.queryByText("Gamma Group")).not.toBeInTheDocument();
  expectPageLabel(2, 3);
});

test("AdminPaymentsPage updates the visible slice when the next page control is used", async () => {
  const user = userEvent.setup();

  fetchAdminPayments.mockResolvedValue([
    { id: 1, user: "Subscriber One", group: "Alpha Group", amount: 9000, status: "paid" },
    { id: 2, user: "Subscriber Two", group: "Beta Group", amount: 9500, status: "pending" },
  ]);

  renderAdminPage("/admin/payments?page=1&limit=1", <AdminPaymentsPage />, "/admin/payments");

  expect(await screen.findByText("Subscriber One")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /next page/i }));

  expect(await screen.findByText("Subscriber Two")).toBeInTheDocument();
  expect(screen.queryByText("Subscriber One")).not.toBeInTheDocument();
  expectPageLabel(2, 2);
});
