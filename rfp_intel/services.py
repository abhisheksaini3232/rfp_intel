"""Functions shared by the CLI and the API (Phase 7a, BUILD_PLAN 6.5).

index_bid, search, extract, ask, list_bids, get_record, run_status plus the
helpers the API needs (bid detail, chunk lookup, background extraction,
uploads, safe file paths, eval results). Every function returns a Pydantic
model from rfp_intel.schemas or a plain Python value; the search engine is
always the shared one from rfp_intel.agents.runtime.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Literal

from rfp_intel.agents.graph import run_extraction, run_question
from rfp_intel.agents.runtime import get_engine
from rfp_intel.config import ROOT, settings
from rfp_intel.ingestion.loader import SUPPORTED_SUFFIXES, load_bid_folder
from rfp_intel.logging_utils import new_run_id, read_trace
from rfp_intel.schemas import (
    Answer,
    BidDetail,
    BidRecord,
    BidSummary,
    Chunk,
    DocType,
    Document,
    DocumentInfo,
    IndexStats,
    RunStatus,
    SearchFilters,
    SearchHit,
)

BID_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
EVAL_RESULTS_DIR = ROOT / "eval" / "results"
_TERMINAL_NODES = {"report", "validate_answer"}

# Background extraction registry: run_id -> {"bid_id", "status", "error"}.
_runs: dict[str, dict[str, str | None]] = {}
_runs_lock = threading.Lock()
# Only one extraction at a time (single Qdrant client, CPU-bound embedding).
_extract_lock = threading.Lock()


# ---------------------------------------------------------------- paths

def bid_folder(bid_id: str) -> Path:
    """Folder of a bid under data_dir."""
    return settings.path("data_dir") / bid_id


def record_path(bid_id: str) -> Path:
    """Path of the saved deliverable outputs/<bid>.json."""
    return settings.path("outputs_dir") / f"{bid_id}.json"


def safe_file_path(bid_id: str, file_name: str) -> Path:
    """Resolve data_dir/bid_id/file_name; raise ValueError if it escapes the bid folder."""
    if not BID_ID_PATTERN.match(bid_id):
        raise ValueError(f"invalid bid id {bid_id!r}")
    base = bid_folder(bid_id).resolve()
    candidate = (base / file_name).resolve()
    if candidate == base or base not in candidate.parents:
        raise ValueError("file path escapes the bid folder")
    return candidate


# ---------------------------------------------------------------- index / search

def index_bid(folder: Path, force: bool = False) -> IndexStats:
    """Index one bid folder with the shared engine."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"bid folder not found: {folder}")
    return get_engine().index_bid(folder, force=force)


def search(query: str, bid_id: str | None = None, doc_type: str | None = None,
           addendum: int | None = None, top_k: int | None = None,
           config: str | None = None) -> list[SearchHit]:
    """Hybrid search with optional filters; ValueError for a bad doc_type or config."""
    settings.retrieval_for(config)  # raises ValueError for an unknown named config
    doc_types = [DocType(doc_type)] if doc_type else None  # ValueError for unknown types
    filters = SearchFilters(bid_id=bid_id or None, doc_types=doc_types, addendum_number=addendum)
    return get_engine().search(query, filters=filters, top_k=top_k, config=config)


# ---------------------------------------------------------------- extraction / Q&A

def extract(bid_id: str, run_id: str | None = None) -> BidRecord:
    """Index the bid folder, run the extraction graph and return the BidRecord."""
    folder = bid_folder(bid_id)
    if not folder.is_dir():
        raise FileNotFoundError(f"bid folder not found: {folder}")
    index_bid(folder)
    state = run_extraction(bid_id, run_id=run_id)
    record = state.get("record")
    if record is None:
        errors = "; ".join(state.get("errors", [])) or "no record produced"
        raise RuntimeError(f"extraction failed: {errors}")
    return record


def ask(question: str, bid_ids: list[str] | None = None) -> Answer:
    """Answer a free-form question over the given bids (default: every indexed bid)."""
    bids = list(bid_ids) if bid_ids else list(get_engine().known_bids())
    state = run_question(question, bids)
    answer = state.get("answer")
    if answer is None:
        return Answer(question=question, answer="Not found in documents", citations=[],
                      confidence=0.0, bids=bids)
    return answer


def start_extraction(bid_id: str) -> str:
    """Start `extract` in a daemon thread; return its run_id.

    Raises FileNotFoundError for an unknown bid and RuntimeError when another
    extraction is still running.
    """
    if not bid_folder(bid_id).is_dir():
        raise FileNotFoundError(f"bid folder not found: {bid_folder(bid_id)}")
    if not _extract_lock.acquire(blocking=False):
        raise RuntimeError("an extraction is already running")
    run_id = new_run_id()
    with _runs_lock:
        _runs[run_id] = {"bid_id": bid_id, "status": "running", "error": None}

    def worker() -> None:
        try:
            extract(bid_id, run_id=run_id)
            _set_run(run_id, "done")
        except Exception as exc:  # noqa: BLE001 - a failed run is reported, never raised
            _set_run(run_id, "failed", f"{type(exc).__name__}: {exc}")
        finally:
            _extract_lock.release()

    threading.Thread(target=worker, name=f"extract-{run_id}", daemon=True).start()
    return run_id


def _set_run(run_id: str, status: str, error: str | None = None) -> None:
    """Update the registry entry of a background run."""
    with _runs_lock:
        entry = _runs.setdefault(run_id, {"bid_id": "", "status": status, "error": None})
        entry["status"], entry["error"] = status, error


