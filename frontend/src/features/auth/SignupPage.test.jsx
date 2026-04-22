import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import SignupPage from "./SignupPage";
import { signupUser } from "./api";
import { saveSession } from "../../lib/auth/store";

const mockNavigate = jest.fn();

jest.mock("./api", () => ({
  signupUser: jest.fn(),
}));

jest.mock("../../lib/auth/store", () => ({
  saveSession: jest.fn(),
}));

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test("creates a subscriber account, saves the session, and routes to the subscriber dashboard", async () => {
  const user = userEvent.setup();
  signupUser.mockResolvedValue({
    access_token: "token-1",
    refresh_token: "refresh-1",
    token_type: "bearer",
    role: "subscriber",
    owner_id: null,
    subscriber_id: 12,
    has_subscriber_profile: true,
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <SignupPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: /Create your account/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Sign in/i })).toHaveAttribute("href", "/");

  await user.type(screen.getByLabelText(/Full name/i), "Asha Rao");
  await user.type(screen.getByLabelText(/^Phone number$/i), "9999999999");
  await user.type(screen.getByLabelText(/Email address/i), "asha@example.com");
  await user.type(screen.getByLabelText(/^Password$/i), "secret123");
  await user.type(screen.getByLabelText(/Confirm password/i), "secret123");
  await user.click(screen.getByRole("button", { name: /Create Account/i }));

  await waitFor(() => {
    expect(signupUser).toHaveBeenCalledWith({
      fullName: "Asha Rao",
      phone: "9999999999",
      email: "asha@example.com",
      password: "secret123",
    });
  });
  expect(saveSession).toHaveBeenCalledWith(
    expect.objectContaining({
      role: "subscriber",
      subscriber_id: 12,
    }),
  );
  expect(mockNavigate).toHaveBeenCalledWith("/subscriber");
});
