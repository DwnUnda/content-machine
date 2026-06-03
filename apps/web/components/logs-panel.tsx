"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatLocalDateTime } from "@/lib/format";
import { AppLog } from "@/types";


export function LogsPanel() {
  const [logs, setLogs] = useState<AppLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listLogs().then((response) => setLogs(response.items)).catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="message error">{error}</div>;
  if (!logs.length) return <div className="panel empty">No logs yet.</div>;

  return (
    <div className="panel">
      {logs.map((log) => (
        <div className="list-card" key={log.id}>
          <div className="toolbar">
            <strong>{log.event_type}</strong>
            <span className="muted">{formatLocalDateTime(log.created_at)}</span>
          </div>
          <div>{log.message}</div>
          {log.article_job_id ? <div className="muted">Article job #{log.article_job_id}</div> : null}
        </div>
      ))}
    </div>
  );
}
