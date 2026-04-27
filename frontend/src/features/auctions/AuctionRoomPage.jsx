import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { FormField, FormFrame } from "../../components/form-primitives";
import { PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { toast } from "../../hooks/use-toast";
import { getApiErrorMessage } from "../../lib/api-error";
import { fetchAuctionRoom, submitBid } from "./api";
import { createInitialRoomState } from "./room-store";
import { createAuctionSocket } from "./socket-client";

const SOCKET_FALLBACK_POLL_MS = 15000;
const SOCKET_CONNECT_TIMEOUT_MS = 3000;

function parseDate(value) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatCountdown(remainingMs) {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (value) => String(value).padStart(2, "0");

  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }

  return `${pad(minutes)}:${pad(seconds)}`;
}

function getRoomResult(room) {
  return room?.auctionResult ?? room?.closeResult ?? room?.result ?? room?.finalResult ?? null;
}

function isNoBidFinalization(room, result) {
  if (result) {
    return false;
  }

  const status = String(room?.status ?? "").toLowerCase();
  const validBidCount = Number(room?.validBidCount);
  const finalizationMessage = String(room?.finalizationMessage ?? "").toLowerCase();

  return (
    status === "finalized" &&
    ((Number.isFinite(validBidCount) && validBidCount === 0) || finalizationMessage.includes("no bids"))
  );
}

function getAuctionModeLabel(mode) {
  const normalized = String(mode ?? "LIVE").toUpperCase();
  if (normalized === "BLIND") {
    return "Blind auction";
  }
  if (normalized === "FIXED") {
    return "Fixed auction";
  }
  return "Live auction";
}

function getBidWindowLabel(room, now) {
  const startsAt = parseDate(room?.startsAt);
  const endsAt = parseDate(room?.endsAt);
  if (!endsAt) {
    return null;
  }

  if (startsAt && now < startsAt.getTime()) {
    return `Opens in ${formatCountdown(startsAt.getTime() - now)}`;
  }

  const remainingMs = endsAt.getTime() - now;
  if (room?.status !== "open" || remainingMs <= 0) {
    return "Closed";
  }

  return `Closes in ${formatCountdown(remainingMs)}`;
}

function getStatusLabel(room, now) {
  if (!room?.sessionId) {
    return "";
  }

  const status = String(room.status ?? "").toLowerCase();
  const endsAt = parseDate(room?.endsAt);
  const isWindowOpen = status === "open" && (!endsAt || endsAt.getTime() > now);

  if (isWindowOpen) {
    return "Open";
  }

  if (status === "scheduled") {
    return "Scheduled";
  }

  if (status === "closed" || status === "settled" || status === "finalized") {
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  if (status === "open") {
    return "Closed";
  }

  return status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown";
}

function getAuctionPhaseLabel(room, result, now) {
  if (isNoBidFinalization(room, result)) {
    return "No bids received";
  }

  const auctionState = String(room?.auctionState ?? "").toUpperCase();
  if (auctionState === "UPCOMING") {
    return "Bidding not started";
  }
  if (auctionState === "OPEN") {
    return "Bidding open";
  }
  if (auctionState === "ENDED") {
    return result ? "Finalized" : "Bidding ended";
  }
  if (auctionState === "FINALIZED") {
    return "Finalized";
  }

  if (result) {
    return "Finalized";
  }

  const status = String(room?.status ?? "").toLowerCase();
  const bidWindowLabel = getBidWindowLabel(room, now);

  if (status === "open" && bidWindowLabel?.startsWith("Closes in")) {
    return "Bidding open";
  }

  if (status === "closed") {
    return "Closed, result pending";
  }

  if (status === "settled") {
    return "Settled";
  }

  if (status === "finalized") {
    return "Finalized";
  }

  if (status === "scheduled") {
    return "Scheduled";
  }

  return getStatusLabel(room, now) || "Unknown";
}

function getWinnerLabel(result) {
  if (!result) {
    return null;
  }

  if (result.winnerName) {
    return result.winnerName;
  }

  if (result.winnerDisplayName) {
    return result.winnerDisplayName;
  }

  if (result.winnerMemberNo != null) {
    return `Member #${result.winnerMemberNo}`;
  }

  if (result.winnerMembershipId != null) {
    return `Membership #${result.winnerMembershipId}`;
  }

  return "Winner unavailable";
}

function formatWinningBid(result) {
  const amount = result?.winningBidAmount ?? result?.winningBid ?? result?.bidAmount;
  if (amount == null) {
    return null;
  }

  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(Number(amount));
}

function formatBidRuleValue(value) {
  if (value == null) {
    return null;
  }

  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(value));
}

