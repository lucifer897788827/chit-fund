import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminAuctionsPage() {
  useAppShellHeader({
    title: "Auctions",
    contextLabel: "Read-only auction oversight",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Auctions</h1>
        <p>Admin can monitor auction activity from a control-layer view only. There is no admin-wide auction feed endpoint yet, so use system health and user detail instead of joining rooms or bidding.</p>
        <div className="panel-grid mt-4 md:grid-cols-2">
          <Link className="action-button" to="/admin/system">
            Open system view
          </Link>
          <Link className="action-button" to="/admin/users">
            Inspect user activity
          </Link>
        </div>
      </section>
    </main>
  );
}
