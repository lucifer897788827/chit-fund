import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminHomePage() {
  useAppShellHeader({
    title: "Admin",
    contextLabel: "System-level control",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Admin</h1>
        <p>Use existing backend-backed admin surfaces for approvals, job health, and readiness.</p>
        <div className="panel-grid mt-4 md:grid-cols-3">
          <Link className="action-button" to="/admin/owner-requests">
            Owner requests
          </Link>
          <Link className="action-button" to="/admin/system">
            System health
          </Link>
          <Link className="action-button" to="/admin/users">
            Users
          </Link>
          <Link className="action-button" to="/admin/groups">
            Groups
          </Link>
          <Link className="action-button" to="/admin/broadcast">
            Broadcast
          </Link>
        </div>
      </section>
    </main>
  );
}
