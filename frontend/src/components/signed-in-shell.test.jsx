import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

jest.mock("../features/auth/api", () => ({
  fetchCurrentUser: jest.fn(() => Promise.resolve({})),
}));

import SignedInAppShell from "./signed-in-shell";
import { fetchCurrentUser } from "../features/auth/api";
import { clearSession, getCurrentUser, saveSession } from "../lib/auth/store";

beforeEach(() => {
  jest.clearAllMocks();
  clearSession();
});

afterEach(() => {
  clearSession();
});

test("refreshes the signed-in session and redirects a subscriber home view after owner upgrade", async () => {
  fetchCurrentUser.mockResolvedValue({
    role: "chit_owner",
    owner_id: 4,
    subscriber_id: 7,
    has_subscriber_profile: true,
    user: {
      id: 7,
      roles: ["subscriber", "owner"],
    },
  });
  saveSession({
    access_token: "token-subscriber",
    role: "subscriber",
    subscriber_id: 7,
    has_subscriber_profile: true,
    user: {
      id: 7,
      roles: ["subscriber"],
    },
  });

  render(
    <MemoryRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      initialEntries={["/subscriber-dashboard"]}
    >
      <Routes>
        <Route
          path="/subscriber-dashboard"
          element={
            <SignedInAppShell>
              <div>Subscriber home</div>
            </SignedInAppShell>
          }
        />
        <Route path="/owner" element={<h1>Owner destination</h1>} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: /Owner destination/i })).toBeInTheDocument();
  expect(getCurrentUser()?.user?.roles).toEqual(["subscriber", "owner"]);
  expect(getCurrentUser()?.owner_id).toBe(4);
});
