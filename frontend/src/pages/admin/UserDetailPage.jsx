import { Link, useParams } from "react-router-dom";

import { useAppShellHeader } from "../../components/app-shell";

export default function UserDetailPage() {
  const { id } = useParams();

  useAppShellHeader({
    title: `User ${id}`,
    contextLabel: "Admin user detail",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>User #{id}</h1>
        <p>Unclear from codebase: no admin user detail endpoint exists.</p>
        <Link className="action-button" to="/admin/users">
          Back to users
        </Link>
      </section>
    </main>
  );
}
