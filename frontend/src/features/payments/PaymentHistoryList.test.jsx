import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PaymentHistoryList from "./PaymentHistoryList";

function normalizedText(element) {
  return element?.textContent?.replace(/\s+/g, " ").trim();
}

test("renders empty, loading, and error states for payment history", async () => {
  const user = userEvent.setup();
  const onRetry = jest.fn();
  const { rerender } = render(<PaymentHistoryList payments={[]} loading />);

  expect(screen.getByText("Loading payment history...")).toBeInTheDocument();

  rerender(<PaymentHistoryList payments={[]} onRetry={onRetry} />);
  expect(screen.getByText("No payments have been recorded yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Refresh history" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Refresh history" }));
  expect(onRetry).toHaveBeenCalledTimes(1);

  rerender(
    <PaymentHistoryList
      payments={[]}
      error="Unable to load payment history."
      onRetry={onRetry}
    />,
  );
  expect(screen.getByText("Unable to load payment history.")).toBeInTheDocument();
});

test("renders payment records in a readable history list", () => {
  render(
    <PaymentHistoryList
      payments={[
        {
          id: 91,
          subscriberName: "Asha Devi",
          subscriberId: 42,
          membershipId: 8,
          installmentId: 3,
          paymentType: "installment",
          paymentMethod: "upi",
          amount: 1250,
          paymentDate: "2026-04-20",
          referenceNo: "UPI-7788",
          status: "recorded",
          paymentStatus: "PARTIAL",
          monthlyInstallmentAmount: 2500,
          shareReceivedAmount: 1000,
          finalPayableAmount: 1500,
          totalPayableAmount: 2250,
          arrearsAmount: 750,
        },
      ]}
    />,
  );

  expect(screen.getByText("Installment")).toBeInTheDocument();
  expect(screen.getByText(/Asha Devi/i)).toBeInTheDocument();
  expect(screen.getAllByText("Rs. 1,500").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Rs. 2,250").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Rs\. 1,250/).length).toBeGreaterThan(0);
  expect(screen.getByText("UPI")).toBeInTheDocument();
  expect(screen.getByText("2026-04-20")).toBeInTheDocument();
  expect(normalizedText(screen.getByText("Partial payment progress").parentElement)).toContain(
    "Rs. 1,250 paid / Rs. 1,000 remaining",
  );
});
