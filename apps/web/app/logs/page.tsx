import { LogsPanel } from "@/components/logs-panel";


export default function LogsPage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Operational history</div>
        <div className="page-title">Logs</div>
      </section>
      <LogsPanel />
    </div>
  );
}
