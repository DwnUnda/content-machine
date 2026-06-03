"use client";

import { FormEvent, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { Source } from "@/types";


const blankSource = {
  title: "",
  url: "",
  source_type: "Research paper",
  publisher: "",
  trust_notes: "",
  article_job_id: "",
};


export function SourceManager() {
  const [items, setItems] = useState<Source[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>(blankSource);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setItems(await api.listSources());
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  function startEdit(item: Source) {
    setEditingId(item.id);
    setDraft({
      title: item.title,
      url: item.url || "",
      source_type: item.source_type,
      publisher: item.publisher || "",
      trust_notes: item.trust_notes || "",
      article_job_id: item.article_job_id ? String(item.article_job_id) : "",
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      const payload = {
        ...draft,
        article_job_id: draft.article_job_id ? Number(draft.article_job_id) : null,
      };
      if (editingId) {
        await api.updateSource(editingId, payload);
      } else {
        await api.createSource(payload);
      }
      setEditingId(null);
      setDraft(blankSource);
      await load();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save source.");
    }
  }

  return (
    <div className="grid-2">
      <form className="panel form-grid" onSubmit={onSubmit}>
        <div className="field-full">
          <strong>{editingId ? "Edit source" : "Create source"}</strong>
        </div>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="source_type">Source type</label>
          <input id="source_type" value={draft.source_type} onChange={(e) => setDraft({ ...draft, source_type: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="url">URL</label>
          <input id="url" value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="publisher">Publisher</label>
          <input id="publisher" value={draft.publisher} onChange={(e) => setDraft({ ...draft, publisher: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="article_job_id">Article job ID</label>
          <input id="article_job_id" value={draft.article_job_id} onChange={(e) => setDraft({ ...draft, article_job_id: e.target.value })} />
        </div>
        <div className="field-full">
          <label htmlFor="trust_notes">Trust notes</label>
          <textarea id="trust_notes" value={draft.trust_notes} onChange={(e) => setDraft({ ...draft, trust_notes: e.target.value })} />
        </div>
        {error ? <div className="field-full message error">{error}</div> : null}
        <div className="field-full actions">
          <button className="button" type="submit">{editingId ? "Save source" : "Create source"}</button>
          {editingId ? (
            <button className="button-secondary" type="button" onClick={() => { setEditingId(null); setDraft(blankSource); }}>
              Cancel edit
            </button>
          ) : null}
        </div>
      </form>
      <div className="panel">
        {items.map((item) => (
          <div className="list-card" key={item.id}>
            <div className="toolbar">
              <div>
                <strong>{item.title}</strong>
                <div className="muted">{item.source_type}</div>
              </div>
              <button className="button-secondary" onClick={() => startEdit(item)} type="button">Edit</button>
            </div>
            <div className="muted">{item.publisher || "No publisher"}{item.url ? ` · ${item.url}` : ""}</div>
          </div>
        ))}
        {!items.length ? <div className="empty">No sources yet.</div> : null}
      </div>
    </div>
  );
}

