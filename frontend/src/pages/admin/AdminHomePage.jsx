import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminHomePage() {
  useAppShellHeader({
    title: "Dashboard",
    contextLabel: "System-level control",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Dashboard</h1>
        <p>Admin is a control layer only. Use these read-only oversight surfaces without joining groups, bidding, or acting like a participant.</p>
        <div className="panel-grid mt-4 md:grid-cols-3">
          <Link className="action-button" to="/admin/users">
            Users
          </Link>
          <Link className="action-button" to="/admin/groups">
            Groups
          </Link>
          <Link className="action-button" to="/admin/auctions">
            Auctions
          </Link>
          <Link className="action-button" to="/admin/payments">
            Payments
          </Link>
          <Link className="action-button" to="/admin/owner-requests">
            Owner requests
          </Link>
          <Link className="action-button" to="/admin/system">
            System
          </Link>
        </div>
      </section>
    </main>
  );
}
