import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import LoginPage from "./LoginPage";
import { loginUser } from "./api";
import { getDashboardPath, saveSession } from "../../lib/auth/store";

const mockNavigate = jest.fn();

jest.mock("./api", () => ({
  loginUser: jest.fn(),
}));

jest.mock("../../lib/auth/store", () => ({
  saveSession: jest.fn(),
  getDashboardPath: jest.fn(),
}));

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  jest.clearAllMocks();
  getDashboardPath.mockImplementation((session) => {
    if (session.role === "admin") {
      return "/admin-dashboard";
    }
    return session.role === "chit_owner" ? "/owner-dashboard" : "/subscriber-dashboard";
  });
});

test("signs in and routes owners to the owner dashboard", async () => {
  const user = userEvent.setup();
  loginUser.mockResolvedValue({
    access_token: "token-1",
    token_type: "bearer",
    role: "chit_owner",
    owner_id: 4,
    subscriber_id: 7,
    has_subscriber_profile: true,
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <LoginPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("link", { name: /Create an account/i })).toHaveAttribute("href", "/signup");
  expect(screen.getByRole("link", { name: /Forgot password\?/i })).toHaveAttribute(
    "href",
    "/reset-password",
  );
  expect(screen.queryByText(/Demo owner/i)).not.toBeInTheDocument();
  expect(screen.getByLabelText(/Phone Number/i)).toHaveAttribute("placeholder", "Enter phone number");

  await user.type(screen.getByLabelText(/Phone Number/i), "9999999999");
  await user.type(screen.getByLabelText(/^Password$/i), "secret123");
  await user.click(screen.getByRole("button", { name: /Sign In/i }));

  await waitFor(() => {
    expect(loginUser).toHaveBeenCalledWith({
      phone: "9999999999",
      password: "secret123",
    });
  });
  expect(saveSession).toHaveBeenCalledWith(
    expect.objectContaining({
      role: "chit_owner",
      owner_id: 4,
      subscriber_id: 7,
    }),
  );
  expect(mockNavigate).toHaveBeenCalledWith("/owner-dashboard");
});

test("keeps subscriber login routing on the subscriber dashboard", async () => {
  const user = userEvent.setup();
  loginUser.mockResolvedValue({
    access_token: "token-2",
    token_type: "bearer",
    role: "subscriber",
    owner_id: null,
    subscriber_id: 9,
    has_subscriber_profile: true,
  });

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <LoginPage />
    </MemoryRouter>,
  );

  await user.type(screen.getByLabelText(/Phone Number/i), "8888888888");
  await user.type(screen.getByLabelText(/^Password$/i), "pass123");
  await user.click(screen.getByRole("button", { name: /Sign In/i }));

  await waitFor(() => {
    expect(saveSession).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "subscriber",
        subscriber_id: 9,
      }),
    );
  });
  expect(mockNavigate).toHaveBeenCalledWith("/subscriber-dashboard");
});

test("lets the user toggle password visibility on the login form", async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <LoginPage />
    </MemoryRouter>,
  );

  const passwordInput = screen.getByLabelText(/^Password$/i);
  expect(passwordInput).toHaveAttribute("type", "password");

  await user.click(screen.getByRole("button", { name: /show password/i }));
  expect(passwordInput).toHaveAttribute("type", "text");

  await user.click(screen.getByRole("button", { name: /hide password/i }));
  expect(passwordInput).toHaveAttribute("type", "password");
});
