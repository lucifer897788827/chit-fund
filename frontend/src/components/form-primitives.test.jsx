import { render, screen } from "@testing-library/react";

import { FormActions, FormField, FormFrame } from "./form-primitives";

test("renders a shared form frame with feedback, fields, and actions", () => {
  render(
    <FormFrame
      title="Record payment"
      description="Capture a secured payment entry."
      error="Owner, subscriber, and amount are required."
      success="Payment recorded successfully."
    >
      <form>
        <FormField label="Subscriber ID" htmlFor="subscriberId" helpText="Use the subscriber's internal id.">
          <input id="subscriberId" />
        </FormField>
        <FormActions note="Fill in the payment details and save.">
          <button type="submit">Record payment</button>
        </FormActions>
      </form>
    </FormFrame>,
  );

  expect(screen.getByRole("heading", { name: "Record payment" })).toBeInTheDocument();
  expect(screen.getByText("Capture a secured payment entry.")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Owner, subscriber, and amount are required.");
  expect(screen.getByRole("status")).toHaveTextContent("Payment recorded successfully.");
  expect(screen.getByLabelText("Subscriber ID")).toBeInTheDocument();
  expect(screen.getByText("Use the subscriber's internal id.")).toBeInTheDocument();
  expect(screen.getByText("Fill in the payment details and save.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Record payment" })).toBeInTheDocument();
});
