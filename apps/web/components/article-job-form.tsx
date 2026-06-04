"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import {
  getMinProductsForPostType,
  getPostTypeLabel,
  isProductGated,
  POST_TYPE_OPTIONS,
} from "@/lib/post-types";
import { ContentCluster } from "@/types";

export function ArticleJobForm() {
  const router = useRouter();
  const [clusters, setClusters] = useState<ContentCluster[]>([]);
  const [postType, setPostType] = useState<string>("informational_blog");
  const [saving, setSaving] = useState(false);
  const [progressIndex, setProgressIndex] = useState(-1);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [productUrlsText, setProductUrlsText] = useState("");

  useEffect(() => {
    api.listClusters().then(setClusters).catch(() => undefined);
  }, []);

  const needsProducts = isProductGated(postType);
  const minProducts = getMinProductsForPostType(postType);

  const progressSteps = useMemo(() => {
    if (needsProducts) {
      return [
        "Create article",
        "Save & extract any product URLs",
        "Run research, products & drafting pipeline",
        "Completed",
      ];
    }
    return [
      "Create article",
      "Run research and drafting pipeline",
      "Completed",
    ];
  }, [needsProducts]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setProgressIndex(0);
    setProgressLabel("Create article");
    setError(null);

    const form = new FormData(event.currentTarget);
    const keyword = String(form.get("primary_keyword") || "").trim();
    const notes = String(form.get("notes") || "").trim();

    if (!keyword) {
      setError("Keyword/topic is required.");
      setSaving(false);
      return;
    }

    const urls = needsProducts
      ? productUrlsText
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean)
      : [];

    try {
      const created = await api.createArticleJob({
        title: keyword,
        primary_keyword: keyword,
        post_type: postType,
        target_audience: String(form.get("target_audience") || "").trim() || null,
        australian_angle: String(form.get("australian_angle") || "").trim() || null,
        notes: notes || null,
        cluster_id: form.get("cluster_id") ? Number(form.get("cluster_id")) : null,
      });

      if (needsProducts && urls.length) {
        setProgressIndex(1);
        setProgressLabel("Save & extract any product URLs");
        for (const url of urls) {
          const link = await api.createArticleProductSource(created.id, {
            source_url: url,
            source_type: "retailer",
          });
          await api.extractArticleProduct(created.id, link.id);
        }
      }

      setProgressIndex(needsProducts ? 2 : 1);
      setProgressLabel("Run research and drafting pipeline");
      await api.runFullWorkflow(created.id, "fresh");
      setProgressIndex(progressSteps.length - 1);
      setProgressLabel("Completed");
      router.push(`/articles/${created.id}`);
    } catch (err) {
      setProgressLabel("Failed");
      setError(err instanceof Error ? err.message : "Failed to create article workflow.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel form-grid" onSubmit={onSubmit}>
      <div className="field-full">
        <div className="brand-kicker">Workflow mode</div>
        <div className="muted">Choose the post type first. The rest of the workflow runs from one button.</div>
      </div>
      <div className="field">
        <label htmlFor="post_type">Post type</label>
        <select
          id="post_type"
          name="post_type"
          value={postType}
          onChange={(event) => setPostType(event.target.value)}
        >
          {POST_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field-full">
        <label htmlFor="primary_keyword">Keyword / topic</label>
        <input
          id="primary_keyword"
          name="primary_keyword"
          placeholder="What humidity level causes mould in Australian homes?"
          required
        />
      </div>
      <div className="field-full">
        <label htmlFor="notes">Optional notes</label>
        <textarea
          id="notes"
          name="notes"
          placeholder="Anything specific to include, avoid, or emphasise."
          rows={4}
        />
      </div>
      {needsProducts ? (
        <div className="field-full">
          <label htmlFor="product_urls">Product URLs</label>
          <textarea
            id="product_urls"
            placeholder={"Optional. Paste product URLs (one per line), or leave blank.\nhttps://example.com.au/product-1\nhttps://example.com.au/product-2"}
            onChange={(event) => setProductUrlsText(event.target.value)}
            value={productUrlsText}
            rows={6}
          />
          <div className="muted small-copy">
            Optional. Any URLs you add are extracted first; if fewer than {minProducts} draft-ready card{minProducts === 1 ? "" : "s"} result, AI web search automatically finds and researches more Australian products. Unconfirmed facts stay as Not confirmed.
            Broad category money pages such as "best dehumidifier Australia" may require 8+ draft-ready products after the topic is classified.
          </div>
        </div>
      ) : null}
      <div className="field-full muted small-copy">
        Completed articles are saved locally under <code>D:\Software\content-machine\Completed-Articles</code> and the finished article page opens automatically when the run completes.
      </div>
      <details className="field-full panel">
        <summary>Advanced settings</summary>
        <div className="form-grid nested">
          <div className="field">
            <label htmlFor="cluster_id">Cluster</label>
            <select id="cluster_id" name="cluster_id" defaultValue="">
              <option value="">No cluster yet</option>
              {clusters.map((cluster) => (
                <option key={cluster.id} value={cluster.id}>
                  {cluster.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="target_audience">Target audience</label>
            <input id="target_audience" name="target_audience" />
          </div>
          <div className="field-full">
            <label htmlFor="australian_angle">Australian angle</label>
            <textarea id="australian_angle" name="australian_angle" rows={3} />
          </div>
        </div>
      </details>
      {error ? <div className="message error field-full">{error}</div> : null}
      <div className="field-full actions">
        <button className="button" disabled={saving} type="submit">
          {saving ? "Creating..." : "Create Blog Draft"}
        </button>
      </div>
      {saving ? (
        <div className="field-full stack">
          <div className="muted small-copy">
            {progressLabel ? `Current step: ${progressLabel}` : "Working..."}
          </div>
          <div className="progress-track" aria-label="Workflow progress">
            <div
              className="progress-fill"
              style={{
                width: `${Math.max(8, ((progressIndex + 1) / progressSteps.length) * 100)}%`,
              }}
            />
          </div>
          <div className="progress-steps">
            {progressSteps.map((step, index) => (
              <div
                className={`progress-step ${index === progressIndex ? "active" : ""} ${index < progressIndex ? "complete" : ""}`}
                key={step}
              >
                <span className="progress-step-index">{index + 1}</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </form>
  );
}
