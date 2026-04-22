import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { fetchAuctionRoom, submitBid } from "./api";

jest.mock("./api", () => ({
  fetchAuctionRoom: jest.fn(),
  submitBid: jest.fn(),
}));

const originalWebSocket = global.WebSocket;
const webSocketInstances = [];

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    webSocketInstances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({ type: "open" });
  }

  message(data) {
    this.onmessage?.({ data });
  }

  close(code = 1000, reason = "client disconnect") {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason, wasClean: true });
  }

  send = jest.fn();
}

import AuctionRoomPage from "./AuctionRoomPage";

function normalizedText(element) {
  return element?.textContent?.replace(/\s+/g, " ").trim();
}

function hasText(expected) {
  return (_content, element) => normalizedText(element) === expected;
}

function makeRoom(overrides = {}) {
  const now = Date.now();
  return {
    sessionId: 5,
    groupId: 9,
    auctionMode: "LIVE",
    auctionState: "OPEN",
    status: "open",
    cycleNo: 1,
    serverTime: new Date(now).toISOString(),
    startsAt: new Date(now - 60000).toISOString(),
    endsAt: new Date(now + 120000).toISOString(),
    canBid: true,
    myMembershipId: 2,
    myBidCount: 0,
    myBidLimit: null,
    myRemainingBidCapacity: null,
    slotCount: 3,
    wonSlotCount: 1,
    remainingSlotCount: 2,
    minBidValue: null,
    maxBidValue: null,
    minIncrement: null,
    myLastBid: 8000,
    ...overrides,
  };
}

async function renderRoom(room) {
  fetchAuctionRoom.mockResolvedValue(room);
  const expectedStatusLabel =
    room.status && typeof room.status === "string"
      ? `${room.status.charAt(0).toUpperCase()}${room.status.slice(1)}`
      : "Open";

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

  return screen.findByText(hasText(`Status: ${expectedStatusLabel}`));
}

beforeEach(() => {
  jest.clearAllMocks();
  webSocketInstances.length = 0;
  global.WebSocket = MockWebSocket;
});

afterEach(() => {
  global.WebSocket = originalWebSocket;
  jest.useRealTimers();
});

