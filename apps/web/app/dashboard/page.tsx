import Link from "next/link";

import { ArticleList } from "@/components/article-list";


export default function DashboardPage() {
  return (
    <div className="stack">
      <section className="hero">
        <div className="hero-grid">
          <div>
            <div className="brand-kicker">Editorial control room</div>
            <h1>Build research-backed Home Dry Lab drafts without losing approval control.</h1>
            <p className="brand-copy">
              This foundation keeps all work local first, records workflow events, and preserves a draft-only WordPress export path.
            </p>
          </div>
          <div className="panel-strong">
            <div className="stats">
              <div className="stat">
                <span className="muted">Workflow</span>
                <strong>5</strong>
                <span className="muted">stubbed stages</span>
              </div>
              <div className="stat">
                <span className="muted">Safety</span>
                <strong>Draft</strong>
                <span className="muted">only export path</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid-3">
        <div className="panel">
          <div className="brand-kicker">Start queue</div>
          <h2>Open a new article job</h2>
          <p className="muted">Capture the keyword, article type, and Australian angle before research begins.</p>
          <Link className="button" href="/articles/new">
            Create article
          </Link>
        </div>
        <div className="panel">
          <div className="brand-kicker">Evidence base</div>
          <h2>Keep products grounded</h2>
          <p className="muted">Track test status and source-backed product notes before any copy makes claims.</p>
          <Link className="button-secondary" href="/products">
            Manage products
          </Link>
        </div>
        <div className="panel">
          <div className="brand-kicker">Compliance</div>
          <h2>Check configuration safely</h2>
          <p className="muted">See whether required keys exist without exposing any value to the UI.</p>
          <Link className="button-secondary" href="/settings">
            Review settings
          </Link>
        </div>
      </section>

      <section className="panel">
        <div className="toolbar">
          <div>
            <strong>Recent article jobs</strong>
            <div className="muted">Status visibility and review-first workflow control.</div>
          </div>
          <Link href="/articles">View all</Link>
        </div>
        <ArticleList compact />
      </section>
    </div>
  );
}

