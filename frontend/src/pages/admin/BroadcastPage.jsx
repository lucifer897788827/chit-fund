import { useAppShellHeader } from "../../components/app-shell";

export default function BroadcastPage() {
  useAppShellHeader({
    title: "Broadcast",
    contextLabel: "Platform messaging",
  });

  return (
    <main className="page-shell">
      <section className="panel">
        <h1>Broadcast</h1>
        <p>Unclear from codebase: no admin broadcast endpoint exists. Notification delivery exists for system events, but there is no broadcast API to call from this UI.</p>
      </section>
    </main>
  );
}
