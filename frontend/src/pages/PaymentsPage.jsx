import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../components/page-state";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser, sessionHasRole } from "../lib/auth/store";
import { fetchOwnerDashboard, fetchSubscriberDashboard } from "../features/dashboard/api";
import { fetchPayments } from "../features/payments/api";
import { formatMoney } from "../features/payments/balances";

function titleCase(value) {
  return String(value || "unknown")
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getStatusBadgeClass(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (["paid", "full", "completed", "recorded"].includes(normalized)) {
    return "status-badge status-badge--success";
  }
  if (["pending", "partial", "overdue", "due"].includes(normalized)) {
    return "status-badge status-badge--danger";
  }
  return "status-badge status-badge--warning";
}

function getMonthLabel(value) {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric" }).format(date);
}

export default function PaymentsPage() {
  const currentUser = getCurrentUser();
  const isOwner = sessionHasRole(currentUser, "owner");
  const [payments, setPayments] = useState([]);
  const [balances, setBalances] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [groupFilter, setGroupFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useAppShellHeader({
    title: "Payments",
    contextLabel: "Aggregated payment status across groups",
  });

  useEffect(() => {
    let active = true;
    const load = isOwner
      ? Promise.all([fetchPayments(), fetchOwnerDashboard()]).then(([paymentData, dashboardData]) => {
          if (active) {
            setPayments(Array.isArray(paymentData) ? paymentData : []);
            setBalances(dashboardData?.balances ?? []);
          }
        })
      : fetchSubscriberDashboard().then((data) => {
          if (active) {
            setBalances(data?.memberships ?? []);
          }
        });

    load
      .catch((loadError) => {
        if (active) {
          setError(getApiErrorMessage(loadError, { fallbackMessage: "Unable to load payments right now." }));
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

  const rows = useMemo(() => {
    if (isOwner && payments.length > 0) {
      return payments.map((payment) => ({
        id: payment.id ?? payment.paymentId,
        groupId: payment.groupId,
        group: payment.groupCode ?? payment.groupTitle ?? `Group #${payment.groupId ?? "N/A"}`,
        month: getMonthLabel(payment.paymentDate),
        status: payment.paymentStatus ?? payment.status ?? "recorded",
        paid: Number(payment.amount ?? 0),
      }));
    }
    return balances.map((balance) => ({
      id: balance.membershipId,
      groupId: balance.groupId,
      group: balance.groupTitle ?? balance.groupCode ?? `Group #${balance.groupId}`,
      month: balance.currentCycleNo ? `Cycle ${balance.currentCycleNo}` : getMonthLabel(balance.nextDueDate),
      status: balance.paymentStatus ?? (Number(balance.outstandingAmount ?? 0) > 0 ? "pending" : "paid"),
      paid: Number(balance.totalPaid ?? 0),
    }));
  }, [balances, isOwner, payments]);
  const groupOptions = useMemo(() => {
    const options = new Map();
    rows.forEach((row) => {
      const key = row.groupId ? String(row.groupId) : row.group;
      if (key) {
        options.set(key, row.group);
      }
    });
    return Array.from(options, ([value, label]) => ({ value, label }));
  }, [rows]);
  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        const normalizedStatus = String(row.status ?? "").toLowerCase();
        const paidMatch =
          statusFilter === "all" ||
          (statusFilter === "paid" && ["paid", "full", "completed", "recorded"].includes(normalizedStatus)) ||
          (statusFilter === "pending" && ["pending", "partial", "overdue", "due"].includes(normalizedStatus));
        const rowGroupKey = row.groupId ? String(row.groupId) : row.group;
        const groupMatch = groupFilter === "all" || rowGroupKey === groupFilter;
        return paidMatch && groupMatch;
      }),
    [groupFilter, rows, statusFilter],
  );

  if (loading) {
    return <PageLoadingState description="Loading cross-group payment status." label="Loading payments..." />;
  }

  if (error) {
    return <PageErrorState error={error} onRetry={() => window.location.reload()} title="We could not load payments." />;
  }

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Payments</h1>
        <p>Aggregated status across groups. Use a group detail page for collection entry or member-level work.</p>
      </section>

      <section className="panel">
        <h2>Group payment status</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="field-label">
            Status
            <select className="text-input mt-2" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
              <option value="all">All statuses</option>
              <option value="paid">Paid</option>
              <option value="pending">Pending</option>
            </select>
          </label>
          <label className="field-label">
            Group
            <select className="text-input mt-2" onChange={(event) => setGroupFilter(event.target.value)} value={groupFilter}>
              <option value="all">All groups</option>
              {groupOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {rows.length === 0 ? (
          <div className="empty-state mt-4">
            <h3>No payments yet</h3>
            <p>Payment records will appear here after a group has recorded or outstanding collections.</p>
          </div>
        ) : null}
        {rows.length > 0 && filteredRows.length === 0 ? (
          <div className="empty-state mt-4">
            <h3>No matching payments</h3>
            <p>Adjust the status or group filter to widen the aggregate view.</p>
          </div>
        ) : null}
        {filteredRows.length > 0 ? (
          <div className="responsive-table mt-4">
            <table>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Month</th>
                  <th>Status</th>
                  <th>Paid</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, index) => (
                  <tr key={row.id ?? `${row.group}-${index}`}>
                    <td>
                      {row.groupId ? <Link to={`/groups/${row.groupId}?tab=payments`}>{row.group}</Link> : row.group}
                    </td>
                    <td>{row.month}</td>
                    <td>
                      <span className={getStatusBadgeClass(row.status)}>{titleCase(row.status)}</span>
                    </td>
                    <td>{formatMoney(row.paid)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
