import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExternalChitHistoryPanel from "./ExternalChitHistoryPanel";

test("renders loading, empty, and summary states for the ledger workspace", async () => {
  const user = userEvent.setup();
  const onRetry = jest.fn();
  const onRetrySummary = jest.fn();

  const { rerender } = render(
    <ExternalChitHistoryPanel
      chit={{ id: 7, title: "Office chit", status: "active", entryHistory: [] }}
      loading
      summary={{ totalPaid: 0, totalReceived: 0, profit: 0, winningMonth: null }}
    />,
  );

  expect(screen.getByText("Loading ledger workspace...")).toBeInTheDocument();

  rerender(
    <ExternalChitHistoryPanel
      chit={{ id: 7, title: "Office chit", status: "active", entryHistory: [] }}
      onRetry={onRetry}
      onRetrySummary={onRetrySummary}
      summary={{ totalPaid: 1000, totalReceived: 1500, profit: 500, winningMonth: 2 }}
      summaryError="Unable to load summary."
    />,
  );

  expect(screen.getByText("No month entries recorded yet.")).toBeInTheDocument();
  expect(screen.getByText("Rs. 1,000")).toBeInTheDocument();
  expect(screen.getByText("Month 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Refresh summary" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Refresh summary" }));
  expect(onRetrySummary).toHaveBeenCalledTimes(1);

  rerender(
    <ExternalChitHistoryPanel
      chit={{ id: 7, title: "Office chit", status: "active", entryHistory: [] }}
      error="Unable to load ledger."
      onRetry={onRetry}
      summary={{ totalPaid: 0, totalReceived: 0, profit: 0, winningMonth: null }}
    />,
  );

  expect(screen.getByText("Unable to load ledger.")).toBeInTheDocument();
});

test("renders saved month entries and supports editing through callbacks", async () => {
  const user = userEvent.setup();
  const onUpdateEntry = jest.fn().mockResolvedValue(true);

  render(
    <ExternalChitHistoryPanel
      chit={{
        id: 8,
        title: "Office chit",
        status: "active",
        startDate: "2026-01-01",
        entryHistory: [
          {
            id: 11,
            entryType: "paid",
            description: "Advance adjustment",
            entryDate: "2026-02-01",
            createdAt: "2026-04-20T11:15:00Z",
            updatedAt: "2026-04-20T11:30:00Z",
            amount: 18000,
            monthNumber: 2,
            bidAmount: 18000,
            winnerType: "OTHER",
            sharePerSlot: 1800,
            myShare: 3600,
            myPayable: 16400,
            myPayout: 0,
            isBidOverridden: false,
            isShareOverridden: true,
            isPayableOverridden: false,
            isPayoutOverridden: true,
          },
        ],
      }}
      onUpdateEntry={onUpdateEntry}
      summary={{ totalPaid: 16400, totalReceived: 3600, profit: -12800, winningMonth: null }}
    />,
  );

  expect(screen.getByText("Other")).toBeInTheDocument();
  expect(screen.getAllByText("Rs. 16,400").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Rs. 3,600").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Manual").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Auto").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Manually adjusted").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Calculated automatically").length).toBeGreaterThan(0);

  await user.click(screen.getByRole("button", { name: /Edit month entry/i }));
  await screen.findByRole("button", { name: /Update month entry/i });
  expect(screen.getAllByText("Manually adjusted").length).toBeGreaterThan(0);
  await user.clear(screen.getByLabelText(/^Share$/i));
  await user.type(screen.getByLabelText(/^Share$/i), "3600");
  await user.clear(screen.getByLabelText(/Payout/i));
  await user.type(screen.getByLabelText(/Payout/i), "2000");
  await user.click(screen.getByRole("button", { name: /Update month entry/i }));

  await waitFor(() => {
    expect(onUpdateEntry).toHaveBeenCalledWith(11, {
      entryType: "paid",
      entryDate: "2026-02-01",
      amount: 18000,
      description: "Month 2 ledger entry",
      monthNumber: 2,
      bidAmount: 18000,
      winnerType: "OTHER",
      winnerName: "",
      myShare: 3600,
      myPayable: 16400,
      myPayout: 2000,
    });
  });
});

test("allows saving a month entry without a bid amount", async () => {
  const user = userEvent.setup();
  const onCreateEntry = jest.fn().mockResolvedValue(true);

  render(
    <ExternalChitHistoryPanel
      chit={{
        id: 12,
        title: "Office chit",
        status: "active",
        startDate: "2026-01-01",
        entryHistory: [],
      }}
      onCreateEntry={onCreateEntry}
      summary={{ totalPaid: 0, totalReceived: 0, profit: 0, winningMonth: null }}
    />,
  );

  const bidInput = screen.getByLabelText(/Bid amount/i);
  expect(bidInput).not.toBeRequired();
  await user.clear(bidInput);
  await user.click(screen.getByRole("button", { name: /Add month entry/i }));

  await waitFor(() => {
    expect(onCreateEntry).toHaveBeenCalledWith({
      entryType: "paid",
      entryDate: "2026-01-01",
      amount: null,
      description: "Month 1 ledger entry",
      monthNumber: 1,
      bidAmount: null,
      winnerType: "OTHER",
      winnerName: "",
      myShare: null,
      myPayable: null,
      myPayout: null,
    });
  });
});