test("renders countdown and keeps bidding enabled while the auction is open", async () => {
  await renderRoom(
    makeRoom({
      myBidCount: 1,
      myBidLimit: 3,
      myRemainingBidCapacity: 2,
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Live auction/i).length).toBeGreaterThan(0);
  expect(await screen.findByText(hasText("Status: Open"))).toBeInTheDocument();
  expect(screen.getByText(hasText("Mode: Live auction"))).toBeInTheDocument();
  expect(screen.getByText(hasText("Window: Closes in 02:00"))).toBeInTheDocument();
  expect(screen.getByText("You own")).toBeInTheDocument();
  expect(
    screen.getAllByText((_content, element) => normalizedText(element)?.includes("3 chits")).length,
  ).toBeGreaterThan(0);
  expect(screen.getAllByText(/You can bid 2 more times/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Bid rules: Min 5,000 · Max 20,000 · Increment 500/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Manual refresh ready/i)).toBeInTheDocument();
  expect(screen.getByText(/Live connection:/i)).toBeInTheDocument();
  expect(screen.getByText(hasText("My last bid: 8000"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Refresh auction room/i })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeEnabled();
});

test("shows an upcoming blind auction state before the bidding window opens", async () => {
  const now = Date.now();
  await renderRoom(
    makeRoom({
      auctionMode: "BLIND",
      auctionState: "UPCOMING",
      startsAt: new Date(now + 120000).toISOString(),
      endsAt: new Date(now + 240000).toISOString(),
      canBid: false,
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Blind auction/i).length).toBeGreaterThan(0);
  expect(screen.getByText(hasText("State: Bidding not started"))).toBeInTheDocument();
  expect(screen.getByText(hasText("Window: Opens in 02:00"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("shows blind auction guidance while keeping the normal bidding flow available", async () => {
  await renderRoom(
    makeRoom({
      auctionMode: "BLIND",
      myBidCount: 1,
      myBidLimit: 4,
      myRemainingBidCapacity: 3,
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Blind auction/i).length).toBeGreaterThan(0);
  expect(screen.getByText(hasText("Mode: Blind auction"))).toBeInTheDocument();
  expect(screen.getAllByText(/You can bid 3 more times/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Other bids stay hidden until the auction is finalized/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeEnabled();
});

test("disables bidding when the auction room has exhausted its remaining bid capacity", async () => {
  await renderRoom(
    makeRoom({
      auctionMode: "BLIND",
      canBid: true,
      myBidCount: 3,
      myBidLimit: 3,
      myRemainingBidCapacity: 0,
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Blind auction/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/You can bid 0 more times/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Bidding capacity exhausted/i)).toBeInTheDocument();
  expect(screen.getByText(/no remaining bid capacity/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("shows client-side bid-rule validation before submitting", async () => {
  const user = userEvent.setup();

  await renderRoom(
    makeRoom({
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  await user.clear(screen.getByLabelText(/Place Bid/i));
  await user.type(screen.getByLabelText(/Place Bid/i), "5200");

  expect((await screen.findAllByText(/Bid must move in increments of 500 from 5,000/i)).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
  expect(submitBid).not.toHaveBeenCalled();
});

test("shows the current highest bid from the recent bid feed when the room snapshot omits it", async () => {
  await renderRoom(
    makeRoom({
      highestBidAmount: null,
      currentHighestBid: null,
      currentBidAmount: null,
      recentBids: [
        { bidAmount: 12000, bidderName: "Member A", createdAt: "2026-07-10T10:00:00Z" },
        { bidAmount: 15000, bidderName: "Member B", createdAt: "2026-07-10T10:01:00Z" },
      ],
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  const currentHighestBidCard = screen.getByText("Current highest bid").closest("article");
  expect(currentHighestBidCard).toBeTruthy();
  expect(currentHighestBidCard).toHaveTextContent("₹15,000");
});

test("shows fixed auction guidance and disables bid submission", async () => {
  await renderRoom(
    makeRoom({
      auctionMode: "FIXED",
      canBid: false,
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  expect(await screen.findByRole("heading", { name: /Cycle 1 auction/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Fixed auction/i).length).toBeGreaterThan(0);
  expect(screen.getByText(hasText("Mode: Fixed auction"))).toBeInTheDocument();
  expect(screen.getByText(hasText("Bid rules: Min 5,000 · Max 20,000 · Increment 500"))).toBeInTheDocument();
  expect(screen.getByText(/assigned to organizer/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/Place Bid/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Submit Bid/i })).not.toBeInTheDocument();
});

test("refreshes the room when a realtime update arrives", async () => {
  fetchAuctionRoom.mockResolvedValueOnce(makeRoom()).mockResolvedValueOnce(
    makeRoom({
      status: "closed",
      canBid: false,
      auctionResult: {
        winnerMembershipId: 4,
        winningBidAmount: 12000,
        finalizedAt: "2026-07-10T10:03:00Z",
      },
    }),
  );

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={["/auctions/5"]}>
      <Routes>
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText(hasText("Status: Open"))).toBeInTheDocument();
  expect(screen.getByText(/Live connection:/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(webSocketInstances).toHaveLength(1);
  });

  act(() => {
    webSocketInstances[0].open();
    webSocketInstances[0].message(JSON.stringify({ event: "auction-room-updated" }));
  });

  await screen.findByText(hasText("Status: Open"));
  await waitFor(() => {
    expect(fetchAuctionRoom).toHaveBeenCalledTimes(2);
  });
});

test("falls back to polling when the realtime socket is unavailable", async () => {
  jest.useFakeTimers();
  global.WebSocket = class {
    constructor() {
      throw new Error("socket unavailable");
    }
  };
  fetchAuctionRoom.mockResolvedValueOnce(makeRoom()).mockResolvedValueOnce(
    makeRoom({
      status: "closed",
      canBid: false,
      auctionResult: {
        winnerMembershipId: 4,
        winningBidAmount: 12000,
        finalizedAt: "2026-07-10T10:03:00Z",
      },
    }),
  );

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={["/auctions/5"]}>
      <Routes>
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText(hasText("Status: Open"))).toBeInTheDocument();
  expect(screen.getByText("Fallback polling active")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(15000);
    await Promise.resolve();
  });

  expect(fetchAuctionRoom).toHaveBeenCalledTimes(2);
});

test("shows a closed-room result summary and disables bidding", async () => {
  await renderRoom(
    makeRoom({
      status: "closed",
      canBid: false,
      auctionResult: {
        winnerMembershipId: 4,
        winningBidAmount: 12000,
        finalizedAt: "2026-07-10T10:03:00Z",
      },
    }),
  );

  expect(await screen.findByText(hasText("Status: Closed"))).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Finalized result/i })).toBeInTheDocument();
  expect(screen.getByText(/Membership #4/i)).toBeInTheDocument();
  expect(screen.getAllByText(/12,000/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Payout snapshot/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("shows a finalized no-bid message instead of a pending result", async () => {
  await renderRoom(
    makeRoom({
      auctionMode: "BLIND",
      auctionState: "FINALIZED",
      status: "finalized",
      canBid: false,
      validBidCount: 0,
      finalizationMessage: "Auction finalized with no winner because no bids were received.",
      myLastBid: null,
    }),
  );

  expect(await screen.findByText(hasText("Status: Finalized"))).toBeInTheDocument();
  expect(screen.getByText(hasText("State: No bids received"))).toBeInTheDocument();
  expect(screen.getByText(/No bids received in this auction/i)).toBeInTheDocument();
  expect(screen.getByText(/No bids were submitted in this round/i)).toBeInTheDocument();
  expect(screen.queryByText(/Auction closed\. Result pending/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("keeps the bid path working when the bid response includes the new session status shape", async () => {
  const user = userEvent.setup();
  await renderRoom(
    makeRoom({
      myBidCount: 1,
      myBidLimit: 3,
      myRemainingBidCapacity: 2,
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  submitBid.mockResolvedValue({
    accepted: true,
    placedAt: new Date("2026-07-10T10:00:30Z").toISOString(),
    sessionStatus: "closed",
    room: makeRoom({
      status: "closed",
      canBid: false,
      auctionState: "ENDED",
      myBidCount: 2,
      myBidLimit: 3,
      myRemainingBidCapacity: 1,
      myLastBid: 12000,
    }),
    auctionResult: {
      winnerMembershipId: 2,
      winningBidAmount: 12000,
    },
  });

  await user.type(screen.getByLabelText(/Place Bid/i), "12000");
  await user.click(screen.getByRole("button", { name: /Submit Bid/i }));

  expect(submitBid).toHaveBeenCalledWith(5, {
    membershipId: 2,
    bidAmount: 12000,
    idempotencyKey: "5-2-12000",
  });
  expect(await screen.findByText(/Bid accepted/i)).toBeInTheDocument();
  expect(screen.getByText(/Membership #2/i)).toBeInTheDocument();
  expect(screen.getAllByText(/12,000/i).length).toBeGreaterThan(0);
  expect(screen.getByText(hasText("My last bid: 12000"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("surfaces backend validation details when the server rejects a bid", async () => {
  const user = userEvent.setup();
  await renderRoom(
    makeRoom({
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  submitBid.mockRejectedValue({
    response: {
      status: 409,
      data: {
        detail: "Bid limit reached for this session",
      },
    },
  });

  await user.clear(screen.getByLabelText(/Place Bid/i));
  await user.type(screen.getByLabelText(/Place Bid/i), "6000");
  await user.click(screen.getByRole("button", { name: /Submit Bid/i }));

  expect(await screen.findByText(/Bid limit reached for this session/i)).toBeInTheDocument();
});

test("uses the bid response room snapshot to disable submission when capacity is exhausted", async () => {
  const user = userEvent.setup();
  await renderRoom(
    makeRoom({
      myBidCount: null,
      myBidLimit: null,
      myRemainingBidCapacity: null,
      minBidValue: 5000,
      maxBidValue: 20000,
      minIncrement: 500,
    }),
  );

  submitBid.mockResolvedValue({
    accepted: true,
    placedAt: new Date("2026-07-10T10:00:30Z").toISOString(),
    sessionStatus: "open",
    room: makeRoom({
      myBidCount: 1,
      myBidLimit: 1,
      myRemainingBidCapacity: 0,
      canBid: false,
    }),
  });

  await user.clear(screen.getByLabelText(/Place Bid/i));
  await user.type(screen.getByLabelText(/Place Bid/i), "5000");
  await user.click(screen.getByRole("button", { name: /Submit Bid/i }));

  expect(await screen.findByText(/Bid accepted/i)).toBeInTheDocument();
  expect(screen.getAllByText(/You can bid 0 more times/i).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeDisabled();
});

test("keeps bidding enabled for legacy open-room payloads without auctionState", async () => {
  await renderRoom(
    makeRoom({
      auctionState: undefined,
      status: "open",
      canBid: true,
      myBidCount: 0,
      myBidLimit: 2,
      myRemainingBidCapacity: 2,
    }),
  );

  expect(await screen.findByText(hasText("Status: Open"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Submit Bid/i })).toBeEnabled();
});

test("refreshes the room manually without clearing the bid draft", async () => {
  const user = userEvent.setup();

  fetchAuctionRoom.mockResolvedValueOnce(makeRoom()).mockResolvedValueOnce(
    makeRoom({
      status: "closed",
      canBid: false,
      auctionResult: {
        winnerMembershipId: 4,
        winningBidAmount: 12000,
        finalizedAt: "2026-07-10T10:03:00Z",
      },
    }),
  );

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={["/auctions/5"]}>
      <Routes>
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText(hasText("Status: Open"));
  await user.type(screen.getByLabelText(/Place Bid/i), "9100");
  await user.click(screen.getByRole("button", { name: /Refresh auction room/i }));

  expect(fetchAuctionRoom).toHaveBeenCalledTimes(2);
  expect(await screen.findByText(hasText("Status: Closed"))).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Finalized result/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/Place Bid/i)).toHaveValue(9100);
});
