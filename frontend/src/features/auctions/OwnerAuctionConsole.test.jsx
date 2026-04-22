import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fetchOwnerAuctionConsole, finalizeAuctionSession } from "./api";

jest.mock("./api", () => ({
  fetchOwnerAuctionConsole: jest.fn(),
  finalizeAuctionSession: jest.fn(),
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

import OwnerAuctionConsole from "./OwnerAuctionConsole";

beforeEach(() => {
  jest.clearAllMocks();
  webSocketInstances.length = 0;
  global.WebSocket = MockWebSocket;
});

afterEach(() => {
  global.WebSocket = originalWebSocket;
  jest.useRealTimers();
});

test("loads the owner auction session summary and enables close/finalize when allowed", async () => {
  fetchOwnerAuctionConsole.mockResolvedValue({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    auctionMode: "LIVE",
    commissionMode: "PERCENTAGE",
    commissionValue: 5,
    auctionState: "OPEN",
    cycleNo: 3,
    status: "open",
    scheduledStartAt: "2026-04-20T09:30:00Z",
    actualStartAt: "2026-04-20T09:31:00Z",
    endTime: "2026-04-20T09:35:00Z",
    serverTime: "2026-04-20T09:33:00Z",
    validBidCount: 4,
    totalBidCount: 6,
    highestBidAmount: 12500,
    highestBidMembershipNo: 7,
    highestBidderName: "Ravi",
    canFinalize: true,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(screen.getByText(/Loading auction console/i)).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getByText("July Chit")).toBeInTheDocument();
  expect(screen.getByText("JUL-001")).toBeInTheDocument();
  expect(screen.getAllByText(/Live auction/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Percentage \(5\)/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Bidding open/i)).toBeInTheDocument();
  expect(screen.getByText(/Cycle 3/i)).toBeInTheDocument();
  expect(screen.getByText(/4 valid \/ 6 total/i)).toBeInTheDocument();
  expect(screen.getAllByText(/12,500/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Manual refresh ready/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Refresh snapshot/i })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Close and finalize auction/i })).toBeEnabled();
  expect(fetchOwnerAuctionConsole).toHaveBeenCalledWith(44);
});

test("hides pre-finalization bid leadership details for blind auctions", async () => {
  fetchOwnerAuctionConsole.mockResolvedValue({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    auctionMode: "BLIND",
    auctionState: "ENDED",
    cycleNo: 3,
    status: "open",
    validBidCount: 4,
    totalBidCount: 6,
    highestBidAmount: null,
    highestBidMembershipNo: null,
    highestBidderName: null,
    canFinalize: true,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Blind auction/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Hidden until finalization/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Bidding ended/i)).toBeInTheDocument();
});

test("shows an upcoming blind auction window before bidding starts", async () => {
  fetchOwnerAuctionConsole.mockResolvedValue({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    auctionMode: "BLIND",
    auctionState: "UPCOMING",
    cycleNo: 3,
    status: "open",
    startTime: "2026-04-20T09:35:00Z",
    endTime: "2026-04-20T09:40:00Z",
    serverTime: "2026-04-20T09:33:00Z",
    validBidCount: 0,
    totalBidCount: 0,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getByText(/Waiting for the blind auction window to open/i)).toBeInTheDocument();
  expect(screen.getByText(/Opens in 02:00/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Close and finalize auction/i })).toBeDisabled();
});

test("shows fixed-auction finalize guidance before the result exists", async () => {
  fetchOwnerAuctionConsole.mockResolvedValue({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    auctionMode: "FIXED",
    cycleNo: 3,
    status: "open",
    validBidCount: 0,
    totalBidCount: 0,
    canFinalize: true,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getAllByText(/Fixed auction/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/Auto-selected on finalize/i)).toBeInTheDocument();
});

test("refreshes the owner console when a realtime update arrives", async () => {
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    canFinalize: true,
  });
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getByText(/Live connection/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(webSocketInstances).toHaveLength(1);
  });

  act(() => {
    webSocketInstances[0].open();
    webSocketInstances[0].message(JSON.stringify({ event: "auction-session-updated" }));
  });

  await waitFor(() => {
    expect(fetchOwnerAuctionConsole).toHaveBeenCalledTimes(2);
  });
});

test("falls back to polling when the owner console socket is unavailable", async () => {
  jest.useFakeTimers();
  global.WebSocket = class {
    constructor() {
      throw new Error("socket unavailable");
    }
  };
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    canFinalize: true,
  });
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  expect(await screen.findByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getByText("Fallback polling active")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(15000);
    await Promise.resolve();
  });

  expect(fetchOwnerAuctionConsole).toHaveBeenCalledTimes(2);
});

test("finalizes the auction session and refreshes the console with the updated result", async () => {
  const user = userEvent.setup();

  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    canFinalize: true,
  });
  finalizeAuctionSession.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    finalizationMessage: "Auction closed and finalized.",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  await screen.findByRole("heading", { name: /Auction Session 44/i });
  await user.click(screen.getByRole("button", { name: /Close and finalize auction/i }));

  await waitFor(() => {
    expect(finalizeAuctionSession).toHaveBeenCalledWith(44);
  });

  expect(await screen.findByText(/Auction closed and finalized/i)).toBeInTheDocument();
  expect(screen.getByText(/Winner membership/i)).toBeInTheDocument();
  expect(screen.getByText(/Owner commission/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Finalized result/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Payout breakdown/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Close and finalize auction/i })).toBeDisabled();
});

