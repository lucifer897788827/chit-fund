import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import GroupsListPage from "./GroupsListPage";
import { fetchPublicChits } from "../features/auctions/api";
import { fetchUserDashboard } from "../features/dashboard/api";
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

jest.mock("../features/auctions/api", () => ({
  fetchPublicChits: jest.fn(),
  requestGroupMembership: jest.fn(),
  searchChitsByCode: jest.fn(),
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

function renderGroupsPage(queryClient = createTestQueryClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GroupsListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
}

beforeEach(() => {
  jest.clearAllMocks();
  getCurrentUser.mockReturnValue({ role: "chit_owner", owner_id: 4 });
  sessionHasRole.mockImplementation((_session, role) => role === "owner");
  fetchUserDashboard.mockResolvedValue({
    role: "owner",
    stats: {
      owner_dashboard: {
        groups: [{ groupId: 42, title: "April Chit", groupCode: "APR-42" }],
      },
    },
  });
  fetchPublicChits.mockResolvedValue([{ id: 99, title: "Public Chit", groupCode: "PUB-99", visibility: "public" }]);
});

test("reuses cached group data on remount", async () => {
  const queryClient = createTestQueryClient();
  const firstRender = renderGroupsPage(queryClient);

  expect(await screen.findByRole("heading", { name: "Groups" })).toBeInTheDocument();
  expect(await screen.findByText("Public Chit")).toBeInTheDocument();
  firstRender.unmount();

  renderGroupsPage(queryClient);

  expect(await screen.findByText("Public Chit")).toBeInTheDocument();
  expect(fetchUserDashboard).toHaveBeenCalledTimes(1);
  expect(fetchPublicChits).toHaveBeenCalledTimes(1);
});
