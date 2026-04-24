import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fetchAdminOwnerRequests } from "../owner-requests/api";
import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { logoutUser } from "../auth/api";

function countByStatus(requests, status) {
  return requests.filter((request) => request.status === status).length;
}

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useSignedInShellHeader({
    title: "Admin dashboard",
    contextLabel: "Owner approvals and platform oversight",
  });

  useEffect(() => {
    let active = true;

    fetchAdminOwnerRequests()
      .then((data) => {
        if (active) {
          setRequests(Array.isArray(data) ? data : []);
        }
      })
      .catch((dashboardError) => {
        if (active) {
          setError(
            getApiErrorMessage(dashboardError, {
              fallbackMessage: "Unable to load the admin dashboard right now.",
            }),
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  return (
    <main className="page-shell">
      <header className="space-y-3" id="profile">
        <h1>Admin Dashboard</h1>
        <p>Review organizer requests and keep the operational workflow moving.</p>
        <div className="panel-grid">
          <Link className="action-button" to="/admin/owner-requests">
            Review owner requests
          </Link>
          <Link className="action-button" to="/notifications">
            Open notifications
          </Link>
          <button className="action-button" onClick={handleLogout} type="button">
            Log Out
          </button>
        </div>
      </header>

      {loading ? (
        <PageLoadingState
          description="Loading the latest upgrade requests for review."
          label="Loading admin dashboard..."
        />
      ) : null}

      {!loading && error ? (
        <PageErrorState
          error={error}
          fallbackMessage="Unable to load the admin dashboard right now."
          onRetry={() => navigate(0)}
          title="We could not load the admin dashboard."
        />
      ) : null}

      {!loading && !error ? (
        <section className="panel" id="home">
          <h2>Owner request overview</h2>
          <div className="panel-grid">
            <article className="panel">
              <h3>{countByStatus(requests, "pending")} pending</h3>
              <p>Requests waiting for approval or rejection.</p>
            </article>
            <article className="panel">
              <h3>{countByStatus(requests, "approved")} approved</h3>
              <p>Requests that already produced owner access.</p>
            </article>
            <article className="panel">
              <h3>{countByStatus(requests, "rejected")} rejected</h3>
              <p>Requests that were reviewed and declined.</p>
            </article>
          </div>
        </section>
      ) : null}
    </main>
  );
}
