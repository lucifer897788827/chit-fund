import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import LoginPage from "./LoginPage";
import { loginUser } from "./api";
import { saveSession } from "../../lib/auth/store";

const mockNavigate = jest.fn();

jest.mock("./api", () => ({
  loginUser: jest.fn(),
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

  await user.type(screen.getByLabelText(/Phone Number/i), "9999999999");
  await user.type(screen.getByLabelText(/Password/i), "secret123");
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
  expect(mockNavigate).toHaveBeenCalledWith("/owner");
});
