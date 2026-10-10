"""Retrieval agent node: the ONLY caller of the search engine.

Extraction: for every field of the task, an EvidenceRequest built from the
field description and search hints (plus the field's doc_types), searched
with the bid filter. A second, addendum-only request per field feeds the
Addendum Reconciler. A widened retry uses more query variants, a larger
top_k and no doc-type filter.
Q&A: the plan's queries, searched per bid in scope.

Evidence keys: "<field>" for extraction, "<field>::addendum" for
reconciliation, "qa::<bid>" for questions. An empty result is a bundle with
no hits, never an error.
"""

from __future__ import annotations

import re

from rfp_intel.agents.runtime import get_engine
from rfp_intel.config import FieldSpec, load_fields, settings
from rfp_intel.logging_utils import log_step, record_tool_call
from rfp_intel.schemas import (
    BidRecord,
    DocType,
    EvidenceBundle,
    EvidenceRequest,
    SearchFilters,
    SearchHit,
    Task,
)
from rfp_intel.search.query import expand_query

ADDENDUM_SUFFIX = "::addendum"
QA_PREFIX = "qa::"
ADDENDUM_TOP_K = 4
MAX_CHANGE_QUERIES = 6
MAX_QA_EVIDENCE = 20
_ADDENDUM_WORD = re.compile(r"\baddend(?:um|a)\b|\bchange[sd]?\b|\brevis", re.IGNORECASE)
MAX_QUERIES = 2                 # each search = embed + vector + BM25 + cross-encoder (~3-5 s on CPU)
MAX_WIDENED_QUERIES = 5
MAX_ADDENDUM_QUERIES = 1
MAX_HINT_WORDS = 12


def evidence_key(field: str, addendum: bool = False) -> str:
    """Evidence dict key for a field (or its addendum evidence)."""
    return f"{field}{ADDENDUM_SUFFIX}" if addendum else field


def field_queries(spec: FieldSpec, widened: bool = False) -> list[str]:
    """Search queries for a field: name + description, then its search hints.

    Normal: the field name with the first hints, and a short description
    query. Widened: every hint as its own query plus synonym expansions.
    """
    hints = list(spec.search_hints)
    primary = f"{spec.name} {' '.join(hints[:4])}".strip()
    description = " ".join(spec.description.split()[:MAX_HINT_WORDS])
    queries = [primary, description]
    if widened:
        queries += hints
        queries = [v for q in queries for v in expand_query(q)]
    limit = MAX_WIDENED_QUERIES if widened else MAX_QUERIES
    return _dedupe(q for q in queries if q.strip())[:limit]


def build_requests(task: Task, widened: bool, only_fields: list[str] | None) -> list[EvidenceRequest]:
    """EvidenceRequests for a task: Q&A queries, or one per field (plus an addendum one)."""
    cfg = settings.agents
    if task.group == "qa":
        top_k = cfg.widened_top_k if widened else cfg.evidence_top_k
        requests = []
        for bid in _bids(task.filters):
            filters = task.filters.model_copy(update={"bid_id": bid, "bid_ids": None})
            extra = change_log_queries(bid, task.queries)
            queries = list(task.queries) + extra
            # keep room for both sides of every change (merged hits are capped at top_k)
            keep = min(MAX_QA_EVIDENCE, top_k + 2 * len(extra))
            requests.append(EvidenceRequest(field_or_question=f"{QA_PREFIX}{bid}", queries=queries,
                                            filters=filters, top_k=keep))
        return requests
    specs = {f.name: f for f in load_fields()}
    requests: list[EvidenceRequest] = []
    for name in task.fields:
        if only_fields is not None and name not in only_fields:
            continue
        spec = specs.get(name)
        if spec is None:
            continue
        doc_types = None if widened else spec.doc_types
        filters = task.filters.model_copy(update={"doc_types": doc_types})
        requests.append(EvidenceRequest(field_or_question=name, queries=field_queries(spec, widened),
                                        filters=filters, top_k=cfg.widened_top_k if widened else cfg.evidence_top_k))
        addendum_filters = task.filters.model_copy(update={"doc_types": [DocType.ADDENDUM]})
        requests.append(EvidenceRequest(field_or_question=evidence_key(name, addendum=True),
                                        queries=field_queries(spec)[:MAX_ADDENDUM_QUERIES], filters=addendum_filters,
                                        top_k=ADDENDUM_TOP_K))
    return requests


def change_log_queries(bid_id: str, queries: list[str]) -> list[str]:
    """Extra queries for change questions, derived from the bid's saved change log.

    When a question mentions an addendum, each recorded change contributes a
    query for its old value (finds the original passage) and its new value
    (finds the addendum passage), so both sides of a change are retrievable.
    """
    if not any(_ADDENDUM_WORD.search(q) for q in queries):
        return []
    path = settings.path("outputs_dir") / f"{bid_id}.json"
    if not path.exists():
        return []
    try:
        record = BidRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    extra: list[str] = []
    for change in record.addendum_changes[:MAX_CHANGE_QUERIES]:
        if change.old_value:
            extra.append(f"{change.field} {change.old_value[:80]}")
        extra.append(f"addendum {change.addendum_number} {change.field} {change.new_value[:80]}")
    return _dedupe(extra)


def run_request(request: EvidenceRequest) -> EvidenceBundle:
    """Search every query of a request and merge the hits (best rank first, no duplicates)."""
    engine = get_engine()
    merged: dict[str, SearchHit] = {}
    expanded: list[str] = []
    for query in request.queries:
        expanded.extend(expand_query(query))
        try:
            hits = engine.search(query, request.filters, top_k=request.top_k, config="hybrid_rerank")
        except Exception as exc:  # noqa: BLE001 - a failing query yields no hits, not a crash
            record_tool_call("search", query=query, error=f"{type(exc).__name__}: {exc}")
            continue
        record_tool_call("search", query=query, filters=request.filters.model_dump(exclude_none=True),
                         top_k=request.top_k, hits=len(hits))
        for hit in hits:
            key = f"{hit.chunk.bid_id}/{hit.chunk.chunk_id}"
            if key not in merged or hit.score > merged[key].score:
                merged[key] = hit
    hits = sorted(merged.values(), key=lambda h: h.score, reverse=True)[:request.top_k]
    return EvidenceBundle(request=request, hits=hits, expanded_queries=_dedupe(expanded))


@log_step(agent="Retrieval", node="retrieve")
def retrieve(state: dict) -> dict:
    """Fill `evidence` for the task in the state (Send payload) or the plan's first task."""
    task: Task | None = state.get("task") or (state["plan"].tasks[0] if state.get("plan") else None)
    if task is None:
        return {"evidence": {}}
    widened = bool(state.get("widened"))
    only = list(state.get("to_retry") or []) if widened and task.group != "qa" else None
    evidence = {}
    for request in build_requests(task, widened, only):
        evidence[request.field_or_question] = run_request(request)
    return {"evidence": evidence}


def _bids(filters: SearchFilters) -> list[str]:
    """Bids a request covers: explicit ids, else every indexed bid."""
    if filters.bid_ids:
        return list(filters.bid_ids)
    if filters.bid_id:
        return [filters.bid_id]
    return get_engine().known_bids()


def _dedupe(items) -> list[str]:
    """Unique items, first occurrence wins."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