def run_status(run_id: str) -> RunStatus:
    """Progress of a run: registry status when known, else inferred from its trace."""
    steps = read_trace(run_id)
    with _runs_lock:
        entry = dict(_runs.get(run_id, {}))
    if entry:
        return RunStatus(run_id=run_id, bid_id=str(entry["bid_id"]), status=entry["status"], steps=steps)
    if not steps:
        raise KeyError(run_id)
    status = "done" if steps[-1].node in _TERMINAL_NODES and steps[-1].error is None else "failed"
    return RunStatus(run_id=run_id, bid_id=_bid_of_run(run_id), status=status, steps=steps)


def _bid_of_run(run_id: str) -> str:
    """Bid whose saved record came from this run (empty when unknown)."""
    out_dir = settings.path("outputs_dir")
    if not out_dir.is_dir():
        return ""
    for path in sorted(out_dir.glob("*.json")):
        record = _load_record(path)
        if record is not None and record.run_id == run_id:
            return record.bid_id
    return ""


# ---------------------------------------------------------------- bids and records

def _load_record(path: Path) -> BidRecord | None:
    """Parse a saved BidRecord; None when missing or malformed."""
    if not path.is_file():
        return None
    try:
        return BidRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def get_record(bid_id: str) -> BidRecord | None:
    """The latest saved BidRecord of a bid (outputs/<bid>.json), or None."""
    return _load_record(record_path(bid_id))


def _value_text(record: BidRecord, field: str) -> str | None:
    """A field's value as text (lists joined with '; ')."""
    item = record.fields.get(field)
    if item is None or item.value is None:
        return None
    return "; ".join(item.value) if isinstance(item.value, list) else str(item.value)


def _due_date_changed_by(record: BidRecord) -> int | None:
    """Addendum number of the latest override of "Due Date", if any."""
    overrides = [c for c in record.addendum_changes if c.field == "Due Date" and c.kind == "override"]
    return overrides[-1].addendum_number if overrides else None


def _input_files(folder: Path) -> list[Path]:
    """Supported input files of a bid folder."""
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)


def list_bids() -> list[BidSummary]:
    """One summary per folder under data_dir, enriched from the saved record."""
    data_dir = settings.path("data_dir")
    if not data_dir.is_dir():
        return []
    indexed = set(get_engine().known_bids())
    summaries: list[BidSummary] = []
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        record = get_record(folder.name)
        summaries.append(BidSummary(
            bid_id=folder.name,
            title=_value_text(record, "Title") if record else None,
            agency=_value_text(record, "company_name") if record else None,
            due_date=_value_text(record, "Due Date") if record else None,
            due_date_changed_by=_due_date_changed_by(record) if record else None,
            doc_count=len(_input_files(folder)),
            indexed=folder.name in indexed,
            last_run=record.generated_at if record else None,
            validation=dict(record.validation) if record else None,
        ))
    return summaries


def _parsed_documents(bid_id: str) -> list[Document] | None:
    """Documents from outputs/parsed/<bid>/*.json when every file parses, else None."""
    parsed_dir = settings.path("outputs_dir") / "parsed" / bid_id
    paths = sorted(parsed_dir.glob("*.json")) if parsed_dir.is_dir() else []
    if not paths:
        return None
    try:
        return [Document.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]
    except (ValueError, OSError):
        return None


def _bid_chunks(bid_id: str) -> list[Chunk]:
    """Indexed chunks of a bid from the engine's BM25 corpus (empty when not indexed)."""
    store = getattr(get_engine(), "bm25", None)
    if store is None:
        return []
    chunks, _tokens = store._load(bid_id)  # noqa: SLF001 - corpus access by id
    return list(chunks)


def get_bid_detail(bid_id: str) -> BidDetail:
    """Documents of a bid (type, pages, tables, warnings) plus index state."""
    folder = bid_folder(bid_id)
    if not folder.is_dir():
        raise FileNotFoundError(f"bid folder not found: {folder}")
    documents = _parsed_documents(bid_id) or load_bid_folder(folder)
    infos = [DocumentInfo(
        file_name=doc.file_name, doc_type=doc.doc_type, addendum_number=doc.addendum_number,
        pages=len(doc.pages), tables=sum(len(page.tables) for page in doc.pages),
        warnings=list(doc.warnings),
    ) for doc in documents]
    indexed = bid_id in set(get_engine().known_bids())
    return BidDetail(bid_id=bid_id, documents=infos, indexed=indexed,
                     chunks=len(_bid_chunks(bid_id)) if indexed else 0)


def get_chunk(chunk_id: str) -> Chunk | None:
    """Look a chunk up by id across every indexed bid."""
    for bid_id in get_engine().known_bids():
        for chunk in _bid_chunks(bid_id):
            if chunk.chunk_id == chunk_id:
                return chunk
    return None


# ---------------------------------------------------------------- eval and uploads

def eval_results(kind: Literal["retrieval", "extraction"]) -> dict | None:
    """Latest eval/results/<kind>.json, or None when it has not been written."""
    if kind not in ("retrieval", "extraction"):
        raise ValueError(f"unknown eval kind {kind!r}")
    path = EVAL_RESULTS_DIR / f"{kind}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_upload(bid_id: str, files: list[tuple[str, bytes]]) -> Path:
    """Write uploaded (name, bytes) pairs into data_dir/bid_id; ValueError on bad input."""
    if not BID_ID_PATTERN.match(bid_id or ""):
        raise ValueError("bid_id must match ^[A-Za-z0-9_-]{1,64}$")
    if not files:
        raise ValueError("no files uploaded")
    for name, _content in files:
        if not name or "/" in name or "\\" in name or name in (".", "..") or "\x00" in name:
            raise ValueError(f"invalid file name {name!r}")
        if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported file type {name!r}: only .pdf/.html/.htm are accepted")
    folder = bid_folder(bid_id)
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (folder / name).write_bytes(content)
    return folder
