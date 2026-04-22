import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { recordPayment } from "./api";

jest.mock("./api", () => ({
  recordPayment: jest.fn(),
}));

import PaymentPanel from "./PaymentPanel";

beforeEach(() => {
  jest.clearAllMocks();
});

test("adds a newly recorded payment to the history list", async () => {
  const user = userEvent.setup();

  recordPayment.mockResolvedValueOnce({
    id: 91,
    ownerId: 17,
    subscriberId: 42,
    membershipId: 8,
    installmentId: 3,
    paymentType: "installment",
    paymentMethod: "upi",
    amount: 1250,
    paymentDate: "2026-04-20",
    referenceNo: "UPI-7788",
    status: "recorded",
  });

  render(
    <PaymentPanel
      ownerId={17}
      initialPayments={[
        {
          id: 55,
          subscriberId: 12,
          paymentType: "membership",
          paymentMethod: "cash",
          amount: 1000,
          paymentDate: "2026-04-19",
          status: "recorded",
        },
      ]}
    />,
  );

  expect(screen.getByRole("heading", { name: "Membership" })).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText("Payment type"), "installment");
  await user.type(screen.getByLabelText("Subscriber ID"), "42");
  await user.type(screen.getByLabelText("Amount"), "1250");

  await user.click(screen.getByRole("button", { name: "Record payment" }));

  await waitFor(() => {
    expect(recordPayment).toHaveBeenCalledWith(
      expect.objectContaining({
        ownerId: 17,
        subscriberId: 42,
        paymentType: "installment",
      }),
    );
  });

  expect(await screen.findByText(/Payment recorded successfully/i)).toBeInTheDocument();
  expect(screen.getAllByText(/Rs\. 1,250/).length).toBeGreaterThan(0);
});
