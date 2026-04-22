import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fetchSubscriberDashboard } from "./api";
import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser } from "../../lib/auth/store";
import { buildMemberBalanceSummary, formatMoney, MemberBalanceSummary } from "../payments/balances";
import { logoutUser } from "../auth/api";

function formatCount(value, singularLabel, pluralLabel) {
  return `${value} ${value === 1 ? singularLabel : pluralLabel}`;
}

function titleCase(value) {
  if (!value) {
    return "Unknown";
  }

  return String(value)
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getPrimaryAuctionLink(activeAuctions) {
  return activeAuctions.length > 0 ? `/auctions/${activeAuctions[0].sessionId}` : "/external-chits";
}

function getAuctionStatusMessage(status) {
  const normalizedStatus = String(status ?? "").trim().toLowerCase();
  if (normalizedStatus === "open") {
    return "This membership is in an active auction round.";
  }
  if (normalizedStatus === "upcoming") {
    return "This membership has an upcoming auction round.";
  }
  if (normalizedStatus === "ended") {
    return "The latest auction round for this membership has ended.";
  }
  if (normalizedStatus === "finalized") {
    return "The latest auction round for this membership has been finalized.";
  }
  return "No live auction is open for this membership right now.";
}

function getOutcomeWinnerLabel(outcome) {
  if (outcome?.winnerMemberNo) {
    return `Member #${outcome.winnerMemberNo}`;
  }

  if (outcome?.winnerMembershipId) {
    return `Membership #${outcome.winnerMembershipId}`;
  }

  return "Not available";
}

function formatOutcomeDate(value) {
  if (!value) {
    return null;
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsedDate);
}

function getSubscriberId(currentUser) {
  return currentUser?.subscriber_id ?? currentUser?.subscriberId ?? null;
}

function getSlotSummary(source = {}) {
  const owned = Number(source.slotCount ?? 1);
  const won = Number(source.wonSlotCount ?? 0);
  const remaining = Number(source.remainingSlotCount ?? Math.max(owned - won, 0));

  return {
    owned,
    won,
    remaining,
  };
}

export default function SubscriberDashboard() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const subscriberId = getSubscriberId(currentUser);
  const [dashboard, setDashboard] = useState({
    memberships: [],
    activeAuctions: [],
    recentAuctionOutcomes: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    if (!subscriberId) {
      setError("Sign in as a subscriber to load your dashboard.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    fetchSubscriberDashboard()
      .then((data) => {
        if (active) {
          setDashboard({
            memberships: Array.isArray(data?.memberships) ? data.memberships : [],
            activeAuctions: Array.isArray(data?.activeAuctions) ? data.activeAuctions : [],
            recentAuctionOutcomes: Array.isArray(data?.recentAuctionOutcomes)
              ? data.recentAuctionOutcomes
              : [],
          });
        }
      })
      .catch((dashboardError) => {
        if (active) {
          const detail = getApiErrorMessage(dashboardError, { fallbackMessage: "" });
          setError({
            message: "Unable to load your dashboard right now.",
            detail: detail && detail !== "Unable to load your dashboard right now." ? detail : "",
          });
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
  }, [subscriberId]);

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  const memberships = dashboard.memberships ?? [];
  const activeAuctions = dashboard.activeAuctions ?? [];
  const recentAuctionOutcomes = Array.isArray(dashboard.recentAuctionOutcomes)
    ? dashboard.recentAuctionOutcomes
    : [];
  const membershipSummaries = memberships.map((membership) =>
    buildMemberBalanceSummary({
      ...membership,
      memberName: `Member #${membership.memberNo}`,
      groupTitle: membership.groupTitle,
    }),
  );
  const totalOutstanding = membershipSummaries.reduce((sum, summary) => sum + Number(summary.outstandingAmount ?? 0), 0);
  const primaryAuctionLink = getPrimaryAuctionLink(activeAuctions);
  const showRecentAuctionOutcomes = recentAuctionOutcomes.length > 0;
  const shellContextLabel =
    memberships.length > 0
      ? `${memberships[0].groupTitle} · ${formatCount(memberships.length, "membership", "memberships")}`
      : "Memberships, dues, and live auction access";

  useSignedInShellHeader({
    title: "Subscriber dashboard",
    contextLabel: shellContextLabel,
  });

  return (
    <main className="page-shell">
      <header className="space-y-3" id="profile">
        <h1>Subscriber Dashboard</h1>
        <p>Track your memberships, watch dues, and move into live auctions without hunting through menus.</p>
        <div className="panel-grid">
          <Link className="action-button" to="/notifications">
            Open notifications
          </Link>
          <Link className="action-button" to={primaryAuctionLink}>
            {activeAuctions.length > 0 ? "Go to auctions" : "Browse external chits"}
          </Link>
          <Link className="action-button" to="/external-chits">
            Open external chits
          </Link>
          <button className="action-button" onClick={handleLogout} type="button">
            Log Out
          </button>
        </div>
      </header>
      {loading ? (
        <PageLoadingState
          description="Fetching your memberships, live auctions, and any recent outcomes."
          label="Loading dashboard..."
        />
      ) : null}
      {!loading && error ? (
        <PageErrorState
          error={error}
          fallbackMessage="Unable to load your dashboard right now."
          onRetry={() => navigate(0)}
          title="We could not load your dashboard."
        />
      ) : null}

      {!loading && !error ? (
        <>
          <section className="panel" id="home">
            <h2>Dashboard snapshot</h2>
            <div className="panel-grid">
              <article className="panel">
                <h3>{formatCount(memberships.length, "active membership", "active memberships")}</h3>
                <p>All of your current group memberships in one place.</p>
              </article>
              <article className="panel">
                <h3>{formatCount(activeAuctions.length, "live auction", "live auctions")}</h3>
                <p>Jump straight into rounds you can bid in right now.</p>
              </article>
              <article className="panel">
                <h3>Outstanding dues</h3>
                <p>{formatMoney(totalOutstanding)}</p>
              </article>
            </div>
          </section>

          <section className="panel" id="payments">
            <h2>Current memberships</h2>
            {memberships.length === 0 ? (
              <div className="space-y-3">
                <p>No memberships yet. Join an external chit to start tracking dues and prizes here.</p>
                <Link className="action-button" to="/external-chits">
                  Browse external chits
                </Link>
              </div>
            ) : (
              <div className="panel-grid">
                {memberships.map((membership, index) => (
                  <article className="panel space-y-4" key={membership.membershipId}>
                    <h3>{membership.groupTitle}</h3>
                    <p>
                      {membership.groupCode} · Member #{membership.memberNo}
                    </p>
                    <p>
                      Cycle {membership.currentCycleNo} · Installment {formatMoney(membership.installmentAmount)}
                    </p>
                    <p>Status: {titleCase(membership.membershipStatus)}</p>
                    <p>Prize state: {titleCase(membership.prizedStatus)}</p>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">You own</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">
                          {getSlotSummary(membership).owned} chits
                        </p>
                      </article>
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Won</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">{getSlotSummary(membership).won}</p>
                      </article>
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Remaining</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">
                          {getSlotSummary(membership).remaining}
                        </p>
                      </article>
                    </div>
                    <p>You can bid {getSlotSummary(membership).remaining} more times.</p>
                    <p>{getAuctionStatusMessage(membership.auctionStatus)}</p>
                    <MemberBalanceSummary summary={membershipSummaries[index]} />
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="panel" id="auctions">
            <h2>Active auctions</h2>
            {activeAuctions.length === 0 ? (
              <div className="space-y-3">
                <p>No live auctions right now. Check external chits for groups you can join next.</p>
                <Link className="action-button" to="/external-chits">
                  Browse external chits
                </Link>
              </div>
            ) : (
              <div className="panel-grid">
                {activeAuctions.map((auction) => (
                  <article className="panel space-y-4" key={auction.sessionId}>
                    <h3>{auction.groupTitle}</h3>
                    <p>
                      {auction.groupCode} · Cycle {auction.cycleNo}
                    </p>
                    <p>{auction.canBid ? "You can bid in this round." : "Viewing only for this round."}</p>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">You own</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">
                          {getSlotSummary(auction).owned} chits
                        </p>
                      </article>
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Won</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">{getSlotSummary(auction).won}</p>
                      </article>
                      <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Remaining</p>
                        <p className="mt-1 text-lg font-semibold text-slate-950">
                          {getSlotSummary(auction).remaining}
                        </p>
                      </article>
                    </div>
                    <p>You can bid {getSlotSummary(auction).remaining} more times.</p>
                    <Link className="action-button" to={`/auctions/${auction.sessionId}`}>
                      Join Live Auction
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>

          {showRecentAuctionOutcomes ? (
            <section className="panel">
              <h2>Recent auction outcomes</h2>
              <div className="panel-grid">
                {recentAuctionOutcomes.map((outcome) => (
                  <article className="panel" key={outcome.sessionId}>
                    <h3>{outcome.groupTitle}</h3>
                    <p>
                      {outcome.groupCode} · Cycle {outcome.cycleNo}
                    </p>
                    <p>Winner: {getOutcomeWinnerLabel(outcome)}</p>
                    <p>Winning bid: {formatMoney(outcome.winningBidAmount)}</p>
                    {formatOutcomeDate(outcome.finalizedAt) ? (
                      <p>Finalized on {formatOutcomeDate(outcome.finalizedAt)}</p>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
