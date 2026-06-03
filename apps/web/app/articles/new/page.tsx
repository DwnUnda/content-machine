import { ArticleJobForm } from "@/components/article-job-form";


export default function NewArticlePage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Create article workflow</div>
        <div className="page-title">New article draft</div>
      </section>
      <ArticleJobForm />
    </div>
  );
}
