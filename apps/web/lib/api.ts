import {
  AppLog,
  ArticleJobProduct,
  ArticleJob,
  ArticleBrief,
  ArticleDraftRecord,
  ArticleJobDetail,
  CompetitorPage,
  ContentRule,
  ContentCluster,
  KeywordResearchRow,
  ProductCandidate,
  Product,
  QaReport,
  SerpAnalysisReport,
  SerpResult,
  SettingsValidation,
  Source,
  StandardPostBatch,
  StandardPostBatchDetail,
  WorkflowRun,
  WorkflowResult,
  WorkflowState,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null;
  const timeout = controller ? globalThis.setTimeout(() => controller.abort(), timeoutMs) : null;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: init?.signal ?? controller?.signal,
      cache: "no-store",
    });
  } finally {
    if (timeout) {
      globalThis.clearTimeout(timeout);
    }
  }

  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  listArticleJobs: () => request<ArticleJob[]>("/article-jobs"),
  createArticleJob: (payload: Partial<ArticleJob>) =>
    request<ArticleJob>("/article-jobs", { method: "POST", body: JSON.stringify(payload) }),
  getArticleJob: (id: number) => request<ArticleJobDetail>(`/article-jobs/${id}`),
  getArticleSerpResults: (id: number) => request<{ items: SerpResult[] }>(`/article-jobs/${id}/serp-results`),
  getArticleKeywordResearch: (id: number) => request<{ items: KeywordResearchRow[] }>(`/article-jobs/${id}/keyword-research`),
  getArticleCompetitorPages: (id: number) => request<{ items: CompetitorPage[] }>(`/article-jobs/${id}/competitor-pages`),
  getArticleSerpAnalysis: (id: number) => request<SerpAnalysisReport | null>(`/article-jobs/${id}/serp-analysis`),
  getArticleProducts: (id: number) => request<{ items: ArticleJobProduct[] }>(`/article-jobs/${id}/products`),
  getArticleProductCandidates: (id: number) => request<{ items: ProductCandidate[] }>(`/article-jobs/${id}/product-candidates`),
  findProductCandidates: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/find-product-candidates`, { method: "POST" }),
  autoResearchProducts: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/auto-research-products`, { method: "POST" }),
  approveProductCandidate: (jobId: number, candidateId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/product-candidates/${candidateId}/approve`, { method: "POST" }),
  ignoreProductCandidate: (jobId: number, candidateId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/product-candidates/${candidateId}/ignore`, { method: "POST" }),
  convertProductCandidate: (jobId: number, candidateId: number, auto_extract = true) =>
    request<{ candidate: ProductCandidate; product_link: ArticleJobProduct }>(
      `/article-jobs/${jobId}/product-candidates/${candidateId}/convert`,
      { method: "POST", body: JSON.stringify({ auto_extract }) },
    ),
  createArticleProductSource: (id: number, payload: { source_url: string; source_type: string }) =>
    request<ArticleJobProduct>(`/article-jobs/${id}/product-sources`, { method: "POST", body: JSON.stringify(payload) }),
  extractArticleProduct: (id: number, product_source_id: number) =>
    request<ArticleJobProduct>(`/article-jobs/${id}/extract-product`, { method: "POST", body: JSON.stringify({ product_source_id }) }),
  researchProductCard: (id: number, linkId: number) =>
    request<ArticleJobProduct>(`/article-jobs/${id}/products/${linkId}/research-card`, { method: "POST" }),
  approveProductDraftReady: (id: number, linkId: number) =>
    request<ArticleJobProduct>(`/article-jobs/${id}/products/${linkId}/approve-draft-ready`, { method: "POST" }),
  deleteArticleJob: (id: number) =>
    request<void>(`/article-jobs/${id}`, { method: "DELETE" }),
  deleteArticleProductSource: (id: number, productSourceId: number) =>
    request<void>(`/article-jobs/${id}/product-sources/${productSourceId}`, { method: "DELETE" }),
  getArticleBriefs: (id: number) => request<{ items: ArticleBrief[] }>(`/article-jobs/${id}/briefs`),
  getArticleDrafts: (id: number) => request<{ items: ArticleDraftRecord[] }>(`/article-jobs/${id}/drafts`),
  getArticleQaReports: (id: number) => request<{ items: QaReport[] }>(`/article-jobs/${id}/qa-reports`),
  getWorkflowState: (id: number) => request<WorkflowState>(`/article-jobs/${id}/workflow-state`, undefined, 15000),
  updateArticleBrief: (briefId: number, brief_markdown: string) =>
    request<ArticleBrief>(`/article-jobs/briefs/${briefId}`, { method: "PUT", body: JSON.stringify({ brief_markdown }) }),
  generateDraft: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/generate-draft`, { method: "POST" }),
  runHumanEdit: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/run-human-edit`, { method: "POST" }),
  runQa: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/run-qa`, { method: "POST" }),
  runFixPass: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/run-fix-pass`, { method: "POST" }),
  applyEditorCorrections: (jobId: number, correction_notes: string) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/apply-editor-corrections`, {
      method: "POST",
      body: JSON.stringify({ correction_notes }),
    }),
  generateResearchBrief: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/generate-research-brief`, { method: "POST" }),
  getLatestWorkflowRun: (id: number) => request<WorkflowRun | null>(`/article-jobs/${id}/workflow-runs/latest`),
  runFullWorkflow: (jobId: number, research_mode: "fresh" | "resume_current" | "reuse_existing" | "refresh_missing_only") =>
    request<WorkflowRun>(`/article-jobs/${jobId}/run-full-workflow`, {
      method: "POST",
      body: JSON.stringify({ research_mode }),
    }),
  updateArticleJob: (id: number, payload: Partial<ArticleJob>) =>
    request<ArticleJob>(`/article-jobs/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  listProducts: () => request<Product[]>("/products"),
  createProduct: (payload: Partial<Product>) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(payload) }),
  getProduct: (id: number) => request<Product>(`/products/${id}`),
  updateProduct: (id: number, payload: Partial<Product>) =>
    request<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  listSources: () => request<Source[]>("/sources"),
  createSource: (payload: Partial<Source>) =>
    request<Source>("/sources", { method: "POST", body: JSON.stringify(payload) }),
  getSource: (id: number) => request<Source>(`/sources/${id}`),
  updateSource: (id: number, payload: Partial<Source>) =>
    request<Source>(`/sources/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  listClusters: () => request<ContentCluster[]>("/content-clusters"),
  createCluster: (payload: Partial<ContentCluster>) =>
    request<ContentCluster>("/content-clusters", { method: "POST", body: JSON.stringify(payload) }),
  getCluster: (id: number) => request<ContentCluster>(`/content-clusters/${id}`),
  updateCluster: (id: number, payload: Partial<ContentCluster>) =>
    request<ContentCluster>(`/content-clusters/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  listLogs: (articleJobId?: number) =>
    request<{ items: AppLog[] }>(`/logs${articleJobId ? `?article_job_id=${articleJobId}` : ""}`),
  validateSettings: () => request<SettingsValidation>("/settings/validation"),
  listContentRules: () => request<{ items: ContentRule[] }>("/settings/content-rules"),
  updateContentRule: (key: string, value: string) =>
    request<ContentRule>(`/settings/content-rules/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  runSerpResearch: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/run-serp-research`, { method: "POST" }),
  runKeywordResearch: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/run-keyword-research`, { method: "POST" }),
  extractCompetitors: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/extract-competitors`, { method: "POST" }),
  analyseSerp: (jobId: number) =>
    request<WorkflowResult>(`/article-jobs/${jobId}/analyse-serp`, { method: "POST" }),
  runWorkflow: (
    jobId: number,
    action:
      | "serp-research"
      | "competitor-gap-analysis"
      | "product-review-research"
      | "brief"
      | "original-value-checklist"
      | "draft"
      | "australian-human-rewrite"
      | "qa"
      | "fix-pass"
      | "generate-html"
      | "wordpress-export",
  ) =>
    request<WorkflowResult>(`/workflow/article-jobs/${jobId}/${action}`, { method: "POST" }),
  setManualReviewOverride: (jobId: number, enabled: boolean) =>
    request<WorkflowResult>(`/workflow/article-jobs/${jobId}/manual-review-override`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  uploadWordPressDraft: (jobId: number) =>
    request<WorkflowResult>(`/workflow/article-jobs/${jobId}/wordpress-export`, { method: "POST" }),
  listStandardPostBatches: () => request<StandardPostBatch[]>("/standard-post-batches"),
  createStandardPostBatch: (payload: { keywords: string; name?: string; wordpress_mode?: "local_only" | "local_plus_draft" }) =>
    request<StandardPostBatchDetail>("/standard-post-batches", { method: "POST", body: JSON.stringify(payload) }),
  getStandardPostBatch: (id: number) => request<StandardPostBatchDetail>(`/standard-post-batches/${id}`),
  startStandardPostBatch: (id: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${id}/start`, { method: "POST" }),
  pauseStandardPostBatch: (id: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${id}/pause`, { method: "POST" }),
  resumeStandardPostBatch: (id: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${id}/resume`, { method: "POST" }),
  cancelStandardPostBatch: (id: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${id}/cancel`, { method: "POST" }),
  retryStandardPostBatchItem: (batchId: number, itemId: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${batchId}/items/${itemId}/retry`, { method: "POST" }),
  skipStandardPostBatchItem: (batchId: number, itemId: number) =>
    request<StandardPostBatchDetail>(`/standard-post-batches/${batchId}/items/${itemId}/skip`, { method: "POST" }),
};
