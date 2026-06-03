"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { SettingsValidation } from "@/types";
import { ContentRulesPanel } from "@/components/content-rules-panel";


export function SettingsPanel() {
  const [settings, setSettings] = useState<SettingsValidation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.validateSettings().then(setSettings).catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="message error">{error}</div>;
  if (!settings) return <div className="panel muted">Loading settings validation...</div>;

  return (
    <div className="stack">
      <div className="grid-2">
        <div className="panel stack">
          <div><strong>Site</strong><div className="muted">{settings.site_name}</div></div>
          <div><strong>Country</strong><div className="muted">{settings.target_country}</div></div>
          <div><strong>Language</strong><div className="muted">{settings.target_language}</div></div>
          <div><strong>Site URL configured</strong><div className="muted">{settings.site_url_present ? "Yes" : "No"}</div></div>
        </div>
        <div className="panel">
          <strong>Required environment variables</strong>
          <div className="stack" style={{ marginTop: 18 }}>
            {settings.required.map((item) => (
              <div className="toolbar" key={item.key}>
                <span>{item.key}</span>
                <span className="status-badge">{item.present ? "Present" : "Missing"}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <ContentRulesPanel />
    </div>
  );
}
