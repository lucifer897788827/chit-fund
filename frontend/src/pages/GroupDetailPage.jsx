import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, sessionHasRole } from "../lib/auth/store";
import {
  fetchUserDashboard,
  getOwnerDashboardFromUserDashboard,
  getSubscriberDashboardFromUserDashboard,
} from "../features/dashboard/api";
import { closeGroupCollection, fetchGroupMemberSummary, fetchGroupStatus, fetchGroups, finalizeAuctionSession, inviteSubscriberToGroup } from "../features/auctions/api";
import AuctionRoomPage from "../features/auctions/AuctionRoomPage";
import OwnerAuctionConsole from "../features/auctions/OwnerAuctionConsole";
import SubscriberManagementPanel from "../features/subscribers/SubscriberManagementPanel";
import PaymentPanel from "../features/payments/PaymentPanel";
import { fetchOwnerPayouts, fetchPayments, markOwnerPayoutPaid } from "../features/payments/api";
import { buildMemberBalanceSummary, formatMoney, MemberBalanceSummary } from "../features/payments/balances";

const TABS = ["members", "payments", "auction", "payout", "ledger", "settings"];

function isClosedLifecycleStatus(status) {
  return ["COLLECTION_CLOSED", "AUCTION_DONE", "PAYOUT_DONE"].includes(String(status ?? "").toUpperCase());
}

function isCollectionClosedLifecycleStatus(status) {
  return String(status ?? "").toUpperCase() === "COLLECTION_CLOSED";
}

function getOwnerId(currentUser) {
  return currentUser?.owner_id ?? currentUser?.ownerId ?? null;
}

