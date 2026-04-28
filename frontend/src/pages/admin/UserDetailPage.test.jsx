import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import UserDetailPage from "./UserDetailPage";
import { fetchAdminUser } from "../../features/admin/api";
import { formatMoney } from "../../features/payments/balances";

jest.mock("../../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../../features/admin/api", () => ({
  fetchAdminUser: jest.fn(),
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

function renderUserDetailPage() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={["/admin/users/7"]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <Routes>
          <Route path="/admin/users/:id" element={<UserDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function buildUserPayload(netPosition) {
  return {
    id: 7,
    role: "subscriber",
    phone: "8888888888",
    email: "member@example.com",
    isActive: true,
    ownerId: null,
    subscriberId: 4,
    participationStats: {
      totalChits: 3,
      ownedChits: 0,
      joinedChits: 3,
      externalChits: 0,
      membershipCount: 3,
      activeMemberships: 2,
      prizedMemberships: 1,
    },
    financialSummary: {
      paymentCount: 2,
      totalPaid: 1000,
      payoutCount: 1,
      totalReceived: 4000,
      netCashflow: 3000,
      paymentScore: 90,
      netPosition,
    },
    chits: [],
    payments: [],
    externalChitsData: [],
  };
}

function getNetPositionValue() {
  const netPositionCard = screen.getByText("Net position").closest("article");
  return within(netPositionCard).getByText(/Rs\./);
}

function getPaymentScoreValue() {
  const paymentScoreCard = screen.getByText("Payment score").closest("article");
  return within(paymentScoreCard).getByLabelText(/Payment score:/);
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("shows positive net position in green on admin user detail", async () => {
  fetchAdminUser.mockResolvedValueOnce(buildUserPayload(900));

  renderUserDetailPage();

  expect(await screen.findByText(/User #/)).toBeInTheDocument();
  expect(getNetPositionValue()).toHaveTextContent(formatMoney(900));
  expect(getNetPositionValue()).toHaveClass("text-emerald-700");
});

test("shows negative net position in red on admin user detail", async () => {
  fetchAdminUser.mockResolvedValueOnce(buildUserPayload(-250));

  renderUserDetailPage();

  expect(await screen.findByText(/User #/)).toBeInTheDocument();
  expect(getNetPositionValue()).toHaveTextContent(formatMoney(-250));
  expect(getNetPositionValue()).toHaveClass("text-red-700");
});

test("shows zero net position in neutral tone on admin user detail", async () => {
  fetchAdminUser.mockResolvedValueOnce(buildUserPayload(0));

  renderUserDetailPage();

  expect(await screen.findByText(/User #/)).toBeInTheDocument();
  expect(getNetPositionValue()).toHaveTextContent(formatMoney(0));
  expect(getNetPositionValue()).toHaveClass("text-slate-700");
});

test.each([
  { score: 80, expectedClasses: ["bg-emerald-100", "text-emerald-900"] },
  { score: 50, expectedClasses: ["bg-amber-100", "text-amber-900"] },
  { score: 49, expectedClasses: ["bg-red-100", "text-red-900"] },
])("shows payment score %s in the correct admin detail band", async ({ score, expectedClasses }) => {
  const payload = buildUserPayload(0);
  payload.financialSummary.paymentScore = score;
  fetchAdminUser.mockResolvedValueOnce(payload);

  renderUserDetailPage();

  expect(await screen.findByText(/User #/)).toBeInTheDocument();
  expect(getPaymentScoreValue()).toHaveTextContent(`${score} / 100`);
  expect(getPaymentScoreValue()).toHaveAttribute("aria-label", `Payment score: ${score} / 100`);
  expect(getPaymentScoreValue()).toHaveClass(...expectedClasses);
});
