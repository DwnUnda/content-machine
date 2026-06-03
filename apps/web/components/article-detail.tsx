"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { getMinProductsForPostType, getPostTypeLabel, isProductGated } from "@/lib/post-types";
import { AppLog, ArticleBrief, ArticleDraftRecord, ArticleJobDetail, ArticleJobProduct, CompetitorPage, ContentModuleRecord, KeywordResearchRow, ProductCandidate, ProductRetailerUrl, PublishReadiness, QaReport, SerpAnalysisReport, SerpResult, WorkflowResult, WorkflowRun, WorkflowState } from "@/types";
import { StatusBadge } from "@/components/status-badge";


const tabs = [
  "Overview",
  "SERP Research",
  "Keywords",
  "Competitors",
  "Products",
  "Reddit Feedback",
  "Brief",
  "Draft",
  "QA Report",
  "WordPress Export",
  "Logs",
] as const;


const workflowButtons = [
  { action: "competitor-gap-analysis", label: "Run competitor gap analysis" },
  { action: "product-review-research", label: "Run product/review research" },
  { action: "brief", label: "Generate Research Brief" },
  { action: "original-value-checklist", label: "Create original value checklist" },
  { action: "draft", label: "Generate Draft" },
  { action: "australian-human-rewrite", label: "Run Human Edit" },
  { action: "qa", label: "Run QA" },
  { action: "fix-pass", label: "Run Fix Pass" },
  { action: "generate-html", label: "Generate HTML" },
  { action: "wordpress-export", label: "Export to WordPress draft" },
] as const;

const wordpressUploadStages = [
  "Generating visuals...",
  "Uploading media...",
  "Inserting images...",
  "Uploading WordPress draft...",
];

function asList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") {
      const record = item as Record<string, unknown>;
      return String(record.message || record.title || JSON.stringify(record));
    }
    return String(item);
  });
}

function countWords(value?: string | null) {
  if (!value) return 0;
  return value.split(/\s+/).filter(Boolean).length;
}

function normalizeContentModules(value: unknown): ContentModuleRecord[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        module_type: String(record.module_type || record.type || "").trim(),
        heading: String(record.heading || "").trim(),
      };
    })
    .filter((item) => item.module_type && item.heading);
}

function toFileUrl(path?: string | null) {
  if (!path) return null;
  const normalized = path.replace(/\\/g, "/");
  return normalized.startsWith("file://") ? normalized : `file:///${normalized}`;
}

function normalizeRetailer(entry: string | ProductRetailerUrl): ProductRetailerUrl {
  return typeof entry === "string" ? { url: entry } : entry;
}

function safeHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function verificationBadge(verification?: string | null): string {
  switch (verification) {
    case "verified":
      return "✓ verified";
    case "unverified_blocked":
      return "⚠ blocked (likely real)";
    case "unverified":
      return "⚠ unverified";
    case "dead":
      return "✗ dead link";
    case "error":
      return "⚠ unreachable";
    default:
      return "";
  }
}

function latestRedditFeedbackLog(logs: AppLog[]) {
  return logs.find((log) => log.event_type === "workflow.reddit_feedback.completed") || null;
}

function metadataList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function getResearchModeLabel(value: string) {
  switch (value) {
    case "fresh":
      return "Start fresh and rerun paid research";
    case "resume_current":
      return "Continue from saved work";
    case "reuse_existing":
      return "Reuse saved research only";
    case "refresh_missing_only":
      return "Refresh only missing or stale steps";
    default:
      return value.replaceAll("_", " ");
  }
}

function getResearchModeHelp(value: string) {
  switch (value) {
    case "fresh":
      return "Reruns research from the start. This can create new paid API calls.";
    case "resume_current":
      return "Continues from the first missing or failed step using saved work where possible.";
    case "reuse_existing":
      return "Uses saved research and skips rerunning paid research, even if the research is older.";
    case "refresh_missing_only":
      return "Keeps current work and only reruns steps that are missing or stale.";
    default:
      return null;
  }
}

function getPrimaryWorkflowButtonLabel(state: WorkflowState | null) {
  if (!state || !state.has_existing_work) {
    return "Create Blog Draft";
  }
  switch (state.next_recommended_action) {
    case "Run fix pass":
      return "Continue from failed QA";
    case "Run QA":
      return "Continue with QA";
    case "Run human edit":
      return "Continue with Human Edit";
    case "Generate draft":
      return "Continue with Draft";
    case "Generate research brief":
      return "Continue with Brief";
    case "Analyse SERP":
      return "Continue with SERP Analysis";
    case "Extract competitors":
      return "Continue with Competitor Extraction";
    case "Run keyword research":
      return "Continue with Keyword Research";
    case "Run SERP research":
      return "Continue with SERP Research";
    case "Review final draft":
      return "Open Completed Draft";
    default:
      return "Resume Workflow";
  }
}

