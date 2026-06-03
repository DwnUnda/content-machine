import { SourceManager } from "@/components/source-manager";


export default function SourcesPage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Evidence library</div>
        <div className="page-title">Sources</div>
      </section>
      <SourceManager />
    </div>
  );
}

