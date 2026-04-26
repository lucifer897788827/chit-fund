import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, sessionHasRole } from "../lib/auth/store";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";
import { fetchPublicChits, requestGroupMembership, searchChitsByCode } from "../features/auctions/api";
import { formatMoney } from "../features/payments/balances";

function titleCase(value) {
  return String(value || "unknown")
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeOwnerGroup(group) {
  return {
    id: group.groupId,
    title: group.title,
    groupCode: group.groupCode,
    visibility: group.visibility,
    chitValue: group.chitValue,
    installmentAmount: group.installmentAmount,
    memberCount: group.memberCount,
    cycleCount: group.cycleCount,
    currentCycleNo: group.currentCycleNo,
    role: "Owner",
  };
}

function normalizeMemberGroup(membership) {
  return {
    id: membership.groupId,
    title: membership.groupTitle,
    groupCode: membership.groupCode,
    installmentAmount: membership.installmentAmount,
    memberCount: null,
    cycleCount: null,
    currentCycleNo: membership.currentCycleNo,
    membershipStatus: membership.membershipStatus,
    role: "Member",
  };
}

export default function GroupsListPage() {
  const currentUser = getCurrentUser();
  const isOwner = sessionHasRole(currentUser, "owner");
  const [ownerGroups, setOwnerGroups] = useState([]);
  const [memberGroups, setMemberGroups] = useState([]);
  const [publicGroups, setPublicGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [codeResults, setCodeResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [feedbackByGroupId, setFeedbackByGroupId] = useState({});
  const [requestingGroupId, setRequestingGroupId] = useState(null);

  useAppShellHeader({
    title: "Groups",
    contextLabel: isOwner ? "Owned groups and member groups" : "Memberships and public groups",
  });

  useEffect(() => {
    let active = true;
    const loads = [
      fetchSubscriberDashboard().then((data) => {
        if (active) {
          setMemberGroups((data?.memberships ?? []).map(normalizeMemberGroup));
        }
      }),
      fetchPublicChits().then((data) => {
        if (active) {
          setPublicGroups(Array.isArray(data) ? data : []);
        }
      }),
    ];

    if (isOwner) {
      loads.push(
        fetchOwnerDashboard().then((data) => {
          if (active) {
            setOwnerGroups((data?.groups ?? []).map(normalizeOwnerGroup));
          }
        }),
      );
    }

    Promise.allSettled(loads)
      .then((results) => {
        if (!active) {
          return;
        }
        const failed = results.find((result) => result.status === "rejected");
        if (failed) {
          setError(getApiErrorMessage(failed.reason, { fallbackMessage: "Unable to load groups right now." }));
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
  }, [isOwner]);

  const visibleGroups = useMemo(() => {
    const seen = new Set();
    return [...ownerGroups, ...memberGroups].filter((group) => {
      if (!group.id || seen.has(group.id)) {
        return false;
      }
      seen.add(group.id);
      return true;
    });
  }, [memberGroups, ownerGroups]);

  async function handleSearch(event) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setCodeResults([]);
      return;
    }
    setSearching(true);
    try {
      setCodeResults(await searchChitsByCode(normalizedQuery));
    } catch (searchError) {
      setError(getApiErrorMessage(searchError, { fallbackMessage: "Unable to search by group code." }));
    } finally {
      setSearching(false);
    }
  }

  async function handleRequestJoin(group) {
    setRequestingGroupId(group.id);
    setFeedbackByGroupId((current) => ({ ...current, [group.id]: "" }));
    try {
      await requestGroupMembership(group.id);
      setFeedbackByGroupId((current) => ({ ...current, [group.id]: "Membership request submitted." }));
    } catch (requestError) {
      setFeedbackByGroupId((current) => ({
        ...current,
        [group.id]: getApiErrorMessage(requestError, { fallbackMessage: "Unable to request membership." }),
      }));
    } finally {
      setRequestingGroupId(null);
    }
  }

  if (loading) {
    return <PageLoadingState description="Loading owned, joined, and public groups." label="Loading groups..." />;
  }

  if (error) {
    return <PageErrorState error={error} onRetry={() => window.location.reload()} title="We could not load groups." />;
  }

  return (
    <main className="page-shell">
      <section className="panel">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1>Groups</h1>
            <p>Open a group to manage members, payments, auction state, payouts, ledger, and settings.</p>
          </div>
          {isOwner ? (
            <Link className="action-button mt-0" to="/groups/create">
              Create group
            </Link>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <h2>Your groups</h2>
        {visibleGroups.length === 0 ? (
          <div className="empty-state">
            <h3>No groups yet</h3>
            <p>Joined and owned chit groups will appear here after your first membership is active.</p>
            {isOwner ? (
              <Link className="action-button" to="/groups/create">
                Create group
              </Link>
            ) : null}
          </div>
        ) : null}
        {visibleGroups.length > 0 ? (
          <div className="panel-grid md:grid-cols-2">
            {visibleGroups.map((group) => (
              <article className="panel" key={group.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <span className="status-badge">{group.role}</span>
                  {group.membershipStatus ? <span className="status-badge status-badge--success">{titleCase(group.membershipStatus)}</span> : null}
                </div>
                <h3 className="mt-3">{group.title}</h3>
                <p>
                  {group.groupCode} · Cycle {group.currentCycleNo ?? "N/A"}
                </p>
                {group.installmentAmount ? <p>Installment {formatMoney(group.installmentAmount)}</p> : null}
                <Link className="action-button" to={`/groups/${group.id}`}>
                  Open group
                </Link>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h2>Join by group code</h2>
        <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleSearch}>
          <input
            className="text-input"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Enter group code"
            type="text"
            value={query}
          />
          <button className="action-button mt-0" disabled={searching} type="submit">
            {searching ? "Searching..." : "Search"}
          </button>
        </form>
        {searching ? <p className="mt-3 text-sm text-slate-600">Searching matching group codes...</p> : null}
        {codeResults.length > 0 ? (
          <div className="panel-grid mt-4 md:grid-cols-2">
            {codeResults.map((group) => (
              <article className="panel" key={`${group.id}-${group.groupCode}`}>
                <h3>{group.title}</h3>
                <p>{group.groupCode}</p>
                <p>{formatMoney(group.chitValue)} chit value</p>
                <button
                  className="action-button"
                  disabled={requestingGroupId === group.id}
                  onClick={() => handleRequestJoin(group)}
                  type="button"
                >
                  {requestingGroupId === group.id ? "Requesting..." : "Request to join"}
                </button>
                {feedbackByGroupId[group.id] ? <p>{feedbackByGroupId[group.id]}</p> : null}
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h2>Public groups</h2>
        {publicGroups.length === 0 ? (
          <div className="empty-state">
            <h3>No public groups</h3>
            <p>Public chit groups are not available right now. Use a group code if an owner invited you directly.</p>
          </div>
        ) : null}
        {publicGroups.length > 0 ? (
          <div className="panel-grid md:grid-cols-2">
            {publicGroups.map((group) => (
              <article className="panel" key={group.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h3>{group.title}</h3>
                  <span className="status-badge">{titleCase(group.visibility)}</span>
                </div>
                <p>{group.groupCode}</p>
                <p>{formatMoney(group.chitValue)} chit value</p>
                <button
                  className="action-button"
                  disabled={requestingGroupId === group.id}
                  onClick={() => handleRequestJoin(group)}
                  type="button"
                >
                  {requestingGroupId === group.id ? "Requesting..." : "Request to join"}
                </button>
                {feedbackByGroupId[group.id] ? <p>{feedbackByGroupId[group.id]}</p> : null}
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  );
}
