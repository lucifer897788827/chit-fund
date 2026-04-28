import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import UsersPage from "./UsersPage";
import { activateAdminUser, bulkDeactivateAdminUsers, deactivateAdminUser, fetchAdminUsers } from "../../features/admin/api";

jest.mock("../../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../../features/admin/api", () => ({
  activateAdminUser: jest.fn(),
  bulkDeactivateAdminUsers: jest.fn(),
  deactivateAdminUser: jest.fn(),
  fetchActiveAdminMessage: jest.fn(),
  fetchAdminAuctions: jest.fn(),
  fetchAdminGroups: jest.fn(),
  fetchAdminPayments: jest.fn(),
  fetchAdminUser: jest.fn(),
  fetchAdminUsers: jest.fn(),
}));

jest.mock("../../lib/auth/store", () => ({
  getCurrentUser: jest.fn(() => ({ user: { id: 99 }, role: "admin" })),
}));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function renderAdminPage(route = "/admin/users") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={[route]}>
        <Routes>
          <Route path="/admin/users" element={<UsersPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function getBadgeByText(label) {
  return screen.getAllByText(label).find((element) => element.tagName.toLowerCase() === "span");
}

function getPaymentScoreBadge(score) {
  return screen.getByLabelText(`Payment score: ${score} / 100`);
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("UsersPage deactivates one non-admin user from the action column", async () => {
  const user = userEvent.setup();
  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 4, role: "owner", name: "Owner Four", isActive: false, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });
  deactivateAdminUser.mockResolvedValue({ id: 4, isActive: false });

  renderAdminPage();

  await user.click(await screen.findByRole("button", { name: "Deactivate" }));
  expect(await screen.findByRole("heading", { name: "Deactivate user?" })).toBeInTheDocument();
  expect(
    screen.getByText("Owner Four will stay visible in admin records but will not be able to sign in until reactivated."),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Deactivate user" }));

  await waitFor(() => {
    expect(deactivateAdminUser).toHaveBeenCalledWith(4);
  });
  expect(await screen.findByText("Owner Four deactivated.")).toBeInTheDocument();
});

test("UsersPage activates one inactive non-admin user from the action column", async () => {
  const user = userEvent.setup();
  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 4, role: "owner", name: "Owner Four", isActive: false, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });
  activateAdminUser.mockResolvedValue({ id: 4, isActive: true });

  renderAdminPage();

  await user.click(await screen.findByRole("button", { name: "Activate" }));
  expect(await screen.findByRole("heading", { name: "Activate user?" })).toBeInTheDocument();
  expect(
    screen.getByText("Owner Four will regain access to sign in and any linked owner/subscriber profile will be reactivated."),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Activate user" }));

  await waitFor(() => {
    expect(activateAdminUser).toHaveBeenCalledWith(4);
  });
  expect(await screen.findByText("Owner Four activated.")).toBeInTheDocument();
});

test("UsersPage sends selected eligible users through the bulk deactivate action", async () => {
  const user = userEvent.setup();
  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [
        { id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" },
        { id: 5, role: "subscriber", name: "Subscriber Five", isActive: true, phone: "7777777775", totalChits: 1, paymentScore: 90, createdAt: "2026-04-02T10:00:00Z" },
      ],
      page: 1,
      pageSize: 20,
      totalCount: 2,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [
        { id: 4, role: "owner", name: "Owner Four", isActive: false, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" },
        { id: 5, role: "subscriber", name: "Subscriber Five", isActive: false, phone: "7777777775", totalChits: 1, paymentScore: 90, createdAt: "2026-04-02T10:00:00Z" },
      ],
      page: 1,
      pageSize: 20,
      totalCount: 2,
      totalPages: 1,
    });
  bulkDeactivateAdminUsers.mockResolvedValue({ deactivatedUserIds: [4, 5], count: 2 });

  renderAdminPage();

  await user.click(await screen.findByLabelText("Select user Owner Four"));
  await user.click(screen.getByLabelText("Select user Subscriber Five"));
  await user.click(screen.getByRole("button", { name: "Deactivate selected" }));
  expect(await screen.findByRole("heading", { name: "Deactivate selected users?" })).toBeInTheDocument();
  expect(
    screen.getByText("2 selected users will stay visible in admin records but will not be able to sign in until reactivated."),
  ).toBeInTheDocument();
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Deactivate selected" }));

  await waitFor(() => {
    expect(bulkDeactivateAdminUsers).toHaveBeenCalledWith([4, 5], expect.any(Object));
  });
  expect(await screen.findByText("2 users deactivated.")).toBeInTheDocument();
});