function getRunningWorkflowLabel(run: WorkflowRun | null): string {
  const currentStep = run?.current_step;
  if (!currentStep) return "workflow";

  const stepLabel = run?.steps.find((step) => step.step_key === currentStep)?.step_label;
  if (stepLabel) return stepLabel;

  return currentStep
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function getDraftStatusLabel(article: ArticleJobDetail, latestDraft: ArticleDraftRecord | null, draftReadyProducts: number, needsProductCards: boolean) {
  if (needsProductCards && draftReadyProducts < 3) {
    return "Needs Product Data";
  }
  if (article.status === "Ready for review") {
    return "Ready for Review";
  }
  if (article.status === "QA failed") {
    return "QA Failed";
  }
  if (latestDraft) {
    return "Draft Complete";
  }
  return "Not started";
}

function PublishReadinessPanel({ readiness }: { readiness?: PublishReadiness | null }) {
  if (!readiness) {
    return (
      <div className="panel stack">
        <div className="toolbar">
          <strong>Publish readiness</strong>
          <span className="muted">Not checked yet</span>
        </div>
        <div className="muted">Run the workflow to generate a draft, QA report, and rendered HTML.</div>
      </div>
    );
  }

  return (
    <div className="panel stack">
      <div className="toolbar">
        <strong>Publish readiness</strong>
        <StatusBadge status={readiness.ready ? "Ready for review" : "QA failed"} />
      </div>
      <div className="muted">{readiness.summary}</div>
      <div className="grid-3">
        {readiness.checks.map((check) => (
          <div className="stat" key={check.key} title={check.detail || undefined}>
            <strong>{check.passed ? "Pass" : "Needs work"}</strong>
            <span className="muted">{check.label}</span>
          </div>
        ))}
      </div>
      {readiness.checks.some((check) => !check.passed) ? (
        <div className="stack">
          {readiness.checks.filter((check) => !check.passed).map((check) => (
            <div className="message error" key={`failed-${check.key}`}>
              <strong>{check.label}:</strong> {check.detail || "This check has not passed."}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}


export function ArticleDetail({ id }: { id: number }) {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("Overview");
  const [article, setArticle] = useState<ArticleJobDetail | null>(null);
  const [logs, setLogs] = useState<AppLog[]>([]);
  const [serpResults, setSerpResults] = useState<SerpResult[]>([]);
  const [keywordResearch, setKeywordResearch] = useState<KeywordResearchRow[]>([]);
  const [competitorPages, setCompetitorPages] = useState<CompetitorPage[]>([]);
  const [serpAnalysis, setSerpAnalysis] = useState<SerpAnalysisReport | null>(null);
  const [productCandidates, setProductCandidates] = useState<ProductCandidate[]>([]);
  const [articleProducts, setArticleProducts] = useState<ArticleJobProduct[]>([]);
  const [briefs, setBriefs] = useState<ArticleBrief[]>([]);
  const [drafts, setDrafts] = useState<ArticleDraftRecord[]>([]);
  const [qaReports, setQaReports] = useState<QaReport[]>([]);
  const [latestWorkflowRun, setLatestWorkflowRun] = useState<WorkflowRun | null>(null);
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null);
  const [workflowMode, setWorkflowMode] = useState<"manual" | "full_draft">("manual");
  const [researchMode, setResearchMode] = useState<"fresh" | "resume_current" | "reuse_existing" | "refresh_missing_only">("fresh");
  const [briefDraft, setBriefDraft] = useState("");
  const [productSourceUrl, setProductSourceUrl] = useState("");
  const [productSourceType, setProductSourceType] = useState("retailer");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [messageDraftLink, setMessageDraftLink] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  async function load() {
    try {
      const [job, logResponse, serpResponse, keywordResponse, competitorResponse, analysisResponse, candidateResponse, productResponse, briefResponse, draftResponse, qaResponse, workflowRun] = await Promise.all([
        api.getArticleJob(id),
        api.listLogs(id),
        api.getArticleSerpResults(id),
        api.getArticleKeywordResearch(id),
        api.getArticleCompetitorPages(id),
        api.getArticleSerpAnalysis(id),
        api.getArticleProductCandidates(id),
        api.getArticleProducts(id),
        api.getArticleBriefs(id),
        api.getArticleDrafts(id),
        api.getArticleQaReports(id),
        api.getLatestWorkflowRun(id),
      ]);
      setArticle(job);
      setLogs(logResponse.items);
      setSerpResults(serpResponse.items);
      setKeywordResearch(keywordResponse.items);
      setCompetitorPages(competitorResponse.items);
      setSerpAnalysis(analysisResponse);
      setProductCandidates(candidateResponse.items);
      setArticleProducts(productResponse.items);
      setBriefs(briefResponse.items);
      setDrafts(draftResponse.items);
      setQaReports(qaResponse.items);
      setLatestWorkflowRun(workflowRun);
      setError(null);
      api.getWorkflowState(id)
        .then((state) => {
          setWorkflowState(state);
        })
        .catch((err: unknown) => {
          setWorkflowState(null);
          setError(err instanceof Error ? `Workflow state failed to load: ${err.message}` : "Workflow state failed to load.");
        });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load article.");
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    if (!workflowState) return;
    setResearchMode(
      workflowState.recommended_research_mode as "fresh" | "resume_current" | "reuse_existing" | "refresh_missing_only",
    );
  }, [workflowState]);

  useEffect(() => {
    setBriefDraft(briefs[0]?.brief_markdown ?? "");
  }, [briefs]);

  useEffect(() => {
    if (loadingAction !== "upload-wordpress-draft") {
      return;
    }

    let index = 0;
    setMessage(wordpressUploadStages[0]);
    const timer = window.setInterval(() => {
      index = (index + 1) % wordpressUploadStages.length;
      setMessage(wordpressUploadStages[index]);
    }, 2200);

    return () => window.clearInterval(timer);
  }, [loadingAction]);

  async function runAction(action: (typeof workflowButtons)[number]["action"]) {
    setLoadingAction(action);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result: WorkflowResult =
        action === "brief"
          ? await api.generateResearchBrief(id)
          : action === "draft"
            ? await api.generateDraft(id)
            : action === "australian-human-rewrite"
              ? await api.runHumanEdit(id)
              : action === "qa"
                ? await api.runQa(id)
                : action === "fix-pass"
                  ? await api.runFixPass(id)
                  : await api.runWorkflow(id, action);
      setMessage(result.message);
      if (action === "draft") {
        setMessage("Draft saved. Open the Draft tab to review it.");
        setMessageDraftLink(true);
        setActiveTab("Draft");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow action failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runSerpResearch() {
    setLoadingAction("serp-research");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.runSerpResearch(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "SERP research failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runKeywordResearch() {
    setLoadingAction("keyword-research");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.runKeywordResearch(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Keyword research failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function toggleOverride(enabled: boolean) {
    setLoadingAction("manual-override");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.setManualReviewOverride(id, enabled);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update manual override.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function extractCompetitors() {
    setLoadingAction("extract-competitors");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.extractCompetitors(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Competitor extraction failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function analyseSerp() {
    setLoadingAction("analyse-serp");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.analyseSerp(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "SERP analysis failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function generateResearchBrief() {
    setLoadingAction("generate-research-brief");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.generateResearchBrief(id);
      setMessage(result.message);
      setActiveTab("Brief");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Brief generation failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function saveBrief() {
    if (!briefs[0]) {
      return;
    }
    setLoadingAction("save-brief");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      await api.updateArticleBrief(briefs[0].id, briefDraft);
      setMessage("Research brief saved.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save brief.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function generateDraft() {
    setLoadingAction("generate-draft");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      await api.generateDraft(id);
      setMessage("Draft saved. Open the Draft tab to review it.");
      setMessageDraftLink(true);
      setActiveTab("Draft");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft generation failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runHumanEdit() {
    setLoadingAction("run-human-edit");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.runHumanEdit(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Human edit failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runQa() {
    setLoadingAction("run-qa");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.runQa(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "QA failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function runFixPass() {
    setLoadingAction("run-fix-pass");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.runFixPass(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fix pass failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function uploadWordPressDraft() {
    const readiness = workflowState?.publish_readiness;
    if (!readiness?.ready) {
      setMessage(null);
      setMessageDraftLink(false);
      setError(readiness?.summary || "This article is not publish-ready yet. Complete the readiness checks before uploading a WordPress draft.");
      setActiveTab("WordPress Export");
      return;
    }

    if (!window.confirm("Generate visuals and upload this article to WordPress as a draft?")) {
      return;
    }

    setLoadingAction("upload-wordpress-draft");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.uploadWordPressDraft(id);
      setLoadingAction(null);
      setMessage(result.message);
      await load();
    } catch (err) {
      setLoadingAction(null);
      setError(err instanceof Error ? err.message : "WordPress upload failed.");
    }
  }

  async function createFullDraft() {
    setLoadingAction("full-draft");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const run = await api.runFullWorkflow(id, researchMode);
      setLatestWorkflowRun(run);
      setWorkflowMode("full_draft");
      setMessage(run.status === "complete"
        ? "Blog draft workflow completed. Open the Draft tab to review it."
        : run.summary_message || "Blog draft workflow completed.");
      setMessageDraftLink(run.status === "complete");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Full draft workflow failed.");
      await load();
    } finally {
      setLoadingAction(null);
    }
  }

  async function extractProductData() {
    if (!productSourceUrl.trim()) {
      setError("Product URL is required.");
      return;
    }
    setLoadingAction("extract-product");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const link = await api.createArticleProductSource(id, {
        source_url: productSourceUrl.trim(),
        source_type: productSourceType,
      });
      const extracted = await api.extractArticleProduct(id, link.id);
      setMessage(
        extracted.extraction_status === "extraction_failed" || extracted.extraction_status === "failed"
          ? "Direct extraction failed (the page likely blocks scraping). The URL was saved with inferred clues - use Research Product Card to build a draft from accessible sources."
          : "Product data extracted and saved."
      );
      setProductSourceUrl("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Product extraction failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function findProductCandidates() {
    setLoadingAction("find-product-candidates");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.findProductCandidates(id);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Product candidate discovery failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function approveCandidate(candidateId: number) {
    setLoadingAction(`approve-candidate-${candidateId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.approveProductCandidate(id, candidateId);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve product candidate.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function ignoreCandidate(candidateId: number) {
    setLoadingAction(`ignore-candidate-${candidateId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.ignoreProductCandidate(id, candidateId);
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ignore product candidate.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function convertCandidate(candidateId: number) {
    setLoadingAction(`convert-candidate-${candidateId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      await api.convertProductCandidate(id, candidateId, true);
      setMessage("Candidate converted into a linked product card.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to convert product candidate.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function removeProductLink(productSourceId: number) {
    setLoadingAction(`delete-product-${productSourceId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      await api.deleteArticleProductSource(id, productSourceId);
      setMessage("Product link removed from this article.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove product link.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function researchProductCard(linkId: number) {
    setLoadingAction(`research-product-${linkId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.researchProductCard(id, linkId);
      setMessage(
        `Researched "${result.product?.name || result.inferred_name || "product"}" from accessible sources. Review the card, then mark it draft-ready. Unknown facts stay "Not confirmed".`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Product research failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function autoResearchProducts() {
    setLoadingAction("auto-research-products");
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      const result = await api.autoResearchProducts(id);
      setMessage(result.message || "AI product research complete.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI product research failed.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function markProductDraftReady(linkId: number) {
    setLoadingAction(`approve-product-${linkId}`);
    setMessage(null);
    setMessageDraftLink(false);
    setError(null);
    try {
      await api.approveProductDraftReady(id, linkId);
      setMessage("Product card marked draft-ready.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mark draft-ready. Fill the core fields first.");
    } finally {
      setLoadingAction(null);
    }
  }

  const needsProductCards = article ? isProductGated(article.post_type) : false;
  const minProductsRequired = article ? getMinProductsForPostType(article.post_type) : 0;
  const draftReadyProducts = articleProducts.filter((item) => item.draft_ready).length;
  const urlsAdded = articleProducts.length;
  const extractionFailedCount = articleProducts.filter(
    (item) => item.extraction_status === "extraction_failed" || item.extraction_status === "failed"
  ).length;
  const needReviewCount = articleProducts.filter((item) => item.needs_review && !item.draft_ready).length;
  const postTypeLabel = article ? getPostTypeLabel(article.post_type) : "Informational Blog Post";
  const workflowSummary = needsProductCards
    ? "Research, brief, product cards, draft, human edit, QA."
    : "Research, brief, draft, human edit, QA.";
  const latestDraft = drafts[0] ?? null;
  const productTabHint = needsProductCards
    ? `This post type requires at least ${minProductsRequired} draft-ready product card${minProductsRequired === 1 ? "" : "s"} before drafting. Add product URLs as starting points, or leave them empty - when you run the workflow, AI web search automatically finds, researches and verifies products. Unconfirmed facts stay as Not confirmed.`
    : "This post type does not require product cards.";
  const productReadinessMessage = needsProductCards && draftReadyProducts < minProductsRequired
    ? (() => {
        const bits: string[] = [];
        if (extractionFailedCount) bits.push(`${extractionFailedCount} need product research because direct extraction failed`);
        if (needReviewCount) bits.push(`${needReviewCount} need review before they count`);
        const tail = bits.length ? ` ${bits.join("; ")}.` : "";
        return `${urlsAdded} product URL${urlsAdded === 1 ? "" : "s"} found. ${draftReadyProducts} draft-ready card${draftReadyProducts === 1 ? "" : "s"}. This post needs at least ${minProductsRequired} draft-ready product card${minProductsRequired === 1 ? "" : "s"} before a proper draft can be generated.${tail}`;
      })()
    : null;
  const workflowRunStatusLabel = latestWorkflowRun
    ? latestWorkflowRun.status === "complete"
      ? "Done"
      : latestWorkflowRun.status === "failed"
        ? "Failed"
        : latestWorkflowRun.status
    : null;
  const localExportUrl = article?.local_export_path ? toFileUrl(article.local_export_path) : null;
  const primaryWorkflowLabel = getPrimaryWorkflowButtonLabel(workflowState);
  const draftButtonLabel = latestDraft ? "Regenerate Draft" : "Generate Draft";
  const publishReadiness = workflowState?.publish_readiness ?? null;
  const canUploadWordPressDraft = Boolean(publishReadiness?.ready);
  const uploadDisabledReason = publishReadiness && !publishReadiness.ready ? publishReadiness.summary : null;
  const latestDraftModules = useMemo(() => {
    if (!latestDraft) return [];
    const explicit = normalizeContentModules(latestDraft.content_modules);
    if (explicit.length) return explicit;
    const sourcePayload = latestDraft.source_payload_json as Record<string, unknown> | null | undefined;
    return normalizeContentModules(sourcePayload?.content_modules);
  }, [latestDraft]);

  useEffect(() => {
    if (activeTab !== "Draft" || !latestDraft || !article) {
      setPreviewHtml("");
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }

    const controller = new AbortController();
    setPreviewLoading(true);
    setPreviewError(null);

    fetch("/api/render-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_markdown: latestDraft.draft_markdown || "",
        post_type: article.post_type,
        content_modules: latestDraftModules,
      }),
      signal: controller.signal,
      cache: "no-store",
    })
      .then(async (response) => {
        const payload = await response.json() as { html?: string; error?: string };
        if (!response.ok) {
          throw new Error(payload.error || "Preview render failed.");
        }
        setPreviewHtml(String(payload.html || ""));
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setPreviewHtml("");
        setPreviewError(err instanceof Error ? err.message : "Preview render failed.");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setPreviewLoading(false);
        }
      });

    return () => controller.abort();
  }, [activeTab, article, latestDraft, latestDraftModules]);

  const tabContent = useMemo(() => {
    if (!article) return null;
    const latestBrief = briefs[0] ?? null;
    const briefOutline = (latestBrief?.outline_json as Record<string, unknown> | null) ?? null;
    const latestDraft = drafts[0] ?? null;
    const latestQa = qaReports[0] ?? null;
    const latestQaFindings = (latestQa?.findings_json ?? {}) as Record<string, unknown>;
    const listFromFindings = (key: string) => asList(latestQaFindings[key]);
    const latestWordCount = countWords(latestDraft?.draft_markdown);
    const minimumWordCount = Number(latestQaFindings.minimum_word_count ?? 0) || null;
    const draftStatusLabel = getDraftStatusLabel(article, latestDraft, draftReadyProducts, needsProductCards);
    const qaNextStep = latestQa?.passed_gate
      ? "QA passed. Review the draft in the Draft tab before final approval."
      : productReadinessMessage
        ? "QA failed because the article has too few draft-ready product recommendations. Add or improve product cards, then regenerate the draft."
        : listFromFindings("fix_instructions")[0]
          || listFromFindings("failed_checks")[0]
          || latestQa?.summary
          || "Review the failed checks, fix the draft, then run QA again.";
    switch (activeTab) {
      case "Overview":
        return (
          <div className="stack">
            <div><strong>Primary keyword</strong><div className="muted">{article.primary_keyword}</div></div>
            <div><strong>Type</strong><div className="muted">{getPostTypeLabel(article.post_type)}</div></div>
            <div><strong>Audience</strong><div className="muted">{article.target_audience || "Not set"}</div></div>
            <div><strong>Australian angle</strong><div className="muted">{article.australian_angle || "Not set"}</div></div>
            <div><strong>Notes</strong><div className="muted">{article.notes || "No notes yet."}</div></div>
            <div className="stack">
              <div><strong>Local output folder</strong><div className="muted">{article.local_export_path || "Not created yet"}</div></div>
              {localExportUrl ? (
                <div>
                  <a className="button-secondary" href={localExportUrl} target="_blank" rel="noreferrer">
                    Open completed article folder
                  </a>
                </div>
              ) : null}
            </div>
            <div><strong>Current QA score</strong><div className="muted">{article.current_qa_score ?? "Not scored yet"}</div></div>
            <div><strong>Manual review override</strong><div className="muted">{article.review_override ? "Enabled" : "Disabled"}</div></div>
          </div>
        );
      case "SERP Research":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>Stored SERP results</strong>
                <div className="muted">
                  Last run: {serpResults.length ? new Date(serpResults[0].created_at).toLocaleString() : "Not run yet"}
                </div>
              </div>
              <button className="button" disabled={loadingAction === "serp-research"} onClick={runSerpResearch} type="button">
                {loadingAction === "serp-research" ? "Running..." : "Run SERP Research"}
              </button>
            </div>
            {serpResults.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Position</th>
                    <th>Title</th>
                    <th>Domain</th>
                    <th>URL</th>
                    <th>Snippet</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {serpResults.map((item) => (
                    <tr key={item.id}>
                      <td>{item.position ?? "-"}</td>
                      <td>{item.title || "-"}</td>
                      <td>{item.domain || "-"}</td>
                      <td>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a> : "-"}</td>
                      <td>{item.snippet || "-"}</td>
                      <td>{item.result_type || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No SERP results yet.</div>
            )}
          </div>
        );
      case "Keywords":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>Stored keyword research</strong>
                <div className="muted">
                  Last run: {keywordResearch.length ? new Date(keywordResearch[0].created_at).toLocaleString() : "Not run yet"}
                </div>
              </div>
              <button className="button" disabled={loadingAction === "keyword-research"} onClick={runKeywordResearch} type="button">
                {loadingAction === "keyword-research" ? "Running..." : "Run Keyword Research"}
              </button>
            </div>
            {keywordResearch.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Keyword</th>
                    <th>Search volume</th>
                    <th>CPC</th>
                    <th>Competition</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {keywordResearch.map((item) => (
                    <tr key={item.id}>
                      <td>{item.keyword}</td>
                      <td>{item.search_volume ?? "-"}</td>
                      <td>{item.cpc ?? "-"}</td>
                      <td>{item.competition ?? item.difficulty ?? "-"}</td>
                      <td>{item.source ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No keyword research yet.</div>
            )}
          </div>
        );
      case "Competitors":
        return (
          <div className="stack">
            <div className="actions">
              <button className="button" disabled={loadingAction === "extract-competitors"} onClick={extractCompetitors} type="button">
                {loadingAction === "extract-competitors" ? "Extracting..." : "Extract Competitors"}
              </button>
              <button className="button-secondary" disabled={loadingAction === "analyse-serp"} onClick={analyseSerp} type="button">
                {loadingAction === "analyse-serp" ? "Analysing..." : "Analyse SERP"}
              </button>
            </div>
            {competitorPages.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>URL</th>
                    <th>Domain</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>AU score</th>
                    <th>Words</th>
                    <th>H1</th>
                    <th>H2/H3</th>
                    <th>Products</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {competitorPages.map((item) => (
                    <tr key={item.id}>
                      <td><a href={item.url} target="_blank" rel="noreferrer">{item.url}</a></td>
                      <td>{item.domain || "-"}</td>
                      <td>{item.page_type || "-"}</td>
                      <td>{item.extraction_status || "-"}</td>
                      <td>{item.australian_relevance_score ?? "-"}</td>
                      <td>{item.word_count_estimate ?? "-"}</td>
                      <td>{item.h1 || "-"}</td>
                      <td>{`${item.h2_list?.length ?? 0}/${item.h3_list?.length ?? 0}`}</td>
                      <td>{item.detected_product_names?.length ?? 0}</td>
                      <td>{item.error_message || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No competitor extractions yet.</div>
            )}
            {serpAnalysis ? (
              <div className="panel stack">
                <div><strong>Dominant intent</strong><div className="muted">{serpAnalysis.dominant_intent || "-"}</div></div>
                <div><strong>Dominant page types</strong><div className="muted">{Object.entries(serpAnalysis.dominant_page_types_json || {}).map(([k, v]) => `${k}: ${v}`).join(", ") || "-"}</div></div>
                <div><strong>Common headings</strong><div className="muted">{(serpAnalysis.common_headings_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Common questions</strong><div className="muted">{(serpAnalysis.common_questions_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Repeated products</strong><div className="muted">{(serpAnalysis.repeated_products_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Competitor gaps</strong><div className="muted">{(serpAnalysis.competitor_gaps_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Australian context gaps</strong><div className="muted">{(serpAnalysis.australian_context_gaps_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Recommended angle</strong><div className="muted">{serpAnalysis.recommended_angle || "-"}</div></div>
                <div><strong>Original value opportunities</strong><div className="muted">{(serpAnalysis.original_value_recommendations_json || []).join(" | ") || "-"}</div></div>
                <div><strong>Difficulty estimate</strong><div className="muted">{serpAnalysis.difficulty_estimate || "-"}</div></div>
              </div>
            ) : (
              <div className="empty">No SERP analysis report yet.</div>
            )}
          </div>
        );
      case "Products":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>Article products</strong>
                <div className="muted">{productTabHint}</div>
              </div>
              <button
                className="button-secondary"
                disabled={loadingAction === "find-product-candidates"}
                onClick={findProductCandidates}
                type="button"
              >
                {loadingAction === "find-product-candidates" ? "Finding..." : "Find Product Candidates"}
              </button>
            </div>
            {productReadinessMessage ? <div className="message error">{productReadinessMessage}</div> : null}
            <div className="stack">
              <div className="toolbar">
                <strong>Product Candidates</strong>
                <span className="muted">{productCandidates.length} candidate{productCandidates.length === 1 ? "" : "s"}</span>
              </div>
              {productCandidates.length ? (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Product name</th>
                        <th>Brand</th>
                        <th>Source</th>
                        <th>Reason found</th>
                        <th>Confidence</th>
                        <th>Suggested best for</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {productCandidates.map((candidate) => {
                        const needsReview = Boolean(candidate.raw_json && candidate.raw_json["needs_review"]);
                        return (
                          <tr key={candidate.id}>
                            <td>
                              <div>{candidate.product_name}</div>
                              {needsReview ? <div className="muted small-copy">Needs review</div> : null}
                            </td>
                            <td>{candidate.brand || "Not confirmed"}</td>
                            <td>
                              <div>{candidate.source_domain || "Not confirmed"}</div>
                              {candidate.source_url ? (
                                <a href={candidate.source_url} rel="noreferrer" target="_blank">
                                  Open source
                                </a>
                              ) : null}
                            </td>
                            <td>{candidate.reason_found || "Not confirmed"}</td>
                            <td>{candidate.confidence_score ?? "-"}</td>
                            <td>{candidate.suggested_best_for || "Not confirmed"}</td>
                            <td>{candidate.status}</td>
                            <td>
                              <div className="stack compact">
                                <button
                                  className="button-link"
                                  disabled={candidate.status === "converted" || loadingAction === `approve-candidate-${candidate.id}`}
                                  onClick={() => approveCandidate(candidate.id)}
                                  type="button"
                                >
                                  {loadingAction === `approve-candidate-${candidate.id}` ? "Approving..." : "Approve"}
                                </button>
                                <button
                                  className="button-link"
                                  disabled={candidate.status === "converted" || loadingAction === `ignore-candidate-${candidate.id}`}
                                  onClick={() => ignoreCandidate(candidate.id)}
                                  type="button"
                                >
                                  {loadingAction === `ignore-candidate-${candidate.id}` ? "Ignoring..." : "Ignore"}
                                </button>
                                <button
                                  className="button-link"
                                  disabled={candidate.status === "converted" || loadingAction === `convert-candidate-${candidate.id}`}
                                  onClick={() => convertCandidate(candidate.id)}
                                  type="button"
                                >
                                  {loadingAction === `convert-candidate-${candidate.id}` ? "Creating..." : "Create product card"}
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty">No product candidates yet. Use Find Product Candidates to suggest products from stored research.</div>
              )}
            </div>
            <div className="stack">
              <div className="toolbar">
                <strong>Linked Product Cards</strong>
                <div className="actions">
                  <span className="muted">{articleProducts.length} linked</span>
                  {needsProductCards ? (
                    <button className="button" disabled={loadingAction === "auto-research-products"} onClick={autoResearchProducts} type="button">
                      {loadingAction === "auto-research-products" ? "Finding & researching..." : "Find & research products with AI"}
                    </button>
                  ) : null}
                </div>
              </div>
              {needsProductCards ? (
                <div className="muted small-copy">
                  Researches any unfinished cards and, if fewer than 3 are draft-ready, finds more Australian products via web search. Uses live OpenAI calls.
                </div>
              ) : null}
            </div>
            {articleProducts.length ? (
              <div className="panel stack">
                <div><strong>Product URLs added</strong><div className="muted">{urlsAdded}</div></div>
                <div><strong>Draft-ready cards</strong><div className="muted">{draftReadyProducts}</div></div>
                <div><strong>Extraction failed</strong><div className="muted">{extractionFailedCount}</div></div>
                <div><strong>Need review</strong><div className="muted">{needReviewCount}</div></div>
              </div>
            ) : null}
            <div className="form-grid">
              <div className="field-full">
                <label htmlFor="product-source-url">Add Product URL</label>
                <input
                  id="product-source-url"
                  onChange={(event) => setProductSourceUrl(event.target.value)}
                  placeholder="https://example.com.au/product-page"
                  value={productSourceUrl}
                />
              </div>
              <div className="field">
                <label htmlFor="product-source-type">Product source type</label>
                <select
                  id="product-source-type"
                  onChange={(event) => setProductSourceType(event.target.value)}
                  value={productSourceType}
                >
                  <option value="retailer">retailer</option>
                  <option value="manufacturer">manufacturer</option>
                  <option value="review page">review page</option>
                  <option value="other">other</option>
                </select>
              </div>
              <div className="field">
                <label>&nbsp;</label>
                <button className="button" disabled={loadingAction === "extract-product"} onClick={extractProductData} type="button">
                  {loadingAction === "extract-product" ? "Extracting..." : "Extract Product Data"}
                </button>
              </div>
            </div>
            {articleProducts.length ? (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Role</th>
                      <th>Brand</th>
                      <th>Retailer</th>
                      <th>Best for</th>
                      <th>Price</th>
                      <th>Capacity</th>
                      <th>Tank size</th>
                      <th>Key drawback</th>
                      <th>Confidence</th>
                      <th>Draft ready</th>
                      <th>Status</th>
                      <th>Source</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {articleProducts.map((item) => {
                      const blockingMissing = item.missing_fields.filter((field) => !field.includes("who should buy") && !field.includes("who should avoid"));
                      const polishMissing = item.missing_fields.filter((field) => field.includes("who should buy") || field.includes("who should avoid"));
                      const extractionFailed = item.extraction_status === "extraction_failed" || item.extraction_status === "failed";
                      const canResearch = extractionFailed || item.extraction_status === "research_needed" || item.extraction_status === "researched_needs_review";
                      const displayName = item.product?.name || item.inferred_name || "Not confirmed";
                      const retailerEntries = (item.product?.retailer_urls || []).map(normalizeRetailer).filter((entry) => entry.url);
                      const alreadyResearched = item.extraction_status === "researched_needs_review" || retailerEntries.length > 0;
                      const raw = (item.raw_extracted_json || {}) as Record<string, unknown>;
                      const whyRecommended = typeof raw.why_recommended === "string" ? raw.why_recommended : null;
                      const roleRationale = typeof raw.role_rationale === "string" ? raw.role_rationale : null;
                      const uncertainFields = Array.isArray(raw.uncertain_fields) ? (raw.uncertain_fields as unknown[]).map(String) : [];
                      return (
                        <tr key={item.id}>
                          <td>
                            <div>{displayName}</div>
                            {whyRecommended ? (
                              <div className="muted small-copy">Why: {whyRecommended}</div>
                            ) : null}
                            {item.inferred_name && (!item.product?.name || item.product.name === "Not confirmed") ? (
                              <div className="muted small-copy">Inferred from URL: {item.inferred_name}</div>
                            ) : null}
                            {extractionFailed && item.extraction_failure_reason ? (
                              <div className="muted small-copy">Extraction failed: {item.extraction_failure_reason}</div>
                            ) : null}
                          </td>
                          <td>
                            <div>{item.product?.role || "—"}</div>
                            {roleRationale ? <div className="muted small-copy">{roleRationale}</div> : null}
                          </td>
                          <td>{item.product?.brand || "Not confirmed"}</td>
                          <td>{item.retailer || item.product?.retailer_domain || "Not confirmed"}</td>
                          <td>{item.product?.best_for || "Not confirmed"}</td>
                          <td>
                            <div>{item.product?.price_range_text || item.product?.price_text || "Not confirmed"}</div>
                            {retailerEntries.length ? (
                              <div className="stack compact" style={{ marginTop: "0.25rem" }}>
                                {retailerEntries.map((entry, idx) => (
                                  <div className="muted small-copy" key={`${item.id}-retailer-${idx}`}>
                                    <a href={entry.url} target="_blank" rel="noreferrer">
                                      {entry.retailer || safeHost(entry.url)}
                                    </a>
                                    {entry.price_aud && entry.price_aud !== "Not confirmed" ? ` — ${entry.price_aud}` : ""}
                                    {verificationBadge(entry.verification) ? ` · ${verificationBadge(entry.verification)}` : ""}
                                    {entry.as_of ? ` · as of ${entry.as_of}` : ""}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </td>
                          <td>{item.product?.capacity_text || "Not confirmed"}</td>
                          <td>{item.product?.tank_size_text || "Not confirmed"}</td>
                          <td>{item.key_drawback || "Not confirmed"}</td>
                          <td>{item.product ? `${item.product.confidence_level || "Low"} (${item.product.confidence_score ?? 0})` : "-"}</td>
                          <td>
                            <div>{item.draft_ready ? "Draft ready" : "Not draft-ready"}</div>
                            {!item.draft_ready && blockingMissing.length ? (
                              <div className="muted small-copy">{blockingMissing.join(" | ")}</div>
                            ) : null}
                            {polishMissing.length ? (
                              <div className="muted small-copy">Manual polish: {polishMissing.join(" | ")}</div>
                            ) : null}
                          </td>
                          <td>
                            <div>{item.readiness_status || item.extraction_status || "pending"}</div>
                            {uncertainFields.length ? (
                              <div className="muted small-copy">AI unsure: {uncertainFields.join("; ")}</div>
                            ) : null}
                          </td>
                          <td>
                            <a href={item.cleaned_source_url || item.source_url} target="_blank" rel="noreferrer">
                              Open source
                            </a>
                          </td>
                          <td>
                            <div className="stack compact">
                              {canResearch ? (
                                <button
                                  className="button-link"
                                  disabled={loadingAction === `research-product-${item.id}`}
                                  onClick={() => researchProductCard(item.id)}
                                  type="button"
                                >
                                  {loadingAction === `research-product-${item.id}`
                                    ? "Researching..."
                                    : alreadyResearched
                                      ? "Re-run AI research"
                                      : "Research Product Card"}
                                </button>
                              ) : null}
                              {item.product_id ? <Link href={`/products/${item.product_id}`}>Edit card</Link> : <span className="muted">No card</span>}
                              {!item.draft_ready && blockingMissing.length === 0 ? (
                                <button
                                  className="button-link"
                                  disabled={loadingAction === `approve-product-${item.id}`}
                                  onClick={() => markProductDraftReady(item.id)}
                                  type="button"
                                >
                                  {loadingAction === `approve-product-${item.id}` ? "Saving..." : "Mark draft-ready"}
                                </button>
                              ) : null}
                              <button
                                className="button-link"
                                disabled={loadingAction === `delete-product-${item.id}`}
                                onClick={() => removeProductLink(item.id)}
                                type="button"
                              >
                                {loadingAction === `delete-product-${item.id}` ? "Removing..." : "Remove"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty">
                {needsProductCards
                  ? "No product URLs added. Add some above, or run the workflow to let AI web search find and research products automatically."
                  : "No product URLs added yet."}
              </div>
            )}
          </div>
        );
      case "Reddit Feedback": {
        const redditLog = latestRedditFeedbackLog(logs);
        const metadata = redditLog?.metadata_json || {};
        const qualified = metadataList(metadata.qualified_patterns);
        const rejected = metadataList(metadata.rejected_patterns);
        const sources = metadataList(metadata.research_sources);
        return redditLog ? (
          <div className="stack">
            <div className="panel stack">
              <div className="toolbar">
                <div>
                  <strong>Reddit feedback research</strong>
                  <div className="muted">{new Date(redditLog.created_at).toLocaleString()}</div>
                </div>
                <span className="muted">{qualified.length} qualified · {rejected.length} rejected</span>
              </div>
              <div className="muted">
                {String(metadata.notes || "Reddit is treated as anecdotal owner feedback only, not as a source for specs.")}
              </div>
            </div>
            <div className="panel stack">
              <strong>Qualified patterns</strong>
              {qualified.length ? (
                qualified.map((pattern, index) => (
                  <div className="list-card" key={`${String(pattern.product_name || "pattern")}-${index}`}>
                    <div className="toolbar">
                      <strong>{String(pattern.product_name || "Category-level feedback")}</strong>
                      <span className="muted">{String(pattern.confidence || "moderate")}</span>
                    </div>
                    <div>{String(pattern.issue || "No issue summary.")}</div>
                    <div className="muted">{String(pattern.publishable_wording || "")}</div>
                    <div className="muted">
                      Evidence: {String(pattern.evidence_comment_count ?? 0)} comments · {String(pattern.evidence_thread_count ?? 0)} thread(s)
                    </div>
                    {Array.isArray(pattern.source_urls) && pattern.source_urls.length ? (
                      <div className="stack">
                        {pattern.source_urls.map((url) => (
                          <a href={String(url)} key={String(url)} rel="noreferrer" target="_blank">{safeHost(String(url))}</a>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="empty">No Reddit patterns met the publishing threshold.</div>
              )}
            </div>
            <div className="panel stack">
              <strong>Rejected patterns</strong>
              {rejected.length ? (
                rejected.map((pattern, index) => (
                  <div className="list-card" key={`${String(pattern.issue || "rejected")}-${index}`}>
                    <div><strong>{String(pattern.product_name || "Category-level feedback")}</strong></div>
                    <div>{String(pattern.issue || "No issue summary.")}</div>
                    <div className="muted">{String(pattern.reason_rejected || "Rejected by threshold rules.")}</div>
                  </div>
                ))
              ) : (
                <div className="empty">No rejected patterns recorded.</div>
              )}
            </div>
            <div className="panel stack">
              <strong>Reddit sources checked</strong>
              {sources.length ? (
                sources.map((source, index) => (
                  <div className="list-card" key={`${String(source.url || "source")}-${index}`}>
                    <a href={String(source.url)} rel="noreferrer" target="_blank">{String(source.url)}</a>
                    <div className="muted">{String(source.used_for || source.subreddit || "")}</div>
                  </div>
                ))
              ) : (
                <div className="empty">No Reddit source URLs were stored.</div>
              )}
            </div>
          </div>
        ) : (
          <div className="empty">No Reddit feedback research has run yet. It runs automatically after product research in the full workflow.</div>
        );
      }
      case "Brief":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>Research brief</strong>
                <div className="muted">
                  Latest version: {latestBrief ? `v${latestBrief.version} from ${new Date(latestBrief.updated_at).toLocaleString()}` : "Not generated yet"}
                </div>
              </div>
              <div className="actions">
                <button className="button" disabled={loadingAction === "generate-research-brief"} onClick={generateResearchBrief} type="button">
                  {loadingAction === "generate-research-brief" ? "Generating..." : "Generate Research Brief"}
                </button>
                <button className="button-secondary" disabled={!latestBrief || loadingAction === "save-brief"} onClick={saveBrief} type="button">
                  {loadingAction === "save-brief" ? "Saving..." : "Save Brief"}
                </button>
              </div>
            </div>
            {briefOutline ? <BriefSummary outline={briefOutline} /> : <div className="empty">No research brief yet.</div>}
            <div className="stack">
              <strong>Editable brief markdown</strong>
              <textarea
                className="textarea"
                onChange={(event) => setBriefDraft(event.target.value)}
                rows={24}
                value={briefDraft}
              />
            </div>
          </div>
        );
      case "Draft":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>Draft pipeline</strong>
                <div className="muted">
                  Latest draft: {latestDraft ? `${latestDraft.stage || "draft"} v${latestDraft.version}` : "Not generated yet"}
                </div>
              </div>
              <div className="actions">
                <button className="button" disabled={loadingAction === "generate-draft"} onClick={generateDraft} type="button">
                  {loadingAction === "generate-draft" ? "Generating..." : draftButtonLabel}
                </button>
                <button className="button-secondary" disabled={loadingAction === "run-human-edit"} onClick={runHumanEdit} type="button">
                  {loadingAction === "run-human-edit" ? "Editing..." : "Run Human Edit"}
                </button>
                <button className="button-secondary" disabled={loadingAction === "run-qa"} onClick={runQa} type="button">
                  {loadingAction === "run-qa" ? "Running..." : "Run QA"}
                </button>
                <button className="button-secondary" disabled={loadingAction === "run-fix-pass"} onClick={runFixPass} type="button">
                  {loadingAction === "run-fix-pass" ? "Fixing..." : "Run Fix Pass"}
                </button>
              </div>
            </div>
            <div className="panel stack">
              <div><strong>Status</strong><div className="muted">{draftStatusLabel}</div></div>
              <div><strong>Stage</strong><div className="muted">{latestDraft?.stage || "Not generated yet"}</div></div>
              <div><strong>QA score</strong><div className="muted">{latestQa?.score ?? "Not scored yet"}</div></div>
              <div><strong>Word count</strong><div className="muted">{latestDraft ? latestWordCount : "Not generated yet"}{minimumWordCount ? ` / minimum ${minimumWordCount}` : ""}</div></div>
              <div className="stack">
                <div><strong>Local output folder</strong><div className="muted">{article.local_export_path || "Not created yet"}</div></div>
                {localExportUrl ? (
                  <div>
                    <a className="button-secondary" href={localExportUrl} target="_blank" rel="noreferrer">
                      Open completed article folder
                    </a>
                  </div>
                ) : null}
              </div>
            </div>
            {latestDraft ? (
              <div className="panel stack">
                <div><strong>Draft stage</strong><div className="muted">{latestDraft.stage || "Not confirmed"}</div></div>
                <div><strong>Status</strong><div className="muted">{draftStatusLabel}</div></div>
                <div><strong>QA score</strong><div className="muted">{latestQa?.score ?? "Not scored yet"}</div></div>
                <div><strong>SEO title</strong><div className="muted">{latestDraft.seo_title || "Not confirmed"}</div></div>
                <div><strong>Meta description</strong><div className="muted">{latestDraft.meta_description || "Not confirmed"}</div></div>
                <div><strong>Slug</strong><div className="muted">{latestDraft.slug || "Not confirmed"}</div></div>
                <div><strong>Excerpt</strong><div className="muted">{latestDraft.excerpt || "Not confirmed"}</div></div>
                <div className="stack">
                  <div><strong>Renderer modules</strong></div>
                  {latestDraftModules.length ? (
                    <div className="muted">
                      {latestDraftModules.map((module, index) => (
                        <div key={`${module.module_type}-${module.heading}-${index}`}>
                          <strong>{module.module_type}</strong>: {module.heading}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="muted">No explicit renderer modules saved for this draft yet. The renderer will fall back to heading-based inference.</div>
                  )}
                </div>
                <div><strong>Draft markdown</strong></div>
                <textarea className="textarea" readOnly rows={26} value={latestDraft.draft_markdown || ""} />
                <div className="stack">
                  <div><strong>Rendered preview</strong></div>
                  {previewLoading ? (
                    <div className="muted">Rendering preview...</div>
                  ) : previewError ? (
                    <div className="message error">{previewError}</div>
                  ) : previewHtml ? (
                    <iframe
                      className="draft-preview-frame"
                      srcDoc={previewHtml}
                      title="Rendered draft preview"
                    />
                  ) : (
                    <div className="muted">Preview not available yet.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="empty">
                No draft has been generated yet. Complete research{needsProductCards ? `, add at least ${minProductsRequired} draft-ready product card${minProductsRequired === 1 ? "" : "s"},` : ""} then click Generate Draft.
              </div>
            )}
            {drafts.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Stage</th>
                    <th>Modules</th>
                    <th>SEO title</th>
                    <th>Slug</th>
                    <th>Model</th>
                  </tr>
                </thead>
                <tbody>
                  {drafts.map((draft) => (
                    <tr key={draft.id}>
                      <td>{draft.version}</td>
                      <td>{draft.stage || "-"}</td>
                      <td>{normalizeContentModules(draft.content_modules || (draft.source_payload_json as Record<string, unknown> | null | undefined)?.content_modules).length || "-"}</td>
                      <td>{draft.seo_title || "-"}</td>
                      <td>{draft.slug || "-"}</td>
                      <td>{draft.model_name || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        );
      case "QA Report":
        return (
          <div className="stack">
            <div className="toolbar">
              <div>
                <strong>QA reports</strong>
                <div className="muted">
                  Latest score: {latestQa?.score ?? "Not scored yet"}
                </div>
              </div>
              <div className="actions">
                <button className="button" disabled={loadingAction === "run-qa"} onClick={runQa} type="button">
                  {loadingAction === "run-qa" ? "Running..." : "Run QA"}
                </button>
                <button className="button-secondary" disabled={loadingAction === "run-fix-pass"} onClick={runFixPass} type="button">
                  {loadingAction === "run-fix-pass" ? "Fixing..." : "Run Fix Pass"}
                </button>
              </div>
            </div>
            {latestQa ? (
              <div className="panel stack">
                <div><strong>Score</strong><div className="muted">{latestQa.score ?? "Not scored yet"}</div></div>
                <div><strong>Pass / fail</strong><div className="muted">{latestQa.passed_gate ? "Pass" : "Fail"}</div></div>
                <div><strong>Status</strong><div className="muted">{latestQa.status}</div></div>
                <div><strong>Why it is not ready</strong><div className="muted">{latestQa.passed_gate ? "The QA gate passed." : qaNextStep}</div></div>
                <div><strong>What to fix next</strong><div className="muted">{qaNextStep}</div></div>
                <div><strong>Summary</strong><div className="muted">{latestQa.summary || "No summary yet."}</div></div>
                <div><strong>Failed checks</strong><div className="muted">{listFromFindings("failed_checks").join(" | ") || "None"}</div></div>
                <div><strong>Warnings</strong><div className="muted">{listFromFindings("warnings").join(" | ") || "None"}</div></div>
                <div><strong>Fix instructions</strong><div className="muted">{listFromFindings("fix_instructions").join(" | ") || "None"}</div></div>
                {"minimum_word_count" in latestQaFindings ? (
                  <div>
                    <strong>Length check</strong>
                    <div className="muted">
                      {String(latestQaFindings.minimum_word_count_passed) === "true" ? "Passed" : "Failed"} · {String(latestQaFindings.word_count ?? 0)} words
                      {latestQaFindings.minimum_word_count ? ` / minimum ${String(latestQaFindings.minimum_word_count)}` : ""}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="empty">No QA report has been generated yet.</div>
            )}
          </div>
        );
      case "WordPress Export":
        return (
          <div className="stack">
            <PublishReadinessPanel readiness={publishReadiness} />
            <div className="panel stack">
              <div className="toolbar">
                <div>
                  <strong>WordPress draft upload</strong>
                  <div className="muted">
                    Upload is available only after the final draft, QA, generated HTML, and WordPress-safe HTML checks pass.
                  </div>
                </div>
                {drafts[0] && localExportUrl ? (
                  <button
                    className="button"
                    disabled={loadingAction === "upload-wordpress-draft" || !canUploadWordPressDraft}
                    onClick={uploadWordPressDraft}
                    title={uploadDisabledReason || undefined}
                    type="button"
                  >
                    {loadingAction === "upload-wordpress-draft" ? "Uploading draft..." : "Upload to WordPress Draft"}
                  </button>
                ) : null}
              </div>
              {uploadDisabledReason ? <div className="message error">{uploadDisabledReason}</div> : null}
              <PanelList count={article.wordpress_exports.length} label="WordPress export records" />
            </div>
            {publishReadiness?.html_validation?.checks?.length ? (
              <div className="panel stack">
                <div className="toolbar">
                  <strong>HTML structure checks</strong>
                  <span className="muted">{publishReadiness.html_validation.summary || "Latest rendered HTML validation"}</span>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Check</th>
                      <th>Status</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {publishReadiness.html_validation.checks.map((check) => (
                      <tr key={check.key}>
                        <td>{check.label}</td>
                        <td>{check.passed ? "Pass" : "Needs work"}</td>
                        <td>{check.detail || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {publishReadiness.html_validation.html_path ? (
                  <div className="muted">Rendered HTML: {publishReadiness.html_validation.html_path}</div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      case "Logs":
        return logs.length ? (
          <div className="stack">
            {logs.map((log) => (
              <div className="list-card" key={log.id}>
                <div className="toolbar">
                  <strong>{log.event_type}</strong>
                  <span className="muted">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <div>{log.message}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No logs for this article yet.</div>
        );
    }
  }, [activeTab, article, logs, serpResults, keywordResearch, competitorPages, serpAnalysis, productCandidates, articleProducts, briefs, drafts, qaReports, briefDraft, loadingAction, productSourceType, productSourceUrl, generateDraft, runHumanEdit, runQa, runFixPass, draftReadyProducts, needsProductCards, productReadinessMessage, urlsAdded, extractionFailedCount, needReviewCount, latestDraftModules, previewError, previewHtml, previewLoading, publishReadiness, canUploadWordPressDraft, uploadDisabledReason]);

  if (error && !article) {
    return <div className="message error">{error}</div>;
  }

  if (!article) {
    return <div className="panel muted">Loading article...</div>;
  }

  return (
    <div className="stack">
      <section className="hero">
        <div className="toolbar">
          <div>
            <div className="brand-kicker">Article workflow</div>
            <h1>{article.title}</h1>
            <p className="brand-copy">Local-first workflow record with draft-only export safeguards.</p>
            <p className="muted">
              {postTypeLabel}: {workflowSummary}
            </p>
          </div>
          <StatusBadge status={article.status} />
        </div>
        <div className="actions">
          <button
            className="button workflow-action-button"
            disabled={loadingAction === "full-draft"}
            onClick={createFullDraft}
            type="button"
          >
            {loadingAction === "full-draft" ? `Running: ${getRunningWorkflowLabel(latestWorkflowRun)}` : primaryWorkflowLabel}
          </button>
          {localExportUrl ? (
            <button className="button-secondary" onClick={() => window.open(localExportUrl, "_blank")} type="button">
              Open Completed Draft
            </button>
          ) : null}
          {drafts[0] ? (
            <button className="button-secondary" onClick={() => setActiveTab("Draft")} type="button">
              View Draft
            </button>
          ) : null}
          <button
            className="button-secondary"
            disabled={loadingAction === "manual-override"}
            onClick={() => toggleOverride(!article.review_override)}
            type="button"
          >
            {loadingAction === "manual-override"
              ? "Saving..."
              : article.review_override
                ? "Disable manual override"
                : "Enable manual override"}
          </button>
          {drafts[0] && localExportUrl ? (
            <button
              className="button"
              disabled={loadingAction === "upload-wordpress-draft" || !canUploadWordPressDraft}
              onClick={uploadWordPressDraft}
              title={uploadDisabledReason || undefined}
              type="button"
            >
              {loadingAction === "upload-wordpress-draft" ? "Uploading draft..." : "Upload to WordPress Draft"}
            </button>
          ) : null}
        </div>
        {workflowState ? (
          <div className="muted">
            {workflowState.next_recommended_action === "Review final draft"
              ? "This article already has a completed draft. Review it before rerunning anything."
              : `${workflowState.summary_message} ${workflowState.estimated_paid_calls > 0 ? `This run may make ${workflowState.estimated_paid_calls} paid API call${workflowState.estimated_paid_calls === 1 ? "" : "s"}.` : "This run should not create new paid API calls."}`}
          </div>
        ) : null}
        <div className="panel stack">
          <div className="grid-3">
            <div className="stat">
              <strong>{postTypeLabel}</strong>
              <span className="muted">Workflow mode</span>
            </div>
            <div className="stat">
              <strong>{latestDraft?.stage || "No draft"}</strong>
              <span className="muted">Latest draft stage</span>
            </div>
            <div className="stat">
              <strong>{article.current_qa_score ?? "Not scored"}</strong>
              <span className="muted">Latest QA score</span>
            </div>
          </div>
          <div className="muted">QA gate: score 85+ required for review readiness unless manual override is enabled.</div>
        </div>
        <PublishReadinessPanel readiness={publishReadiness} />
        {workflowState ? (
          <div className="panel stack">
            <div className="toolbar">
              <strong>Workflow state</strong>
              <span className="muted">
                Estimated paid calls if run now: {workflowState.estimated_paid_calls}
              </span>
            </div>
            <div className="grid-3">
              <div className="stat">
                <strong>{getResearchModeLabel(workflowState.recommended_research_mode)}</strong>
                <span className="muted">Recommended mode</span>
              </div>
              <div className="stat">
                <strong>{workflowState.next_recommended_action}</strong>
                <span className="muted">Recommended next action</span>
              </div>
              <div className="stat">
                <strong>{workflowState.has_existing_work ? "Stored work found" : "New article"}</strong>
                <span className="muted">Reuse status</span>
              </div>
            </div>
            <div className="message">{workflowState.summary_message}</div>
            <table className="table">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Status</th>
                  <th>Paid</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {workflowState.steps.map((step) => (
                  <tr key={step.step_key}>
                    <td>{step.step_label}</td>
                    <td>{step.status}</td>
                    <td>{step.paid_step ? "Yes" : "No"}</td>
                    <td>{step.detail || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {latestWorkflowRun ? (
          <div className="panel stack">
            <div className="toolbar">
              <strong>Workflow progress</strong>
              <span className="muted">
                {workflowRunStatusLabel} · {new Date(latestWorkflowRun.updated_at).toLocaleString()}
              </span>
            </div>
            <div className="muted">
              Research mode: {getResearchModeLabel(latestWorkflowRun.research_mode)}
            </div>
            <div className="message">
              {latestWorkflowRun.status === "complete"
                ? "Draft saved locally. Open the Draft tab or check the Local output folder in Overview."
                : "The workflow is still running or failed. Use the steps below to inspect what happened."}
            </div>
            <div className="grid-3">
              <div className="stat">
                <strong>{getDraftStatusLabel(article, drafts[0] ?? null, draftReadyProducts, needsProductCards)}</strong>
                <span className="muted">Draft status</span>
              </div>
              <div className="stat">
                <strong>{draftReadyProducts}</strong>
                <span className="muted">Draft-ready products</span>
              </div>
              <div className="stat">
                <strong>{getPostTypeLabel(article.post_type)}</strong>
                <span className="muted">Post type</span>
              </div>
            </div>
            {latestWorkflowRun.summary_message ? <div>{latestWorkflowRun.summary_message}</div> : null}
            <table className="table">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Status</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {latestWorkflowRun.steps.map((step) => (
                  <tr key={step.id}>
                    <td>{step.step_label}</td>
                    <td>{step.status}</td>
                    <td>{step.message || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {message ? (
          <div className="message">
            <div>{message}</div>
            {messageDraftLink ? (
              <div className="actions">
                <button className="button-secondary" onClick={() => setActiveTab("Draft")} type="button">
                  View Draft
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
        {error ? <div className="message error">{error}</div> : null}
        <details className="panel stack">
          <summary>Advanced workflow tools</summary>
          <div className="actions">
            <label className="field-inline">
              <span>Workflow mode</span>
              <select value={workflowMode} onChange={(event) => setWorkflowMode(event.target.value as "manual" | "full_draft")}>
                <option value="manual">Manual</option>
                <option value="full_draft">Full Draft</option>
              </select>
            </label>
            <label className="field-inline">
              <span>Research mode</span>
              <select value={researchMode} onChange={(event) => setResearchMode(event.target.value as "fresh" | "resume_current" | "reuse_existing" | "refresh_missing_only")}>
                <option value="resume_current">Continue from saved work</option>
                <option value="fresh">Start fresh and rerun paid research</option>
                <option value="reuse_existing">Reuse saved research only</option>
                <option value="refresh_missing_only">Refresh only missing or stale steps</option>
              </select>
            </label>
          </div>
          <div className="muted">
            {getResearchModeHelp(researchMode)}
          </div>
          <div className="actions">
            <button
              className="button-secondary"
              disabled={loadingAction === "serp-research"}
              onClick={runSerpResearch}
              type="button"
            >
              {loadingAction === "serp-research" ? "Running..." : "Run SERP Research"}
            </button>
            <button
              className="button-secondary"
              disabled={loadingAction === "keyword-research"}
              onClick={runKeywordResearch}
              type="button"
            >
              {loadingAction === "keyword-research" ? "Running..." : "Run Keyword Research"}
            </button>
            <button
              className="button-secondary"
              disabled={loadingAction === "extract-competitors"}
              onClick={extractCompetitors}
              type="button"
            >
              {loadingAction === "extract-competitors" ? "Extracting..." : "Extract Competitors"}
            </button>
            <button
              className="button-secondary"
              disabled={loadingAction === "analyse-serp"}
              onClick={analyseSerp}
              type="button"
            >
              {loadingAction === "analyse-serp" ? "Analysing..." : "Analyse SERP"}
            </button>
            <button
              className="button-secondary"
              disabled={loadingAction === "generate-research-brief"}
              onClick={generateResearchBrief}
              type="button"
            >
              {loadingAction === "generate-research-brief" ? "Generating..." : "Generate Research Brief"}
            </button>
            {workflowButtons.filter((button) => button.action !== "brief").map((button) => (
              <button
                key={button.action}
                className="button-secondary"
                disabled={loadingAction === button.action}
                onClick={() => runAction(button.action)}
                type="button"
              >
                {loadingAction === button.action ? "Running..." : button.label}
              </button>
            ))}
          </div>
        </details>
      </section>

      <section className="panel">
        <div className="tab-row">
          {tabs.map((tab) => (
            <button
              className="tab"
              data-active={activeTab === tab}
              key={tab}
              onClick={() => setActiveTab(tab)}
              type="button"
            >
              {tab}
            </button>
          ))}
        </div>
      </section>

      <section className="panel">{tabContent}</section>
    </div>
  );
}


function PanelList({ count, label }: { count: number; label: string }) {
  return count ? <div>{count} {label} recorded.</div> : <div className="empty">No {label.toLowerCase()} yet.</div>;
}


function BriefSummary({ outline }: { outline: Record<string, unknown> }) {
  const listValue = (key: string) => {
    const value = outline[key];
    return Array.isArray(value) ? value.map((item) => String(item)) : [];
  };

  return (
    <div className="panel stack">
      <div><strong>Primary keyword</strong><div className="muted">{String(outline.primary_keyword ?? "-")}</div></div>
      <div><strong>Search intent</strong><div className="muted">{String(outline.search_intent ?? "-")}</div></div>
      <div><strong>Reader profile</strong><div className="muted">{String(outline.reader_profile ?? "-")}</div></div>
      <div><strong>Recommended angle</strong><div className="muted">{String(outline.recommended_article_angle ?? "-")}</div></div>
      <div><strong>Secondary keywords</strong><div className="muted">{listValue("secondary_keywords").join(" | ") || "-"}</div></div>
      <div><strong>Competitor gaps</strong><div className="muted">{listValue("competitor_gaps").join(" | ") || "-"}</div></div>
      <div><strong>Australian context gaps</strong><div className="muted">{listValue("australian_context_gaps").join(" | ") || "-"}</div></div>
      <div><strong>Required sections</strong><div className="muted">{listValue("required_sections").join(" | ") || "-"}</div></div>
      <div><strong>Original value points</strong><div className="muted">{listValue("original_value_points").join(" | ") || "-"}</div></div>
      <div><strong>Internal link suggestions</strong><div className="muted">{listValue("internal_link_suggestions").join(" | ") || "-"}</div></div>
      <div><strong>FAQ questions</strong><div className="muted">{listValue("faq_questions").join(" | ") || "-"}</div></div>
      <div><strong>Suggested titles</strong><div className="muted">{listValue("suggested_title_options").join(" | ") || "-"}</div></div>
      <div><strong>Suggested slug</strong><div className="muted">{String(outline.suggested_slug ?? "-")}</div></div>
      <div><strong>Meta description</strong><div className="muted">{String(outline.meta_description_draft ?? "-")}</div></div>
    </div>
  );
}
