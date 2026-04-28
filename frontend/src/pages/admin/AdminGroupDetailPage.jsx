import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminGroupDetail } from "../../features/admin/api";
import { formatMoney } from "../../features/payments/balances";
import { getApiErrorMessage } from "../../lib/api-error";

function getSignedMoneyTone(value) {
  if (Number(value) > 0) {
    return "text-emerald-700";
  }
  if (Number(value) < 0) {
    return "text-red-700";
  }
  return "text-slate-700";
}

function getStatusBadgeClass(status) {
  if (String(status).toLowerCase() === "active") {
    return "border-emerald-200 bg-emerald-100 text-emerald-900";
  }
  if (String(status).toLowerCase() === "completed") {
    return "border-slate-200 bg-slate-100 text-slate-800";
  }
  return "border-amber-200 bg-amber-100 text-amber-900";
}

function getPaymentScoreBadgeClass(score) {
  if (score >= 80) {
    return "border-emerald-200 bg-emerald-100 text-emerald-900";
  }
  if (score >= 50) {
    return "border-amber-200 bg-amber-100 text-amber-900";
  }
  return "border-red-200 bg-red-100 text-red-900";
}

function PaymentScoreBadge({ score }) {
  const normalizedScore = Number(score ?? 0);
  return (
    <span
      aria-label={`Payment score: ${normalizedScore} / 100`}
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getPaymentScoreBadgeClass(normalizedScore)}`}
    >
      {normalizedScore} / 100
    </span>
  );
}

function StatCard({ label, tone = "", value }) {
  return (
    <article className="panel">
      <h3 className={tone}>{value}</h3>
      <p>{label}</p>
    </article>
  );
}

function formatValue(value) {
  return value ?? "N/A";
}

export default function AdminGroupDetailPage() {
  const { id } = useParams();

  useAppShellHeader({
    title: `Group ${id}`,
    contextLabel: "Admin group intelligence",
  });

  const groupQuery = useQuery({
    queryKey: ["admin-group", id],
    queryFn: () => fetchAdminGroupDetail(id),
    enabled: Boolean(id),
    staleTime: 30_000,
  });

  if (groupQuery.isLoading) {
    return <PageLoadingState description="Loading admin group detail." label="Loading group..." />;
  }

  if (groupQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(groupQuery.error, { fallbackMessage: "Unable to load admin group detail right now." })}
        onRetry={() => groupQuery.refetch()}
        title="We could not load this group."
      />
    );
  }

  const data = groupQuery.data ?? {};
  const group = data.group ?? {};
  const members = Array.isArray(data.members) ? data.members : [];
  const auctions = Array.isArray(data.auctions) ? data.auctions : [];
  const defaulters = Array.isArray(data.defaulters) ? data.defaulters : [];
  const financialSummary = data.financialSummary ?? {};
  const lowScoreMembers = members.filter((member) => Number(member.paymentScore ?? 0) < 50);

  return (
    <main className="page-shell">
      <section className="panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1>{group.name ?? `Group #${id}`}</h1>
            <p>Owner: {formatValue(group.owner)}</p>
            <p>Owner phone: {formatValue(group.ownerPhone)}</p>
          </div>
          <span className={`inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${getStatusBadgeClass(group.status)}`}>
            {group.status ?? "Unknown"}
          </span>
        </div>
        <div className="mt-4 panel-grid md:grid-cols-4">
          <StatCard label="Monthly amount" value={formatMoney(group.monthlyAmount ?? 0)} />
          <StatCard label="Chit value" value={formatMoney(group.chitValue ?? 0)} />
          <StatCard label="Members count" value={group.membersCount ?? 0} />
          <StatCard label="Current cycle" value={group.currentCycleNo ?? 0} />
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-700">
          <span>Start date: {formatValue(group.startDate)}</span>
          <span>First auction: {formatValue(group.firstAuctionDate)}</span>
        </div>
        <div className="mt-4">
          <Link className="action-button" to="/admin/groups">
            Back to admin groups
          </Link>
        </div>
      </section>

      <section className="panel">
        <h2>Financial snapshot</h2>
        <div className="panel-grid md:grid-cols-3">
          <StatCard label="Total collected" value={formatMoney(financialSummary.totalCollected ?? 0)} />
          <StatCard label="Total paid" value={formatMoney(financialSummary.totalPaid ?? 0)} />
          <StatCard label="Pending" value={formatMoney(financialSummary.pendingAmount ?? 0)} />
        </div>
      </section>

      <section className="panel">
        <h2>Members</h2>
        {members.length === 0 ? (
          <p>No members found for this group.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Paid</th>
                  <th>Received</th>
                  <th>Net</th>
                  <th>Score</th>
                  <th>Pending</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const netPosition = Number(member.netPosition ?? 0);
                  return (
                    <tr key={member.membershipId}>
                      <td>
                        <div>
                          <Link to={`/admin/users/${member.userId}`}>{member.name}</Link>
                          <div className="text-sm text-slate-600">{member.phone}</div>
                        </div>
                      </td>
                      <td>{formatMoney(member.totalPaid ?? 0)}</td>
                      <td>{formatMoney(member.totalReceived ?? 0)}</td>
                      <td className={getSignedMoneyTone(netPosition)}>{formatMoney(netPosition)}</td>
                      <td><PaymentScoreBadge score={member.paymentScore} /></td>
                      <td>{member.pendingPaymentsCount ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Auction history</h2>
        {auctions.length === 0 ? (
          <p>No auctions found for this group.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Winner</th>
                  <th>Bid</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {auctions.map((auction) => (
                  <tr key={auction.id}>
                    <td>{formatValue(auction.month)}</td>
                    <td>{formatValue(auction.winner)}</td>
                    <td>{auction.bidAmount === null || auction.bidAmount === undefined ? "N/A" : formatMoney(auction.bidAmount)}</td>
                    <td>{formatValue(auction.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Risk panel</h2>
        <div className="panel-grid md:grid-cols-2">
          <article className="panel">
            <div className="flex items-center justify-between gap-3">
              <h3>Defaulters</h3>
              <span className="inline-flex rounded-full border border-red-200 bg-red-50 px-3 py-1 text-sm font-semibold text-red-900">
                {defaulters.length} flagged
              </span>
            </div>
            {defaulters.length === 0 ? (
              <p className="mt-3">No defaulters in this group.</p>
            ) : (
              <div className="mt-3 space-y-3">
                {defaulters.map((member) => (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3" key={`defaulter-${member.userId}`}>
                    <p className="font-semibold text-slate-950">{member.name}</p>
                    <p className="text-sm text-slate-700">{member.phone}</p>
                    <p className="text-sm text-red-900">{member.pendingPaymentsCount} pending payments</p>
                    <p className="text-sm text-red-800">{formatMoney(member.pendingAmount ?? 0)}</p>
                  </div>
                ))}
              </div>
            )}
          </article>
          <article className="panel">
            <div className="flex items-center justify-between gap-3">
              <h3>Low score users</h3>
              <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-900">
                {lowScoreMembers.length} flagged
              </span>
            </div>
            {lowScoreMembers.length === 0 ? (
              <p className="mt-3">No low score users in this group.</p>
            ) : (
              <div className="mt-3 space-y-3">
                {lowScoreMembers.map((member) => (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3" key={`low-score-${member.userId}`}>
                    <p className="font-semibold text-slate-950">{member.name}</p>
                    <p className="text-sm text-slate-700">{member.phone}</p>
                    <div className="mt-2">
                      <PaymentScoreBadge score={member.paymentScore} />
                    </div>
                    <p className={`mt-2 text-sm ${getSignedMoneyTone(member.netPosition)}`}>Net: {formatMoney(member.netPosition ?? 0)}</p>
                  </div>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>
    </main>
  );
}
