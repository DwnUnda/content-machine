import { ClusterManager } from "@/components/cluster-manager";


export default function ClustersPage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Content architecture</div>
        <div className="page-title">Clusters</div>
      </section>
      <ClusterManager />
    </div>
  );
}

