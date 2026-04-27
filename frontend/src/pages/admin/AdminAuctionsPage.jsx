import { useQuery } from "@tanstack/react-query";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { fetchAdminAuctions } from "../../features/admin/api";
import { getApiErrorMessage } from "../../lib/api-error";

export default function AdminAuctionsPage() {
  useAppShellHeader({
    title: "Auctions",
    contextLabel: "Read-only auction oversight",
  });

  const auctionsQuery = useQuery({
    queryKey: ["admin-auctions"],
    queryFn: () => fetchAdminAuctions(),
    staleTime: 30_000,
  });

  if (auctionsQuery.isLoading) {
    return <PageLoadingState description="Loading admin auction oversight." label="Loading auctions..." />;
  }

  if (auctionsQuery.error) {
    return (
      <PageErrorState
        error={getApiErrorMessage(auctionsQuery.error, { fallbackMessage: "Unable to load admin auctions right now." })}
        onRetry={() => auctionsQuery.refetch()}
        title="We could not load auctions."
      />
    );
  }

  const auctions = Array.isArray(auctionsQuery.data) ? auctionsQuery.data : [];

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Auctions</h1>
        <p>Read-only auction summaries across all groups, with winners and winning bid visibility for admins.</p>
      </section>

      <section className="panel">
        {auctions.length === 0 ? (
          <p>No auctions are available.</p>
        ) : (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Group</th>
                  <th>Winner</th>
                  <th>Bid amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {auctions.map((auction) => (
                  <tr key={auction.id}>
                    <td>#{auction.id}</td>
                    <td>{auction.group}</td>
                    <td>{auction.winner ?? "Pending"}</td>
                    <td>{auction.bidAmount ?? "Pending"}</td>
                    <td>{auction.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
