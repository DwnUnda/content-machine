"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatLocalDateTime } from "@/lib/format";
import { StandardPostBatch, StandardPostBatchDetail, StandardPostBatchItem } from "@/types";
import { StatusBadge } from "@/components/status-badge";

const POLL_INTERVAL_MS = 4000;

function itemActionLabel(item: StandardPostBatchItem): string {
  if (item.status === "complete") return "complete";
  if (item.status === "running") return item.current_step ? `running (${item.current_step})` : "running";
  return item.status;
}

export function BulkStandardPosts() {
  const [keywords, setKeywords] = useState("");
  const [wordpressMode, setWordpressMode] = useState<"local_only" | "local_plus_draft">("local_only");
  const [batches, setBatches] = useState<StandardPostBatch[]>([]);
  const [selected, setSelected] = useState<StandardPostBatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadBatches = useCallback(async () => {
    try {
      const list = await api.listStandardPostBatches();
      setBatches(list);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const loadSelected = useCallback(async (id: number) => {
    try {
      const detail = await api.getStandardPostBatch(id);
      setSelected(detail);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  // Poll the selected batch while it is running.
  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (selected && (selected.is_running || selected.status === "running")) {
      pollRef.current = setInterval(() => {
        loadSelected(selected.id);
        loadBatches();
      }, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [selected, loadSelected, loadBatches]);

  const runAction = useCallback(
    async (action: () => Promise<StandardPostBatchDetail>) => {
      setBusy(true);
      setError(null);
      try {
        const detail = await action();
        setSelected(detail);
        await loadBatches();
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [loadBatches],
  );

  const handleCreate = () =>
    runAction(() => api.createStandardPostBatch({ keywords, wordpress_mode: wordpressMode })).then(() => {
      setKeywords("");
    });

  const counts = selected?.counts;

  return (
    <div className="stack">
      {error ? <div className="message error">{error}</div> : null}

      <div className="list-card stack">
        <div>
          <strong>Create a bulk queue</strong>
          <div className="muted">
            Paste one keyword per line (or comma-separated). These run as standard informational posts only — no
            money pages and no product cards required.
          </div>
        </div>
        <textarea
          className="input"
          rows={6}
          placeholder={"how to dry clothes indoors without mould\nhow long should you run a dehumidifier\nbest humidity level to prevent mould"}
          value={keywords}
          onChange={(event) => setKeywords(event.target.value)}
        />
        <div className="toolbar">
          <label className="muted">
            WordPress:{" "}
            <select
              value={wordpressMode}
              onChange={(event) => setWordpressMode(event.target.value as "local_only" | "local_plus_draft")}
            >
              <option value="local_only">Save local only</option>
              <option value="local_plus_draft">Save local + upload to WordPress draft</option>
            </select>
          </label>
          <button className="button" disabled={busy || !keywords.trim()} onClick={handleCreate}>
            Create queue
          </button>
        </div>
      </div>

      <div className="list-card stack">
        <strong>Queues</strong>
        {!batches.length ? (
          <div className="empty">No bulk queues yet.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Queue</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{batch.name ?? `Batch #${batch.id}`}</td>
                  <td>
                    <StatusBadge status={batch.status} />
                  </td>
                  <td>
                    {batch.counts.complete}/{batch.counts.total} done
                    {batch.counts.failed ? `, ${batch.counts.failed} failed` : ""}
                  </td>
                  <td>{formatLocalDateTime(batch.created_at)}</td>
                  <td>
                    <button className="button" onClick={() => loadSelected(batch.id)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected ? (
        <div className="list-card stack">
          <div className="toolbar">
            <div>
              <strong>{selected.name ?? `Batch #${selected.id}`}</strong>
              <div className="muted">{selected.summary_message}</div>
            </div>
            <StatusBadge status={selected.status} />
          </div>

          {counts ? (
            <div className="muted">
              Total {counts.total} · Pending {counts.pending} · Running {counts.running} · Complete {counts.complete} ·
              Failed {counts.failed} · Skipped {counts.skipped} · Cancelled {counts.cancelled}
            </div>
          ) : null}

          <div className="toolbar">
            <button
              className="button"
              disabled={busy || selected.is_running || selected.status === "complete" || selected.status === "cancelled"}
              onClick={() => runAction(() => api.startStandardPostBatch(selected.id))}
            >
              Start queue
            </button>
            <button
              className="button"
              disabled={busy || !selected.is_running}
              onClick={() => runAction(() => api.pauseStandardPostBatch(selected.id))}
            >
              Pause queue
            </button>
            <button
              className="button"
              disabled={busy || selected.status !== "paused"}
              onClick={() => runAction(() => api.resumeStandardPostBatch(selected.id))}
            >
              Resume queue
            </button>
            <button
              className="button"
              disabled={busy || selected.status === "complete" || selected.status === "cancelled"}
              onClick={() => runAction(() => api.cancelStandardPostBatch(selected.id))}
            >
              Cancel remaining
            </button>
            <button className="button" disabled={busy} onClick={() => loadSelected(selected.id)}>
              Refresh
            </button>
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>Keyword</th>
                <th>Status</th>
                <th>Folder</th>
                <th>Created</th>
                <th>Completed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {selected.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.keyword}
                    {item.error_message ? <div className="message error">{item.error_message}</div> : null}
                  </td>
                  <td>
                    <StatusBadge status={item.status} /> <span className="muted">{itemActionLabel(item)}</span>
                  </td>
                  <td className="muted">{item.article_folder ?? "—"}</td>
                  <td>{formatLocalDateTime(item.created_at)}</td>
                  <td>{formatLocalDateTime(item.completed_at)}</td>
                  <td>
                    {(item.status === "failed" || item.status === "skipped" || item.status === "cancelled") ? (
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => runAction(() => api.retryStandardPostBatchItem(selected.id, item.id))}
                      >
                        Retry
                      </button>
                    ) : null}
                    {item.status === "pending" ? (
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => runAction(() => api.skipStandardPostBatchItem(selected.id, item.id))}
                      >
                        Skip
                      </button>
                    ) : null}
                    {item.article_job_id ? (
                      <a className="button" href={`/articles/${item.article_job_id}`}>
                        Open draft
                      </a>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