function getNumericRoomValue(...values) {
  for (const value of values) {
    if (value == null || value === "") {
      continue;
    }

    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
}

function getRemainingBidCapacity(room) {
  const totalBids = getNumericRoomValue(room?.myBidLimit, room?.bidCapacityTotal, room?.maxBidCount);
  const remainingBids = getNumericRoomValue(
    room?.myRemainingBidCapacity,
    room?.remainingBidCount,
    room?.remainingBids,
    room?.bidCapacityRemaining,
    room?.availableBidCount,
  );
  const usedBids = getNumericRoomValue(room?.myBidCount, room?.usedBidCount, room?.spentBidCount);

  if (totalBids == null && remainingBids == null && usedBids == null) {
    return null;
  }

  const normalizedRemainingBids =
    remainingBids ?? (totalBids != null && usedBids != null ? Math.max(0, totalBids - usedBids) : null);

  return {
    totalBids,
    remainingBids: normalizedRemainingBids,
  };
}

function formatRemainingBidCapacity(capacity) {
  if (!capacity) {
    return null;
  }

  const { totalBids, remainingBids } = capacity;
  if (remainingBids == null && totalBids == null) {
    return null;
  }

  if (totalBids != null && remainingBids != null) {
    return `${remainingBids} of ${totalBids}`;
  }

  if (remainingBids != null) {
    return `${remainingBids}`;
  }

  return `${totalBids}`;
}

function getSlotSummary(room, remainingBidCapacity) {
  const owned = getNumericRoomValue(
    room?.mySlotCount,
    room?.slotCount,
    room?.ownedSlotCount,
    room?.membershipSlotCount,
    remainingBidCapacity?.totalBids,
  );
  const won = getNumericRoomValue(room?.myWonSlotCount, room?.wonSlotCount, room?.consumedSlotCount, room?.usedSlotCount) ?? 0;
  const remaining =
    getNumericRoomValue(
      room?.myRemainingSlotCount,
      room?.remainingSlotCount,
      room?.eligibleSlotCount,
      remainingBidCapacity?.remainingBids,
    ) ??
    (owned != null ? Math.max(owned - won, 0) : null);

  return {
    owned,
    won,
    remaining,
  };
}

function getBidRuleConfig(room) {
  const minBid = getNumericRoomValue(
    room?.minBidValue,
    room?.minBid,
    room?.minBidAmount,
    room?.minimumBid,
    room?.minimumBidAmount,
    room?.minimumAllowedBid,
  );
  const maxBid = getNumericRoomValue(
    room?.maxBidValue,
    room?.maxBid,
    room?.maxBidAmount,
    room?.maximumBid,
    room?.maximumBidAmount,
    room?.maximumAllowedBid,
  );
  const minIncrement = getNumericRoomValue(
    room?.minIncrement,
    room?.minIncrementAmount,
    room?.minBidIncrement,
    room?.minimumIncrement,
    room?.minimumBidIncrement,
    room?.bidIncrement,
  );

  if (minBid == null && maxBid == null && minIncrement == null) {
    return null;
  }

  return {
    minBid,
    maxBid,
    minIncrement,
  };
}

function formatBidRuleSummary(rules) {
  if (!rules) {
    return null;
  }

  const parts = [];
  if (rules.minBid != null) {
    parts.push(`Min ${formatBidRuleValue(rules.minBid)}`);
  }
  if (rules.maxBid != null) {
    parts.push(`Max ${formatBidRuleValue(rules.maxBid)}`);
  }
  if (rules.minIncrement != null) {
    parts.push(`Increment ${formatBidRuleValue(rules.minIncrement)}`);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

function formatCurrencyAmount(value) {
  if (value == null || value === "") {
    return "Not available";
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatActivityTime(value) {
  const parsed = parseDate(value);
  if (!parsed) {
    return "Just now";
  }

  return new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function getHighestBidAmount(room, result, isBlindMode) {
  if (result?.winningBidAmount != null) {
    return result.winningBidAmount;
  }

  if (isBlindMode) {
    return null;
  }

  const roomHighestBid = getNumericRoomValue(
    room?.highestBidAmount,
    room?.currentHighestBid,
    room?.currentBidAmount,
    room?.leadingBidAmount,
  );
  if (roomHighestBid != null) {
    return roomHighestBid;
  }

  const recentBids = Array.isArray(room?.recentBids) ? room.recentBids : [];
  const feedHighestBid = recentBids.reduce((highestBid, entry) => {
    const bidAmount = getNumericRoomValue(entry?.bidAmount, entry?.amount, entry?.value, entry?.highestBidAmount);
    if (bidAmount == null) {
      return highestBid;
    }
    return highestBid == null ? bidAmount : Math.max(highestBid, bidAmount);
  }, null);

  return feedHighestBid;
}

function getHighestBidLabel({ room, result, isBlindMode }) {
  if (result?.winningBidAmount != null) {
    return formatCurrencyAmount(result.winningBidAmount);
  }

  if (isBlindMode) {
    return "Hidden";
  }

  const highestBidAmount = getHighestBidAmount(room, result, isBlindMode);
  if (highestBidAmount != null) {
    return formatCurrencyAmount(highestBidAmount);
  }

  return "Waiting";
}

function getHighestBidDetail({ room, result, isBlindMode }) {
  if (result?.winningBidAmount != null) {
    return "Final winning bid";
  }

  if (isNoBidFinalization(room, result)) {
    return "No bids were submitted in this round.";
  }

  if (isBlindMode) {
    return "Blind bids stay hidden until finalization.";
  }

  const bidderName = room?.highestBidderName;
  if (bidderName) {
    return `Leading bidder: ${bidderName}`;
  }

  const membershipNo = room?.highestBidMembershipNo;
  if (membershipNo != null) {
    return `Leading member: #${membershipNo}`;
  }

  return "Current leader is not published in this room feed.";
}

function normalizeBidFeedEntry(entry, index) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const bidAmount = getNumericRoomValue(
    entry.bidAmount,
    entry.amount,
    entry.value,
    entry.highestBidAmount,
  );
  const createdAt = entry.placedAt ?? entry.createdAt ?? entry.timestamp ?? entry.occurredAt ?? null;
  const label =
    entry.label ??
    (bidAmount != null
      ? `Bid ${formatCurrencyAmount(bidAmount)}`
      : "Live bid update");
  const detail =
    entry.detail ??
    entry.message ??
    (entry.bidderName
      ? `Submitted by ${entry.bidderName}`
      : entry.bidId != null
        ? `Bid #${entry.bidId} reached the room`
        : "A new bid was submitted in this room.");

  return {
    id: entry.id ?? entry.bidId ?? `feed-${index}-${createdAt ?? "now"}`,
    label,
    detail,
    timeLabel: formatActivityTime(createdAt),
    isLatest: Boolean(entry.isLatest ?? index === 0),
  };
}

function getDecimalPlaces(value) {
  const text = String(value);
  if (!text.includes(".")) {
    return 0;
  }

  return text.split(".")[1].length;
}

function isIncrementAligned(amount, step, base = 0) {
  if (step == null || step <= 0) {
    return true;
  }

  const decimals = Math.max(getDecimalPlaces(amount), getDecimalPlaces(step), getDecimalPlaces(base));
  const factor = 10 ** Math.min(decimals, 6);
  const scaledDifference = Math.round((amount - base) * factor);
  const scaledStep = Math.round(step * factor);

  if (scaledStep === 0) {
    return true;
  }

  return scaledDifference % scaledStep === 0;
}

function getBidValidationError(bidAmount, rules) {
  if (!bidAmount) {
    return "";
  }

  const amount = Number(bidAmount);
  if (!Number.isFinite(amount)) {
    return "Enter a valid bid amount.";
  }

  if (amount <= 0) {
    return "Enter a bid amount greater than 0.";
  }

  if (rules?.minBid != null && amount < rules.minBid) {
    return `Bid must be at least ${formatBidRuleValue(rules.minBid)}.`;
  }

  if (rules?.maxBid != null && amount > rules.maxBid) {
    return `Bid cannot exceed ${formatBidRuleValue(rules.maxBid)}.`;
  }

  if (rules?.minIncrement != null) {
    const incrementBase = rules.minBid ?? 0;
    if (!isIncrementAligned(amount, rules.minIncrement, incrementBase)) {
      return `Bid must move in increments of ${formatBidRuleValue(rules.minIncrement)}${rules.minBid != null ? ` from ${formatBidRuleValue(rules.minBid)}` : ""}.`;
    }
  }

  return "";
}

function extractResultFromResponse(response) {
  const nestedResult = getRoomResult(response);
  if (nestedResult) {
    return nestedResult;
  }

  const directFields = [
    "winnerMembershipId",
    "winnerMemberNo",
    "winnerName",
    "winnerDisplayName",
    "winningBidAmount",
    "winningBid",
    "bidAmount",
    "finalizedAt",
    "closedAt",
  ];

  if (directFields.some((field) => response?.[field] != null)) {
    return response;
  }

  return null;
}

export default function AuctionRoomPage({ embedded = false, sessionId: sessionIdProp } = {}) {
  const { sessionId: routeSessionId = "1" } = useParams();
  const sessionId = sessionIdProp ?? routeSessionId;
  const [room, setRoom] = useState(createInitialRoomState());
  const [bidAmount, setBidAmount] = useState("");
  const [feedback, setFeedback] = useState({ type: "", text: "" });
  const [liveActivity, setLiveActivity] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [connectionState, setConnectionState] = useState("connecting");
  const [serverClockOffsetMs, setServerClockOffsetMs] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const isActiveRef = useRef(true);
  const latestSessionIdRef = useRef(String(sessionId));

  useEffect(() => {
    isActiveRef.current = true;

    return () => {
      isActiveRef.current = false;
    };
  }, []);

  useEffect(() => {
    latestSessionIdRef.current = String(sessionId);
  }, [sessionId]);

  const pushLiveActivity = useCallback((entry) => {
    if (!entry) {
      return;
    }

    setLiveActivity((currentEntries) => {
      const nextEntry = {
        ...entry,
        isLatest: true,
      };
      const remainingEntries = currentEntries
        .filter((currentEntry) => currentEntry.id !== nextEntry.id)
        .map((currentEntry) => ({
          ...currentEntry,
          isLatest: false,
        }));

      return [nextEntry, ...remainingEntries].slice(0, 6);
    });
  }, []);

  useEffect(() => {
    setLiveActivity([]);
  }, [sessionId]);

  const loadAuctionRoom = useCallback(
    async ({ reportError = true } = {}) => {
      const requestedSessionId = String(sessionId);
      try {
        const data = await fetchAuctionRoom(sessionId);
        if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
          return false;
        }
        if (data && typeof data === "object") {
          setRoom(data);
          setLastSyncedAt(new Date());
          const serverTime = parseDate(data.serverTime);
          if (serverTime) {
            setServerClockOffsetMs(serverTime.getTime() - Date.now());
            setNow(serverTime.getTime());
          }
        }
        return true;
      } catch (_error) {
        if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
          return false;
        }
        if (reportError) {
          setFeedback({ type: "error", text: "Unable to refresh the auction room." });
        }
        return false;
      }
    },
    [sessionId],
  );

  useEffect(() => {
    const intervalId = setInterval(() => {
      setNow(Date.now() + serverClockOffsetMs);
    }, 1000);

    return () => {
      clearInterval(intervalId);
    };
  }, [serverClockOffsetMs]);

  useEffect(() => {
    let isMounted = true;

    setLoading(true);
    Promise.resolve(loadAuctionRoom({ reportError: false }))
      .then((loaded) => {
        if (isMounted && !loaded) {
          setRoom({
            sessionId: null,
            status: "error",
          });
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [loadAuctionRoom]);

  useEffect(() => {
    let active = true;
    let pollIntervalId = null;
    let connectTimeoutId = null;
    const unsubscribeHandlers = [];

    const startPolling = () => {
      if (!active || pollIntervalId !== null) {
        return;
      }

      setConnectionState("fallback");
      pollIntervalId = setInterval(() => {
        void loadAuctionRoom({ reportError: false });
      }, SOCKET_FALLBACK_POLL_MS);
    };

    const stopPolling = () => {
      if (pollIntervalId !== null) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
      }
    };

    const handleConnect = () => {
      if (!active) {
        return;
      }

      setConnectionState("connected");
      if (connectTimeoutId !== null) {
        clearTimeout(connectTimeoutId);
        connectTimeoutId = null;
      }
      stopPolling();
    };

    const handleDisconnect = () => {
      if (!active) {
        return;
      }

      startPolling();
    };

    const handleUpdate = () => {
      void loadAuctionRoom({ reportError: false });
    };

    const handleBidPlaced = (detail) => {
      const nextRoom = detail?.payload?.room;
      const serverTime = parseDate(nextRoom?.serverTime);

      pushLiveActivity({
        id: `socket-bid-${detail?.payload?.bidId ?? serverTime?.toISOString() ?? Date.now()}`,
        label: "New live bid",
        detail: "A bid was submitted to this room.",
        placedAt: serverTime?.toISOString() ?? new Date().toISOString(),
      });

      if (nextRoom && typeof nextRoom === "object") {
        setRoom((currentRoom) => ({
          ...currentRoom,
          ...nextRoom,
        }));
      }

      void loadAuctionRoom({ reportError: false });
    };

    let socket = null;

    try {
      socket = createAuctionSocket({ sessionId });
    } catch (_error) {
      startPolling();
      return () => {
        active = false;
        if (connectTimeoutId !== null) {
          clearTimeout(connectTimeoutId);
        }
        stopPolling();
      };
    }

    if (!socket || typeof socket.connect !== "function") {
      startPolling();
      return () => {
        active = false;
        if (connectTimeoutId !== null) {
          clearTimeout(connectTimeoutId);
        }
        stopPolling();
      };
    }

    setConnectionState("connecting");

    if (typeof socket.on === "function") {
      const register = (event, handler) => {
        const unsubscribe = socket.on(event, handler);
        if (typeof unsubscribe === "function") {
          unsubscribeHandlers.push(unsubscribe);
        }
      };

      register("connect", handleConnect);
      register("disconnect", handleDisconnect);
      register("connect_error", handleDisconnect);
      register("error", handleDisconnect);
      register("auction-room-updated", handleUpdate);
      register("auction-session-updated", handleUpdate);
      register("auction-updated", handleUpdate);
      register("room-updated", handleUpdate);
      register("finalized", handleUpdate);
      register("auction.snapshot", handleUpdate);
      register("auction.bid.placed", handleBidPlaced);
      register("auction.finalized", handleUpdate);
    } else {
      startPolling();
    }

    connectTimeoutId = setTimeout(() => {
      if (active) {
        startPolling();
      }
    }, SOCKET_CONNECT_TIMEOUT_MS);

    try {
      socket.connect();
    } catch (_error) {
      startPolling();
    }

    return () => {
      active = false;
      if (connectTimeoutId !== null) {
        clearTimeout(connectTimeoutId);
      }
      stopPolling();
      unsubscribeHandlers.forEach((unsubscribe) => {
        try {
          unsubscribe();
        } catch (_error) {
          // Ignore cleanup failures while tearing down the socket.
        }
      });
      if (typeof socket.disconnect === "function") {
        socket.disconnect();
      }
    };
  }, [loadAuctionRoom, pushLiveActivity, sessionId]);

  async function handleRefresh() {
    const requestedSessionId = String(sessionId);
    if (!room.sessionId || loading || refreshing) {
      return;
    }

    setRefreshing(true);
    setFeedback({ type: "", text: "" });
    try {
      const loaded = await loadAuctionRoom();
      if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
        return;
      }
      if (!loaded) {
        setFeedback({ type: "error", text: "Unable to refresh the auction room." });
      }
    } catch (_error) {
      if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
        return;
      }
      setFeedback({ type: "error", text: "Unable to refresh the auction room." });
    } finally {
      if (isActiveRef.current && latestSessionIdRef.current === requestedSessionId) {
        setRefreshing(false);
      }
    }
  }

  async function handleBidSubmit(event) {
    event.preventDefault();

    if (submitting) {
      return;
    }

    const requestedSessionId = String(sessionId);
    const amount = Number(bidAmount);
    if (!room.sessionId || !room.myMembershipId || !bidAmount || Number.isNaN(amount)) {
      return;
    }

    const clientValidationError = getBidValidationError(bidAmount, getBidRuleConfig(room));
    if (clientValidationError) {
      setFeedback({ type: "error", text: clientValidationError });
      return;
    }

    const previousRoom = room;
    const optimisticActivityId = `self-bid-${room.sessionId}-${room.myMembershipId}-${amount}-optimistic`;
    const placedAt = new Date().toISOString();
    setSubmitting(true);
    setFeedback({ type: "success", text: isBlindMode ? "Submitting your bid..." : `Submitting ${formatCurrencyAmount(amount)}...` });
    setRoom((currentRoom) => ({
      ...currentRoom,
      myLastBid: amount,
      myBidCount:
        currentRoom.myBidCount != null && Number.isFinite(Number(currentRoom.myBidCount))
          ? Number(currentRoom.myBidCount) + 1
          : currentRoom.myBidCount,
      myRemainingBidCapacity:
        currentRoom.myRemainingBidCapacity != null && Number.isFinite(Number(currentRoom.myRemainingBidCapacity))
          ? Math.max(Number(currentRoom.myRemainingBidCapacity) - 1, 0)
          : currentRoom.myRemainingBidCapacity,
    }));
    if (!isBlindMode && !isFixedMode) {
      pushLiveActivity({
        id: optimisticActivityId,
        label: `Your bid ${formatCurrencyAmount(amount)}`,
        detail: "Syncing with the auction room.",
        placedAt,
      });
    }
    try {
      const bid = await submitBid(room.sessionId, {
        membershipId: room.myMembershipId,
        bidAmount: amount,
        idempotencyKey: `${room.sessionId}-${room.myMembershipId}-${bidAmount}`,
      });
      const nextStatus = bid.sessionStatus ?? bid.auctionStatus ?? bid.status;
      const nextResult = extractResultFromResponse(bid);
      const nextPlacedAt = parseDate(bid.placedAt);
      const nextRoomSnapshot = bid?.room && typeof bid.room === "object" ? bid.room : null;
      if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
        return;
      }
      setFeedback({
        type: "success",
        text: isBlindMode ? "Your bid is submitted." : `Bid accepted at ${new Date(bid.placedAt).toLocaleTimeString()}`,
      });
      toast({
        title: "Bid placed",
        description: isBlindMode
          ? "Your blind bid was submitted successfully."
          : `${formatCurrencyAmount(amount)} submitted to the live room.`,
      });
      if (!isBlindMode && !isFixedMode) {
        pushLiveActivity({
          id: optimisticActivityId,
          label: `Your bid ${formatCurrencyAmount(amount)}`,
          detail: "Submitted from this device.",
          placedAt: bid.placedAt,
        });
      }
      if (nextRoomSnapshot) {
        setRoom({
          ...nextRoomSnapshot,
          ...(nextResult ? { auctionResult: nextResult } : {}),
        });
      } else {
        const refreshed = await loadAuctionRoom({ reportError: false });
        if (!refreshed && isActiveRef.current && latestSessionIdRef.current === requestedSessionId) {
          setRoom((currentRoom) => ({
            ...currentRoom,
            status: nextStatus ?? currentRoom.status,
            myLastBid: amount,
            myBidCount:
              currentRoom.myBidCount != null && Number.isFinite(Number(currentRoom.myBidCount))
                ? Number(currentRoom.myBidCount) + 1
                : currentRoom.myBidCount,
            myRemainingBidCapacity:
              currentRoom.myRemainingBidCapacity != null &&
              Number.isFinite(Number(currentRoom.myRemainingBidCapacity))
                ? Math.max(Number(currentRoom.myRemainingBidCapacity) - 1, 0)
                : currentRoom.myRemainingBidCapacity,
            canBid:
              (nextStatus ?? currentRoom.status) === "open" &&
              currentRoom.canBid &&
              !(
                currentRoom.myRemainingBidCapacity != null &&
                Number.isFinite(Number(currentRoom.myRemainingBidCapacity)) &&
                Number(currentRoom.myRemainingBidCapacity) <= 1
              ),
            auctionState:
              (nextStatus ?? currentRoom.status) === "open"
                ? currentRoom.auctionState
                : nextResult
                  ? "FINALIZED"
                  : "ENDED",
            serverTime: nextPlacedAt ? nextPlacedAt.toISOString() : currentRoom.serverTime,
            ...(nextResult ? { auctionResult: nextResult } : {}),
          }));
        }
      }
      if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
        return;
      }
      if (nextPlacedAt) {
        setServerClockOffsetMs(nextPlacedAt.getTime() - Date.now());
        setNow(nextPlacedAt.getTime());
      }
      setBidAmount("");
    } catch (submitError) {
      if (!isActiveRef.current || latestSessionIdRef.current !== requestedSessionId) {
        return;
      }
      setRoom(previousRoom);
      setLiveActivity((currentEntries) => currentEntries.filter((entry) => entry.id !== optimisticActivityId));
      setFeedback({
        type: "error",
        text: getApiErrorMessage(submitError, { fallbackMessage: "Unable to place bid." }),
      });
    } finally {
      if (isActiveRef.current && latestSessionIdRef.current === requestedSessionId) {
        setSubmitting(false);
      }
    }
  }

  const statusLabel = getStatusLabel(room, now);
  const bidWindowLabel = getBidWindowLabel(room, now);
  const result = getRoomResult(room);
  const winningBid = formatWinningBid(result);
  const winnerLabel = getWinnerLabel(result);
  const auctionPhaseLabel = getAuctionPhaseLabel(room, result, now);
  const auctionState = String(room.auctionState ?? "").toUpperCase();
  const isAuctionOpen =
    auctionState === "OPEN" ||
    (!auctionState && String(room.status ?? "").toLowerCase() === "open" && bidWindowLabel !== "Closed");
  const refreshStateLabel = refreshing ? "Refreshing snapshot" : "Manual refresh ready";
  const freshnessLabel = lastSyncedAt ? lastSyncedAt.toLocaleTimeString() : "Waiting for the first snapshot";
  const connectionLabel =
    connectionState === "connected"
      ? "Connected"
      : connectionState === "fallback"
        ? "Fallback polling active"
        : "Connecting live updates";
  const auctionModeLabel = getAuctionModeLabel(room.auctionMode);
  const isBlindMode = String(room.auctionMode ?? "LIVE").toUpperCase() === "BLIND";
  const isFixedMode = String(room.auctionMode ?? "LIVE").toUpperCase() === "FIXED";
  const bidRules = getBidRuleConfig(room);
  const bidRuleSummary = formatBidRuleSummary(bidRules);
  const clientValidationError = getBidValidationError(bidAmount, bidRules);
  const remainingBidCapacity = getRemainingBidCapacity(room);
  const remainingBidLabel = formatRemainingBidCapacity(remainingBidCapacity);
  const slotSummary = getSlotSummary(room, remainingBidCapacity);
  const eligibilityCount = remainingBidCapacity?.remainingBids ?? slotSummary.remaining;
  const remainingBidsExhausted = remainingBidCapacity?.remainingBids === 0;
  const bidInputDisabled = submitting || !room.canBid || !isAuctionOpen || isFixedMode || remainingBidsExhausted;
  const submitDisabled = bidInputDisabled || Boolean(clientValidationError);
  const biddingDescription = isFixedMode
    ? "This fixed auction does not accept bids. The organizer will finalize it and the backend will auto-select the eligible winner."
    : remainingBidsExhausted
      ? "This auction room has no remaining bid capacity. You can still follow the room, but bidding is currently disabled."
      : isBlindMode
        ? "Submit your blind bid. Other bids stay hidden until the auction is finalized."
        : "Enter the bid amount you want to place in this live auction.";
  const biddingNote = isFixedMode
    ? "Fixed auctions skip bidding and move straight to organizer finalization."
    : remainingBidsExhausted
      ? "Remaining bid capacity has been exhausted for this room."
      : isBlindMode
        ? "Blind bids remain hidden until finalization."
        : "Bids can only be submitted while the auction is open.";
  const formErrorMessage = feedback.type === "error" ? feedback.text : clientValidationError;
  const ruleHint = bidRuleSummary ? `Bid rules: ${bidRuleSummary}.` : "";
  const shellContextLabel = room?.groupTitle
    ? `${room.groupTitle}${room.groupCode ? ` · ${room.groupCode}` : ""}`
    : room?.sessionId
      ? `Session ${room.sessionId} · ${auctionPhaseLabel}`
      : "Live round updates and bidding";
  const auctionDisplayName = room?.groupTitle ?? (room?.cycleNo ? `Cycle ${room.cycleNo} auction` : `${auctionModeLabel} room`);
  const highestBidLabel = getHighestBidLabel({ room, result, isBlindMode });
  const highestBidDetail = getHighestBidDetail({ room, result, isBlindMode });
  const timeLeftLabel = bidWindowLabel ?? statusLabel;
  const paymentSummaryLabel =
    result?.winningBidAmount != null
      ? formatCurrencyAmount(result.winningBidAmount)
      : room.myLastBid != null
        ? formatCurrencyAmount(room.myLastBid)
        : "Not placed";
  const liveBidFeed = useMemo(() => {
    const serverEntries = Array.isArray(room?.recentBids)
      ? room.recentBids.map((entry, index) => normalizeBidFeedEntry(entry, index)).filter(Boolean)
      : [];
    const localEntries = liveActivity.map((entry, index) => normalizeBidFeedEntry(entry, index)).filter(Boolean);
    const mergedEntries = [...localEntries, ...serverEntries];
    const dedupedEntries = [];
    const seenIds = new Set();

    for (const entry of mergedEntries) {
      if (seenIds.has(entry.id)) {
        continue;
      }
      seenIds.add(entry.id);
      dedupedEntries.push(entry);
    }

    return dedupedEntries.slice(0, 6);
  }, [liveActivity, room?.recentBids]);

  useSignedInShellHeader({
    title: auctionModeLabel,
    contextLabel: shellContextLabel,
  });

  const content = (
    <main className={embedded ? "auction-room" : "page-shell auction-room"}>
      {loading ? (
        <PageLoadingState description="Preparing the latest room snapshot and live bid feed." label="Loading auction room..." />
      ) : null}
      {!loading && room.sessionId ? (
        <>
          <section className="panel auction-hero">
            <div className="auction-hero__top">
              <div className="auction-status-row">
                <span className="auction-chip">{auctionModeLabel}</span>
                <span className="auction-chip">{statusLabel}</span>
                <span className="auction-chip">{auctionPhaseLabel}</span>
              </div>
              <button className="action-button auction-refresh-button" disabled={refreshing} onClick={handleRefresh} type="button">
                {refreshing ? "Refreshing..." : "Refresh auction room"}
              </button>
            </div>

            <div className="auction-hero__copy">
              <p className="auction-eyebrow">Auction name</p>
              <h1>{auctionDisplayName}</h1>
              <p>
                Session {room.sessionId} · Cycle {room.cycleNo}
              </p>
            </div>

            <div className="auction-metrics">
              <article className="auction-metric-card auction-metric-card--primary">
                <p className="auction-metric-label">Time left</p>
                <p className="auction-metric-value">{timeLeftLabel}</p>
                <p className="auction-metric-detail">
                  {isAuctionOpen ? "Live server time" : "Room status"}
                </p>
              </article>
              <article className="auction-metric-card">
                <p className="auction-metric-label">Current highest bid</p>
                <p className="auction-metric-value">{highestBidLabel}</p>
                <p className="auction-metric-detail">{highestBidDetail}</p>
              </article>
              <article className="auction-metric-card">
                <p className="auction-metric-label">Your last bid</p>
                <p className="auction-metric-value">{paymentSummaryLabel}</p>
                <p className="auction-metric-detail">
                  {room.myLastBid != null ? "Latest amount you submitted" : "No bid submitted yet"}
                </p>
              </article>
              <article className="auction-metric-card">
                <p className="auction-metric-label">Bid eligibility</p>
                <p className="auction-metric-value">
                  {eligibilityCount != null ? `You can bid ${eligibilityCount} more times` : remainingBidLabel ?? "Not available"}
                </p>
                <p className="auction-metric-detail">
                  {remainingBidsExhausted ? "Slot-based bid capacity exhausted" : "Slot-based bid eligibility"}
                </p>
              </article>
            </div>

            <div className="grid gap-3 sm:grid-cols-4">
              <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">You own</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {slotSummary.owned != null ? `${slotSummary.owned} chits` : "Not available"}
                </p>
              </article>
              <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Won</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {slotSummary.owned != null ? slotSummary.won : "Not available"}
                </p>
              </article>
              <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Remaining</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {slotSummary.remaining != null ? slotSummary.remaining : "Not available"}
                </p>
              </article>
              <article className="rounded-2xl border border-teal-200 bg-teal-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">Auction eligibility</p>
                <p className="mt-1 text-lg font-semibold text-teal-900">
                  {eligibilityCount != null ? `You can bid ${eligibilityCount} more times` : "Not available"}
                </p>
              </article>
            </div>

            <div className="auction-details">
              <p>
                <strong>Mode:</strong> {auctionModeLabel}
              </p>
              <p>
                <strong>Status:</strong> {statusLabel}
              </p>
              <p>
                <strong>State:</strong> {auctionPhaseLabel}
              </p>
              {bidWindowLabel ? (
                <p>
                  <strong>Window:</strong> {bidWindowLabel}
                </p>
              ) : null}
              {bidRuleSummary ? (
                <p>
                  <strong>Bid rules:</strong> {bidRuleSummary}
                </p>
              ) : null}
              {remainingBidsExhausted ? <p>Bidding capacity exhausted.</p> : null}
              {eligibilityCount != null ? (
                <p>
                  <strong>Eligibility:</strong> You can bid {eligibilityCount} more times.
                </p>
              ) : null}
              <p>
                <strong>Live connection:</strong> {connectionLabel}
              </p>
              <p>
                <strong>Live updates:</strong> {refreshStateLabel}
              </p>
              <p>
                <strong>Last checked:</strong> {freshnessLabel}
              </p>
            </div>
          </section>

          {feedback.type === "success" ? (
            <section className="panel auction-feedback auction-feedback--success">
              <p>{feedback.text}</p>
            </section>
          ) : null}

          {isBlindMode ? (
            <section className="panel auction-mode-panel">
              <h2>Blind auction</h2>
              <p>Other bids stay hidden until finalization. Only valid submissions are accepted during the blind window.</p>
              {feedback.type === "success" ? (
                <p className="auction-callout">Your bid is submitted.</p>
              ) : (
                <p className="auction-callout">Submit once the amount passes the bid rules shown below.</p>
              )}
            </section>
          ) : null}

          {!isBlindMode && !isFixedMode ? (
            <section className="panel auction-mode-panel">
              <div className="auction-section-header">
                <div>
                  <h2>Live bids</h2>
                  <p>Realtime room activity appears here as the feed updates.</p>
                </div>
              </div>
              {liveBidFeed.length === 0 ? (
                <div className="auction-empty-state">
                  <p>No live bid updates yet.</p>
                  <p>The list will refresh as soon as the room receives its first bid event.</p>
                </div>
              ) : (
                <div className="auction-bid-feed">
                  {liveBidFeed.map((entry) => (
                    <article
                      className={`auction-bid-feed__item${entry.isLatest ? " auction-bid-feed__item--latest" : ""}`}
                      key={entry.id}
                    >
                      <div>
                        <p className="auction-bid-feed__label">{entry.label}</p>
                        <p className="auction-bid-feed__detail">{entry.detail}</p>
                      </div>
                      <p className="auction-bid-feed__time">{entry.timeLabel}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          ) : null}

          {isFixedMode ? (
            <section className="panel auction-mode-panel">
              <h2>Fixed mode</h2>
              <p>This round assigned to organizer.</p>
              <p>The bidding UI stays hidden because the organizer finalizes the auto-assigned outcome.</p>
            </section>
          ) : null}

          <section className="panel">
            <div className="auction-section-header">
              <div>
                <h2>Finalized result</h2>
                <p>When the backend finalizes the session, the room shows the winner and settlement details here.</p>
              </div>
            </div>
            {result ? (
              <>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <article className="panel">
                    <p className="text-sm text-slate-500">Winner</p>
                    <p className="text-lg font-semibold text-slate-900">{winnerLabel}</p>
                  </article>
                  <article className="panel">
                    <p className="text-sm text-slate-500">Winning bid</p>
                    <p className="text-lg font-semibold text-slate-900">{winningBid ?? "Not available"}</p>
                  </article>
                  <article className="panel">
                    <p className="text-sm text-slate-500">Finalized at</p>
                    <p className="text-lg font-semibold text-slate-900">
                      {result.finalizedAt ? new Date(result.finalizedAt).toLocaleString() : "Not available"}
                    </p>
                  </article>
                  <article className="panel">
                    <p className="text-sm text-slate-500">Payout snapshot</p>
                    <p className="text-lg font-semibold text-slate-900">
                      {room.status === "finalized" || room.status === "closed"
                        ? "Ready for settlement display"
                        : "Waiting for the final settlement payload"}
                    </p>
                  </article>
                </div>
              </>
            ) : isNoBidFinalization(room, result) ? (
              <p>No bids received in this auction.</p>
            ) : room.status !== "open" ? (
              <p>Auction closed. Result pending.</p>
            ) : null}
            {room.myLastBid != null ? <p>My last bid: {room.myLastBid}</p> : null}
          </section>
          {!isFixedMode ? (
            <FormFrame
              className="auction-bid-frame"
              description={biddingDescription}
              error={formErrorMessage}
              success=""
              title="Place a bid"
            >
              <form className="auction-form" onSubmit={handleBidSubmit}>
                <FormField
                  helpText={ruleHint || "Enter your bid amount and submit while the room is open."}
                  htmlFor="bidAmount"
                  label="Place Bid"
                >
                  <input
                    className="text-input"
                    disabled={bidInputDisabled}
                    id="bidAmount"
                    max={bidRules?.maxBid ?? undefined}
                    min={bidRules?.minBid ?? undefined}
                    onChange={(event) => setBidAmount(event.target.value)}
                    placeholder="Enter bid amount"
                    step={bidRules?.minIncrement ?? "any"}
                    type="number"
                    value={bidAmount}
                  />
                </FormField>

                {clientValidationError ? (
                  <p className="auction-validation-card" role="alert">
                    {clientValidationError}
                  </p>
                ) : null}

                <p className="auction-form-note">{biddingNote}</p>

                <div className="auction-mobile-cta">
                  <button className="action-button auction-submit-button" disabled={submitDisabled} type="submit">
                    {submitting ? "Submitting..." : "Submit Bid"}
                  </button>
                </div>
              </form>
            </FormFrame>
          ) : null}
        </>
      ) : null}
      {!loading && !room.sessionId ? (
        <section className="panel">
          <p>Unable to load the auction room.</p>
        </section>
      ) : null}
    </main>
  );

  return content;
}
