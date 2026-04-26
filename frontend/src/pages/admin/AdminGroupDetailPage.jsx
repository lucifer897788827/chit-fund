import { Link, useParams } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function AdminGroupDetailPage() {
  const { id } = useParams();

  useAppShellHeader({
    title: `Admin group ${id}`,
    contextLabel: "System-wide group detail",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Group #{id}</h1>
        <p>Unclear from codebase: no admin group detail endpoint exists.</p>
        <Link className="action-button" to="/admin/groups">
          Back to admin groups
        </Link>
      </section>
    </main>
  );
}