test("hydrates the finalized owner console view from the nested finalize response summary", async () => {
  const user = userEvent.setup();

  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    canFinalize: true,
  });
  finalizeAuctionSession.mockResolvedValueOnce({
    sessionId: 44,
    groupId: 11,
    auctionMode: "LIVE",
    commissionMode: "PERCENTAGE",
    commissionValue: 5,
    cycleNo: 3,
    status: "finalized",
    closedAt: "2026-04-20T09:35:00Z",
    finalizedAt: "2026-04-20T09:40:00Z",
    closedByUserId: 1,
    finalizedByUserId: 1,
    finalizedByName: "Owner One",
    finalizationMessage: "Auction closed and finalized.",
    console: {
      sessionId: 44,
      groupTitle: "July Chit",
      groupCode: "JUL-001",
      auctionMode: "LIVE",
      commissionMode: "PERCENTAGE",
      commissionValue: 5,
      auctionState: "FINALIZED",
      cycleNo: 3,
      status: "finalized",
      totalBidCount: 6,
      validBidCount: 4,
      highestBidAmount: 12500,
      highestBidMembershipNo: 7,
      highestBidderName: "Ravi",
      canFinalize: false,
      finalizedAt: "2026-04-20T09:40:00Z",
      finalizedByName: "Owner One",
      winnerMembershipNo: 7,
      winnerName: "Ravi",
      winningBidAmount: 12500,
      ownerCommissionAmount: 500,
      dividendPoolAmount: 12000,
      dividendPerMemberAmount: 600,
      winnerPayoutAmount: 11500,
      finalizationMessage: "Auction closed and finalized.",
    },
    resultSummary: {
      sessionId: 44,
      status: "finalized",
      totalBids: 6,
      validBidCount: 4,
      winnerMembershipId: 7,
      winnerMembershipNo: 7,
      winnerName: "Ravi",
      winningBidId: 18,
      winningBidAmount: 12500,
      ownerCommissionAmount: 500,
      dividendPoolAmount: 12000,
      dividendPerMemberAmount: 600,
      winnerPayoutAmount: 11500,
    },
  });
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  await screen.findByRole("heading", { name: /Auction Session 44/i });
  await user.click(screen.getByRole("button", { name: /Close and finalize auction/i }));

  expect(await screen.findByText(/Auction closed and finalized/i)).toBeInTheDocument();
  expect(screen.getAllByText(/Ravi #7/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/12,500/).length).toBeGreaterThan(0);
});

test("keeps the console visible when finalize fails", async () => {
  const user = userEvent.setup();

  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    canFinalize: true,
  });
  finalizeAuctionSession.mockRejectedValueOnce({
    response: {
      status: 409,
      data: {
        detail: "Auction cannot be finalized yet.",
      },
    },
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  await screen.findByRole("heading", { name: /Auction Session 44/i });
  await user.click(screen.getByRole("button", { name: /Close and finalize auction/i }));

  expect(await screen.findByText(/Auction cannot be finalized yet/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Auction Session 44/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Close and finalize auction/i })).toBeEnabled();
});

test("refreshes the snapshot manually without dropping the finalized payout view", async () => {
  const user = userEvent.setup();

  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "open",
    actualEndAt: "2026-04-20T09:35:00Z",
    serverTime: "2026-04-20T09:33:00Z",
    validBidCount: 4,
    totalBidCount: 6,
    highestBidAmount: 12500,
    highestBidMembershipNo: 7,
    highestBidderName: "Ravi",
    canFinalize: true,
  });
  fetchOwnerAuctionConsole.mockResolvedValueOnce({
    sessionId: 44,
    groupTitle: "July Chit",
    groupCode: "JUL-001",
    cycleNo: 3,
    status: "finalized",
    actualEndAt: "2026-04-20T09:35:00Z",
    serverTime: "2026-04-20T09:40:00Z",
    finalizedAt: "2026-04-20T09:40:00Z",
    finalizedByName: "Owner One",
    winnerMembershipNo: 7,
    winnerName: "Ravi",
    winningBidAmount: 12500,
    ownerCommissionAmount: 500,
    dividendPoolAmount: 12000,
    dividendPerMemberAmount: 600,
    winnerPayoutAmount: 11500,
    totalBidCount: 6,
    validBidCount: 4,
    canFinalize: false,
  });

  render(<OwnerAuctionConsole sessionId={44} />);

  await screen.findByRole("heading", { name: /Auction Session 44/i });
  await user.click(screen.getByRole("button", { name: /Refresh snapshot/i }));

  expect(fetchOwnerAuctionConsole).toHaveBeenCalledTimes(2);
  expect(await screen.findByText(/Finalized result/i)).toBeInTheDocument();
  expect(screen.getByText(/Winner membership/i)).toBeInTheDocument();
  expect(screen.getByText(/Winner payout/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Close and finalize auction/i })).toBeDisabled();
});
