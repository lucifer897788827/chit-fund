import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { fetchAuctionRoom, submitBid } from "./api";

jest.mock("./api", () => ({
  fetchAuctionRoom: jest.fn(),
  submitBid: jest.fn(),
}));

import AuctionRoomPage from "./AuctionRoomPage";

test("renders auction room heading", async () => {
  fetchAuctionRoom.mockResolvedValue({
    sessionId: 5,
    status: "open",
    canBid: true,
    myMembershipId: 2,
  });
  render(
    <MemoryRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      initialEntries={["/auctions/5"]}
    >
      <Routes>
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText(/Live Auction/i)).toBeInTheDocument();
  expect(await screen.findByText(/Session 5 is open/i)).toBeInTheDocument();
});

test("submits bid using route session id", async () => {
  const user = userEvent.setup();
  fetchAuctionRoom.mockResolvedValue({
    sessionId: 5,
    status: "open",
    canBid: true,
    myMembershipId: 2,
  });
  submitBid.mockResolvedValue({
    accepted: true,
    placedAt: new Date("2026-07-10T10:00:00Z").toISOString(),
  });

  render(
    <MemoryRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      initialEntries={["/auctions/5"]}
    >
      <Routes>
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText(/Session 5 is open/i);
  await user.type(screen.getByLabelText(/Place Bid/i), "12000");
  await user.click(screen.getByRole("button", { name: /Submit Bid/i }));

  expect(submitBid).toHaveBeenCalledWith(5, {
    membershipId: 2,
    bidAmount: 12000,
    idempotencyKey: "5-2-12000",
  });
});
