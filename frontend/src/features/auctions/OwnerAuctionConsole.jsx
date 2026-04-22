import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { getApiErrorMessage } from "../../lib/api-error";
import { fetchOwnerAuctionConsole, finalizeAuctionSession } from "./api";
import { createAuctionSocket } from "./socket-client";

const SOCKET_FALLBACK_POLL_MS = 15000;
const SOCKET_CONNECT_TIMEOUT_MS = 3000;

function formatDateTime(value) {
  if (!value) {
    return "Not available";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

function formatAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }

  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) {
    return String(value);
  }

  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(numericValue);
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

function parseDate(value) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getCountdownLabel(consoleData) {
  const startsAt = parseDate(consoleData?.startTime ?? consoleData?.actualStartAt ?? consoleData?.scheduledStartAt);
  const endsAt = parseDate(consoleData?.endTime ?? consoleData?.actualEndAt);
  const serverTime = parseDate(consoleData?.serverTime) ?? new Date();

  if (startsAt && serverTime < startsAt) {
    return `Opens in ${formatCountdown(startsAt.getTime() - serverTime.getTime())}`;
  }

  if (!endsAt) {
    return "Not available";
  }

  if (String(consoleData?.auctionState ?? "").toUpperCase() === "ENDED") {
    return "Closed";
  }

  const remainingMs = endsAt.getTime() - serverTime.getTime();
  if (remainingMs <= 0) {
    return "Closed";
  }

  return `Closes in ${formatCountdown(remainingMs)}`;
}

function getAuctionStateLabel(auctionState) {
  const normalized = String(auctionState ?? "").toUpperCase();
  if (normalized === "UPCOMING") {
    return "Bidding not started";
  }
  if (normalized === "OPEN") {
    return "Bidding open";
  }
  if (normalized === "ENDED") {
    return "Bidding ended";
  }
  if (normalized === "FINALIZED") {
    return "Finalized";
  }
  return normalized || "Unknown";
}

