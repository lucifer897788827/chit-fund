import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getCurrentUser } from "../../lib/auth/store";
import { fetchExternalChits } from "./api";

export default function ExternalChitsPage() {
  const currentUser = getCurrentUser();
  const [externalChits, setExternalChits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const subscriberId = currentUser?.subscriber_id;

    if (!subscriberId) {
      setError("A subscriber profile is required to view private chit records.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    fetchExternalChits(subscriberId)
      .then((data) => {
        if (active) {
          setExternalChits(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => {
        if (active) {
          setError("Unable to load external chit records right now.");
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
  }, [currentUser?.subscriber_id]);

  return (
    <main className="page-shell">
      <h1>My External Chits</h1>
      <p>Maintain private records for outside chits in one place.</p>
      <p>
        <Link to={currentUser?.role === "chit_owner" ? "/owner" : "/subscriber"}>Back to dashboard</Link>
      </p>
      {error ? <p>{error}</p> : null}
      {loading ? <p>Loading external chits...</p> : null}
      {!loading && externalChits.length === 0 ? <p>No external chits added yet.</p> : null}
      {!loading && externalChits.length > 0 ? (
        <div className="panel-grid">
          {externalChits.map((chit) => (
            <section className="panel" key={chit.id}>
              <h2>{chit.title}</h2>
              <p>Organizer: {chit.organizerName}</p>
              <p>Installment: Rs. {chit.installmentAmount}</p>
              <p>Status: {chit.status}</p>
            </section>
          ))}
        </div>
      ) : null}
    </main>
  );
}