function titleCase(value) {
  return String(value || "unknown")
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getStatusBadgeClass(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (["paid", "full", "completed", "active", "open"].includes(normalized)) {
    return "status-badge status-badge--success";
  }
  if (["pending", "partial", "overdue", "due", "failed"].includes(normalized)) {
    return "status-badge status-badge--danger";
  }
  if (["upcoming", "scheduled", "processing"].includes(normalized)) {
    return "status-badge status-badge--warning";
  }
  return "status-badge";
}

function isLiveAuction(auction) {
  const status = String(auction?.status ?? auction?.auctionState ?? "").toLowerCase();
  return ["open", "live", "started", "bidding_open"].includes(status);
}

function normalizeOwnerGroup(group, detail) {
  if (!group && !detail) {
    return null;
  }
  return {
    id: group?.groupId ?? detail?.id,
    title: group?.title ?? detail?.title,
    groupCode: group?.groupCode ?? detail?.groupCode,
    status: group?.status ?? detail?.status,
    currentCycleNo: group?.currentCycleNo ?? detail?.currentCycleNo,
    cycleCount: detail?.cycleCount,
    chitValue: detail?.chitValue,
    installmentAmount: group?.installmentAmount ?? detail?.installmentAmount,
    memberCount: group?.memberCount ?? detail?.memberCount,
    activeMemberCount: group?.activeMemberCount,
    totalDue: group?.totalDue,
    totalPaid: group?.totalPaid,
    outstandingAmount: group?.outstandingAmount,
    visibility: group?.visibility ?? detail?.visibility,
  };
}

function normalizeMemberGroup(membership) {
  if (!membership) {
    return null;
  }
  return {
    id: membership.groupId,
    title: membership.groupTitle,
    groupCode: membership.groupCode,
    status: membership.membershipStatus,
    currentCycleNo: membership.currentCycleNo,
    installmentAmount: membership.installmentAmount,
    memberNo: membership.memberNo,
    totalDue: membership.totalDue,
    totalPaid: membership.totalPaid,
    outstandingAmount: membership.outstandingAmount,
    slotCount: membership.slotCount,
    wonSlotCount: membership.wonSlotCount,
    remainingSlotCount: membership.remainingSlotCount,
  };
}

function buildMemberRows({ balances, memberGroup }) {
  if (balances.length > 0) {
    return balances.map((balance) => ({
      id: balance.membershipId,
      name: balance.memberName ?? `Member #${balance.memberNo ?? balance.membershipId}`,
      status: Number(balance.outstandingAmount ?? 0) > 0 ? "pending" : "active",
      paymentStatus: Number(balance.outstandingAmount ?? 0) > 0 ? "pending" : "paid",
      slotLabel: balance.memberNo ? `Slot ${balance.memberNo}` : balance.slotCount ? `${balance.slotCount} slots` : "Slot unclear",
      paid: Number(balance.totalPaid ?? 0),
      due: Number(balance.totalDue ?? 0),
      balance: Number(balance.outstandingAmount ?? 0),
      raw: balance,
    }));
  }
  if (memberGroup) {
    return [
      {
        id: memberGroup.id,
        name: `Member #${memberGroup.memberNo ?? "N/A"}`,
        status: memberGroup.status,
        paymentStatus: Number(memberGroup.outstandingAmount ?? 0) > 0 ? "pending" : "paid",
        slotLabel: memberGroup.memberNo ? `Slot ${memberGroup.memberNo}` : memberGroup.slotCount ? `${memberGroup.slotCount} slots` : "Slot unclear",
        paid: Number(memberGroup.totalPaid ?? 0),
        due: Number(memberGroup.totalDue ?? 0),
        balance: Number(memberGroup.outstandingAmount ?? 0),
        raw: memberGroup,
      },
    ];
  }
  return [];
}

function GroupHeader({ auction, auctionBlockedByCollection, financials, group, isAuctionTabActive, isOwner, onOpenAuction, paymentSummary }) {
  const netTone = financials.net >= 0 ? "text-emerald-700" : "text-red-700";
  const liveAuction = isLiveAuction(auction);
  return (
    <section className="panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-wide text-slate-500">{isOwner ? "Owner group" : "Member group"}</p>
          <h1>{group.title}</h1>
          <p>
            {group.groupCode} · Month {group.currentCycleNo ?? "N/A"}/{group.cycleCount ?? "N/A"} · {titleCase(group.status)}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className={getStatusBadgeClass(liveAuction ? "active" : auction?.status ?? group.status)}>
            Auction {titleCase(liveAuction ? "live" : auction?.status ?? "not scheduled")}
          </span>
          {liveAuction && !isAuctionTabActive ? (
            <button className="action-button mt-0" disabled={auctionBlockedByCollection} onClick={onOpenAuction} type="button">
              {isOwner ? "Open Auction Console" : "Join Auction"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="panel-grid mt-4 md:grid-cols-5">
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Chit value</p>
          <h3>{group.chitValue != null ? formatMoney(group.chitValue) : "N/A"}</h3>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Month progress</p>
          <h3>
            {group.currentCycleNo ?? "N/A"}/{group.cycleCount ?? "N/A"}
          </h3>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Members</p>
          <h3>{group.activeMemberCount ?? group.memberCount ?? "N/A"}</h3>
        </article>
        <article className="panel status-panel status-panel--success">
          <p className="text-sm uppercase tracking-wide text-emerald-700">Paid</p>
          <h3>{paymentSummary.paidCount}/{paymentSummary.totalCount}</h3>
        </article>
        <article className={paymentSummary.pendingCount > 0 ? "panel status-panel status-panel--danger" : "panel status-panel status-panel--success"}>
          <p className="text-sm uppercase tracking-wide">Pending</p>
          <h3>{paymentSummary.pendingCount}</h3>
        </article>
      </div>

      <div className="panel-grid mt-4 md:grid-cols-4">
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Total paid</p>
          <h3>{formatMoney(financials.totalPaid)}</h3>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Dividend earned</p>
          <h3>{formatMoney(financials.dividendEarned)}</h3>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Total received</p>
          <h3>{formatMoney(financials.totalReceived)}</h3>
        </article>
        <article className="panel">
          <p className="text-sm uppercase tracking-wide text-slate-500">Net profit/loss</p>
          <h3 className={netTone}>{formatMoney(financials.net)}</h3>
        </article>
      </div>
    </section>
  );
}

function MemberStatusTable({ emptyMessage, members }) {
  if (members.length === 0) {
    return <p>{emptyMessage}</p>;
  }

  return (
    <div className="responsive-table mt-3">
      <table>
        <thead>
          <tr>
            <th>Member</th>
            <th>Slot</th>
            <th>Status</th>
            <th>Paid</th>
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={member.id}>
              <td>{member.name}</td>
              <td>{member.slotLabel}</td>
              <td>
                <span className={getStatusBadgeClass(member.paymentStatus)}>{titleCase(member.paymentStatus)}</span>
              </td>
              <td>{formatMoney(member.paid)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabButton({ active, children, onClick }) {
  return (
    <button aria-selected={active} className={`tab-button${active ? " tab-button--active" : ""}`} onClick={onClick} role="tab" type="button">
      {children}
    </button>
  );
}

export default function GroupDetailPage() {
  const { groupId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentUser = getCurrentUser();
  const ownerId = getOwnerId(currentUser);
  const isOwner = sessionHasRole(currentUser, "owner");
  const [ownerDashboard, setOwnerDashboard] = useState(null);
  const [memberDashboard, setMemberDashboard] = useState(null);
  const [groupDetails, setGroupDetails] = useState([]);
  const [payments, setPayments] = useState([]);
  const [paymentsLoading, setPaymentsLoading] = useState(false);
  const [paymentsError, setPaymentsError] = useState("");
  const [payouts, setPayouts] = useState([]);
  const [payoutsLoading, setPayoutsLoading] = useState(false);
  const [payoutsError, setPayoutsError] = useState("");
  const [settlingPayoutId, setSettlingPayoutId] = useState(null);
  const [groupStatus, setGroupStatus] = useState(null);
  const [groupStatusError, setGroupStatusError] = useState("");
  const [groupMemberSummary, setGroupMemberSummary] = useState([]);
  const [groupMemberSummaryError, setGroupMemberSummaryError] = useState("");
  const [collectionError, setCollectionError] = useState("");
  const [closingCollection, setClosingCollection] = useState(false);
  const [memberSearch, setMemberSearch] = useState("");
  const [invitePhone, setInvitePhone] = useState("");
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [inviting, setInviting] = useState(false);
  const [confirmingResult, setConfirmingResult] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");
  const [confirmError, setConfirmError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const activeTab = TABS.includes(searchParams.get("tab")) ? searchParams.get("tab") : "members";
  const numericGroupId = Number(groupId);

  useEffect(() => {
    let active = true;

    setLoading(true);
    setError("");
    setGroupStatusError("");
    setGroupMemberSummaryError("");
    setPaymentsError("");
    setPayoutsError("");
    setPaymentsLoading(Boolean(isOwner && numericGroupId));
    setPayoutsLoading(Boolean(isOwner && numericGroupId));

    const dashboardPromise = fetchUserDashboard();
    const groupsPromise = isOwner ? fetchGroups() : Promise.resolve([]);
    const groupStatusPromise = numericGroupId ? fetchGroupStatus(numericGroupId) : Promise.resolve(null);
    const groupMemberSummaryPromise = numericGroupId ? fetchGroupMemberSummary(numericGroupId) : Promise.resolve([]);
    const paymentsPromise = isOwner && numericGroupId ? fetchPayments({ groupId: numericGroupId }) : Promise.resolve([]);
    const payoutsPromise = isOwner && numericGroupId ? fetchOwnerPayouts({ groupId: numericGroupId }) : Promise.resolve([]);

    Promise.allSettled([
      dashboardPromise,
      groupsPromise,
      groupStatusPromise,
      groupMemberSummaryPromise,
      paymentsPromise,
      payoutsPromise,
    ])
      .then(([dashboardResult, groupsResult, groupStatusResult, groupMemberSummaryResult, paymentsResult, payoutsResult]) => {
        if (!active) {
          return;
        }

        if (dashboardResult.status === "fulfilled") {
          const data = dashboardResult.value;
          setMemberDashboard(getSubscriberDashboardFromUserDashboard(data));
          if (data?.role === "owner") {
            setOwnerDashboard(getOwnerDashboardFromUserDashboard(data));
          } else {
            setOwnerDashboard(null);
          }
        } else {
          setError(getApiErrorMessage(dashboardResult.reason, { fallbackMessage: "Unable to load this group." }));
        }

        if (groupsResult.status === "fulfilled") {
          setGroupDetails(Array.isArray(groupsResult.value) ? groupsResult.value : []);
        } else if (isOwner) {
          setError(getApiErrorMessage(groupsResult.reason, { fallbackMessage: "Unable to load this group." }));
        }

        if (groupStatusResult.status === "fulfilled") {
          setGroupStatus(groupStatusResult.value);
        } else {
          setGroupStatusError(getApiErrorMessage(groupStatusResult.reason, { fallbackMessage: "Unable to load group status." }));
        }

        if (groupMemberSummaryResult.status === "fulfilled") {
          setGroupMemberSummary(Array.isArray(groupMemberSummaryResult.value) ? groupMemberSummaryResult.value : []);
        } else {
          setGroupMemberSummaryError(
            getApiErrorMessage(groupMemberSummaryResult.reason, { fallbackMessage: "Unable to load member summary." }),
          );
        }

        if (paymentsResult.status === "fulfilled") {
          setPayments(Array.isArray(paymentsResult.value) ? paymentsResult.value : []);
        } else if (isOwner) {
          setPaymentsError(getApiErrorMessage(paymentsResult.reason, { fallbackMessage: "Unable to load payments." }));
        }

        if (payoutsResult.status === "fulfilled") {
          setPayouts(Array.isArray(payoutsResult.value) ? payoutsResult.value : []);
        } else if (isOwner) {
          setPayoutsError(getApiErrorMessage(payoutsResult.reason, { fallbackMessage: "Unable to load payouts." }));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          setPaymentsLoading(false);
          setPayoutsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isOwner, numericGroupId]);

  const ownerGroup = useMemo(() => {
    const summary = (ownerDashboard?.groups ?? []).find((group) => Number(group.groupId) === numericGroupId);
    const detail = groupDetails.find((group) => Number(group.id) === numericGroupId);
    return normalizeOwnerGroup(summary, detail);
  }, [groupDetails, numericGroupId, ownerDashboard]);
  const memberGroup = useMemo(
    () => normalizeMemberGroup((memberDashboard?.memberships ?? []).find((group) => Number(group.groupId) === numericGroupId)),
    [memberDashboard, numericGroupId],
  );
  const group = ownerGroup ?? memberGroup;
  const collectionClosed = useMemo(() => {
    if (groupStatus) {
      return Boolean(groupStatus.collection_closed) || isClosedLifecycleStatus(groupStatus.status);
    }
    return Boolean(group?.collectionClosed) || isClosedLifecycleStatus(group?.currentMonthStatus);
  }, [group, groupStatus]);
  const auctionBlockedByCollection = !isCollectionClosedLifecycleStatus(groupStatus?.status ?? group?.currentMonthStatus);
  const activeAuction = useMemo(() => {
    const ownerAuction = (ownerDashboard?.recentAuctions ?? []).find((auction) => Number(auction.groupId) === numericGroupId);
    const memberAuction = (memberDashboard?.activeAuctions ?? []).find((auction) => Number(auction.groupId) === numericGroupId);
    return ownerAuction ?? memberAuction ?? null;
  }, [memberDashboard, numericGroupId, ownerDashboard]);
  const balances = useMemo(
    () => (ownerDashboard?.balances ?? memberDashboard?.memberships ?? []).filter((item) => Number(item.groupId) === numericGroupId),
    [memberDashboard, numericGroupId, ownerDashboard],
  );
  const memberRows = useMemo(() => buildMemberRows({ balances, memberGroup }), [balances, memberGroup]);
  const filteredMembers = useMemo(() => {
    const query = memberSearch.trim().toLowerCase();
    if (!query) {
      return memberRows;
    }
    return memberRows.filter((member) => member.name.toLowerCase().includes(query) || String(member.id).includes(query));
  }, [memberRows, memberSearch]);
  const activeMembers = filteredMembers.filter((member) => String(member.status).toLowerCase() !== "pending");
  const pendingMembers = filteredMembers.filter((member) => String(member.status).toLowerCase() === "pending");
  const paymentSummary = useMemo(() => {
    const backendTotalCount = Number(groupStatus?.total_members);
    const backendPaidCount = Number(groupStatus?.paid_members);
    const fallbackTotalCount = memberRows.length || Number(group?.memberCount ?? group?.activeMemberCount ?? 0);
    const totalCount = Number.isFinite(backendTotalCount) && backendTotalCount > 0 ? backendTotalCount : fallbackTotalCount;
    const fallbackPaidCount = memberRows.filter((member) => Number(member.balance) <= 0).length;
    const paidCount = Number.isFinite(backendPaidCount) && backendPaidCount >= 0 ? Math.min(backendPaidCount, totalCount) : fallbackPaidCount;
    return {
      totalCount,
      paidCount,
      pendingCount: Math.max(totalCount - paidCount, 0),
      paidAmount: Number(group?.totalPaid ?? memberRows.reduce((sum, member) => sum + member.paid, 0)),
      totalAmount: Number(group?.totalDue ?? memberRows.reduce((sum, member) => sum + member.due, 0)),
    };
  }, [group, groupStatus, memberRows]);
  const financials = useMemo(() => {
    if (groupMemberSummary.length > 0) {
      const totalPaid = groupMemberSummary.reduce((sum, member) => sum + Number(member.paid ?? 0), 0);
      const dividendEarned = groupMemberSummary.reduce((sum, member) => sum + Number(member.dividend ?? 0), 0);
      const totalReceived = groupMemberSummary.reduce((sum, member) => sum + Number(member.received ?? 0), 0);
      const net = groupMemberSummary.reduce((sum, member) => sum + Number(member.net ?? 0), 0);
      return {
        totalPaid,
        dividendEarned,
        totalReceived,
        net,
        isDerived: false,
      };
    }
    const totalPaid = Number(group?.totalPaid ?? memberRows.reduce((sum, member) => sum + member.paid, 0));
    const dividendEarned = payouts.reduce((sum, payout) => sum + Number(payout.deductionsAmount ?? 0), 0);
    const totalReceived = payouts.reduce((sum, payout) => sum + Number(payout.netAmount ?? 0), 0);
    return {
      totalPaid,
      dividendEarned,
      totalReceived,
      net: totalReceived + dividendEarned - totalPaid,
      isDerived: true,
    };
  }, [group, groupMemberSummary, memberRows, payouts]);

  const ledgerRows = useMemo(() => {
    if (groupMemberSummary.length > 0) {
      return groupMemberSummary.map((member) => ({
        id: member.membershipId,
        name: member.memberName ?? `Member #${member.memberNo ?? member.membershipId}`,
        paid: Number(member.paid ?? 0),
        received: Number(member.received ?? 0),
        net: Number(member.net ?? 0),
      }));
    }
    return memberRows.map((member) => ({
      id: member.id,
      name: member.name,
      paid: Number(member.paid ?? 0),
      received: Number(payouts.find((payout) => payout.membershipId === member.id)?.netAmount ?? 0),
      net: Number(payouts.find((payout) => payout.membershipId === member.id)?.netAmount ?? 0) - Number(member.paid ?? 0),
    }));
  }, [groupMemberSummary, memberRows, payouts]);

  useAppShellHeader({
    title: group?.title ?? "Group",
    contextLabel: group?.groupCode ?? "Members, payments, auction, and ledger",
  });

  async function handleCopyGroupId() {
    try {
      await navigator.clipboard.writeText(String(groupId));
      setInviteMessage("Group ID copied.");
      setInviteError("");
    } catch (_error) {
      setInviteError("Copy is not available in this browser.");
    }
  }

  async function handleInvite(event) {
    event.preventDefault();
    if (!invitePhone.trim()) {
      setInviteError("Enter a phone number to invite.");
      return;
    }
    setInviting(true);
    setInviteError("");
    setInviteMessage("");
    try {
      await inviteSubscriberToGroup(numericGroupId, invitePhone.trim());
      setInvitePhone("");
      setInviteMessage("Invite sent.");
    } catch (inviteFailure) {
      setInviteError(getApiErrorMessage(inviteFailure, { fallbackMessage: "Unable to send invite." }));
    } finally {
      setInviting(false);
    }
  }

  async function handleSettlePayout(payout) {
    if (typeof window !== "undefined" && !window.confirm("Mark this payout as paid?")) {
      return;
    }
    setSettlingPayoutId(payout.id);
    try {
      const updated = await markOwnerPayoutPaid(payout.id);
      setPayouts((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (settleError) {
      setPayoutsError(getApiErrorMessage(settleError, { fallbackMessage: "Unable to mark this payout as paid." }));
    } finally {
      setSettlingPayoutId(null);
    }
  }

  async function handleConfirmResult() {
    if (!activeAuction?.sessionId) {
      return;
    }
    setConfirmingResult(true);
    setConfirmMessage("");
    setConfirmError("");
    try {
      await finalizeAuctionSession(activeAuction.sessionId);
      setConfirmMessage("Auction result confirmed.");
    } catch (confirmFailure) {
      setConfirmError(getApiErrorMessage(confirmFailure, { fallbackMessage: "Unable to confirm this result." }));
    } finally {
      setConfirmingResult(false);
    }
  }

  async function handleCloseCollection() {
    if (!numericGroupId) {
      return;
    }
    if (typeof window !== "undefined" && !window.confirm("Close collection for this group?")) {
      return;
    }
    setClosingCollection(true);
    setCollectionError("");
    try {
      const updated = await closeGroupCollection(numericGroupId);
      setGroupStatus((current) => ({
        collection_closed: Boolean(updated.collectionClosed),
        status: updated.currentMonthStatus ?? current?.status ?? "COLLECTION_CLOSED",
        paid_members: current?.paid_members ?? paymentSummary.paidCount,
        total_members: current?.total_members ?? paymentSummary.totalCount,
      }));
      setGroupDetails((current) => current.map((item) => (Number(item.id) === numericGroupId ? { ...item, ...updated } : item)));
      setOwnerDashboard((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          groups: (current.groups ?? []).map((item) =>
            Number(item.groupId) === numericGroupId
              ? {
                  ...item,
                  collectionClosed: Boolean(updated.collectionClosed),
                  currentMonthStatus: updated.currentMonthStatus,
                }
              : item,
          ),
        };
      });
    } catch (closeError) {
      setCollectionError(getApiErrorMessage(closeError, { fallbackMessage: "Unable to close collection." }));
    } finally {
      setClosingCollection(false);
    }
  }

  if (loading) {
    return <PageLoadingState description="Loading group workspace." label="Loading group..." />;
  }

  if (error) {
    return <PageErrorState error={error} onRetry={() => window.location.reload()} title="We could not load this group." />;
  }

  if (!group) {
    return (
      <main className="page-shell">
        <section className="panel">
          <h1>Group not available</h1>
          <p>This group is unclear from codebase because there is no dedicated group-detail API; it must appear in dashboard data.</p>
          <Link className="action-button" to="/groups">
            Back to groups
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <GroupHeader
        auction={activeAuction}
        auctionBlockedByCollection={auctionBlockedByCollection}
        financials={financials}
        group={group}
        isAuctionTabActive={activeTab === "auction"}
        isOwner={isOwner}
        onOpenAuction={() => setSearchParams({ tab: "auction" })}
        paymentSummary={paymentSummary}
      />

      <section className="panel">
        <div className="tab-list" role="tablist">
          {TABS.map((tab) => (
            <TabButton active={activeTab === tab} key={tab} onClick={() => setSearchParams({ tab })}>
              {titleCase(tab)}
            </TabButton>
          ))}
        </div>
      </section>

      {activeTab === "members" ? (
        <section className="panel" role="tabpanel">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2>Members</h2>
              <p>Active and pending members are separated for faster review.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="action-button mt-0" onClick={handleCopyGroupId} type="button">
                Copy Group ID
              </button>
            </div>
          </div>

          <input
            className="text-input mt-4"
            onChange={(event) => setMemberSearch(event.target.value)}
            placeholder="Search members"
            type="search"
            value={memberSearch}
          />

          {isOwner ? (
            <form className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleInvite}>
              <input
                className="text-input"
                onChange={(event) => setInvitePhone(event.target.value)}
                placeholder="Subscriber phone number"
                type="tel"
                value={invitePhone}
              />
              <button className="action-button mt-0" disabled={inviting} type="submit">
                {inviting ? "Sending..." : "Invite"}
              </button>
            </form>
          ) : null}
          {inviteMessage ? <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">{inviteMessage}</p> : null}
          {inviteError ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-red-900">{inviteError}</p> : null}

          <div className="panel-grid mt-4 md:grid-cols-2">
            <section className="status-panel status-panel--success">
              <h3>Active</h3>
              <MemberStatusTable emptyMessage="No active members match this view." members={activeMembers} />
            </section>
            <section className="status-panel status-panel--danger">
              <h3>Pending</h3>
              <MemberStatusTable emptyMessage="No pending members match this view." members={pendingMembers} />
            </section>
          </div>

          {isOwner ? (
            <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <summary className="cursor-pointer font-semibold text-slate-950">Manage subscriber directory</summary>
              <div className="mt-4">
                <SubscriberManagementPanel ownerId={ownerId} />
              </div>
            </details>
          ) : null}
        </section>
      ) : null}

      {activeTab === "payments" ? (
        <section className="panel" role="tabpanel">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2>Payments</h2>
              <p>Monthly summary: Paid {paymentSummary.paidCount} / Total {paymentSummary.totalCount}</p>
            </div>
            {isOwner ? (
              <button className="action-button mt-0" disabled={collectionClosed || closingCollection} onClick={handleCloseCollection} type="button">
                {closingCollection ? "Closing..." : collectionClosed ? "Collection closed" : "Close Collection"}
              </button>
            ) : null}
          </div>
          {groupStatusError ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-red-900">{groupStatusError}</p> : null}
          {groupMemberSummaryError ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-red-900">{groupMemberSummaryError}</p> : null}
          {collectionError ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-red-900">{collectionError}</p> : null}
          <div className="panel-grid mt-4 md:grid-cols-3">
            <article className="panel status-panel status-panel--success">
              <h3>{formatMoney(paymentSummary.paidAmount)}</h3>
              <p>Paid this month</p>
            </article>
            <article className={paymentSummary.pendingCount > 0 ? "panel status-panel status-panel--danger" : "panel status-panel status-panel--success"}>
              <h3>{paymentSummary.pendingCount}</h3>
              <p>Unpaid members</p>
            </article>
            <article className="panel">
              <h3>{formatMoney(paymentSummary.totalAmount)}</h3>
              <p>Total expected</p>
            </article>
          </div>

          {collectionClosed ? (
            <div className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">
              <strong>Collection closed.</strong> Editing is hidden and the auction tab is ready for review.
            </div>
          ) : null}

          {isOwner && !collectionClosed ? (
            <div className="mt-4">
              <PaymentPanel
                historyError={paymentsError}
                historyLoading={paymentsLoading}
                initialPayments={payments}
                onRecorded={(payment) => setPayments((current) => [payment, ...current])}
                onRetryHistory={() => window.location.reload()}
                ownerId={ownerId}
              />
            </div>
          ) : (
            <div className="panel-grid mt-4">
              {balances.map((balance) => (
                <MemberBalanceSummary key={balance.membershipId} summary={buildMemberBalanceSummary(balance)} />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "auction" ? (
        <section className="panel" role="tabpanel">
          <div className="panel-grid md:grid-cols-3">
            <article className={paymentSummary.pendingCount > 0 ? "panel status-panel status-panel--danger" : "panel status-panel status-panel--success"}>
              <p className="text-sm uppercase tracking-wide">Payments status</p>
              <h3>{paymentSummary.paidCount}/{paymentSummary.totalCount}</h3>
              <p>{paymentSummary.pendingCount > 0 ? "Pending payments exist." : "Payments are complete."}</p>
            </article>
            <article className="panel">
              <p className="text-sm uppercase tracking-wide text-slate-500">Auction state</p>
              <h3>{titleCase(activeAuction?.status ?? "not scheduled")}</h3>
              <p>{activeAuction?.auctionMode ? `${titleCase(activeAuction.auctionMode)} auction` : "No auction mode available"}</p>
            </article>
            <article className="panel">
              <p className="text-sm uppercase tracking-wide text-slate-500">Bid signal</p>
              <h3>{activeAuction?.validBidCount ?? activeAuction?.totalBidCount ?? 0}</h3>
              <p>{String(activeAuction?.auctionMode ?? "").toUpperCase() === "BLIND" ? "Total bids" : "Current bid count"}</p>
            </article>
          </div>

          {auctionBlockedByCollection ? (
            <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-red-900">Close collection before starting an auction.</p>
          ) : null}

          {activeAuction?.sessionId ? (
            <div className="mt-4">
              {isOwner ? <OwnerAuctionConsole sessionId={activeAuction.sessionId} /> : <AuctionRoomPage embedded sessionId={activeAuction.sessionId} />}
              {isOwner ? (
                <div className="mt-4">
                  <button
                    className="action-button"
                    disabled={confirmingResult || auctionBlockedByCollection}
                    onClick={handleConfirmResult}
                    type="button"
                  >
                    {confirmingResult ? "Confirming..." : "Confirm result"}
                  </button>
                  {confirmMessage ? <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-emerald-900">{confirmMessage}</p> : null}
                  {confirmError ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-red-900">{confirmError}</p> : null}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h2>Auction</h2>
              <p>No active or recent auction session is visible for this group in current dashboard data.</p>
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "payout" ? (
        <section className="panel" role="tabpanel">
          <h2>Payout</h2>
          {!isOwner ? <p>Payout records are owner-scoped in the current backend.</p> : null}
          {payoutsLoading ? <PageLoadingState description="Loading payout records." label="Loading payouts..." /> : null}
          {payoutsError ? <p className="rounded-md bg-red-50 px-3 py-2 text-red-900">{payoutsError}</p> : null}
          {isOwner && !payoutsLoading && payouts.length === 0 ? <p>No payout has been generated for this group yet.</p> : null}
          {isOwner && payouts.length > 0 ? (
            <div className="responsive-table mt-4">
              <table>
                <thead>
                  <tr>
                    <th>Winner</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {payouts.map((payout) => (
                    <tr key={payout.id}>
                      <td>{payout.subscriberName ?? `Subscriber #${payout.subscriberId}`}</td>
                      <td>{formatMoney(payout.netAmount)}</td>
                      <td>
                        <span className={getStatusBadgeClass(payout.status)}>{titleCase(payout.status)}</span>
                      </td>
                      <td>
                        {String(payout.status ?? "").toLowerCase() === "pending" ? (
                          <button className="action-button mt-0" disabled={settlingPayoutId === payout.id} onClick={() => handleSettlePayout(payout)} type="button">
                            {settlingPayoutId === payout.id ? "Updating..." : "Mark as Paid"}
                          </button>
                        ) : (
                          "Closed"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : null}

      {activeTab === "ledger" ? (
        <section className="panel" role="tabpanel">
          <h2>Ledger</h2>
          <div className="responsive-table mt-4">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Paid</th>
                  <th>Received</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {ledgerRows.map((member) => (
                  <tr key={member.id}>
                    <td>{member.name}</td>
                    <td>{formatMoney(member.paid)}</td>
                    <td>{formatMoney(member.received)}</td>
                    <td className={member.net >= 0 ? "text-emerald-700" : "text-red-700"}>{formatMoney(member.net)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total / Net</td>
                  <td>{formatMoney(financials.totalPaid)}</td>
                  <td>{formatMoney(financials.totalReceived)}</td>
                  <td className={financials.net >= 0 ? "text-emerald-700" : "text-red-700"}>{formatMoney(financials.net)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {ledgerRows.length === 0 ? <p className="mt-4">Ledger rows are not visible from current dashboard data.</p> : null}
        </section>
      ) : null}

      {activeTab === "settings" ? (
        <section className="panel" role="tabpanel">
          <h2>Settings</h2>
          <p>Settings are read-only here because a backend group-update endpoint is unclear from codebase.</p>
          <dl className="mt-4 grid gap-3 md:grid-cols-2">
            <div>
              <dt className="font-semibold text-slate-500">Code</dt>
              <dd>{group.groupCode}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Visibility</dt>
              <dd>{titleCase(group.visibility)}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Installment</dt>
              <dd>{formatMoney(group.installmentAmount)}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-500">Members</dt>
              <dd>{group.activeMemberCount ?? group.memberCount ?? "N/A"}</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </main>
  );
}
