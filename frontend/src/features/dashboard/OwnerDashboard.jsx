import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { createAuctionSession, fetchGroups } from "../auctions/api";
import { getCurrentUser } from "../../lib/auth/store";

export default function OwnerDashboard() {
  const currentUser = getCurrentUser();
  const ownerId = currentUser?.owner_id;
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [launchingGroupId, setLaunchingGroupId] = useState(null);
  const [launchedSessionId, setLaunchedSessionId] = useState(null);

  useEffect(() => {
    let active = true;

    if (!ownerId) {
      setError("Sign in as a chit owner to load groups.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    fetchGroups(ownerId)
      .then((data) => {
        if (active) {
          setGroups(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => {
        if (active) {
          setError("Unable to load groups right now.");
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
  }, [ownerId]);

  async function handleLaunch(group) {
    setLaunchingGroupId(group.id);
    setError("");
    try {
      const session = await createAuctionSession(group.id, {
        cycleNo: group.currentCycleNo,
        biddingWindowSeconds: 180,
      });
      setLaunchedSessionId(session.id);
    } catch (_error) {
      setError("Unable to launch an auction session.");
    } finally {
      setLaunchingGroupId(null);
    }
  }

  return (
    <main className="page-shell">
      <h1>Owner Dashboard</h1>
      <p>Manage groups, payments, and live auction sessions.</p>
      {currentUser?.has_subscriber_profile ? (
        <p>
          Your subscriber tools are also ready. <Link to="/external-chits">Open external chits</Link>
        </p>
      ) : null}
      {error ? <p>{error}</p> : null}
      {launchedSessionId ? (
        <p>
          Auction launched. <Link to={`/auctions/${launchedSessionId}`}>Open live room</Link>
        </p>
      ) : null}
      {loading ? <p>Loading groups...</p> : null}
      {!loading && groups.length === 0 ? <p>No groups available yet.</p> : null}
      {!loading ? (
        <div className="panel-grid">
          {groups.map((group) => (
            <section className="panel" key={group.id}>
              <h2>{group.title}</h2>
              <p>
                {group.groupCode} · Cycle {group.currentCycleNo}
              </p>
              <button
                className="action-button"
                disabled={launchingGroupId === group.id}
                onClick={() => handleLaunch(group)}
                type="button"
              >
                {launchingGroupId === group.id ? "Launching..." : "Launch Auction"}
              </button>
            </section>
          ))}
        </div>
      ) : null}
    </main>
  );
}
