"""GraphState: the shared state object passed between graph nodes (BUILD_PLAN 6.4).

Parallel branches (Send) return partial states; the annotated reducers merge
their dict/list fields instead of overwriting them.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from rfp_intel.schemas import (
    AddendumChange,
    Answer,
    BidRecord,
    EvidenceBundle,
    FieldValue,
    Plan,
    StepLog,
    ValidationResult,
)


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Reducer: later values win per key."""
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict, total=False):
    """Everything the agents share during one run."""

    run_id: str
    mode: Literal["extract", "qa"]
    bid_ids: list[str]
    question: str | None
    plan: Plan
    evidence: Annotated[dict[str, EvidenceBundle], merge_dicts]
    drafts: Annotated[dict[str, FieldValue], merge_dicts]
    addendum_changes: list[AddendumChange]
    validation: dict[str, ValidationResult]
    retries: dict[str, int]
    to_retry: list[str]
    widened: bool                        # retry pass: wider retrieval for the fields in to_retry
    answer: Answer | None
    record: BidRecord | None
    errors: Annotated[list[str], operator.add]
    usage: Annotated[list[StepLog], operator.add]
