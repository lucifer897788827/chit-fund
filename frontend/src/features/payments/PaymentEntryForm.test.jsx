import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { recordPayment } from "./api";

jest.mock("./api", () => ({
  recordPayment: jest.fn(),
}));

import PaymentEntryForm from "./PaymentEntryForm";

beforeEach(() => {
  jest.clearAllMocks();
});

test("submits a payment, shows success, and keeps the current draft visible", async () => {
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

  render(<PaymentEntryForm ownerId={17} />);

  await user.selectOptions(screen.getByLabelText("Payment type"), "installment");
  await user.selectOptions(screen.getByLabelText("Payment method"), "upi");
  await user.type(screen.getByLabelText("Subscriber ID"), "42");
  await user.type(screen.getByLabelText("Membership ID"), "8");
  await user.type(screen.getByLabelText("Installment ID (optional)"), "3");
  await user.type(screen.getByLabelText("Amount"), "1250");
  await user.clear(screen.getByLabelText("Payment date"));
  await user.type(screen.getByLabelText("Payment date"), "2026-04-20");
  await user.type(screen.getByLabelText("Reference number"), "UPI-7788");

  await user.click(screen.getByRole("button", { name: "Record payment" }));

  await waitFor(() => {
    expect(recordPayment).toHaveBeenCalledWith({
      ownerId: 17,
      subscriberId: 42,
      membershipId: 8,
      installmentId: 3,
      paymentType: "installment",
      paymentMethod: "upi",
      amount: 1250,
      paymentDate: "2026-04-20",
      referenceNo: "UPI-7788",
    });
  });

  expect(await screen.findByText(/Payment recorded successfully/i)).toBeInTheDocument();
  expect(screen.getByLabelText("Subscriber ID")).toHaveValue(42);
  expect(screen.getByLabelText("Amount")).toHaveValue(1250);
  expect(screen.getByLabelText("Reference number")).toHaveValue("UPI-7788");
});

test("allows installment payments without entering an installment id", async () => {
  const user = userEvent.setup();

  recordPayment.mockResolvedValueOnce({
    id: 94,
    ownerId: 17,
    subscriberId: 42,
    membershipId: 8,
    installmentId: 7,
    cycleNo: 2,
    paymentType: "installment",
    paymentMethod: "upi",
    amount: 900,
    paymentDate: "2026-04-22",
    referenceNo: null,
    status: "recorded",
  });

  render(<PaymentEntryForm ownerId={17} />);

  await user.selectOptions(screen.getByLabelText("Payment type"), "installment");
  await user.type(screen.getByLabelText("Subscriber ID"), "42");
  await user.type(screen.getByLabelText("Membership ID"), "8");
  await user.type(screen.getByLabelText("Amount"), "900");

  await user.click(screen.getByRole("button", { name: "Record payment" }));

  await waitFor(() => {
    expect(recordPayment).toHaveBeenCalledWith({
      ownerId: 17,
      subscriberId: 42,
      membershipId: 8,
      installmentId: null,
      paymentType: "installment",
      paymentMethod: "cash",
      amount: 900,
      paymentDate: expect.any(String),
      referenceNo: null,
    });
  });

  expect(await screen.findByText(/Payment recorded successfully/i)).toBeInTheDocument();
  expect(screen.getByText(/leave this blank to apply the payment to the next unpaid installment/i)).toBeInTheDocument();
});

test("surfaces an API error without losing the current draft", async () => {
  const user = userEvent.setup();

  recordPayment.mockRejectedValueOnce({
    response: {
      status: 403,
      data: {
        detail: "Cannot record payments for another owner",
      },
    },
  });

  render(<PaymentEntryForm ownerId={17} />);

  await user.selectOptions(screen.getByLabelText("Payment type"), "installment");
  await user.type(screen.getByLabelText("Subscriber ID"), "42");
  await user.type(screen.getByLabelText("Amount"), "1250");

  await user.click(screen.getByRole("button", { name: "Record payment" }));

  expect(await screen.findByText("Cannot record payments for another owner")).toBeInTheDocument();
  expect(screen.getByLabelText("Subscriber ID")).toHaveValue(42);
  expect(screen.getByLabelText("Amount")).toHaveValue(1250);
});

test("resyncs the hidden owner id when the owner prop changes", async () => {
  const user = userEvent.setup();

  recordPayment.mockResolvedValueOnce({
    id: 92,
    ownerId: 18,
    subscriberId: 51,
    membershipId: null,
    installmentId: null,
    paymentType: "membership",
    paymentMethod: "cash",
    amount: 900,
    paymentDate: "2026-04-21",
    referenceNo: null,
    status: "recorded",
  });

  const { rerender } = render(<PaymentEntryForm ownerId={17} />);

  rerender(<PaymentEntryForm ownerId={18} />);

  await user.type(screen.getByLabelText("Subscriber ID"), "51");
  await user.type(screen.getByLabelText("Amount"), "900");
  await user.click(screen.getByRole("button", { name: "Record payment" }));

  await waitFor(() => {
    expect(recordPayment).toHaveBeenCalledWith(
      expect.objectContaining({
        ownerId: 18,
        subscriberId: 51,
        amount: 900,
      }),
    );
  });
});

test("shows penalty details in the success note when the backend returns them", async () => {
  const user = userEvent.setup();

  recordPayment.mockResolvedValueOnce({
    id: 93,
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
    paymentStatus: "PARTIAL",
    penaltyAmount: 250,
    arrearsAmount: 750,
  });

  render(<PaymentEntryForm ownerId={17} />);

  await user.type(screen.getByLabelText("Subscriber ID"), "42");
  await user.type(screen.getByLabelText("Amount"), "1250");
  await user.click(screen.getByRole("button", { name: "Record payment" }));

  expect(await screen.findByText(/Payment recorded successfully/i)).toBeInTheDocument();
  expect(screen.getByText(/Penalty: Rs\. 250\.00/i)).toBeInTheDocument();
  expect(screen.getByText(/Arrears: Rs\. 750\.00/i)).toBeInTheDocument();
});
