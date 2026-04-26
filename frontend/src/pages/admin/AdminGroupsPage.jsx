import { Link } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminGroupsPage() {
  useAppShellHeader({
    title: "Admin groups",
    contextLabel: "System-wide group oversight",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Groups</h1>
        <p>Unclear from codebase: no system-wide admin groups endpoint exists. Owner-scoped groups are available at `/groups` for owner profiles.</p>
        <Link className="action-button" to="/groups">
          Open my groups
        </Link>
      </section>
    </main>
  );
}
