import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import OwnerPayoutsPanel from "./OwnerPayoutsPanel";

test("shows payout records and allows pending payouts to be settled", async () => {
  const user = userEvent.setup();
  const onSettle = jest.fn();

  render(
    <OwnerPayoutsPanel
      loading={false}
      onSettle={onSettle}
      payouts={[
        {
          id: 71,
          subscriberName: "Asha Devi",
          subscriberId: 77,
          groupTitle: "July Chit",
          groupCode: "JUL-001",
          auctionResultId: 44,
          chitValue: 200000,
          bidAmount: 15000,
          commissionAmount: 12000,
          monthlyInstallmentAmount: 10000,
          shareReceivedAmount: 3500,
          grossAmount: 200000,
          deductionsAmount: 12000,
          netAmount: 188000,
          payoutMethod: "auction_settlement",
          payoutDate: "2026-04-21",
          referenceNo: "UPI-9911",
          status: "pending",
        },
        {
          id: 72,
          subscriberName: "Ravi Kumar",
          subscriberId: 78,
          groupTitle: "July Chit",
          groupCode: "JUL-001",
          auctionResultId: 45,
          grossAmount: 200000,
          deductionsAmount: 15000,
          netAmount: 185000,
          payoutMethod: "auction_settlement",
          payoutDate: "2026-04-20",
          status: "paid",
        },
      ]}
    />,
  );

  expect(screen.getByText("Payouts")).toBeInTheDocument();
  expect(screen.getByText("Pending payouts")).toBeInTheDocument();
  expect(screen.getByText("Settled payouts")).toBeInTheDocument();
  expect(screen.getByText("Asha Devi · July Chit · JUL-001")).toBeInTheDocument();
  expect(screen.getAllByText("Winner payout breakdown").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Rs. 1,88,000").length).toBeGreaterThan(0);

  await user.click(screen.getByRole("button", { name: /Mark settled/i }));

  expect(onSettle).toHaveBeenCalledWith(
    expect.objectContaining({
      id: 71,
      status: "pending",
    }),
  );
});
