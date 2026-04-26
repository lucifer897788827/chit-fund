import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import ProfilePage from "./ProfilePage";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";
import { fetchMyFinancialSummary } from "../features/users/api";

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
  getUserRoles: jest.fn(),
  sessionHasRole: jest.fn(),
}));

jest.mock("../features/auth/api", () => ({
  logoutUser: jest.fn(),
}));

jest.mock("../features/owner-requests/api", () => ({
  createOwnerRequest: jest.fn(),
}));

jest.mock("../features/dashboard/api", () => ({
  fetchOwnerDashboard: jest.fn(),
  fetchSubscriberDashboard: jest.fn(),
}));

jest.mock("../features/users/api", () => ({
  fetchMyFinancialSummary: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  getCurrentUser.mockReturnValue({
    user: {
      id: 1,
      name: "Owner One",
      phone: "9999999999",
      email: "owner@example.com",
    },
    owner_id: 1,
    role: "chit_owner",
  });
  getUserRoles.mockReturnValue(["owner"]);
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchSubscriberDashboard.mockResolvedValue({
    memberships: [
      {
        groupId: 42,
        installmentAmount: 5000,
        slotCount: 1,
        membershipStatus: "active",
        wonSlotCount: 1,
        prizedStatus: "prized",
      },
    ],
  });
  fetchOwnerDashboard.mockResolvedValue({
    totalPaidAmount: 1000,
    recentPayouts: [],
  });
  fetchMyFinancialSummary.mockResolvedValue({
    total_paid: 1000,
    total_received: 4000,
    dividend: 100,
    net: 3100,
  });
});

test("uses backend financial summary instead of approximate local totals", async () => {
  render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  );

  await waitFor(() => expect(fetchMyFinancialSummary).toHaveBeenCalled());
  expect(await screen.findByText("Rs. 1,000")).toBeInTheDocument();
  expect(screen.getByText("Rs. 100")).toBeInTheDocument();
  expect(screen.getByText("Rs. 4,000")).toBeInTheDocument();
  expect(screen.getByText("Rs. 3,100")).toBeInTheDocument();
  expect(screen.queryByText("Approximate calculation")).not.toBeInTheDocument();
});
