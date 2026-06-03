"use client";

import { FormEvent, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { ContentCluster } from "@/types";


const blankCluster = {
  name: "",
  description: "",
  target_url_slug: "",
  notes: "",
};


export function ClusterManager() {
  const [items, setItems] = useState<ContentCluster[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>(blankCluster);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setItems(await api.listClusters());
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  function startEdit(item: ContentCluster) {
    setEditingId(item.id);
    setDraft({
      name: item.name,
      description: item.description || "",
      target_url_slug: item.target_url_slug || "",
      notes: item.notes || "",
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      if (editingId) {
        await api.updateCluster(editingId, draft);
      } else {
        await api.createCluster(draft);
      }
      setEditingId(null);
      setDraft(blankCluster);
      await load();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save cluster.");
    }
  }

  return (
    <div className="grid-2">
      <form className="panel form-grid" onSubmit={onSubmit}>
        <div className="field-full">
          <strong>{editingId ? "Edit cluster" : "Create cluster"}</strong>
        </div>
        <div className="field">
          <label htmlFor="name">Name</label>
          <input id="name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="target_url_slug">Target slug</label>
          <input id="target_url_slug" value={draft.target_url_slug} onChange={(e) => setDraft({ ...draft, target_url_slug: e.target.value })} />
        </div>
        <div className="field-full">
          <label htmlFor="description">Description</label>
          <textarea id="description" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
        </div>
        <div className="field-full">
          <label htmlFor="notes">Notes</label>
          <textarea id="notes" value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        </div>
        {error ? <div className="field-full message error">{error}</div> : null}
        <div className="field-full actions">
          <button className="button" type="submit">{editingId ? "Save cluster" : "Create cluster"}</button>
          {editingId ? (
            <button className="button-secondary" type="button" onClick={() => { setEditingId(null); setDraft(blankCluster); }}>
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
                <strong>{item.name}</strong>
                <div className="muted">{item.target_url_slug || "No slug yet"}</div>
              </div>
              <button className="button-secondary" onClick={() => startEdit(item)} type="button">Edit</button>
            </div>
            <div className="muted">{item.description || "No description yet."}</div>
          </div>
        ))}
        {!items.length ? <div className="empty">No clusters yet.</div> : null}
      </div>
    </div>
  );
}

