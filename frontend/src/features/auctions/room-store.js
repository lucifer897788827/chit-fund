export function createInitialRoomState() {
  return {
    sessionId: null,
    status: "loading",
    myBidCount: null,
    myBidLimit: null,
    myRemainingBidCapacity: null,
    minBid: null,
    maxBid: null,
    minIncrement: null,
  };
}
