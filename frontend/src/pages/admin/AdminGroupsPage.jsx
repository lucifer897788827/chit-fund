import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminGroupsPage() {
  useAppShellHeader({
    title: "Groups",
    contextLabel: "Read-only group oversight",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Groups</h1>
        <p>Admin access is read-only here. There is no dedicated admin groups API yet, so use user detail, system health, and owner requests without crossing into owner/member workflows.</p>
        <Link className="action-button" to="/admin/users">
          Review users
        </Link>
      </section>
    </main>
  );
}
