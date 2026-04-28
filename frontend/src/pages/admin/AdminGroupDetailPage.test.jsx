import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AdminGroupDetailPage from "./AdminGroupDetailPage";
import { fetchAdminGroupDetail } from "../../features/admin/api";

jest.mock("../../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../../features/admin/api", () => ({
  fetchActiveAdminMessage: jest.fn(),
  fetchAdminAuctions: jest.fn(),
  fetchAdminDashboardOverview: jest.fn(),
  fetchAdminDefaulters: jest.fn(),
  fetchAdminGroupDetail: jest.fn(),
  fetchAdminGroups: jest.fn(),
  fetchAdminInsightsSummary: jest.fn(),
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

function renderGroupDetail(route = "/admin/groups/11") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={[route]}>
        <Routes>
          <Route path="/admin/groups/:id" element={<AdminGroupDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("AdminGroupDetailPage renders the full intelligence view for one group", async () => {
  fetchAdminGroupDetail.mockResolvedValue({
    group: {
      id: 11,
      name: "Alpha Group",
      status: "active",
      owner: "Owner One",
      ownerPhone: "7777777777",
      membersCount: 2,
      monthlyAmount: 10000,
      chitValue: 200000,
      currentCycleNo: 2,
      startDate: "2026-04-01",
      firstAuctionDate: "2026-04-15",
    },
    members: [
      {
        membershipId: 1,
        userId: 21,
        name: "Subscriber One",
        phone: "9999999999",
        totalPaid: 10000,
        totalReceived: 0,
        netPosition: -10000,
        paymentScore: 33,
        pendingPaymentsCount: 2,
      },
      {
        membershipId: 2,
        userId: 22,
        name: "Subscriber Two",
        phone: "8888888888",
        totalPaid: 10000,
        totalReceived: 8500,
        netPosition: -1500,
        paymentScore: 80,
        pendingPaymentsCount: 0,
      },
    ],
    financialSummary: {
      totalCollected: 20000,
      totalPaid: 8500,
      pendingAmount: 10000,
    },
    auctions: [
      {
        id: 51,
        cycleNo: 1,
        month: "Apr 2026",
        winner: "Subscriber Two",
        bidAmount: 15000,
        status: "closed",
      },
    ],
    defaulters: [
      {
        userId: 21,
        name: "Subscriber One",
        phone: "9999999999",
        pendingPaymentsCount: 2,
        pendingAmount: 10000,
        paymentScore: 33,
        netPosition: -10000,
      },
    ],
  });

  renderGroupDetail();

  expect(await screen.findByRole("heading", { name: "Alpha Group" })).toBeInTheDocument();
  expect(screen.getByText((_content, element) => element?.textContent === "Owner: Owner One")).toBeInTheDocument();
  expect(screen.getByText((_content, element) => element?.textContent === "Owner phone: 7777777777")).toBeInTheDocument();
  expect(screen.getByText("Financial snapshot")).toBeInTheDocument();
  expect(screen.getByText("Members")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Subscriber One" })).toHaveAttribute("href", "/admin/users/21");
  expect(screen.getByText("Auction history")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Subscriber Two" })).toHaveAttribute("href", "/admin/users/22");
  expect(screen.getByText("Risk panel")).toBeInTheDocument();
  expect(screen.getByText("Defaulters")).toBeInTheDocument();
  expect(screen.getByText("Low score users")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to admin groups" })).toHaveAttribute("href", "/admin/groups");
});
