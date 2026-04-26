import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import HomePage from "./HomePage";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { fetchActiveAdminMessage } from "../features/admin/api";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  getUserRoles: jest.fn(),
  sessionHasRole: jest.fn(),
}));

jest.mock("../features/admin/api", () => ({
  fetchActiveAdminMessage: jest.fn(),
}));

jest.mock("../features/dashboard/api", () => ({
  fetchOwnerDashboard: jest.fn(),
  fetchSubscriberDashboard: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  getCurrentUser.mockReturnValue({ owner_id: 1, role: "chit_owner" });
  getUserRoles.mockReturnValue(["owner"]);
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchOwnerDashboard.mockResolvedValue({ groups: [], balances: [], recentAuctions: [] });
  fetchSubscriberDashboard.mockResolvedValue({ memberships: [], activeAuctions: [] });
  fetchActiveAdminMessage.mockResolvedValue({
    id: 5,
    message: "Collection window closes tonight",
    type: "warning",
    active: true,
  });
});

test("loads the admin message from the backend and keeps dismiss behavior", async () => {
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );

  expect(await screen.findByText(/Collection window closes tonight/)).toBeInTheDocument();
  expect(fetchActiveAdminMessage).toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

  await waitFor(() => expect(screen.queryByText(/Collection window closes tonight/)).not.toBeInTheDocument());
  expect(window.localStorage.getItem("chit-fund-dismissed-admin-message")).toBe("Collection window closes tonight");
});
