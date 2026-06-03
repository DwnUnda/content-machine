export type ArticleJob = {
  id: number;
  title: string;
  primary_keyword: string;
  post_type: string;
  status: string;
  target_audience?: string | null;
  australian_angle?: string | null;
  notes?: string | null;
  cluster_id?: number | null;
  review_override: boolean;
  current_qa_score?: number | null;
  created_at: string;
  updated_at: string;
};

export type ArticleJobDetail = ArticleJob & {
  local_export_path?: string | null;
  serp_results: SerpResult[];
  keyword_research: KeywordResearchRow[];
  competitor_pages: CompetitorPage[];
  sources: RelatedRecord[];
  briefs: ArticleBrief[];
  drafts: RelatedRecord[];
  qa_reports: RelatedRecord[];
  wordpress_exports: RelatedRecord[];
  internal_links: RelatedRecord[];
};

export type RelatedRecord = {
  id: number;
  created_at: string;
  updated_at: string;
};

export type StandardPostBatchItem = {
  id: number;
  batch_id: number;
  keyword: string;
  slug?: string | null;
  position: number;
  status: "pending" | "running" | "complete" | "failed" | "skipped" | "cancelled";
  current_step?: string | null;
  article_job_id?: number | null;
  article_folder?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type StandardPostBatchCounts = {
  total: number;
  pending: number;
  running: number;
  complete: number;
  failed: number;
  skipped: number;
  cancelled: number;
};

export type StandardPostBatch = {
  id: number;
  name?: string | null;
  status: "pending" | "running" | "paused" | "complete" | "cancelled";
  wordpress_mode: "local_only" | "local_plus_draft";
  summary_message?: string | null;
  counts: StandardPostBatchCounts;
  is_running: boolean;
  created_at: string;
  updated_at: string;
};

export type StandardPostBatchDetail = StandardPostBatch & {
  items: StandardPostBatchItem[];
};

export type SerpResult = {
  id: number;
  article_job_id: number;
  keyword: string;
  position?: number | null;
  title?: string | null;
  url?: string | null;
  domain?: string | null;
  snippet?: string | null;
  result_type?: string | null;
  source_payload?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type KeywordResearchRow = {
  id: number;
  article_job_id: number;
  keyword: string;
  intent?: string | null;
  search_volume?: number | null;
  difficulty?: number | null;
  cpc?: number | null;
  competition?: string | null;
  source?: string | null;
  notes?: string | null;
  source_payload?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type CompetitorPage = {
  id: number;
  article_job_id: number;
  serp_result_id?: number | null;
  title?: string | null;
  url: string;
  domain?: string | null;
  meta_description?: string | null;
  h1?: string | null;
  h2_list?: string[] | null;
  h3_list?: string[] | null;
  word_count_estimate?: number | null;
  visible_text_extract?: string | null;
  detected_product_names?: string[] | null;
  tables_count?: number | null;
  faq_headings?: string[] | null;
  affiliate_indicators?: string[] | null;
  australian_relevance_signals?: string[] | null;
  australian_relevance_score?: number | null;
  notes?: string | null;
  page_type?: string | null;
  extraction_method?: string | null;
  extraction_status?: string | null;
  error_message?: string | null;
  raw_extracted_data_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type SerpAnalysisReport = {
  id: number;
  article_job_id: number;
  dominant_intent?: string | null;
  dominant_page_types_json?: Record<string, number> | null;
  common_headings_json?: string[] | null;
  common_questions_json?: string[] | null;
  repeated_products_json?: string[] | null;
  competitor_gaps_json?: string[] | null;
  australian_context_gaps_json?: string[] | null;
  recommended_angle?: string | null;
  original_value_recommendations_json?: string[] | null;
  suggested_support_articles_json?: string[] | null;
  difficulty_estimate?: string | null;
  raw_report_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ProductRetailerUrl = {
  retailer?: string | null;
  url: string;
  price_aud?: string | null;
  as_of?: string | null;
  verification?: string | null;
  status?: number | null;
};

export type Product = {
  id: number;
  name: string;
  brand?: string | null;
  category?: string | null;
  role?: string | null;
  product_url?: string | null;
  personally_tested: boolean;
  model_number?: string | null;
  retailer_domain?: string | null;
  price_text?: string | null;
  capacity_text?: string | null;
  tank_size_text?: string | null;
  noise_level_text?: string | null;
  power_use_text?: string | null;
  warranty_text?: string | null;
  drainage_text?: string | null;
  room_size_text?: string | null;
  review_rating_text?: string | null;
  review_count_text?: string | null;
  description_snippet?: string | null;
  visible_specs_table?: Record<string, string> | null;
  confidence_level?: string | null;
  confidence_score?: number | null;
  common_positives?: string | null;
  common_complaints?: string | null;
  who_should_buy?: string | null;
  who_should_avoid?: string | null;
  best_for?: string | null;
  bottom_line?: string | null;
  extraction_status?: string | null;
  extraction_error?: string | null;
  raw_extracted_json?: Record<string, unknown> | null;
  notes?: string | null;
  // Review-led product analysis layer (additive, all optional).
  manufacturer_url?: string | null;
  // Plain URL strings (manual edit) or rich objects (web-search research with price/verification).
  retailer_urls?: Array<string | ProductRetailerUrl> | null;
  positive_review_patterns?: string | null;
  negative_review_patterns?: string | null;
  reliability_concerns?: string | null;
  key_specs?: string[] | null;
  price_range_text?: string | null;
  australian_availability?: string | null;
  review_methodology_notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type ArticleJobProduct = {
  id: number;
  article_job_id: number;
  product_id?: number | null;
  source_url: string;
  original_source_url?: string | null;
  cleaned_source_url?: string | null;
  source_type: string;
  retailer?: string | null;
  key_drawback?: string | null;
  draft_ready: boolean;
  readiness_status: string;
  missing_fields: string[];
  extraction_status?: string | null;
  extraction_error?: string | null;
  needs_review?: boolean;
  draft_ready_approved?: boolean;
  inferred_name?: string | null;
  extraction_failure_reason?: string | null;
  research_sources?: Array<Record<string, unknown>>;
  affiliate_url?: string | null;
  raw_extracted_json?: Record<string, unknown> | null;
  product?: Product | null;
  created_at: string;
  updated_at: string;
};

export type ProductCandidate = {
  id: number;
  article_job_id: number;
  product_name: string;
  brand?: string | null;
  model_number?: string | null;
  source_url?: string | null;
  source_domain?: string | null;
  source_type: string;
  reason_found?: string | null;
  found_count: number;
  confidence_score?: number | null;
  suggested_best_for?: string | null;
  status: string;
  raw_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type Source = {
  id: number;
  title: string;
  url?: string | null;
  source_type: string;
  publisher?: string | null;
  trust_notes?: string | null;
  article_job_id?: number | null;
  created_at: string;
  updated_at: string;
};

export type ContentCluster = {
  id: number;
  name: string;
  description?: string | null;
  target_url_slug?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type AppLog = {
  id: number;
  level: string;
  event_type: string;
  message: string;
  article_job_id?: number | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type SettingsValidation = {
  site_name: string;
  site_url_present: boolean;
  target_country: string;
  target_language: string;
  required: { key: string; present: boolean }[];
};

export type WorkflowResult = {
  action: string;
  article_job_id: number;
  status: string;
  message: string;
  next_step?: string | null;
};

export type ArticleBrief = {
  id: number;
  article_job_id: number;
  version: number;
  brief_markdown?: string | null;
  outline_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ArticleDraftRecord = {
  id: number;
  article_job_id: number;
  version: number;
  stage?: string | null;
  draft_markdown?: string | null;
  seo_title?: string | null;
  meta_description?: string | null;
  slug?: string | null;
  excerpt?: string | null;
  content_modules?: ContentModuleRecord[] | null;
  model_name?: string | null;
  prompt_name?: string | null;
  source_payload_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ContentModuleRecord = {
  module_type: string;
  heading: string;
};

export type QaReport = {
  id: number;
  article_job_id: number;
  status: string;
  score?: number | null;
  passed_gate: boolean;
  findings_json?: Record<string, unknown> | null;
  summary?: string | null;
  model_name?: string | null;
  prompt_name?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowRunStep = {
  id: number;
  workflow_run_id: number;
  step_key: string;
  step_label: string;
  status: string;
  message?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowRun = {
  id: number;
  article_job_id: number;
  workflow_mode: string;
  research_mode: string;
  status: string;
  current_step?: string | null;
  summary_message?: string | null;
  steps: WorkflowRunStep[];
  created_at: string;
  updated_at: string;
};

export type WorkflowStateStep = {
  step_key: string;
  step_label: string;
  status: string;
  detail?: string | null;
  paid_step: boolean;
};

export type PublishReadinessCheck = {
  key: string;
  label: string;
  passed: boolean;
  detail?: string | null;
};

export type PublishReadiness = {
  ready: boolean;
  summary: string;
  checks: PublishReadinessCheck[];
  html_validation?: {
    passed?: boolean;
    summary?: string;
    html_path?: string | null;
    checks?: PublishReadinessCheck[];
  } | null;
};

export type WorkflowState = {
  article_job_id: number;
  recommended_research_mode: "fresh" | "resume_current" | "reuse_existing" | "refresh_missing_only" | string;
  next_recommended_action: string;
  next_step_key?: string | null;
  summary_message: string;
  estimated_paid_calls: number;
  has_existing_work: boolean;
  steps: WorkflowStateStep[];
  publish_readiness?: PublishReadiness | null;
};

export type ContentRule = {
  key: string;
  label: string;
  description: string;
  category: string;
  value: string;
};
