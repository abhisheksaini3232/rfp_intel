"""All Pydantic models shared between modules and agents (BUILD_PLAN Section 5).

No raw dicts cross module boundaries: ingestion, search, agents, API and CLI
exchange only these models.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DocType(str, Enum):
    """Kind of document inside a bid folder."""

    BID_PAGE = "bid_page"
    RFP = "rfp"
    ADDENDUM = "addendum"
    SPECS = "specs"
    AFFIDAVIT = "affidavit"
    FORM = "form"
    OTHER = "other"


class Page(BaseModel):
    """One parsed page of a document."""

    number: int                          # 1-based; HTML = 1
    text: str
    tables: list[list[list[str]]] = []   # rows x cells
    is_empty: bool = False


class Document(BaseModel):
    """One parsed input file with its metadata."""

    doc_id: str                          # sha1 of file bytes
    bid_id: str                          # folder name
    file_name: str
    doc_type: DocType
    addendum_number: int | None = None
    doc_date: str | None = None          # ISO
    title: str | None = None
    pages: list[Page]
    fields: dict[str, str] = {}          # HTML label/value pairs
    warnings: list[str] = []


class Chunk(BaseModel):
    """A retrievable unit of text with its context metadata."""

    chunk_id: str                        # f"{doc_id}:{page}:{seq}"
    bid_id: str
    file_name: str
    doc_type: DocType
    addendum_number: int | None
    page: int
    doc_date: str | None
    section: str | None
    kind: Literal["text", "table", "qa", "spec_list", "record"]
    header: str                          # "Bid1 | addendum 1 | file | p2 | Q31"
    text: str
    token_count: int


class Citation(BaseModel):
    """A pointer to the exact source text supporting a value."""

    file: str
    page: int
    chunk_id: str
    quote: str                           # exact supporting span, <= 300 chars


class SearchFilters(BaseModel):
    """Metadata filters applied to a search."""

    bid_id: str | None = None
    bid_ids: list[str] | None = None
    doc_types: list[DocType] | None = None
    addendum_number: int | None = None


class SearchHit(BaseModel):
    """One search result with its final score and per-retriever ranks."""

    chunk: Chunk
    score: float
    ranks: dict[str, int] = {}           # {"vector": 3, "bm25": 1, "rerank": 1}


# ---- agent-to-agent messages ----
class Task(BaseModel):
    """A unit of work the orchestrator hands to retrieval + extraction."""

    group: str                           # dates_logistics | commercial_legal | product_specs | qa
    fields: list[str] = []
    queries: list[str] = []
    filters: SearchFilters = SearchFilters()


class Plan(BaseModel):
    """The orchestrator's plan for a run."""

    mode: Literal["extract", "qa"]
    question_type: Literal["extract", "single", "comparison", "changes"] = "extract"
    tasks: list[Task]


class EvidenceRequest(BaseModel):
    """What an agent asks the Retrieval agent to find."""

    field_or_question: str
    queries: list[str]
    filters: SearchFilters
    top_k: int = 6


class EvidenceBundle(BaseModel):
    """The Retrieval agent's answer to an EvidenceRequest."""

    request: EvidenceRequest
    hits: list[SearchHit]
    expanded_queries: list[str]


class FieldExtraction(BaseModel):        # LLM output per field
    """Raw extraction of one field as returned by the LLM."""

    field: str
    value: str | list[str] | None
    evidence_ids: list[str]              # ["E2", "E5"] -> mapped to Citation in code
    quotes: list[str]
    status: Literal["ok", "not_found"]
    notes: str = ""


class FieldValue(BaseModel):
    """Final value of one field in the deliverable JSON."""

    value: str | list[str] | None
    sources: list[Citation] = []
    confidence: float = Field(ge=0, le=1)
    notes: str = ""
    status: Literal["ok", "not_found", "failed"] = "ok"


class AddendumChange(BaseModel):
    """One change an addendum made to a field."""

    field: str
    kind: Literal["override", "clarification", "addition"]
    old_value: str | None
    new_value: str
    addendum_number: int
    source: Citation


class ValidationResult(BaseModel):
    """Validator verdict for one field."""

    field: str
    passed: bool
    checks: dict[str, bool]              # has_citation, quote_in_chunk, supported, format_ok, consistent
    reason: str = ""


class BidRecord(BaseModel):              # deliverable JSON (outputs/<bid>.json)
    """The per-bid deliverable: exactly the 20 configured fields."""

    bid_id: str
    fields: dict[str, FieldValue]        # exactly the 20 field names
    addendum_changes: list[AddendumChange] = []
    validation: dict[str, int]           # {"passed", "failed", "not_found"}
    generated_at: str
    run_id: str

    @model_validator(mode="after")
    def _check_field_names(self) -> BidRecord:
        """Require exactly the field names listed in config/fields.yaml."""
        from rfp_intel.config import field_names  # local import avoids a cycle

        expected, got = set(field_names()), set(self.fields)
        if got != expected:
            raise ValueError(
                f"fields must match config/fields.yaml; "
                f"missing={sorted(expected - got)} unexpected={sorted(got - expected)}"
            )
        return self


class Answer(BaseModel):
    """A cited answer to a free-form question."""

    question: str
    answer: str
    citations: list[Citation]
    confidence: float
    bids: list[str]


class StepLog(BaseModel):                # one line of logs/trace_<run_id>.jsonl
    """Observability record for one graph step."""

    run_id: str
    step: int
    agent: str
    node: str
    started_at: str
    input_summary: str
    tool_calls: list[dict]
    output_summary: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int
    error: str | None = None


class RunStatus(BaseModel):
    """Progress of a background extraction run."""

    run_id: str
    bid_id: str
    status: Literal["running", "done", "failed"]
    steps: list[StepLog]


class Usage(BaseModel):
    """Token and cost usage of one or more LLM calls (BUILD_PLAN 6.3)."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        """Sum two usages."""
        return Usage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            cost_usd=self.cost_usd + other.cost_usd,
        )
