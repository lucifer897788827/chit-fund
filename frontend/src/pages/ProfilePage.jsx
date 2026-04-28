import { memo, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, getUserRoles, sessionHasRole } from "../lib/auth/store";
import { logoutUser } from "../features/auth/api";
import { createOwnerRequest } from "../features/owner-requests/api";
import {
  fetchUserDashboard,
  getOwnerDashboardFromUserDashboard,
  getSubscriberDashboardFromUserDashboard,
} from "../features/dashboard/api";
import { formatMoney } from "../features/payments/balances";
import { fetchMyFinancialSummary } from "../features/users/api";

function getFirstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "") ?? null;
}

function getSignedMoneyTone(value) {
  if (Number(value) > 0) {
    return "text-emerald-700";
  }
  if (Number(value) < 0) {
    return "text-red-700";
  }
  return "text-slate-700";
}

const MetricCard = memo(function MetricCard({ label, tone = "", value }) {
  return (
    <article className="panel">
      <p className="text-sm uppercase tracking-wide text-slate-500">{label}</p>
      <h3 className={tone}>{value}</h3>
    </article>
  );
});

const StatCard = memo(function StatCard({ label, value }) {
  return (
    <article className="panel">
      <h3>{value}</h3>
      <p>{label}</p>
    </article>
  );
});

export default function ProfilePage() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const roles = getUserRoles(currentUser);
  const isOwner = sessionHasRole(currentUser, "owner");
  const [requestState, setRequestState] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useAppShellHeader({
    title: "Profile",
    contextLabel: "Account access, financial snapshot, and quick links",
  });

  const dashboardQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchUserDashboard,
    staleTime: 30_000,
  });
  const financialSummaryQuery = useQuery({
    queryKey: ["profile", "financial-summary"],
    queryFn: fetchMyFinancialSummary,
    staleTime: 30_000,
  });
  const dashboardData = dashboardQuery.data;
  const ownerDashboard = dashboardData?.role === "owner" ? getOwnerDashboardFromUserDashboard(dashboardData) : null;
  const memberDashboard = getSubscriberDashboardFromUserDashboard(dashboardData);
  const financialSummary = financialSummaryQuery.data;
  const dashboardFinancialSummary = dashboardData?.financial_summary ?? {};
  const loading = dashboardQuery.isLoading || financialSummaryQuery.isLoading;
  const loadErrorSource = dashboardQuery.error ?? financialSummaryQuery.error;
  const loadError = loadErrorSource
    ? getApiErrorMessage(loadErrorSource, { fallbackMessage: "Some profile data could not be loaded." })
    : "";

  const snapshot = useMemo(() => {
    const memberships = memberDashboard?.memberships ?? [];
    const monthlyCommitment = memberships.reduce((sum, item) => sum + Number(item.installmentAmount ?? 0), 0);
    const memberPaid = memberships.reduce((sum, item) => sum + Number(item.totalPaid ?? 0), 0);
    const totalDividend = Number(getFirstDefined(dashboardFinancialSummary?.dividend, financialSummary?.dividend) ?? 0);
    const totalReceived = Number(getFirstDefined(dashboardFinancialSummary?.total_received, financialSummary?.total_received) ?? 0);
    const totalPaid = Number(
      getFirstDefined(dashboardFinancialSummary?.total_paid, financialSummary?.total_paid, ownerDashboard?.totalPaidAmount, memberPaid) ?? 0,
    );
    const calculatedNet = totalReceived + totalDividend - totalPaid;
    const calculatedNetPosition = totalReceived - totalPaid;
    const wonCount = memberships.filter((item) => Number(item.wonSlotCount ?? 0) > 0 || String(item.prizedStatus ?? "").toLowerCase() === "prized").length;
    return {
      monthlyCommitment,
      totalPaid,
      totalDividend,
      totalReceived,
      netProfit: Number(getFirstDefined(dashboardFinancialSummary?.net, financialSummary?.net, calculatedNet) ?? 0),
      netPosition: Number(
        getFirstDefined(dashboardFinancialSummary?.netPosition, financialSummary?.netPosition, calculatedNetPosition) ?? 0,
      ),
      totalChits: memberships.reduce((sum, item) => sum + Number(item.slotCount ?? 1), 0),
      activeCount: memberships.filter((item) => String(item.membershipStatus ?? "").toLowerCase() === "active").length,
      completedCount: memberships.filter((item) => String(item.membershipStatus ?? "").toLowerCase() === "completed").length,
      wonCount,
      notWonCount: Math.max(memberships.length - wonCount, 0),
    };
  }, [dashboardFinancialSummary, financialSummary, memberDashboard, ownerDashboard]);

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

  const user = currentUser?.user ?? {};
  const displayName =
    getFirstDefined(user.name, user.fullName, user.full_name, currentUser?.fullName, currentUser?.full_name, currentUser?.displayName) ??
    (user.id || currentUser?.userId ? `User #${user.id ?? currentUser.userId}` : "Profile");
  const profileFields = useMemo(
    () =>
      [
        { label: "Name", value: displayName },
        { label: "Phone", value: getFirstDefined(user.phone, user.phoneNumber, user.phone_number, currentUser?.phone, currentUser?.phoneNumber) },
        { label: "Email", value: getFirstDefined(user.email, currentUser?.email) },
      ].filter((field) => field.value),
    [currentUser, displayName, user.email, user.phone, user.phoneNumber, user.phone_number],
  );
  const ownerProfileId = getFirstDefined(currentUser?.owner_id, currentUser?.ownerId);
  const netProfitTone = getSignedMoneyTone(snapshot.netProfit);
  const netPositionTone = getSignedMoneyTone(snapshot.netPosition);
  const financialMetrics = useMemo(
    () => [
      { label: "Monthly commitment", value: formatMoney(snapshot.monthlyCommitment) },
      { label: "Total paid", value: formatMoney(snapshot.totalPaid) },
      { label: "Total dividend", value: formatMoney(snapshot.totalDividend) },
      { label: "Total received", value: formatMoney(snapshot.totalReceived) },
      { label: "Net profit", tone: netProfitTone, value: formatMoney(snapshot.netProfit) },
      { label: "Net position", tone: netPositionTone, value: formatMoney(snapshot.netPosition) },
    ],
    [
      netPositionTone,
      netProfitTone,
      snapshot.monthlyCommitment,
      snapshot.netPosition,
      snapshot.netProfit,
      snapshot.totalDividend,
      snapshot.totalPaid,
      snapshot.totalReceived,
    ],
  );
  const statCards = useMemo(
    () => [
      { label: "Total chits", value: snapshot.totalChits },
      { label: "Active / Completed", value: `${snapshot.activeCount} / ${snapshot.completedCount}` },
      { label: "Won / Not won", value: `${snapshot.wonCount} / ${snapshot.notWonCount}` },
      ...(ownerProfileId ? [{ label: "Owner profile ID", value: ownerProfileId }] : []),
    ],
    [ownerProfileId, snapshot.activeCount, snapshot.completedCount, snapshot.notWonCount, snapshot.totalChits, snapshot.wonCount],
  );

  if (loading) {
    return <PageLoadingState description="Loading account and financial snapshot." label="Loading profile..." />;
  }

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
        <div className="panel-grid mt-4 md:grid-cols-6">
          {financialMetrics.map((metric) => (
            <MetricCard key={metric.label} label={metric.label} tone={metric.tone} value={metric.value} />
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Stats</h2>
        <div className="panel-grid mt-4 md:grid-cols-4">
          {statCards.map((stat) => (
            <StatCard key={stat.label} label={stat.label} value={stat.value} />
          ))}
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