function normalizeConsoleResponse(payload, fallbackSessionId) {
  const session =
    payload?.console && typeof payload.console === "object"
      ? payload.console
      : payload?.session && typeof payload.session === "object"
        ? payload.session
        : payload ?? {};
  const result = payload?.result && typeof payload.result === "object" ? payload.result : null;
  const summary = payload?.resultSummary && typeof payload.resultSummary === "object" ? payload.resultSummary : null;
  const status = session.status ?? payload?.status ?? "unknown";

  return {
    sessionId: session.sessionId ?? payload?.sessionId ?? fallbackSessionId ?? null,
    groupTitle: session.groupTitle ?? payload?.groupTitle ?? "",
    groupCode: session.groupCode ?? payload?.groupCode ?? "",
    auctionMode: session.auctionMode ?? payload?.auctionMode ?? "LIVE",
    commissionMode: session.commissionMode ?? payload?.commissionMode ?? "NONE",
    commissionValue: session.commissionValue ?? payload?.commissionValue ?? null,
    auctionState: session.auctionState ?? payload?.auctionState ?? "UNKNOWN",
    cycleNo: session.cycleNo ?? payload?.cycleNo ?? null,
    status,
    canFinalize: Boolean(session.canFinalize ?? payload?.canFinalize ?? status === "open"),
    scheduledStartAt: session.scheduledStartAt ?? payload?.scheduledStartAt ?? null,
    actualStartAt: session.actualStartAt ?? payload?.actualStartAt ?? null,
    actualEndAt: session.actualEndAt ?? payload?.actualEndAt ?? null,
    startTime: session.startTime ?? payload?.startTime ?? null,
    endTime: session.endTime ?? payload?.endTime ?? null,
    serverTime: session.serverTime ?? payload?.serverTime ?? null,
    totalBidCount: session.totalBidCount ?? payload?.totalBidCount ?? null,
    validBidCount: session.validBidCount ?? payload?.validBidCount ?? null,
    highestBidAmount:
      session.highestBidAmount ?? summary?.winningBidAmount ?? result?.winningBidAmount ?? payload?.winningBidAmount ?? null,
    highestBidMembershipNo:
      session.highestBidMembershipNo ?? summary?.winnerMembershipNo ?? result?.winnerMembershipNo ?? payload?.winnerMembershipNo ?? null,
    highestBidderName:
      session.highestBidderName ?? summary?.winnerName ?? result?.winnerName ?? payload?.winnerName ?? "",
    finalizedAt: session.finalizedAt ?? payload?.finalizedAt ?? result?.finalizedAt ?? null,
    finalizedByName: session.finalizedByName ?? payload?.finalizedByName ?? result?.finalizedByName ?? "",
    winnerMembershipNo:
      session.winnerMembershipNo ?? summary?.winnerMembershipNo ?? result?.winnerMembershipNo ?? payload?.winnerMembershipNo ?? null,
    winnerName: session.winnerName ?? summary?.winnerName ?? result?.winnerName ?? payload?.winnerName ?? "",
    winningBidAmount: session.winningBidAmount ?? summary?.winningBidAmount ?? result?.winningBidAmount ?? payload?.winningBidAmount ?? null,
    ownerCommissionAmount:
      session.ownerCommissionAmount ?? summary?.ownerCommissionAmount ?? result?.ownerCommissionAmount ?? payload?.ownerCommissionAmount ?? null,
    dividendPoolAmount:
      session.dividendPoolAmount ?? summary?.dividendPoolAmount ?? result?.dividendPoolAmount ?? payload?.dividendPoolAmount ?? null,
    dividendPerMemberAmount:
      session.dividendPerMemberAmount ??
      summary?.dividendPerMemberAmount ??
      result?.dividendPerMemberAmount ??
      payload?.dividendPerMemberAmount ??
      null,
    winnerPayoutAmount:
      session.winnerPayoutAmount ?? summary?.winnerPayoutAmount ?? result?.winnerPayoutAmount ?? payload?.winnerPayoutAmount ?? null,
    finalizationMessage:
      session.finalizationMessage ??
      payload?.finalizationMessage ??
      result?.finalizationMessage ??
      (status === "finalized" ? "Auction closed and finalized." : ""),
  };
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

function getCommissionModeLabel(mode) {
  const normalized = String(mode ?? "NONE").toUpperCase();
  if (normalized === "FIRST_MONTH") {
    return "First month";
  }
  if (normalized === "PERCENTAGE") {
    return "Percentage";
  }
  if (normalized === "FIXED_AMOUNT") {
    return "Fixed amount";
  }
  return "None";
}

function DetailCard({ label, value }) {
  return (
    <article className="panel">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="text-lg font-semibold text-slate-900">{value}</p>
    </article>
  );
}

export default function OwnerAuctionConsole({ sessionId: sessionIdProp }) {
  const params = useParams();
  const resolvedSessionId = sessionIdProp ?? params.sessionId ?? "";
  const requestSessionId = useMemo(() => {
    if (resolvedSessionId === "" || resolvedSessionId === null || resolvedSessionId === undefined) {
      return "";
    }

    const parsedSessionId = Number(resolvedSessionId);
    return Number.isNaN(parsedSessionId) ? resolvedSessionId : parsedSessionId;
  }, [resolvedSessionId]);
  const [consoleData, setConsoleData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [connectionState, setConnectionState] = useState("connecting");

  const loadConsoleSnapshot = useCallback(
    async ({ reportError = true } = {}) => {
      try {
        const data = await fetchOwnerAuctionConsole(requestSessionId);
        setConsoleData(normalizeConsoleResponse(data, requestSessionId));
        setLastSyncedAt(new Date());
        return true;
      } catch (loadError) {
        if (reportError) {
          setLoadError(getApiErrorMessage(loadError, { fallbackMessage: "Unable to load this auction session." }));
        }
        return false;
      }
    },
    [requestSessionId],
  );

  useEffect(() => {
    let active = true;

    if (requestSessionId === "") {
      setLoadError("A session id is required to inspect an auction.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    setLoadError("");
    setActionError("");

    loadConsoleSnapshot({ reportError: false })
      .then((loaded) => {
        if (active && !loaded) {
          setLoadError("Unable to load this auction session.");
          setConsoleData(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [loadConsoleSnapshot, reloadToken]);

  useEffect(() => {
    let active = true;
    let pollIntervalId = null;
    let connectTimeoutId = null;
    const unsubscribeHandlers = [];

    const stopPolling = () => {
      if (pollIntervalId !== null) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
      }
    };

    const startPolling = () => {
      if (!active || pollIntervalId !== null) {
        return;
      }

      setConnectionState("fallback");
      pollIntervalId = setInterval(() => {
        void loadConsoleSnapshot({ reportError: false });
      }, SOCKET_FALLBACK_POLL_MS);
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
      void loadConsoleSnapshot({ reportError: false });
    };

    let socket = null;

    try {
      socket = createAuctionSocket({ sessionId: requestSessionId });
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
      register("auction-session-updated", handleUpdate);
      register("auction-room-updated", handleUpdate);
      register("auction-updated", handleUpdate);
      register("finalized", handleUpdate);
      register("auction.snapshot", handleUpdate);
      register("auction.bid.placed", handleUpdate);
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
  }, [loadConsoleSnapshot, requestSessionId]);

  async function handleRefresh() {
    if (requestSessionId === "" || loading || refreshing) {
      return;
    }

    setRefreshing(true);
    setActionError("");
    setActionMessage("");
    try {
      const loaded = await loadConsoleSnapshot();
      if (!loaded) {
        setActionError(getApiErrorMessage(new Error("refresh failed"), { fallbackMessage: "Unable to refresh the auction session." }));
      }
    } catch (refreshError) {
      setActionError(getApiErrorMessage(refreshError, { fallbackMessage: "Unable to refresh the auction session." }));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleFinalize() {
    if (!consoleData?.canFinalize || actionLoading || requestSessionId === "") {
      return;
    }

    setActionLoading(true);
    setActionError("");
    setActionMessage("");
    try {
      const updatedSession = await finalizeAuctionSession(requestSessionId);
      const normalized = normalizeConsoleResponse(updatedSession, requestSessionId);
      setConsoleData(normalized);
      setActionMessage(normalized.finalizationMessage || "Auction closed and finalized.");
      setReloadToken((currentToken) => currentToken + 1);
    } catch (finalizeError) {
      setActionError(getApiErrorMessage(finalizeError, { fallbackMessage: "Unable to finalize the auction session." }));
    } finally {
      setActionLoading(false);
    }
  }

  const title = consoleData?.sessionId ? `Auction Session ${consoleData.sessionId}` : "Auction Console";
  const finalizeDisabled = loading || actionLoading || !consoleData?.canFinalize || consoleData?.status === "finalized";
  const sessionSummary =
    consoleData?.groupTitle || consoleData?.groupCode || consoleData?.cycleNo
      ? `${consoleData.groupTitle || "Unnamed group"}${consoleData.groupCode ? ` · ${consoleData.groupCode}` : ""}`
      : "Session details will appear here once the backend responds.";
  const countdownLabel = getCountdownLabel(consoleData);
  const refreshLabel = refreshing ? "Refreshing snapshot" : "Manual refresh ready";
  const freshnessLabel = lastSyncedAt ? formatDateTime(lastSyncedAt) : "Waiting for the first snapshot";
  const finalized = consoleData?.status === "finalized" || Boolean(consoleData?.finalizedAt);
  const auctionModeLabel = getAuctionModeLabel(consoleData?.auctionMode);
  const commissionModeLabel = getCommissionModeLabel(consoleData?.commissionMode);
  const auctionStateLabel = getAuctionStateLabel(consoleData?.auctionState);
  const isBlindMode = String(consoleData?.auctionMode ?? "LIVE").toUpperCase() === "BLIND";
  const isFixedMode = String(consoleData?.auctionMode ?? "LIVE").toUpperCase() === "FIXED";
  const liveStateLabel = finalized
    ? "Finalized and ready for settlement review"
    : String(consoleData?.auctionState ?? "").toUpperCase() === "UPCOMING"
      ? "Waiting for the blind auction window to open"
      : String(consoleData?.auctionState ?? "").toUpperCase() === "ENDED"
        ? "Blind bidding is locked and ready for finalization"
        : isFixedMode
          ? "Waiting for organizer finalization"
          : isBlindMode
            ? "Blind bids stay hidden until finalization"
            : "Awaiting finalization";
  const connectionLabel =
    connectionState === "connected"
      ? "Connected"
      : connectionState === "fallback"
        ? "Fallback polling active"
        : "Connecting live updates";
  const winnerPayoutBreakdownRows = [
    `Chit Value: ${consoleData?.grossAmount != null ? formatAmount(consoleData.grossAmount) : "Not available"}`,
    `Bid Amount: ${consoleData?.winningBidAmount != null ? formatAmount(consoleData.winningBidAmount) : "Not available"}`,
    `Commission: ${consoleData?.ownerCommissionAmount != null ? formatAmount(consoleData.ownerCommissionAmount) : "Not available"}`,
    `Monthly Installment: Not available`,
    `Share Received: ${
      consoleData?.dividendPerMemberAmount != null
        ? formatAmount(consoleData.dividendPerMemberAmount)
        : "Not available"
    }`,
  ];

  return (
    <section className="panel space-y-6">
      <div className="space-y-2">
        <h2>{title}</h2>
        <p>Open, monitor, and close the session from one fast control surface.</p>
        <p className="text-sm text-slate-600">{sessionSummary}</p>
        {consoleData ? <p className="text-sm text-slate-600">Mode: {auctionModeLabel}</p> : null}
        {consoleData ? (
          <p className="text-sm text-slate-600">
            Commission: {commissionModeLabel}
            {consoleData.commissionValue != null ? ` (${consoleData.commissionValue})` : ""}
          </p>
        ) : null}
      </div>

      {consoleData ? (
        <div className="grid gap-3 md:grid-cols-3">
          <article className="panel">
            <p className="text-sm text-slate-500">Live connection</p>
            <p className="text-lg font-semibold text-slate-900">{connectionLabel}</p>
          </article>
          <article className="panel">
            <p className="text-sm text-slate-500">Refresh mode</p>
            <p className="text-lg font-semibold text-slate-900">{refreshLabel}</p>
          </article>
          <article className="panel">
            <p className="text-sm text-slate-500">Last checked</p>
            <p className="text-lg font-semibold text-slate-900">{freshnessLabel}</p>
          </article>
          <article className="panel">
            <p className="text-sm text-slate-500">Auction window</p>
            <p className="text-lg font-semibold text-slate-900">{countdownLabel}</p>
          </article>
        </div>
      ) : null}

      {loading ? (
        <PageLoadingState
          description="Fetching the latest owner-scoped auction session details."
          label="Loading auction console..."
        />
      ) : null}

      {!loading && loadError ? (
        <PageErrorState
          error={loadError}
          fallbackMessage="Unable to load this auction session."
          onRetry={() => setReloadToken((currentToken) => currentToken + 1)}
          title="We could not load the auction console."
        />
      ) : null}

      {!loading && !loadError && consoleData ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <DetailCard label="Status" value={consoleData.status} />
            <DetailCard label="Mode" value={auctionModeLabel} />
            <DetailCard
              label="Commission"
              value={`${commissionModeLabel}${consoleData.commissionValue != null ? ` (${consoleData.commissionValue})` : ""}`}
            />
            <DetailCard label="Auction state" value={auctionStateLabel} />
            <DetailCard label="Live state" value={liveStateLabel} />
            <DetailCard label="Group title" value={consoleData.groupTitle || "Not available"} />
            <DetailCard label="Group code" value={consoleData.groupCode || "Not available"} />
            <DetailCard
              label="Cycle"
              value={consoleData.cycleNo !== null && consoleData.cycleNo !== undefined ? `Cycle ${consoleData.cycleNo}` : "Not available"}
            />
            <DetailCard
              label="Bids"
              value={`${consoleData.validBidCount ?? 0} valid / ${consoleData.totalBidCount ?? 0} total`}
            />
            <DetailCard
              label="Highest bid"
              value={
                consoleData.highestBidAmount !== null && consoleData.highestBidAmount !== undefined
                  ? formatAmount(consoleData.highestBidAmount)
                  : isBlindMode && !finalized
                    ? "Hidden until finalization"
                    : isFixedMode
                      ? "Not used in fixed mode"
                      : "Waiting for bids"
              }
            />
            <DetailCard label="Scheduled start" value={formatDateTime(consoleData.scheduledStartAt)} />
            <DetailCard label="Actual start" value={formatDateTime(consoleData.actualStartAt)} />
            <DetailCard label="Configured start" value={formatDateTime(consoleData.startTime)} />
            <DetailCard label="Configured end" value={formatDateTime(consoleData.endTime)} />
            <DetailCard label="Actual end" value={formatDateTime(consoleData.actualEndAt)} />
            <DetailCard label="Server time" value={formatDateTime(consoleData.serverTime)} />
            <DetailCard
              label="Winning bidder"
              value={
                consoleData.highestBidderName || consoleData.highestBidMembershipNo
                  ? `${consoleData.highestBidderName || "Membership"}${
                      consoleData.highestBidMembershipNo ? ` #${consoleData.highestBidMembershipNo}` : ""
                    }`
                  : isBlindMode && !finalized
                    ? "Hidden until finalization"
                    : isFixedMode
                      ? "Auto-selected on finalize"
                      : "Not finalized yet"
              }
            />
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <h3>Finalized result</h3>
              <p>Outcome, winner, and finalization metadata for the current session.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <DetailCard
                label="Finalized at"
                value={consoleData.finalizedAt ? formatDateTime(consoleData.finalizedAt) : "Not finalized yet"}
              />
              <DetailCard
                label="Finalized by"
                value={consoleData.finalizedByName || "Not finalized yet"}
              />
              <DetailCard
                label="Winner membership"
                value={
                  consoleData.winnerName || consoleData.winnerMembershipNo
                    ? `${consoleData.winnerName || "Membership"}${
                        consoleData.winnerMembershipNo ? ` #${consoleData.winnerMembershipNo}` : ""
                      }`
                    : "Not finalized yet"
                }
              />
              <DetailCard
                label="Winning bid"
                value={consoleData.winningBidAmount !== null ? formatAmount(consoleData.winningBidAmount) : "Not available"}
              />
            </div>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <h3>Payout breakdown</h3>
              <p>Structured payout slots for the commission, pool, and winner settlement amounts.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <article className="panel border-emerald-200 bg-emerald-50/70">
                <p className="text-sm text-emerald-700">Final payout</p>
                <p className="text-2xl font-semibold text-emerald-800">
                  {consoleData.winnerPayoutAmount !== null
                    ? formatAmount(consoleData.winnerPayoutAmount)
                    : "Not available"}
                </p>
              </article>
              <DetailCard
                label="Chit value"
                value="Not available"
              />
              <DetailCard
                label="Bid amount"
                value={consoleData.winningBidAmount !== null ? formatAmount(consoleData.winningBidAmount) : "Not available"}
              />
              <DetailCard
                label="Owner commission"
                value={
                  consoleData.ownerCommissionAmount !== null
                    ? formatAmount(consoleData.ownerCommissionAmount)
                    : "Not available"
                }
              />
              <DetailCard
                label="Dividend pool"
                value={
                  consoleData.dividendPoolAmount !== null
                    ? formatAmount(consoleData.dividendPoolAmount)
                    : "Not available"
                }
              />
              <DetailCard
                label="Share received"
                value={
                  consoleData.dividendPerMemberAmount !== null
                    ? formatAmount(consoleData.dividendPerMemberAmount)
                    : "Not available"
                }
              />
              <DetailCard
                label="Monthly installment"
                value="Not available"
              />
            </div>
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4">
              <p className="text-sm font-semibold text-slate-900">Winner payout screen</p>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                {winnerPayoutBreakdownRows.map((row) => (
                  <p key={row}>{row}</p>
                ))}
                <p className="border-t border-slate-200 pt-2 font-semibold text-slate-950">
                  + Share - Installment ={" "}
                  {consoleData.winnerPayoutAmount !== null
                    ? formatAmount(consoleData.winnerPayoutAmount)
                    : "Not available"}
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <DetailCard label="Group summary" value={sessionSummary} />
            <DetailCard
              label="Snapshot mode"
              value={refreshing ? "Refreshing snapshot" : "Ready for future live updates"}
            />
          </div>

          {actionMessage ? <p className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">{actionMessage}</p> : null}
          {actionError ? <p className="rounded-md bg-red-50 px-3 py-2 text-red-900">{actionError}</p> : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              className="action-button"
              disabled={finalizeDisabled}
              onClick={handleFinalize}
              type="button"
            >
              {actionLoading ? "Finalizing..." : "Close and finalize auction"}
            </button>
            <button className="action-button" disabled={refreshing || loading} onClick={handleRefresh} type="button">
              {refreshing ? "Refreshing..." : "Refresh snapshot"}
            </button>
            {!consoleData.canFinalize ? (
              <p className="text-sm text-slate-600">
                This session cannot be finalized yet because there are no eligible bids or the backend has already
                locked it.
              </p>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
