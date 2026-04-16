import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

jest.mock("./api", () => ({
  fetchExternalChits: jest.fn(),
}));

import ExternalChitsPage from "./ExternalChitsPage";
import { fetchExternalChits } from "./api";

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.setItem(
    "chit-fund-session",
    JSON.stringify({
      subscriber_id: 7,
      has_subscriber_profile: true,
      role: "subscriber",
    }),
  );
});

afterEach(() => {
  window.localStorage.clear();
});

test("loads and renders external chits for the signed-in subscriber", async () => {
  fetchExternalChits.mockResolvedValue([
    {
      id: 1,
      title: "Neighbourhood Savings Pot",
      organizerName: "Lakshmi",
      chitValue: 120000,
      installmentAmount: 6000,
      cycleFrequency: "monthly",
      startDate: "2026-03-01",
      status: "active",
    },
  ]);

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <ExternalChitsPage />
    </MemoryRouter>,
  );

  await waitFor(() => {
    expect(fetchExternalChits).toHaveBeenCalledWith(7);
  });
  expect(await screen.findByText(/Neighbourhood Savings Pot/i)).toBeInTheDocument();
});
