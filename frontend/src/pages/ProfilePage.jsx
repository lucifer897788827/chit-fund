import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { logoutUser } from "../features/auth/api";
import { createOwnerRequest } from "../features/owner-requests/api";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";
import { formatMoney } from "../features/payments/balances";
import { fetchMyFinancialSummary } from "../features/users/api";

function getFirstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "") ?? null;
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const roles = getUserRoles(currentUser);
  const isOwner = sessionHasRole(currentUser, "owner");
  const [ownerDashboard, setOwnerDashboard] = useState(null);
  const [memberDashboard, setMemberDashboard] = useState(null);
  const [financialSummary, setFinancialSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [requestState, setRequestState] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useAppShellHeader({
    title: "Profile",
    contextLabel: "Account access, financial snapshot, and quick links",
  });

  useEffect(() => {
    let active = true;
    const loads = [
      fetchSubscriberDashboard().then((data) => {
        if (active) {
          setMemberDashboard(data);
        }
      }),
      fetchMyFinancialSummary().then((data) => {
        if (active) {
          setFinancialSummary(data);
        }
      }),
    ];
    if (isOwner) {
      loads.push(
        fetchOwnerDashboard().then((data) => {
          if (active) {
            setOwnerDashboard(data);
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
          setLoadError(getApiErrorMessage(failed.reason, { fallbackMessage: "Some profile data could not be loaded." }));
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

  const snapshot = useMemo(() => {
    const memberships = memberDashboard?.memberships ?? [];
    const monthlyCommitment = memberships.reduce((sum, item) => sum + Number(item.installmentAmount ?? 0), 0);
    const memberPaid = memberships.reduce((sum, item) => sum + Number(item.totalPaid ?? 0), 0);
    const totalDividend = Number(financialSummary?.dividend ?? 0);
    const totalReceived = Number(financialSummary?.total_received ?? 0);
    const totalPaid = Number(financialSummary?.total_paid ?? ownerDashboard?.totalPaidAmount ?? memberPaid);
    const wonCount = memberships.filter((item) => Number(item.wonSlotCount ?? 0) > 0 || String(item.prizedStatus ?? "").toLowerCase() === "prized").length;
    return {
      monthlyCommitment,
      totalPaid,
      totalDividend,
      totalReceived,
      netProfit: Number(financialSummary?.net ?? totalReceived + totalDividend - totalPaid),
      totalChits: memberships.reduce((sum, item) => sum + Number(item.slotCount ?? 1), 0),
      activeCount: memberships.filter((item) => String(item.membershipStatus ?? "").toLowerCase() === "active").length,
      completedCount: memberships.filter((item) => String(item.membershipStatus ?? "").toLowerCase() === "completed").length,
      wonCount,
      notWonCount: Math.max(memberships.length - wonCount, 0),
    };
  }, [financialSummary, memberDashboard, ownerDashboard]);

  async function handleBecomeOwner() {
    setSubmitting(true);
    setRequestState(null);
    try {
      const response = await createOwnerRequest();
      setRequestState({
        type: "success",
        message: response?.status === "pending" ? "Owner request submitted for admin review." : "Owner request updated.",
      });
    } catch (error) {
      setRequestState({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to submit owner request." }),
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  if (loading) {
    return <PageLoadingState description="Loading account and financial snapshot." label="Loading profile..." />;
  }

  const user = currentUser?.user ?? {};
  const displayName =
    getFirstDefined(user.name, user.fullName, user.full_name, currentUser?.fullName, currentUser?.full_name, currentUser?.displayName) ??
    (user.id || currentUser?.userId ? `User #${user.id ?? currentUser.userId}` : "Profile");
  const profileFields = [
    { label: "Name", value: displayName },
    { label: "Phone", value: getFirstDefined(user.phone, user.phoneNumber, user.phone_number, currentUser?.phone, currentUser?.phoneNumber) },
    { label: "Email", value: getFirstDefined(user.email, currentUser?.email) },
  ].filter((field) => field.value);
  const ownerProfileId = getFirstDefined(currentUser?.owner_id, currentUser?.ownerId);
  const netTone = snapshot.netProfit >= 0 ? "text-emerald-700" : "text-red-700";

  return (
    <main className="page-shell">
      {loadError ? <p className="rounded-md bg-amber-50 px-3 py-2 text-amber-950">{loadError}</p> : null}

      <section className="panel">
        <h1>Profile</h1>
        <div className="panel-grid mt-4 md:grid-cols-3">
          {profileFields.map((field) => (
            <article className="panel" key={field.label}>
              <p className="text-sm uppercase tracking-wide text-slate-500">{field.label}</p>
              <h3>{field.value}</h3>
            </article>
          ))}
        </div>
        <p className="mt-4">Roles: {roles.length ? roles.join(", ") : "No roles found in session"}</p>
      </section>

      <section className="panel">
        <h2>Financial snapshot</h2>
        <div className="panel-grid mt-4 md:grid-cols-5">
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Monthly commitment</p>
            <h3>{formatMoney(snapshot.monthlyCommitment)}</h3>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Total paid</p>
            <h3>{formatMoney(snapshot.totalPaid)}</h3>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Total dividend</p>
            <h3>{formatMoney(snapshot.totalDividend)}</h3>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Total received</p>
            <h3>{formatMoney(snapshot.totalReceived)}</h3>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Net profit</p>
            <h3 className={netTone}>{formatMoney(snapshot.netProfit)}</h3>
          </article>
        </div>
      </section>

      <section className="panel">
        <h2>Stats</h2>
        <div className="panel-grid mt-4 md:grid-cols-4">
          <article className="panel">
            <h3>{snapshot.totalChits}</h3>
            <p>Total chits</p>
          </article>
          <article className="panel">
            <h3>{snapshot.activeCount} / {snapshot.completedCount}</h3>
            <p>Active / Completed</p>
          </article>
          <article className="panel">
            <h3>{snapshot.wonCount} / {snapshot.notWonCount}</h3>
            <p>Won / Not won</p>
          </article>
          {ownerProfileId ? (
            <article className="panel">
              <h3>{ownerProfileId}</h3>
              <p>Owner profile ID</p>
            </article>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <h2>Quick links</h2>
        <div className="panel-grid md:grid-cols-4">
          <Link className="action-button" to="/groups">
            Groups
          </Link>
          <Link className="action-button" to="/payments">
            Payments
          </Link>
          <Link className="action-button" to="/external-chits">
            External Chits
          </Link>
          {!isOwner ? (
            <button className="action-button" disabled={submitting} onClick={handleBecomeOwner} type="button">
              {submitting ? "Submitting..." : "Become Owner"}
            </button>
          ) : null}
          <button className="action-button" onClick={handleLogout} type="button">
            Log out
          </button>
        </div>
        {requestState ? (
          <p className={requestState.type === "error" ? "mt-4 rounded-md bg-red-50 px-3 py-2 text-red-900" : "mt-4 rounded-md bg-emerald-50 px-3 py-2 text-emerald-900"}>
            {requestState.message}
          </p>
        ) : null}
      </section>
    </main>
  );
}
