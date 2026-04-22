import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import ResetPasswordPage from "./ResetPasswordPage";
import { confirmPasswordReset, requestPasswordReset } from "./api";

jest.mock("./api", () => ({
  requestPasswordReset: jest.fn(),
  confirmPasswordReset: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("requests a reset token and submits the new password", async () => {
  const user = userEvent.setup();
  requestPasswordReset.mockResolvedValue({
    message: "If an account exists, a password reset token has been generated.",
    reset_token: null,
  });
  confirmPasswordReset.mockResolvedValue({
    message: "Password has been reset",
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <ResetPasswordPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: /Reset your password/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Back to sign in/i })).toHaveAttribute("href", "/");

  await user.type(screen.getByLabelText(/^Phone number$/i), "9999999999");
  await user.click(screen.getByRole("button", { name: /Request reset token/i }));

  await waitFor(() => {
    expect(requestPasswordReset).toHaveBeenCalledWith({ phone: "9999999999" });
  });
  expect(screen.getByLabelText(/Reset token/i)).toHaveValue("");

  await user.type(screen.getByLabelText(/Reset token/i), "reset-token-123");
  await user.type(screen.getByLabelText(/^New password$/i), "secret123");
  await user.type(screen.getByLabelText(/Confirm new password/i), "secret123");
  await user.click(screen.getByRole("button", { name: /Save New Password/i }));

  await waitFor(() => {
    expect(confirmPasswordReset).toHaveBeenCalledWith({
      token: "reset-token-123",
      new_password: "secret123",
    });
  });
  expect(screen.getByText(/Password has been reset/i)).toBeInTheDocument();
});
