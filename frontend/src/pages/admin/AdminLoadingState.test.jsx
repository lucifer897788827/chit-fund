import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AdminGroupsPage from "./AdminGroupsPage";
import UsersPage from "./UsersPage";
import { fetchAdminGroups, fetchAdminUsers } from "../../features/admin/api";

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

function renderAdminPage(route, element, path, queryClient = createTestQueryClient()) {
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

function createDeferred() {
  let resolve;
  const promise = new Promise((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("UsersPage keeps the current rows visible while the next page is loading", async () => {
  const user = userEvent.setup();
  const nextPageRequest = createDeferred();

  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 1, role: "subscriber", name: "Subscriber One", isActive: true, phone: "9999999999", totalChits: 1, paymentScore: 80, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 1,
      totalCount: 2,
      totalPages: 2,
    })
    .mockImplementationOnce(() => nextPageRequest.promise);

  renderAdminPage("/admin/users?page=1&limit=1", <UsersPage />, "/admin/users");

  expect(await screen.findByText("Subscriber One")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next page" }));

  expect(screen.getByText("Subscriber One")).toBeInTheDocument();
  expect(screen.getByText("Updating results...")).toBeInTheDocument();

  nextPageRequest.resolve({
    items: [{ id: 2, role: "owner", name: "Owner Two", isActive: true, phone: "7777777777", totalChits: 3, paymentScore: 65, createdAt: "2026-04-02T10:00:00Z" }],
    page: 2,
    pageSize: 1,
    totalCount: 2,
    totalPages: 2,
  });

  expect(await screen.findByText("Owner Two")).toBeInTheDocument();
});

test("AdminGroupsPage renders a loading skeleton that matches table workflows", async () => {
  fetchAdminGroups.mockImplementation(() => new Promise(() => {}));

  const { container } = renderAdminPage("/admin/groups", <AdminGroupsPage />, "/admin/groups");

  expect(await screen.findByLabelText("Loading groups...")).toBeInTheDocument();
  expect(container.querySelectorAll(".skeleton-card").length).toBeGreaterThan(0);
});
