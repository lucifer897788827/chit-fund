import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { fetchAuctionRoom, submitBid } from "./api";
import { createInitialRoomState } from "./room-store";

export default function AuctionRoomPage() {
  const { sessionId = "1" } = useParams();
  const [room, setRoom] = useState(createInitialRoomState());
  const [bidAmount, setBidAmount] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let isMounted = true;

    Promise.resolve(fetchAuctionRoom(sessionId))
      .then((data) => {
        if (isMounted && data && typeof data === "object") {
          setRoom(data);
        }
      })
      .catch(() => {
        if (isMounted) {
          setRoom({
            sessionId: null,
            status: "error",
          });
        }
      });

    return () => {
      isMounted = false;
    };
  }, [sessionId]);

  async function handleBidSubmit(event) {
    event.preventDefault();
    if (!room.sessionId || !room.myMembershipId || !bidAmount) {
      return;
    }

    setSubmitting(true);
    setMessage("");
    try {
      const bid = await submitBid(room.sessionId, {
        membershipId: room.myMembershipId,
        bidAmount: Number(bidAmount),
        idempotencyKey: `${room.sessionId}-${room.myMembershipId}-${bidAmount}`,
      });
      setMessage(`Bid accepted at ${new Date(bid.placedAt).toLocaleTimeString()}`);
      setRoom((currentRoom) => ({
        ...currentRoom,
        myLastBid: Number(bidAmount),
      }));
      setBidAmount("");
    } catch (_error) {
      setMessage("Unable to place bid.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <h1>Live Auction</h1>
      <p>
        {room.sessionId
          ? `Session ${room.sessionId} is ${room.status}`
          : "Loading..."}
      </p>
      {room.sessionId ? (
        <form className="auction-form" onSubmit={handleBidSubmit}>
          <label className="field-label" htmlFor="bidAmount">
            Place Bid
          </label>
          <input
            className="text-input"
            id="bidAmount"
            onChange={(event) => setBidAmount(event.target.value)}
            placeholder="Enter bid amount"
            type="number"
            value={bidAmount}
          />
          <button className="action-button" disabled={submitting || !room.canBid} type="submit">
            {submitting ? "Submitting..." : "Submit Bid"}
          </button>
        </form>
      ) : null}
      {room.myLastBid ? <p>My last bid: {room.myLastBid}</p> : null}
      {message ? <p>{message}</p> : null}
    </main>
  );
}
