import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  approveOwnerRequest,
  fetchAdminOwnerRequests,
  rejectOwnerRequest,
} from "./api";
import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { getApiErrorMessage } from "../../lib/api-error";
import { logoutUser } from "../auth/api";

export default function AdminOwnerRequestsPage() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyRequestId, setBusyRequestId] = useState(null);

  useEffect(() => {
    let active = true;

    fetchAdminOwnerRequests()
      .then((data) => {
        if (active) {
          setRequests(Array.isArray(data) ? data : []);
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(
            getApiErrorMessage(requestError, {
              fallbackMessage: "Unable to load owner requests right now.",
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

  async function handleDecision(requestId, action) {
    setBusyRequestId(requestId);
    setError("");

    try {
      const updated =
        action === "approve" ? await approveOwnerRequest(requestId) : await rejectOwnerRequest(requestId);
      setRequests((currentRequests) =>
        currentRequests.map((request) => (request.id === requestId ? updated : request)),
      );
    } catch (requestError) {
      setError(
        getApiErrorMessage(requestError, {
          fallbackMessage: "Unable to update this owner request right now.",
        }),
      );
    } finally {
      setBusyRequestId(null);
    }
  }

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  return (
    <main className="page-shell">
      <header className="space-y-3">
        <h1>Owner requests</h1>
        <p>Review subscriber upgrade requests and decide who can start running chit groups.</p>
        <div className="panel-grid">
          <button className="action-button" onClick={() => navigate("/notifications")} type="button">
            Open notifications
          </button>
          <button className="action-button" onClick={handleLogout} type="button">
            Log Out
          </button>
        </div>
      </header>

      {loading ? (
        <PageLoadingState
          description="Loading the latest owner-upgrade requests from the backend."
          label="Loading owner requests..."
        />
      ) : null}

      {!loading && error ? (
        <PageErrorState
          error={error}
          fallbackMessage="Unable to load owner requests right now."
          onRetry={() => navigate(0)}
          title="We could not load the owner requests."
        />
      ) : null}

      {!loading && !error ? (
        <section className="panel">
          <h2>Pending and processed requests</h2>
          {requests.length === 0 ? (
            <p>No owner requests have been submitted yet.</p>
          ) : (
            <div className="panel-grid">
              {requests.map((request) => {
                const isPending = request.status === "pending";
                const isBusy = busyRequestId === request.id;
                return (
                  <article className="panel space-y-3" key={request.id}>
                    <h3>{request.requesterName || request.phone || `User #${request.userId}`}</h3>
                    <p>Phone: {request.phone || "Not available"}</p>
                    <p>Email: {request.email || "Not available"}</p>
                    <p>Status: {request.status}</p>
                    {request.ownerId ? <p>Owner profile ID: {request.ownerId}</p> : null}
                    {isPending ? (
                      <div className="panel-grid">
                        <button
                          className="action-button"
                          disabled={isBusy}
                          onClick={() => handleDecision(request.id, "approve")}
                          type="button"
                        >
                          {isBusy ? "Updating..." : "Approve"}
                        </button>
                        <button
                          className="action-button"
                          disabled={isBusy}
                          onClick={() => handleDecision(request.id, "reject")}
                          type="button"
                        >
                          {isBusy ? "Updating..." : "Reject"}
                        </button>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ) : null}
    </main>
  );
}
