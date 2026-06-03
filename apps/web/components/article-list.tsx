"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatLocalDateTime } from "@/lib/format";
import { getPostTypeLabel } from "@/lib/post-types";
import { ArticleJob } from "@/types";
import { StatusBadge } from "@/components/status-badge";


export function ArticleList({ compact = false }: { compact?: boolean }) {
  const [items, setItems] = useState<ArticleJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => {
    api.listArticleJobs().then(setItems).catch((err) => setError(err.message));
  }, []);

  async function handleDelete(item: ArticleJob) {
    if (!confirm(`Delete "${item.title}"? This cannot be undone.`)) return;
    setDeleting(item.id);
    try {
      await api.deleteArticleJob(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    } catch (err: unknown) {
      alert(`Delete failed: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setDeleting(null);
    }
  }

  if (error) {
    return <div className="message error">{error}</div>;
  }

  if (!items.length) {
    return <div className="empty">No article jobs yet.</div>;
  }

  if (compact) {
    return (
      <div className="stack">
        {items.slice(0, 6).map((item) => (
          <div className="list-card" key={item.id}>
            <div className="toolbar">
              <div>
                <strong>{item.title}</strong>
                <div className="muted">{item.primary_keyword}</div>
              </div>
              <StatusBadge status={item.status} />
            </div>
            <Link href={`/articles/${item.id}`}>Open article</Link>
          </div>
        ))}
      </div>
    );
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Keyword</th>
          <th>Type</th>
          <th>Status</th>
          <th>Updated</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id}>
            <td>
              <Link href={`/articles/${item.id}`}>{item.title}</Link>
            </td>
            <td>{item.primary_keyword}</td>
            <td>{getPostTypeLabel(item.post_type)}</td>
            <td>
              <StatusBadge status={item.status} />
            </td>
            <td>{formatLocalDateTime(item.updated_at)}</td>
            <td>
              <button
                className="button-link"
                onClick={() => handleDelete(item)}
                disabled={deleting === item.id}
                style={{ color: "#c0392b", fontSize: "0.85rem", opacity: deleting === item.id ? 0.5 : 1 }}
              >
                {deleting === item.id ? "Deleting…" : "Delete"}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
