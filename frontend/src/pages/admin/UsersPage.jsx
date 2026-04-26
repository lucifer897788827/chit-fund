import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function UsersPage() {
  useAppShellHeader({
    title: "Users",
    contextLabel: "Admin user directory",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Users</h1>
        <p>Unclear from codebase: no admin users list endpoint exists in the backend router table.</p>
        <Link className="action-button" to="/admin/owner-requests">
          Review owner requests
        </Link>
      </section>
    </main>
  );
}
