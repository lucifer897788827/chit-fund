import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fetchUserDashboard, getSubscriberDashboardFromUserDashboard } from "./api";
import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser, getDashboardPath, sessionHasRole } from "../../lib/auth/store";
import {
  acceptGroupInvite,
  fetchPublicChits,
  rejectGroupInvite,
  requestGroupMembership,
  searchChitsByCode,
} from "../auctions/api";
import { buildMemberBalanceSummary, formatMoney, MemberBalanceSummary } from "../payments/balances";
import { logoutUser } from "../auth/api";
import { createOwnerRequest } from "../owner-requests/api";

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

function getInviteState(invite) {
  const inviteStatus = String(invite?.inviteStatus ?? "").toLowerCase();
  if (inviteStatus === "expired") {
    return "expired";
  }
  if (inviteStatus === "accepted") {
    return "accepted";
  }
  return "pending";
}

function normalizeSubscriberDashboard(data = {}) {
  return {
    memberships: Array.isArray(data?.memberships) ? data.memberships : [],
    activeAuctions: Array.isArray(data?.activeAuctions) ? data.activeAuctions : [],
    recentAuctionOutcomes: Array.isArray(data?.recentAuctionOutcomes) ? data.recentAuctionOutcomes : [],
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
  const [publicGroups, setPublicGroups] = useState([]);
  const [publicGroupsError, setPublicGroupsError] = useState("");
  const [groupCodeSearch, setGroupCodeSearch] = useState("");
  const [groupCodeResults, setGroupCodeResults] = useState([]);
  const [groupCodeSearchError, setGroupCodeSearchError] = useState("");
  const [groupCodeSearchMessage, setGroupCodeSearchMessage] = useState("");
  const [hasSearchedGroupCode, setHasSearchedGroupCode] = useState(false);
  const [searchingGroupCode, setSearchingGroupCode] = useState(false);
  const [publicGroupRequestStates, setPublicGroupRequestStates] = useState({});
  const [requestingGroupId, setRequestingGroupId] = useState(null);
  const [actingInviteId, setActingInviteId] = useState(null);
  const [inviteActionError, setInviteActionError] = useState("");
  const [inviteActionMessage, setInviteActionMessage] = useState("");
  const [ownerRequestState, setOwnerRequestState] = useState(null);
  const [submittingOwnerRequest, setSubmittingOwnerRequest] = useState(false);

  const loadDashboard = useCallback(async () => {
    const data = await fetchUserDashboard();
    return normalizeSubscriberDashboard(getSubscriberDashboardFromUserDashboard(data));
  }, []);

  useEffect(() => {
    let active = true;

    if (sessionHasRole(currentUser, "owner")) {
      navigate(getDashboardPath(currentUser), { replace: true });
      setLoading(false);
      return () => {
        active = false;
      };
    }

    if (!subscriberId) {
      setError("Sign in as a subscriber to load your dashboard.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    loadDashboard()
      .then((data) => {
        if (active) {
          setDashboard(data);
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
  }, [currentUser, loadDashboard, navigate, subscriberId]);

  useEffect(() => {
    let active = true;

    if (!subscriberId) {
      return () => {
        active = false;
      };
    }

    fetchPublicChits()
      .then((data) => {
        if (active) {
          setPublicGroups(Array.isArray(data) ? data : []);
        }
      })
      .catch((publicGroupError) => {
        if (active) {
          setPublicGroupsError(
            getApiErrorMessage(publicGroupError, {
              fallbackMessage: "Unable to load public chit groups right now.",
            }),
          );
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

  async function handleBecomeOrganizer() {
    setSubmittingOwnerRequest(true);
    setOwnerRequestState(null);

    try {
      const response = await createOwnerRequest();
      setOwnerRequestState({
        tone: "success",
        message:
          response?.status === "pending"
            ? "Organizer request submitted. An admin can now review it."
            : "Organizer request updated.",
      });
    } catch (requestError) {
      setOwnerRequestState({
        tone: "error",
        message: getApiErrorMessage(requestError, {
          fallbackMessage: "Unable to submit your organizer request right now.",
        }),
      });
    } finally {
      setSubmittingOwnerRequest(false);
    }
  }

  async function handleRequestMembership(group) {
    if (!group?.id || requestingGroupId === group.id) {
      return;
    }

    setRequestingGroupId(group.id);
    setPublicGroupRequestStates((currentState) => ({
      ...currentState,
      [group.id]: null,
    }));

    try {
      const response = await requestGroupMembership(group.id);
      setPublicGroupRequestStates((currentState) => ({
        ...currentState,
        [group.id]: {
          tone: "success",
          status: response?.membershipStatus ?? "pending",
          message: "Membership request submitted. The organizer can review it now.",
        },
      }));
    } catch (requestError) {
      setPublicGroupRequestStates((currentState) => ({
        ...currentState,
        [group.id]: {
          tone: "error",
          status: "error",
          message: getApiErrorMessage(requestError, {
            fallbackMessage: "Unable to send your membership request right now.",
          }),
        },
      }));
    } finally {
      setRequestingGroupId(null);
    }
  }

  async function handleGroupCodeSearch(event) {
    event.preventDefault();

    const normalizedGroupCode = String(groupCodeSearch ?? "").trim();
    if (!normalizedGroupCode) {
      setHasSearchedGroupCode(false);
      setGroupCodeResults([]);
      setGroupCodeSearchMessage("");
      setGroupCodeSearchError("Enter a group code to search.");
      return;
    }

    setSearchingGroupCode(true);
    setHasSearchedGroupCode(true);
    setGroupCodeSearchError("");
    setGroupCodeSearchMessage("");

    try {
      const results = await searchChitsByCode(normalizedGroupCode);
      const normalizedResults = Array.isArray(results) ? results : [];
      setGroupCodeResults(normalizedResults);
      if (normalizedResults.length === 0) {
        setGroupCodeSearchMessage(`No active chit groups match ${normalizedGroupCode}.`);
      }
    } catch (searchError) {
      setGroupCodeResults([]);
      setGroupCodeSearchError(
        getApiErrorMessage(searchError, {
          fallbackMessage: "Unable to search for this group code right now.",
        }),
      );
    } finally {
      setSearchingGroupCode(false);
    }
  }

  async function handleInviteAction(invite, action) {
    if (!invite?.membershipId || !invite?.groupId || actingInviteId === invite.membershipId) {
      return;
    }

    const actionLabel = action === "accept" ? "accept" : "reject";
    setActingInviteId(invite.membershipId);
    setInviteActionError("");
    setInviteActionMessage("");

    try {
      if (action === "accept") {
        await acceptGroupInvite(invite.groupId, invite.membershipId);
      } else {
        await rejectGroupInvite(invite.groupId, invite.membershipId);
      }
      setDashboard(await loadDashboard());
      setInviteActionMessage(
        `${actionLabel === "accept" ? "Accepted" : "Rejected"} your invite for ${invite.groupTitle}.`,
      );
    } catch (inviteError) {
      setInviteActionError(
        getApiErrorMessage(inviteError, {
          fallbackMessage: `Unable to ${actionLabel} this invite right now.`,
        }),
      );
    } finally {
      setActingInviteId(null);
    }
  }

  const memberships = dashboard.memberships ?? [];
  const visibleMemberships = memberships.filter(
    (membership) => !["invited", "rejected"].includes(String(membership.membershipStatus ?? "").toLowerCase()),
  );
  const invitedMemberships = memberships.filter(
    (membership) => String(membership.membershipStatus ?? "").toLowerCase() === "invited",
  );
  const activeMembershipCount = visibleMemberships.filter(
    (membership) => String(membership.membershipStatus ?? "").toLowerCase() === "active",
  ).length;
  const activeAuctions = dashboard.activeAuctions ?? [];
  const recentAuctionOutcomes = Array.isArray(dashboard.recentAuctionOutcomes)
    ? dashboard.recentAuctionOutcomes
    : [];
  const membershipSummaries = visibleMemberships.map((membership) =>
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
    visibleMemberships.length > 0
      ? `${visibleMemberships[0].groupTitle} · ${formatCount(visibleMemberships.length, "membership", "memberships")}`
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
          <button className="action-button" disabled={submittingOwnerRequest} onClick={handleBecomeOrganizer} type="button">
            {submittingOwnerRequest ? "Submitting..." : "Become Organizer"}
          </button>
          <button className="action-button" onClick={handleLogout} type="button">
            Log Out
          </button>
        </div>
        {ownerRequestState ? (
          <p
            className={
              ownerRequestState.tone === "error"
                ? "rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900"
                : "rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
            }
            role="status"
          >
            {ownerRequestState.message}
          </p>
        ) : null}
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
                <h3>{formatCount(activeMembershipCount, "active membership", "active memberships")}</h3>
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
            {visibleMemberships.length === 0 ? (
              <div className="space-y-3">
                <p>No memberships yet. Join an external chit to start tracking dues and prizes here.</p>
                <Link className="action-button" to="/external-chits">
                  Browse external chits
                </Link>
              </div>
            ) : (
              <div className="panel-grid">
                {visibleMemberships.map((membership, index) => (
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

          <section className="panel">
            <h2>Private group invites</h2>
            {invitedMemberships.length === 0 ? <p>No private-group invites are waiting right now.</p> : null}
            {invitedMemberships.length > 0 ? (
              <div className="panel-grid">
                {invitedMemberships.map((invite) => (
                  <article className="panel space-y-3" key={invite.membershipId}>
                    <h3>{invite.groupTitle}</h3>
                    <p>
                      {invite.groupCode} · Member #{invite.memberNo}
                    </p>
                    <p>Installment {formatMoney(invite.installmentAmount)}</p>
                    <p>
                      Invite status: {titleCase(getInviteState(invite))}
                      {invite.inviteExpiresAt ? ` · Expires ${formatOutcomeDate(invite.inviteExpiresAt) ?? invite.inviteExpiresAt}` : ""}
                    </p>
                    <p>
                      {getInviteState(invite) === "expired"
                        ? "This invite has expired. Ask the organizer to send a fresh invite."
                        : "Accept this invite to activate the membership and start dues tracking."}
                    </p>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="action-button"
                        disabled={actingInviteId === invite.membershipId || getInviteState(invite) === "expired"}
                        onClick={() => handleInviteAction(invite, "accept")}
                        type="button"
                      >
                        {actingInviteId === invite.membershipId ? "Updating..." : `Accept invite to ${invite.groupTitle}`}
                      </button>
                      <button
                        className="action-button"
                        disabled={actingInviteId === invite.membershipId || getInviteState(invite) === "expired"}
                        onClick={() => handleInviteAction(invite, "reject")}
                        type="button"
                      >
                        {actingInviteId === invite.membershipId ? "Updating..." : `Reject invite to ${invite.groupTitle}`}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            {inviteActionMessage ? (
              <p className="rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">{inviteActionMessage}</p>
            ) : null}
            {inviteActionError ? (
              <p className="rounded-md bg-red-50 px-3 py-2 text-red-900">{inviteActionError}</p>
            ) : null}
          </section>

          <section className="panel">
            <h2>Join with group code</h2>
            <form className="space-y-3" onSubmit={handleGroupCodeSearch}>
              <label className="flex flex-col gap-2" htmlFor="subscriber-group-code-search">
                <span>Group code</span>
                <input
                  id="subscriber-group-code-search"
                  name="groupCode"
                  onChange={(event) => setGroupCodeSearch(event.target.value)}
                  placeholder="Enter a chit group code"
                  type="text"
                  value={groupCodeSearch}
                />
              </label>
              <button className="action-button" disabled={searchingGroupCode} type="submit">
                {searchingGroupCode ? "Searching..." : "Search by code"}
              </button>
            </form>
            {groupCodeSearchError ? <p>{groupCodeSearchError}</p> : null}
            {groupCodeSearchMessage ? <p>{groupCodeSearchMessage}</p> : null}
            {hasSearchedGroupCode && groupCodeResults.length > 0 ? (
              <div className="panel-grid">
                {groupCodeResults.map((group) => (
                  <article className="panel space-y-3" key={`${group.id}-${group.ownerId}`}>
                    <h3>{group.title}</h3>
                    <p>
                      {group.groupCode} · {titleCase(group.visibility)}
                    </p>
                    <p>
                      {formatMoney(group.chitValue)} · Installment {formatMoney(group.installmentAmount)}
                    </p>
                    <p>
                      {group.memberCount} members · {group.cycleCount} cycles
                    </p>
                    {(() => {
                      const membership = memberships.find((item) => item.groupId === group.id);
                      const requestState = publicGroupRequestStates[group.id];
                      const membershipStatus = String(
                        requestState?.status ?? membership?.membershipStatus ?? "",
                      ).toLowerCase();
                      const isJoined = Boolean(membership) && membershipStatus === "active";
                      const isPending = membershipStatus === "pending";
                      const isRequesting = requestingGroupId === group.id;
                      const buttonLabel = isJoined
                        ? "Already joined"
                        : isPending
                          ? "Request pending"
                          : isRequesting
                            ? "Requesting..."
                            : "Request to join";

                      return (
                        <>
                          <button
                            className="action-button"
                            disabled={isJoined || isPending || isRequesting}
                            onClick={() => handleRequestMembership(group)}
                            type="button"
                          >
                            {buttonLabel}
                          </button>
                          {requestState?.message ? (
                            <p
                              className={
                                requestState.tone === "error"
                                  ? "rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900"
                                  : "rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
                              }
                              role="status"
                            >
                              {requestState.message}
                            </p>
                          ) : null}
                        </>
                      );
                    })()}
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <section className="panel">
            <h2>Public chit groups</h2>
            {publicGroupsError ? <p>{publicGroupsError}</p> : null}
            {!publicGroupsError && publicGroups.length === 0 ? (
              <p>No public chit groups are available right now.</p>
            ) : null}
            {publicGroups.length > 0 ? (
              <div className="panel-grid">
                {publicGroups.map((group) => (
                  <article className="panel space-y-3" key={group.id}>
                    <h3>{group.title}</h3>
                    <p>
                      {group.groupCode} · {titleCase(group.visibility)}
                    </p>
                    <p>
                      {formatMoney(group.chitValue)} · Installment {formatMoney(group.installmentAmount)}
                    </p>
                    <p>
                      {group.memberCount} members · {group.cycleCount} cycles
                    </p>
                    {(() => {
                      const membership = memberships.find((item) => item.groupId === group.id);
                      const requestState = publicGroupRequestStates[group.id];
                      const membershipStatus = String(
                        requestState?.status ?? membership?.membershipStatus ?? "",
                      ).toLowerCase();
                      const isJoined = Boolean(membership) && membershipStatus === "active";
                      const isPending = membershipStatus === "pending";
                      const isRequesting = requestingGroupId === group.id;
                      const buttonLabel = isJoined
                        ? "Already joined"
                        : isPending
                          ? "Request pending"
                          : isRequesting
                            ? "Requesting..."
                            : "Request to join";

                      return (
                        <>
                          <button
                            className="action-button"
                            disabled={isJoined || isPending || isRequesting}
                            onClick={() => handleRequestMembership(group)}
                            type="button"
                          >
                            {buttonLabel}
                          </button>
                          {requestState?.message ? (
                            <p
                              className={
                                requestState.tone === "error"
                                  ? "rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900"
                                  : "rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
                              }
                              role="status"
                            >
                              {requestState.message}
                            </p>
                          ) : null}
                        </>
                      );
                    })()}
                  </article>
                ))}
              </div>
            ) : null}
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
