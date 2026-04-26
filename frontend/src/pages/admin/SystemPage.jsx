import { useEffect, useState } from "react";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useAppShellHeader } from "../../components/app-shell";
import { apiClient } from "../../lib/api/client";
import { getApiErrorMessage } from "../../lib/api-error";

export default function SystemPage() {
  const [health, setHealth] = useState(null);
  const [jobs, setJobs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useAppShellHeader({
    title: "System",
    contextLabel: "Readiness and finalize job health",
  });

  useEffect(() => {
    let active = true;
    Promise.all([apiClient.get("/admin/system-health"), apiClient.get("/admin/finalize-jobs")])
      .then(([healthResponse, jobsResponse]) => {
        if (active) {
          setHealth(healthResponse.data);
          setJobs(jobsResponse.data);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(getApiErrorMessage(loadError, { fallbackMessage: "Unable to load system health." }));
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

  if (loading) {
    return <PageLoadingState description="Loading readiness, worker, and queue status." label="Loading system..." />;
  }

  if (error) {
    return <PageErrorState error={error} onRetry={() => window.location.reload()} title="We could not load system health." />;
  }

  const checks = health?.readiness?.checks ?? {};
  const counts = jobs?.counts ?? {};

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>System health</h1>
        <p>Status: {health?.readiness?.status ?? "unknown"}</p>
        <div className="panel-grid mt-4 md:grid-cols-3">
          {Object.entries(checks).map(([name, check]) => (
            <article className="panel" key={name}>
              <h3>{name}</h3>
              <p>{check?.status ?? "unknown"}</p>
              {check?.detail ? <p>{check.detail}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Finalize queue</h2>
        <div className="panel-grid md:grid-cols-4">
          {["pending", "processing", "failed", "done"].map((status) => (
            <article className="panel" key={status}>
              <h3>{counts[status] ?? 0}</h3>
              <p>{status}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
