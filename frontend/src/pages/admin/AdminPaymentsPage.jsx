import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminPaymentsPage() {
  useAppShellHeader({
    title: "Payments",
    contextLabel: "Read-only payment oversight",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Payments</h1>
        <p>Admin can review payment-related summaries without recording collections or acting as a participant. Use user detail for profile-level totals and system view for operational health.</p>
        <div className="panel-grid mt-4 md:grid-cols-2">
          <Link className="action-button" to="/admin/users">
            Review users
          </Link>
          <Link className="action-button" to="/admin/system">
            Open system view
          </Link>
        </div>
      </section>
    </main>
  );
}
