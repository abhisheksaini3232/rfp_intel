"""Extraction and Q&A graphs with a fake engine and a scripted LLM."""

import json

import pytest

from rfp_intel.agents import runtime
from rfp_intel.agents.graph import run_extraction, run_question
from rfp_intel.config import field_names, settings
from rfp_intel.logging_utils import read_trace
from rfp_intel.schemas import BidRecord
from tests.graph_fakes import FakeEngine, ScriptedLLM, install


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "data" / "BidT").mkdir(parents=True)
    monkeypatch.setattr(settings.paths, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(settings.paths, "outputs_dir", str(tmp_path / "outputs"))
    monkeypatch.setattr(settings.paths, "logs_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings.env, "extract_model", "fake-extract")
    monkeypatch.setattr(settings.env, "reason_model", "fake-reason")
    yield tmp_path
    runtime.set_engine(None)


def _steps(run_id):
    return [(s.node, s.started_at, s.agent) for s in read_trace(run_id)]


def test_extraction_graph_end_to_end(workspace, monkeypatch):
    engine = FakeEngine()
    runtime.set_engine(engine)
    install(monkeypatch, ScriptedLLM())
    state = run_extraction("BidT", run_id="t-e2e")
    record: BidRecord = state["record"]

    assert set(record.fields) == set(field_names())
    due = record.fields["Due Date"]
    assert due.value == "July 9, 2024 at 2:00 PM CST" and due.status == "ok"
    assert due.sources[0].file == "addendum_2.pdf" and "July 9, 2024" in due.sources[0].quote
    assert "originally June 27, 2024" in due.notes
    assert [c.kind for c in record.addendum_changes] == ["override"]
    assert record.fields["Bid Bond Requirement"].status == "not_found"
    assert record.fields["Bid Bond Requirement"].notes == "Not found in documents"
    assert all(v.sources for v in record.fields.values() if v.value is not None)
    assert record.validation["passed"] + record.validation["failed"] + record.validation["not_found"] == 20
    assert state["errors"] == []

    saved = json.loads((workspace / "outputs" / "BidT.json").read_text(encoding="utf-8"))
    assert saved["bid_id"] == "BidT" and (workspace / "outputs" / "BidT_summary.md").exists()

    nodes = [n for n, _, _ in _steps("t-e2e")]
    assert nodes[:2] == ["ingest", "orchestrate"] and nodes[-1] == "report"
    extract_steps = [s for s in read_trace("t-e2e") if s.node.startswith("extract_")]
    assert len(extract_steps) == 3
    for step in extract_steps:
        earlier = [r for r in read_trace("t-e2e") if r.node == "retrieve" and r.started_at <= step.started_at]
        assert earlier, "retrieve must run before every extraction"
    assert any(s.node == "retrieve" and s.tool_calls and s.tool_calls[0]["kind"] == "search" for s in read_trace("t-e2e"))
    assert all(s.node != "retrieve" or "search" in {c["kind"] for c in s.tool_calls} for s in read_trace("t-e2e"))


def test_validator_retry_path(workspace, monkeypatch):
    runtime.set_engine(FakeEngine())
    bad = ("sometime soon", "due June 27, 2024 at 2:00 PM CST")      # fails format_ok once
    install(monkeypatch, ScriptedLLM(overrides={"Pre Bid Meeting": [bad]}))
    state = run_extraction("BidT", run_id="t-retry")
    assert state["retries"].get("Pre Bid Meeting") == 1
    nodes = [n for n, _, _ in _steps("t-retry")]
    assert nodes.count("validate") == 2 and nodes.count("retrieve") == 4
    assert nodes.count("extract_dates_logistics") == 2 and nodes.count("extract_product_specs") == 1
    retry_step = [s for s in read_trace("t-retry") if s.node == "retrieve"][-1]
    assert retry_step.tool_calls[0]["top_k"] == settings.agents.widened_top_k
    assert state["record"].fields["Pre Bid Meeting"].status == "not_found"
    assert state["validation"]["Pre Bid Meeting"].passed


def test_retries_exhausted_marks_field_failed(workspace, monkeypatch):
    runtime.set_engine(FakeEngine())
    bad = [("sometime soon", "due June 27, 2024 at 2:00 PM CST")] * 5
    install(monkeypatch, ScriptedLLM(overrides={"Pre Bid Meeting": bad}))
    state = run_extraction("BidT", run_id="t-exhausted")
    delivery = state["record"].fields["Pre Bid Meeting"]
    assert state["retries"]["Pre Bid Meeting"] == settings.agents.max_field_retries
    assert delivery.status == "failed" and delivery.confidence <= 0.2 and "format_ok" in delivery.notes
    assert state["record"].validation["failed"] == 1


def test_qa_graph_answers_with_citations(workspace, monkeypatch):
    runtime.set_engine(FakeEngine())
    install(monkeypatch, ScriptedLLM())
    state = run_question("What is the due date?", ["BidT"], run_id="t-qa")
    ans = state["answer"]
    assert "July 9, 2024" in ans.answer and ans.citations and ans.citations[0].file == "addendum_2.pdf"
    assert ans.bids == ["BidT"] and ans.confidence >= 0.5
    assert [n for n, _, _ in _steps("t-qa")] == ["orchestrate", "retrieve", "answer", "validate_answer"]


def test_qa_graph_not_found_without_evidence(workspace, monkeypatch):
    runtime.set_engine(FakeEngine(empty=True))
    scripted = ScriptedLLM()
    install(monkeypatch, scripted)
    state = run_question("Is a bid bond required?", ["BidT"], run_id="t-qa-empty")
    assert state["answer"].answer == "Not found in documents" and state["answer"].citations == []
    assert "AnswerDraft" not in scripted.calls
