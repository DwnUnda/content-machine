"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { ContentRule } from "@/types";


export function ContentRulesPanel() {
  const [rules, setRules] = useState<ContentRule[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await api.listContentRules();
    setRules(response.items);
    setDrafts(Object.fromEntries(response.items.map((item) => [item.key, item.value])));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function saveRule(rule: ContentRule) {
    setSavingKey(rule.key);
    setError(null);
    try {
      await api.updateContentRule(rule.key, drafts[rule.key] ?? "");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save content rule.");
    } finally {
      setSavingKey(null);
    }
  }

  if (error && !rules.length) {
    return <div className="message error">{error}</div>;
  }

  if (!rules.length) {
    return <div className="panel muted">Loading content rules...</div>;
  }

  return (
    <div className="panel stack">
      <div>
        <div className="brand-kicker">Content Rules</div>
        <strong>Editable Home Dry Lab quality controls</strong>
        <div className="muted">Tighten the writing system here without changing code.</div>
      </div>
      {error ? <div className="message error">{error}</div> : null}
      {rules.map((rule) => (
        <div className="list-card" key={rule.key}>
          <div className="toolbar">
            <div>
              <strong>{rule.label}</strong>
              <div className="muted">{rule.description}</div>
            </div>
            <button
              className="button-secondary"
              disabled={savingKey === rule.key}
              onClick={() => saveRule(rule)}
              type="button"
            >
              {savingKey === rule.key ? "Saving..." : "Save"}
            </button>
          </div>
          <textarea
            value={drafts[rule.key] ?? ""}
            onChange={(event) => setDrafts({ ...drafts, [rule.key]: event.target.value })}
          />
        </div>
      ))}
    </div>
  );
}

