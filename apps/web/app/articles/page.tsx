import Link from "next/link";

import { ArticleList } from "@/components/article-list";
import { BulkStandardPosts } from "@/components/bulk-standard-posts";


export default function ArticlesPage() {
  return (
    <div className="stack">
      <section className="toolbar">
        <div>
          <div className="brand-kicker">Article queue</div>
          <div className="page-title">Articles</div>
        </div>
        <Link className="button" href="/articles/new">
          New article job
        </Link>
      </section>
      <section className="panel">
        <ArticleList />
      </section>
      <section className="toolbar">
        <div>
          <div className="brand-kicker">Bulk queue</div>
          <div className="page-title">Bulk Standard Posts</div>
        </div>
      </section>
      <section className="panel">
        <BulkStandardPosts />
      </section>
    </div>
  );
}