test("UsersPage lets admins cancel the modal without firing a mutation", async () => {
  const user = userEvent.setup();
  fetchAdminUsers.mockResolvedValue({
    items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
    page: 1,
    pageSize: 20,
    totalCount: 1,
    totalPages: 1,
  });

  renderAdminPage();

  await user.click(await screen.findByRole("button", { name: "Deactivate" }));
  expect(await screen.findByRole("heading", { name: "Deactivate user?" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Cancel" }));

  await waitFor(() => {
    expect(screen.queryByRole("heading", { name: "Deactivate user?" })).not.toBeInTheDocument();
  });
  expect(deactivateAdminUser).not.toHaveBeenCalled();
});

test("UsersPage clears selected users when filters move the list to a different eligible set", async () => {
  const user = userEvent.setup();
  fetchAdminUsers
    .mockResolvedValueOnce({
      items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    })
    .mockResolvedValueOnce({
      items: [{ id: 5, role: "subscriber", name: "Inactive Five", isActive: false, phone: "7777777775", totalChits: 1, paymentScore: 30, createdAt: "2026-04-02T10:00:00Z" }],
      page: 1,
      pageSize: 20,
      totalCount: 1,
      totalPages: 1,
    });

  renderAdminPage();

  const ownerCheckbox = await screen.findByLabelText("Select user Owner Four");
  await user.click(ownerCheckbox);
  await waitFor(() => {
    expect(ownerCheckbox).toBeChecked();
  });

  await user.selectOptions(screen.getByLabelText("Activity"), "inactive");

  expect(await screen.findByText("Inactive Five")).toBeInTheDocument();
  expect(screen.queryByText("1 user selected")).not.toBeInTheDocument();
});

test("UsersPage keeps the confirmation modal open and shows an error when deactivation fails", async () => {
  const user = userEvent.setup();
  fetchAdminUsers.mockResolvedValue({
    items: [{ id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" }],
    page: 1,
    pageSize: 20,
    totalCount: 1,
    totalPages: 1,
  });
  deactivateAdminUser.mockRejectedValue(new Error("boom"));

  renderAdminPage();

  await user.click(await screen.findByRole("button", { name: "Deactivate" }));
  await user.click(screen.getByRole("button", { name: "Deactivate user" }));

  expect(await screen.findByRole("heading", { name: "Deactivate user?" })).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});

test("UsersPage keeps admin rows protected from selection and deactivation", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [
      { id: 99, role: "admin", name: "Current Admin", isActive: true, phone: "7000000001", totalChits: 0, paymentScore: 0, createdAt: "2026-04-01T10:00:00Z" },
      { id: 100, role: "admin", name: "Another Admin", isActive: true, phone: "7000000002", totalChits: 0, paymentScore: 0, createdAt: "2026-04-02T10:00:00Z" },
    ],
    page: 1,
    pageSize: 20,
    totalCount: 2,
    totalPages: 1,
  });

  renderAdminPage();

  expect(await screen.findAllByRole("button", { name: /admin/i })).toHaveLength(2);
  screen.getAllByRole("button", { name: /admin/i }).forEach((button) => {
    expect(button).toBeDisabled();
  });
  expect(screen.getByLabelText("Select user Current Admin")).toBeDisabled();
  expect(screen.getByLabelText("Select user Another Admin")).toBeDisabled();
  expect(screen.getByLabelText("Select all eligible users")).toBeDisabled();
});

test("UsersPage renders clear active and inactive badges without enabling protected actions", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [
      { id: 99, role: "admin", name: "Current Admin", isActive: true, phone: "7000000001", totalChits: 0, paymentScore: 0, createdAt: "2026-04-01T10:00:00Z" },
      { id: 4, role: "owner", name: "Owner Four", isActive: false, phone: "7777777774", totalChits: 2, paymentScore: 70, createdAt: "2026-04-01T10:00:00Z" },
    ],
    page: 1,
    pageSize: 20,
    totalCount: 2,
    totalPages: 1,
  });

  renderAdminPage();

  await screen.findByRole("button", { name: "Activate" });
  expect(getBadgeByText("Active")).toHaveClass("bg-emerald-100");
  expect(getBadgeByText("Inactive")).toHaveClass("bg-red-100");
  expect(screen.getByRole("button", { name: "Protected admin" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Activate" })).toBeEnabled();
});

test("UsersPage renders payment score badges in green, yellow, and red bands", async () => {
  fetchAdminUsers.mockResolvedValue({
    items: [
      { id: 4, role: "owner", name: "Owner Four", isActive: true, phone: "7777777774", totalChits: 2, paymentScore: 80, createdAt: "2026-04-01T10:00:00Z" },
      { id: 5, role: "subscriber", name: "Subscriber Five", isActive: true, phone: "7777777775", totalChits: 1, paymentScore: 50, createdAt: "2026-04-02T10:00:00Z" },
      { id: 6, role: "owner", name: "Owner Six", isActive: true, phone: "7777777776", totalChits: 3, paymentScore: 49, createdAt: "2026-04-03T10:00:00Z" },
    ],
    page: 1,
    pageSize: 20,
    totalCount: 3,
    totalPages: 1,
  });

  renderAdminPage();

  await screen.findByText("Owner Six");
  expect(getPaymentScoreBadge(80)).toHaveClass("bg-emerald-100", "text-emerald-900");
  expect(getPaymentScoreBadge(50)).toHaveClass("bg-amber-100", "text-amber-900");
  expect(getPaymentScoreBadge(49)).toHaveClass("bg-red-100", "text-red-900");
});
