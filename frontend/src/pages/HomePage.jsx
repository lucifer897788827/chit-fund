import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { fetchActiveAdminMessage } from "../features/admin/api";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";
import { formatMoney } from "../features/payments/balances";

const DISMISSED_ADMIN_MESSAGE_KEY = "chit-fund-dismissed-admin-message";

function readDismissedAdminMessage() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(DISMISSED_ADMIN_MESSAGE_KEY) ?? "";
}

function getStatusBadgeClass(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (["paid", "full", "completed", "active", "open"].includes(normalized)) {
    return "status-badge status-badge--success";
  }
  if (["pending", "partial", "overdue", "due"].includes(normalized)) {
    return "status-badge status-badge--danger";
  }
  return "status-badge";
}

function titleCase(value) {
  return String(value || "unknown")
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function HomePage() {
  const currentUser = getCurrentUser();
  const roles = getUserRoles(currentUser);
  const isOwner = sessionHasRole(currentUser, "owner");
  const isAdmin = sessionHasRole(currentUser, "admin");
  const [ownerDashboard, setOwnerDashboard] = useState(null);
  const [memberDashboard, setMemberDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [adminMessage, setAdminMessage] = useState("");
  const [dismissedAdminMessage, setDismissedAdminMessage] = useState(() => readDismissedAdminMessage());
  const showAdminMessage = Boolean(adminMessage && dismissedAdminMessage !== adminMessage);

  useAppShellHeader({
    title: "Home",
    contextLabel: roles.length ? `${roles.join(" + ")} workspace` : "Today in your chit fund workspace",
  });

  useEffect(() => {
    let active = true;
    const loads = [];

    if (isOwner) {
      loads.push(fetchOwnerDashboard().then((data) => active && setOwnerDashboard(data)));
    }
    if (!isAdmin) {
      loads.push(fetchSubscriberDashboard().then((data) => active && setMemberDashboard(data)));
    }

    Promise.allSettled(loads)
      .then((results) => {
        if (!active) {
          return;
        }
        const failed = results.find((result) => result.status === "rejected");
        if (failed) {
          setError(getApiErrorMessage(failed.reason, { fallbackMessage: "Unable to load home right now." }));
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
  }, [isAdmin, isOwner]);

  useEffect(() => {
    let active = true;
    fetchActiveAdminMessage()
      .then((data) => {
        if (active) {
          setAdminMessage(String(data?.message ?? "").trim());
        }
      })
      .catch(() => {
        if (active) {
          setAdminMessage("");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  function handleDismissAdminMessage() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(DISMISSED_ADMIN_MESSAGE_KEY, adminMessage);
    }
    setDismissedAdminMessage(adminMessage);
  }

  const homeData = useMemo(() => {
    const memberships = memberDashboard?.memberships ?? [];
    const ownerGroups = ownerDashboard?.groups ?? [];
    const activeGroups = (isOwner ? ownerGroups : memberships)
      .filter((item) => String(item.status ?? item.membershipStatus ?? "active").toLowerCase() !== "completed")
      .slice(0, 4);
    const pendingPayments = (isOwner ? ownerDashboard?.balances ?? [] : memberships)
      .filter((item) => Number(item.outstandingAmount ?? item.arrearsAmount ?? 0) > 0)
      .slice(0, 4);
    const auctionAlerts = [
      ...(memberDashboard?.activeAuctions ?? []),
      ...(ownerDashboard?.recentAuctions ?? []).filter((auction) =>
        ["open", "upcoming", "scheduled"].includes(String(auction.status ?? "").toLowerCase()),
      ),
    ].slice(0, 4);

    return {
      activeGroups,
      pendingPayments,
      auctionAlerts,
    };
  }, [isOwner, memberDashboard, ownerDashboard]);

  if (loading) {
    return <PageLoadingState description="Loading your groups, dues, and auction access." label="Loading home..." />;
  }

  if (error) {
    return <PageErrorState error={error} onRetry={() => window.location.reload()} title="We could not load home." />;
  }

  return (
    <main className="page-shell">
      {showAdminMessage ? (
        <section className="panel status-panel status-panel--warning" role="status">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="font-semibold text-amber-950">⚠ Message: {adminMessage}</p>
            <button className="action-button mt-0" onClick={handleDismissAdminMessage} type="button">
              Dismiss
            </button>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h1>Home</h1>
        <p>What needs attention now: active groups, pending collections, and auction alerts.</p>
      </section>

      <section className="panel">
        <h2>Active groups</h2>
        {homeData.activeGroups.length === 0 ? <p>No active groups are visible right now.</p> : null}
        <div className="panel-grid md:grid-cols-2">
          {homeData.activeGroups.map((group, index) => {
            const groupId = group.groupId ?? group.id;
            const title = group.title ?? group.groupTitle ?? `Group #${groupId ?? index + 1}`;
            const status = group.status ?? group.membershipStatus ?? "active";
            return (
              <Link className="quiet-card-link" key={`${groupId ?? title}-${index}`} to={groupId ? `/groups/${groupId}` : "/groups"}>
                <article className="panel">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <h3>{title}</h3>
                    <span className={getStatusBadgeClass(status)}>{titleCase(status)}</span>
                  </div>
                  <p>{group.groupCode ?? "Code not available"}</p>
                  <p>Cycle {group.currentCycleNo ?? "N/A"}</p>
                </article>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <h2>Pending payments</h2>
        {homeData.pendingPayments.length === 0 ? (
          <div className="status-panel status-panel--success">
            <span className="status-badge status-badge--success">Completed</span>
            <p className="mt-2">No pending payment items are visible.</p>
          </div>
        ) : null}
        <div className="panel-grid md:grid-cols-2">
          {homeData.pendingPayments.map((item, index) => (
            <article className="panel status-panel status-panel--danger" key={`${item.membershipId ?? item.subscriberId ?? index}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3>{item.groupTitle ?? item.memberName ?? `Member #${item.memberNo ?? item.membershipId ?? "N/A"}`}</h3>
                <span className="status-badge status-badge--danger">Pending</span>
              </div>
              <p>{item.groupCode ?? `Group #${item.groupId ?? "N/A"}`}</p>
              <p className="mt-2 text-lg font-semibold text-red-800">
                {formatMoney(item.outstandingAmount ?? item.arrearsAmount ?? 0)} pending
              </p>
              <Link className="action-button" to="/payments">
                Review payment
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Auction alerts</h2>
        {homeData.auctionAlerts.length === 0 ? <p>No live or upcoming auction alerts right now.</p> : null}
        <div className="panel-grid md:grid-cols-2">
          {homeData.auctionAlerts.map((auction, index) => (
            <article className="panel" key={`${auction.sessionId ?? index}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3>{auction.groupTitle ?? `Group #${auction.groupId ?? "N/A"}`}</h3>
                <span className={getStatusBadgeClass(auction.status)}>{titleCase(auction.status)}</span>
              </div>
              <p>
                {auction.groupCode ?? "Code not available"} · Cycle {auction.cycleNo ?? "N/A"}
              </p>
              {auction.sessionId ? (
                <Link className="action-button" to={`/groups/${auction.groupId}?tab=auction`}>
                  Open auction
                </Link>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
