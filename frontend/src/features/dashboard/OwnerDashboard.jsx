import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser } from "../../lib/auth/store";
import { createAuctionSession } from "../auctions/api";
import { buildMemberBalanceSummary, formatMoney, MemberBalanceSummary } from "../payments/balances";
import OwnerPayoutsPanel from "../payments/OwnerPayoutsPanel";
import { fetchOwnerPayouts, settleOwnerPayout } from "../payments/api";
import { fetchOwnerDashboard } from "./api";
import { logoutUser } from "../auth/api";

function formatDateTime(value) {
  if (!value) {
    return "N/A";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "N/A";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDate(value) {
  if (!value) {
    return "N/A";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "N/A";
  }

  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function formatOptionalStatus(value) {
  if (!value) {
    return "Not available";
  }

  return String(value)
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatAuditPreview(value) {
  if (value == null) {
    return null;
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function SummaryCard({ label, value, detail }) {
  return (
    <article className="panel">
      <p className="text-sm uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
      {detail ? <p className="mt-2 text-sm text-slate-600">{detail}</p> : null}
    </article>
  );
}

function getOwnerId(currentUser) {
  return currentUser?.owner_id ?? currentUser?.ownerId ?? null;
}

function normalizePayout(payout = {}, fallback = {}) {
  return {
    id: payout.id ?? fallback.id ?? null,
    ownerId: payout.ownerId ?? fallback.ownerId ?? null,
    auctionResultId: payout.auctionResultId ?? fallback.auctionResultId ?? null,
    subscriberId: payout.subscriberId ?? fallback.subscriberId ?? null,
    subscriberName: payout.subscriberName ?? fallback.subscriberName ?? "",
    groupId: payout.groupId ?? fallback.groupId ?? null,
    groupCode: payout.groupCode ?? fallback.groupCode ?? "",
    groupTitle: payout.groupTitle ?? fallback.groupTitle ?? "",
    membershipId: payout.membershipId ?? fallback.membershipId ?? null,
    grossAmount: payout.grossAmount ?? fallback.grossAmount ?? 0,
    deductionsAmount: payout.deductionsAmount ?? fallback.deductionsAmount ?? 0,
    netAmount: payout.netAmount ?? fallback.netAmount ?? 0,
    payoutMethod: payout.payoutMethod ?? fallback.payoutMethod ?? "",
    payoutDate: payout.payoutDate ?? fallback.payoutDate ?? null,
    referenceNo: payout.referenceNo ?? fallback.referenceNo ?? null,
    status: payout.status ?? fallback.status ?? "pending",
    createdAt: payout.createdAt ?? fallback.createdAt ?? null,
    updatedAt: payout.updatedAt ?? fallback.updatedAt ?? null,
  };
}

function normalizeOwnerDashboard(data = {}, currentOwnerId = null) {
  return {
    ownerId: data?.ownerId ?? currentOwnerId ?? null,
    groupCount: data?.groupCount ?? 0,
    auctionCount: data?.auctionCount ?? 0,
    paymentCount: data?.paymentCount ?? 0,
    totalDueAmount: data?.totalDueAmount ?? 0,
    totalPaidAmount: data?.totalPaidAmount ?? 0,
    totalOutstandingAmount: data?.totalOutstandingAmount ?? 0,
    groups: Array.isArray(data?.groups) ? data.groups : [],
    recentAuctions: Array.isArray(data?.recentAuctions) ? data.recentAuctions : [],
    recentPayments: Array.isArray(data?.recentPayments) ? data.recentPayments : [],
    balances: Array.isArray(data?.balances) ? data.balances : [],
    recentActivity: Array.isArray(data?.recentActivity) ? data.recentActivity : [],
    recentAuditLogs: Array.isArray(data?.recentAuditLogs) ? data.recentAuditLogs : [],
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
  return "No commission";
}

function getNumericConfigValue(value) {
  if (value == null || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getBidRuleValue(source, keys) {
  for (const key of keys) {
    const value = getNumericConfigValue(source?.[key]);
    if (value != null) {
      return value;
    }
  }

  return null;
}

function getBidRuleConfig(source = {}) {
  const minBid = getBidRuleValue(source, [
    "minBidValue",
    "minBid",
    "minBidAmount",
    "minimumBid",
    "minimumBidAmount",
  ]);
  const maxBid = getBidRuleValue(source, [
    "maxBidValue",
    "maxBid",
    "maxBidAmount",
    "maximumBid",
    "maximumBidAmount",
  ]);
  const minIncrement = getBidRuleValue(source, [
    "minIncrement",
    "minIncrementAmount",
    "minBidIncrement",
    "minimumIncrement",
    "minimumBidIncrement",
  ]);

  if (minBid == null && maxBid == null && minIncrement == null) {
    return null;
  }

  return {
    minBid,
    maxBid,
    minIncrement,
  };
}

function formatBidRuleValue(value) {
  if (value == null) {
    return null;
  }

  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(value));
}

function formatBidRuleSummary(source) {
  const rules = getBidRuleConfig(source);
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

function getAuctionSessionRuleError(draft) {
  const isFixedMode = String(draft?.auctionMode ?? "LIVE").toUpperCase() === "FIXED";
  if (isFixedMode) {
    return "";
  }

  const rules = getBidRuleConfig(draft);
  if (!rules) {
    return "";
  }

  if (rules.minBid != null && rules.minBid < 0) {
    return "Minimum bid must be zero or more.";
  }

  if (rules.maxBid != null && rules.maxBid < 0) {
    return "Maximum bid must be zero or more.";
  }

  if (rules.minIncrement != null && rules.minIncrement <= 0) {
    return "Minimum increment must be greater than zero.";
  }

  if (rules.minBid != null && rules.maxBid != null && rules.maxBid < rules.minBid) {
    return "Maximum bid must be greater than or equal to the minimum bid.";
  }

  return "";
}

export default function OwnerDashboard() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const currentOwnerId = getOwnerId(currentUser);
  const isSignedIn = Boolean(currentOwnerId);
  const [dashboard, setDashboard] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [payoutsLoading, setPayoutsLoading] = useState(true);
  const [error, setError] = useState("");
  const [payoutsError, setPayoutsError] = useState("");
  const [payoutActionError, setPayoutActionError] = useState("");
  const [payoutActionMessage, setPayoutActionMessage] = useState("");
  const [settlingPayoutId, setSettlingPayoutId] = useState(null);
  const [creatingAuctionSession, setCreatingAuctionSession] = useState(false);
  const [auctionSessionMessage, setAuctionSessionMessage] = useState("");
  const [auctionSessionError, setAuctionSessionError] = useState("");
  const [auctionSessionDraft, setAuctionSessionDraft] = useState({
    groupId: "",
    cycleNo: "1",
    auctionMode: "LIVE",
    commissionMode: "NONE",
    commissionValue: "",
    biddingWindowSeconds: "180",
    minBid: "",
    maxBid: "",
    minIncrement: "",
    startTime: "",
    endTime: "",
  });

  const loadPayouts = useCallback(async ({ reportError = true } = {}) => {
    try {
      const data = await fetchOwnerPayouts();
      setPayouts(Array.isArray(data) ? data.map((payout) => normalizePayout(payout)) : []);
      return true;
    } catch (payoutsLoadError) {
      if (reportError) {
        setPayoutsError(getApiErrorMessage(payoutsLoadError, { fallbackMessage: "Unable to load payout records right now." }));
        return false;
      }
      throw payoutsLoadError;
    }
  }, []);

  const loadDashboard = useCallback(async ({ reportError = true } = {}) => {
    try {
      const data = await fetchOwnerDashboard();
      setDashboard(normalizeOwnerDashboard(data, currentOwnerId));
      return true;
    } catch (dashboardLoadError) {
      if (reportError) {
        const detail = getApiErrorMessage(dashboardLoadError, { fallbackMessage: "" });
        setError({
          message: "Unable to load your owner dashboard right now.",
          detail: detail && detail !== "Unable to load your owner dashboard right now." ? detail : "",
        });
      }
      return false;
    }
  }, [currentOwnerId]);

  useEffect(() => {
    let active = true;

    if (!isSignedIn) {
      setError("Sign in as a chit owner to load your dashboard.");
      setLoading(false);
      setPayoutsLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    setPayoutsLoading(true);
    setError("");
    setPayoutsError("");

    Promise.allSettled([loadDashboard({ reportError: false }), loadPayouts({ reportError: false })])
      .then(([dashboardResult, payoutsResult]) => {
        if (!active) {
          return;
        }

        if (dashboardResult.status === "rejected" || dashboardResult.value !== true) {
          const detail = getApiErrorMessage(dashboardResult.reason, { fallbackMessage: "" });
          setError({
            message: "Unable to load your owner dashboard right now.",
            detail: detail && detail !== "Unable to load your owner dashboard right now." ? detail : "",
          });
        }

        if (payoutsResult.status === "rejected") {
          const detail = getApiErrorMessage(payoutsResult.reason, {
            fallbackMessage: "Unable to load payout records right now.",
          });
          setPayoutsError(detail);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          setPayoutsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [currentOwnerId, isSignedIn, loadDashboard, loadPayouts]);

  useEffect(() => {
    if (!dashboard?.groups?.length) {
      return;
    }

    setAuctionSessionDraft((currentDraft) => {
      if (currentDraft.groupId) {
        return currentDraft;
      }

      const defaultGroup = dashboard.groups[0];
      return {
        ...currentDraft,
        groupId: String(defaultGroup.groupId),
        cycleNo: String(defaultGroup.currentCycleNo ?? 1),
      };
    });
  }, [dashboard]);

  const groupById = useMemo(() => {
    const groups = dashboard?.groups ?? [];
    return new Map(groups.map((group) => [group.groupId, group]));
  }, [dashboard]);
  const shellContextLabel = useMemo(() => {
    if (!dashboard) {
      return "Groups, auctions, and collections";
    }

    if (dashboard.groups.length === 1) {
      const [group] = dashboard.groups;
      return `${group.title} · ${group.groupCode}`;
    }

    return `${dashboard.groupCount} groups tracked · ${dashboard.auctionCount} auctions`;
  }, [dashboard]);
  const isFixedAuctionDraft = String(auctionSessionDraft.auctionMode ?? "LIVE").toUpperCase() === "FIXED";
  const draftBidRuleSummary = formatBidRuleSummary(auctionSessionDraft);

  useSignedInShellHeader({
    title: "Owner dashboard",
    contextLabel: shellContextLabel,
  });

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  async function handleSettlePayout(payout) {
    if (!payout?.id || settlingPayoutId === payout.id) {
      return;
    }

    setSettlingPayoutId(payout.id);
    setPayoutActionError("");
    setPayoutActionMessage("");

    try {
      const updatedPayout = await settleOwnerPayout(payout.id);
      const normalizedPayout = normalizePayout(updatedPayout, { ...payout, status: "paid" });
      setPayouts((currentPayouts) =>
        currentPayouts.map((currentPayout) => (currentPayout.id === payout.id ? normalizedPayout : currentPayout)),
      );
      setPayoutActionMessage(
        `${normalizedPayout.subscriberName || `Payout #${normalizedPayout.id}`} marked as settled.`,
      );
    } catch (settleError) {
      setPayoutActionError(getApiErrorMessage(settleError, { fallbackMessage: "Unable to settle this payout right now." }));
    } finally {
      setSettlingPayoutId(null);
    }
  }

  function updateAuctionSessionDraft(field, value) {
    setAuctionSessionDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  }

  async function handleCreateAuctionSession(event) {
    event.preventDefault();
    if (creatingAuctionSession) {
      return;
    }
    if (!auctionSessionDraft.groupId) {
      setAuctionSessionError("Select a group before creating an auction session.");
      return;
    }

    const requiresCommissionValue = ["PERCENTAGE", "FIXED_AMOUNT"].includes(auctionSessionDraft.commissionMode);
    if (requiresCommissionValue && !auctionSessionDraft.commissionValue) {
      setAuctionSessionError("Enter a commission value for the selected commission mode.");
      return;
    }

    if ((auctionSessionDraft.startTime && !auctionSessionDraft.endTime) || (!auctionSessionDraft.startTime && auctionSessionDraft.endTime)) {
      setAuctionSessionError("Blind auction windows require both a start time and an end time.");
      return;
    }

    const auctionSessionRuleError = getAuctionSessionRuleError(auctionSessionDraft);
    if (auctionSessionRuleError) {
      setAuctionSessionError(auctionSessionRuleError);
      return;
    }

    setCreatingAuctionSession(true);
    setAuctionSessionError("");
    setAuctionSessionMessage("");

    try {
      const payload = {
        cycleNo: Number(auctionSessionDraft.cycleNo),
        auctionMode: auctionSessionDraft.auctionMode,
        commissionMode: auctionSessionDraft.commissionMode,
        biddingWindowSeconds: Number(auctionSessionDraft.biddingWindowSeconds),
      };

      if (requiresCommissionValue) {
        payload.commissionValue = Number(auctionSessionDraft.commissionValue);
      }
      if (!isFixedAuctionDraft) {
        const bidRules = getBidRuleConfig(auctionSessionDraft);
        if (bidRules?.minBid != null) {
          payload.minBidValue = bidRules.minBid;
        }
        if (bidRules?.maxBid != null) {
          payload.maxBidValue = bidRules.maxBid;
        }
        if (bidRules?.minIncrement != null) {
          payload.minIncrement = bidRules.minIncrement;
        }
      }
      if (auctionSessionDraft.startTime && auctionSessionDraft.endTime) {
        payload.startTime = new Date(auctionSessionDraft.startTime).toISOString();
        payload.endTime = new Date(auctionSessionDraft.endTime).toISOString();
      }

      const session = await createAuctionSession(Number(auctionSessionDraft.groupId), payload);
      await loadDashboard({ reportError: false });
      setAuctionSessionMessage(
        `Created session #${session.id} with ${getAuctionModeLabel(session.auctionMode)} and ${getCommissionModeLabel(session.commissionMode)}.`,
      );
      setAuctionSessionDraft((currentDraft) => ({
        ...currentDraft,
        commissionValue: "",
        minBid: "",
        maxBid: "",
        minIncrement: "",
        startTime: "",
        endTime: "",
      }));
    } catch (createError) {
      setAuctionSessionError(
        getApiErrorMessage(createError, { fallbackMessage: "Unable to create the auction session right now." }),
      );
    } finally {
      setCreatingAuctionSession(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="space-y-3" id="profile">
        <h1>Owner Dashboard</h1>
        <p>Monitor groups, auctions, payments, balances, and recent activity from one place.</p>
        <div className="panel-grid sm:grid-cols-2">
          <Link className="action-button" to="/notifications">
            Open notifications
          </Link>
        </div>
        {dashboard ? (
          <div className="panel-grid">
            <SummaryCard label="Groups" value={`${dashboard.groupCount} groups`} />
            <SummaryCard label="Auctions" value={`${dashboard.auctionCount} auctions`} />
            <SummaryCard label="Payments" value={`${dashboard.paymentCount} payments`} />
            <SummaryCard label="Due" value={formatMoney(dashboard.totalDueAmount)} />
            <SummaryCard label="Paid" value={formatMoney(dashboard.totalPaidAmount)} />
            <SummaryCard label="Outstanding" value={formatMoney(dashboard.totalOutstandingAmount)} />
          </div>
        ) : null}
        <button className="action-button" onClick={handleLogout} type="button">
          Log Out
        </button>
      </header>

      {loading ? (
        <PageLoadingState description="Fetching the owner reporting summary." label="Loading dashboard..." />
      ) : null}
      {!loading && error ? (
        <PageErrorState
          error={error}
          fallbackMessage="Unable to load your owner dashboard right now."
          onRetry={() => navigate(0)}
          title="We could not load your owner dashboard."
        />
      ) : null}

      {!loading && !error && dashboard ? (
        <>
          <FormFrame
            description="Create a new auction session with mode, timing, organizer commission settings, and optional bid rules."
            error={auctionSessionError}
            success={auctionSessionMessage}
            title="Create Auction Session"
          >
            <form className="space-y-4" onSubmit={handleCreateAuctionSession}>
              <div className="grid gap-4 md:grid-cols-2">
                <FormField htmlFor="auctionGroupId" label="Group">
                  <select
                    className="text-input"
                    id="auctionGroupId"
                    onChange={(event) => updateAuctionSessionDraft("groupId", event.target.value)}
                    value={auctionSessionDraft.groupId}
                  >
                    <option value="">Select a group</option>
                    {dashboard.groups.map((group) => (
                      <option
                        key={group.groupId}
                        label={`${group.title} (${group.groupCode})`}
                        value={group.groupId}
                      />
                    ))}
                  </select>
                </FormField>
                <FormField htmlFor="auctionCycleNo" label="Cycle Number">
                  <input
                    className="text-input"
                    id="auctionCycleNo"
                    min="1"
                    onChange={(event) => updateAuctionSessionDraft("cycleNo", event.target.value)}
                    type="number"
                    value={auctionSessionDraft.cycleNo}
                  />
                </FormField>
                <FormField htmlFor="auctionMode" label="Auction Mode">
                  <select
                    className="text-input"
                    id="auctionMode"
                    onChange={(event) => updateAuctionSessionDraft("auctionMode", event.target.value)}
                    value={auctionSessionDraft.auctionMode}
                  >
                    <option value="LIVE">Live</option>
                    <option value="BLIND">Blind</option>
                    <option value="FIXED">Fixed</option>
                  </select>
                </FormField>
                <FormField htmlFor="biddingWindowSeconds" label="Bidding Window (seconds)">
                  <input
                    className="text-input"
                    id="biddingWindowSeconds"
                    min="1"
                    onChange={(event) => updateAuctionSessionDraft("biddingWindowSeconds", event.target.value)}
                    type="number"
                    value={auctionSessionDraft.biddingWindowSeconds}
                  />
                </FormField>
                <FormField htmlFor="commissionMode" label="Commission Mode">
                  <select
                    className="text-input"
                    id="commissionMode"
                    onChange={(event) => updateAuctionSessionDraft("commissionMode", event.target.value)}
                    value={auctionSessionDraft.commissionMode}
                  >
                    <option value="NONE">None</option>
                    <option value="FIRST_MONTH">First month</option>
                    <option value="PERCENTAGE">Percentage</option>
                    <option value="FIXED_AMOUNT">Fixed amount</option>
                  </select>
                </FormField>
                <FormField htmlFor="commissionValue" label="Commission Value">
                  <input
                    className="text-input"
                    disabled={!["PERCENTAGE", "FIXED_AMOUNT"].includes(auctionSessionDraft.commissionMode)}
                    id="commissionValue"
                    min="0"
                    onChange={(event) => updateAuctionSessionDraft("commissionValue", event.target.value)}
                    placeholder={
                      auctionSessionDraft.commissionMode === "PERCENTAGE" ? "Enter a percent" : "Enter an amount"
                    }
                    step="0.01"
                    type="number"
                    value={auctionSessionDraft.commissionValue}
                  />
                </FormField>
                <FormField
                  helpText={isFixedAuctionDraft ? "Fixed auctions do not accept bids, so minimum bid is ignored." : "Optional. Leave blank to use the backend default."}
                  htmlFor="auctionMinBid"
                  label="Minimum Bid"
                >
                  <input
                    className="text-input"
                    disabled={isFixedAuctionDraft}
                    id="auctionMinBid"
                    min="0"
                    onChange={(event) => updateAuctionSessionDraft("minBid", event.target.value)}
                    placeholder="Optional minimum bid"
                    step="0.01"
                    type="number"
                    value={auctionSessionDraft.minBid}
                  />
                </FormField>
                <FormField
                  helpText={isFixedAuctionDraft ? "Fixed auctions do not accept bids, so maximum bid is ignored." : "Optional. Leave blank to allow the backend default."}
                  htmlFor="auctionMaxBid"
                  label="Maximum Bid"
                >
                  <input
                    className="text-input"
                    disabled={isFixedAuctionDraft}
                    id="auctionMaxBid"
                    min="0"
                    onChange={(event) => updateAuctionSessionDraft("maxBid", event.target.value)}
                    placeholder="Optional maximum bid"
                    step="0.01"
                    type="number"
                    value={auctionSessionDraft.maxBid}
                  />
                </FormField>
                <FormField
                  helpText={isFixedAuctionDraft ? "Fixed auctions do not accept bids, so minimum increment is ignored." : "Optional. Use this to guide valid bid steps in the room."}
                  htmlFor="auctionMinIncrement"
                  label="Minimum Increment"
                >
                  <input
                    className="text-input"
                    disabled={isFixedAuctionDraft}
                    id="auctionMinIncrement"
                    min="0.01"
                    onChange={(event) => updateAuctionSessionDraft("minIncrement", event.target.value)}
                    placeholder="Optional bid increment"
                    step="0.01"
                    type="number"
                    value={auctionSessionDraft.minIncrement}
                  />
                </FormField>
                <FormField htmlFor="auctionStartTime" label="Blind Start Time">
                  <input
                    className="text-input"
                    disabled={auctionSessionDraft.auctionMode !== "BLIND"}
                    id="auctionStartTime"
                    onChange={(event) => updateAuctionSessionDraft("startTime", event.target.value)}
                    type="datetime-local"
                    value={auctionSessionDraft.startTime}
                  />
                </FormField>
                <FormField htmlFor="auctionEndTime" label="Blind End Time">
                  <input
                    className="text-input"
                    disabled={auctionSessionDraft.auctionMode !== "BLIND"}
                    id="auctionEndTime"
                    onChange={(event) => updateAuctionSessionDraft("endTime", event.target.value)}
                    type="datetime-local"
                    value={auctionSessionDraft.endTime}
                  />
                </FormField>
              </div>
              <FormActions
                note={
                  `${draftBidRuleSummary ? `Bid rules: ${draftBidRuleSummary}. ` : ""}FIRST_MONTH uses the group installment amount; percentage and fixed amount modes require an explicit value.`
                }
              >
                <button className="action-button" disabled={creatingAuctionSession} type="submit">
                  {creatingAuctionSession ? "Loading..." : "Create auction session"}
                </button>
              </FormActions>
            </form>
          </FormFrame>

          <section className="panel" id="home">
            <h2>Groups</h2>
            {dashboard.groups.length === 0 ? <p>No groups available yet.</p> : null}
            {dashboard.groups.length > 0 ? (
              <div className="panel-grid">
                {dashboard.groups.map((group) => (
                  <article className="panel" key={group.groupId}>
                    <h3>{group.title}</h3>
                    <p>
                      {group.groupCode} · Cycle {group.currentCycleNo}
                    </p>
                    <p>
                      {group.memberCount} members · {group.activeMemberCount} active
                    </p>
                    <p>
                      {formatMoney(group.totalDue)} due · {formatMoney(group.totalPaid)} paid
                    </p>
                    <p>{formatMoney(group.outstandingAmount)} outstanding</p>
                    <p>
                      {group.auctionCount} auctions · {group.openAuctionCount} open
                    </p>
                    <p>Latest payment: {formatDateTime(group.latestPaymentAt)}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel" id="auctions">
            <h2>Recent auctions</h2>
            {dashboard.recentAuctions.length === 0 ? <p>No recent auctions yet.</p> : null}
            {dashboard.recentAuctions.length > 0 ? (
              <div className="panel-grid">
                {dashboard.recentAuctions.map((auction) => (
                  <article className="panel" key={auction.sessionId}>
                    <h3>{auction.groupTitle}</h3>
                    <p>
                      {auction.groupCode} · Cycle {auction.cycleNo}
                    </p>
                    <p>
                      {getAuctionModeLabel(auction.auctionMode)} · {getCommissionModeLabel(auction.commissionMode)}
                      {auction.commissionValue != null ? ` (${auction.commissionValue})` : ""}
                    </p>
                    {formatBidRuleSummary(auction) ? <p>Bid rules: {formatBidRuleSummary(auction)}</p> : null}
                    <p>Status: {auction.status}</p>
                    <p>Scheduled: {formatDateTime(auction.scheduledStartAt)}</p>
                    <p>Started: {formatDateTime(auction.actualStartAt)}</p>
                    <p>Ended: {formatDateTime(auction.actualEndAt)}</p>
                    <p>Created: {formatDateTime(auction.createdAt)}</p>
                    <p>Session #{auction.sessionId}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel" id="payments">
            <h2>Recent payments</h2>
            {dashboard.recentPayments.length === 0 ? <p>No recent payments yet.</p> : null}
            {dashboard.recentPayments.length > 0 ? (
              <div className="panel-grid">
                {dashboard.recentPayments.map((payment) => (
                  <article className="panel" key={payment.paymentId}>
                    <h3>{payment.subscriberName}</h3>
                    <p>{payment.groupCode ?? "Unassigned group"}</p>
                    <p>{formatMoney(payment.amount)}</p>
                    <p>Method: {payment.paymentMethod}</p>
                    <p>Record status: {formatOptionalStatus(payment.status)}</p>
                    <p>Payment status: {formatOptionalStatus(payment.paymentStatus)}</p>
                    {Number(payment.penaltyAmount ?? 0) > 0 ? (
                      <p>Penalty: {formatMoney(payment.penaltyAmount)}</p>
                    ) : null}
                    {Number(payment.arrearsAmount ?? 0) > 0 ? (
                      <p>Arrears: {formatMoney(payment.arrearsAmount)}</p>
                    ) : null}
                    {payment.nextDueAmount != null ? (
                      <p>Next due amount: {formatMoney(payment.nextDueAmount)}</p>
                    ) : null}
                    {payment.nextDueDate ? <p>Next due date: {formatDate(payment.nextDueDate)}</p> : null}
                    <p>Payment date: {formatDate(payment.paymentDate)}</p>
                    <p>Recorded: {formatDateTime(payment.createdAt)}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <OwnerPayoutsPanel
            error={payoutsError}
            loading={payoutsLoading}
            onRetry={() => {
              setPayoutsLoading(true);
              setPayoutsError("");
              void loadPayouts().finally(() => {
                setPayoutsLoading(false);
              });
            }}
            onSettle={handleSettlePayout}
            payouts={payouts}
            settlingPayoutId={settlingPayoutId}
          />

          {payoutActionMessage ? <p className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">{payoutActionMessage}</p> : null}
          {payoutActionError ? <p className="rounded-md bg-red-50 px-3 py-2 text-red-900">{payoutActionError}</p> : null}

          <section className="panel">
            <h2>Outstanding balances</h2>
            {dashboard.balances.length === 0 ? <p>No outstanding balances yet.</p> : null}
            {dashboard.balances.length > 0 ? (
              <div className="panel-grid">
                {dashboard.balances.map((balance) => {
                  const groupTitle = groupById.get(balance.groupId)?.title ?? `Group #${balance.groupId}`;

                  return (
                    <MemberBalanceSummary
                      key={balance.membershipId}
                      summary={buildMemberBalanceSummary({
                        ...balance,
                        memberName:
                          balance.memberName ??
                          (balance.memberNo != null ? `Member #${balance.memberNo}` : `Membership #${balance.membershipId}`),
                        groupTitle,
                      })}
                    />
                  );
                })}
              </div>
            ) : null}
          </section>

          <section className="panel">
            <h2>Recent activity</h2>
            {dashboard.recentActivity.length === 0 ? <p>No recent activity yet.</p> : null}
            {dashboard.recentActivity.length > 0 ? (
              <div className="panel-grid">
                {dashboard.recentActivity.map((item) => (
                  <article className="panel" key={`${item.kind}-${item.refId}`}>
                    <p className="text-sm uppercase tracking-wide text-slate-500">{item.kind}</p>
                    <h3>{item.title}</h3>
                    <p>{item.detail}</p>
                    <p>{item.groupCode ?? `Group #${item.groupId ?? "N/A"}`}</p>
                    <p>{formatDateTime(item.occurredAt)}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel">
            <h2>Audit log</h2>
            {dashboard.recentAuditLogs.length === 0 ? <p>No audit logs yet.</p> : null}
            {dashboard.recentAuditLogs.length > 0 ? (
              <div className="panel-grid">
                {dashboard.recentAuditLogs.map((item) => {
                  const metadataPreview = formatAuditPreview(item.metadata);
                  const beforePreview = formatAuditPreview(item.before);
                  const afterPreview = formatAuditPreview(item.after);

                  return (
                    <article className="panel" key={`audit-${item.id}`}>
                      <p className="text-sm uppercase tracking-wide text-slate-500">
                        {item.actionLabel ?? formatOptionalStatus(item.action)}
                      </p>
                      <h3>
                        {item.entityType} #{item.entityId}
                      </h3>
                      <p>{item.actorName ? `Actor: ${item.actorName}` : `Actor ID: ${item.actorId ?? "N/A"}`}</p>
                      {metadataPreview ? <p>Metadata: {metadataPreview}</p> : null}
                      {beforePreview ? <p>Before: {beforePreview}</p> : null}
                      {afterPreview ? <p>After: {afterPreview}</p> : null}
                      <p>{formatDateTime(item.occurredAt)}</p>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  );
}
