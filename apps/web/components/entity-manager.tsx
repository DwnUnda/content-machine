"use client";

import { FormEvent, useEffect, useState } from "react";


type FieldSpec = {
  key: string;
  label: string;
  type?: "text" | "textarea" | "checkbox";
};

type EntityManagerProps<T extends { id: number }> = {
  title: string;
  fields: FieldSpec[];
  list: () => Promise<T[]>;
  create: (payload: Record<string, unknown>) => Promise<T>;
  renderItem: (item: T) => React.ReactNode;
};


export function EntityManager<T extends { id: number }>({
  title,
  fields,
  list,
  create,
  renderItem,
}: EntityManagerProps<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setItems(await list());
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to load ${title}.`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);

    const form = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {};

    fields.forEach((field) => {
      if (field.type === "checkbox") {
        payload[field.key] = form.get(field.key) === "on";
      } else {
        payload[field.key] = form.get(field.key) ? String(form.get(field.key)) : "";
      }
    });

    try {
      await create(payload);
      event.currentTarget.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to save ${title}.`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid-2">
      <form className="panel form-grid" onSubmit={onSubmit}>
        <div className="field-full">
          <strong>{title}</strong>
        </div>
        {fields.map((field) => (
          <div className={field.type === "textarea" ? "field-full" : "field"} key={field.key}>
            <label htmlFor={field.key}>{field.label}</label>
            {field.type === "textarea" ? <textarea id={field.key} name={field.key} /> : null}
            {field.type === "checkbox" ? <input id={field.key} name={field.key} type="checkbox" /> : null}
            {!field.type || field.type === "text" ? <input id={field.key} name={field.key} /> : null}
          </div>
        ))}
        {error ? <div className="message error field-full">{error}</div> : null}
        <div className="field-full">
          <button className="button" disabled={saving} type="submit">
            {saving ? "Saving..." : `Save ${title}`}
          </button>
        </div>
      </form>
      <div className="panel">
        <div className="toolbar">
          <strong>Existing {title}</strong>
        </div>
        {loading ? <div className="muted">Loading...</div> : null}
        {!loading && !items.length ? <div className="empty">No records yet.</div> : null}
        {!loading &&
          items.map((item) => (
            <div key={item.id} className="list-card">
              {renderItem(item)}
            </div>
          ))}
      </div>
    </div>
  );
}

