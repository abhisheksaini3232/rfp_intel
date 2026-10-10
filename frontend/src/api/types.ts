/**
 * Hand-written mirrors of the Pydantic models in rfp_intel/schemas.py plus the
 * API-only response shapes from BUILD_PLAN Section 6.5. This file is the
 * source of truth for the UI until `npm run types` generates src/api/schema.ts.
 */

export type DocType =
  | "bid_page"
  | "rfp"
  | "addendum"
  | "specs"
  | "affidavit"
  | "form"
  | "other";

export const DOC_TYPES: DocType[] = [
  "bid_page",
  "rfp",
  "addendum",
  "specs",
  "affidavit",
  "form",
  "other",
];

export type SearchConfig = "vector" | "hybrid" | "hybrid_rerank";

export const SEARCH_CONFIGS: SearchConfig[] = ["vector", "hybrid", "hybrid_rerank"];

export type FieldStatus = "ok" | "not_found" | "failed";

export type RunState = "running" | "done" | "failed";

export interface Citation {
  file: string;
  page: number;
  chunk_id: string;
  quote: string;
}

export interface Chunk {
  chunk_id: string;
  bid_id: string;
  file_name: string;
  doc_type: DocType;
  addendum_number: number | null;
  page: number;
  doc_date: string | null;
  section: string | null;
  kind: "text" | "table" | "qa" | "spec_list" | "record";
  header: string;
  text: string;
  token_count: number;
}

export interface SearchHit {
  chunk: Chunk;
  score: number;
  ranks: Record<string, number>;
}

export interface FieldValue {
  value: string | string[] | null;
  sources: Citation[];
  confidence: number;
  notes: string;
  status: FieldStatus;
}

export interface AddendumChange {
  field: string;
  kind: "override" | "clarification" | "addition";
  old_value: string | null;
  new_value: string;
  addendum_number: number;
  source: Citation;
}

export interface ValidationCounts {
  passed: number;
  failed: number;
  not_found: number;
}

export interface BidRecord {
  bid_id: string;
  fields: Record<string, FieldValue>;
  addendum_changes: AddendumChange[];
  validation: ValidationCounts;
  generated_at: string;
  run_id: string;
}

export interface Answer {
  question: string;
  answer: string;
  citations: Citation[];
  confidence: number;
  bids: string[];
}

export interface StepLog {
  run_id: string;
  step: number;
  agent: string;
  node: string;
  started_at: string;
  input_summary: string;
  tool_calls: Record<string, unknown>[];
  output_summary: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  error: string | null;
}

export interface RunStatus {
  run_id: string;
  bid_id: string;
  status: RunState;
  steps: StepLog[];
}

export interface IndexStats {
  bid_id: string;
  documents: number;
  chunks_added: number;
  chunks_total: number;
  skipped: boolean;
  warnings: string[];
  seconds: number;
}

// ---- API-only shapes (Section 6.5) ----

export interface Health {
  status: string;
  indexed_bids: string[];
}

export interface BidSummary {
  bid_id: string;
  title: string | null;
  agency: string | null;
  due_date: string | null;
  due_date_changed_by: number | null;
  doc_count: number;
  indexed: boolean;
  last_run: string | null;
  validation: ValidationCounts | null;
}

export interface DocumentSummary {
  file_name: string;
  doc_type: DocType;
  addendum_number: number | null;
  pages: number;
  tables: number;
  warnings: string[];
}

export interface BidDetail {
  bid_id: string;
  documents: DocumentSummary[];
  indexed: boolean;
  chunks: number;
}

export interface ExtractResponse {
  run_id: string;
}

export interface SearchResponse {
  hits: SearchHit[];
}

export interface SearchParams {
  q: string;
  bid_id?: string;
  doc_type?: DocType;
  addendum?: number;
  top_k?: number;
  config?: SearchConfig;
}

export interface AskRequest {
  question: string;
  bid_ids?: string[];
}

export type RetrievalMetric = "recall@1" | "recall@3" | "recall@5" | "recall@10" | "mrr";

export type RetrievalSummary = Record<string, Partial<Record<RetrievalMetric, number>>>;

export interface RetrievalQuestionResult {
  id: string;
  question: string;
  bid_id: string;
  expected_file: string;
  key_phrase: string;
  ranks: Record<string, number | null>;
}

export interface RetrievalEval {
  summary: RetrievalSummary;
  questions: RetrievalQuestionResult[];
}

export type ExtractionScore = "exact" | "partial" | "wrong" | "not_scored";

export interface ExtractionFieldResult {
  field: string;
  gold: unknown;
  output: unknown;
  score: ExtractionScore;
  citations?: unknown;
}

export interface ExtractionBidResult {
  fields: ExtractionFieldResult[];
  summary: { exact?: number; partial?: number; wrong?: number; accuracy?: number };
}

export interface ExtractionEval {
  bids: Record<string, ExtractionBidResult>;
}

export interface ApiErrorBody {
  error: string;
  run_id: string | null;
}
