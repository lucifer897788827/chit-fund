import { Link } from "react-router-dom";

import { useAppShellHeader } from "../components/app-shell";

export default function ActionsPage() {
  useAppShellHeader({
    title: "Actions",
    contextLabel: "Owner shortcuts",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Actions</h1>
        <div className="panel-grid md:grid-cols-3">
          <Link className="action-button" to="/groups/create">
            Create group
          </Link>
          <Link className="action-button" to="/payments">
            Record payment
          </Link>
          <Link className="action-button" to="/groups">
            Manage groups
          </Link>
        </div>
      </section>
    </main>
  );
}
