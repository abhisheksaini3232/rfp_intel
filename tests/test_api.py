"""FastAPI endpoints with a fake engine and a scripted LLM (no network, models or storage/)."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rfp_intel import services
from rfp_intel.agents import runtime
from rfp_intel.api.server import app
from rfp_intel.config import field_names, settings
from tests.graph_fakes import FakeEngine, ScriptedLLM, install

BID = "BidT"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Temp data/outputs/logs dirs, a fake engine with a BM25-like corpus and a scripted LLM."""
    data = tmp_path / "data"
    (data / BID).mkdir(parents=True)
    (data / BID / "rfp.pdf").write_bytes(b"%PDF-1.4 fake")
    (data / "Other").mkdir()
    (tmp_path / ".env").write_text("LLM_API_KEY=super-secret", encoding="utf-8")
    monkeypatch.setattr(settings.paths, "data_dir", str(data))
    monkeypatch.setattr(settings.paths, "outputs_dir", str(tmp_path / "outputs"))
    monkeypatch.setattr(settings.paths, "logs_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings.env, "extract_model", "fake-extract")
    monkeypatch.setattr(settings.env, "reason_model", "fake-reason")
    monkeypatch.setattr(services, "EVAL_RESULTS_DIR", tmp_path / "eval_results")
    engine = FakeEngine(bid=BID)
    engine.bm25 = SimpleNamespace(_load=lambda bid: (engine.chunks, []) if bid == BID else ([], []))
    runtime.set_engine(engine)
    install(monkeypatch, ScriptedLLM())
    services._runs.clear()
    yield tmp_path
    runtime.set_engine(None)


@pytest.fixture
def client(workspace):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _wait_for_run(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} still running after {timeout}s")


def test_health_and_lifespan_keep_injected_engine(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "indexed_bids": [BID]}
    assert isinstance(runtime.get_engine(), FakeEngine)


def test_bids_lists_folders_with_indexed_flags(client):
    rows = client.get("/bids").json()
    assert [(r["bid_id"], r["indexed"], r["doc_count"]) for r in rows] == [(BID, True, 1), ("Other", False, 0)]
    assert rows[0]["title"] is None and rows[0]["last_run"] is None and rows[0]["validation"] is None


def test_search_shape_and_bad_config(client):
    body = client.get("/search", params={"q": "due date", "bid_id": BID, "doc_type": "addendum", "top_k": 2}).json()
    assert set(body) == {"hits"} and body["hits"]
    hit = body["hits"][0]
    assert set(hit) == {"chunk", "score", "ranks"} and hit["chunk"]["doc_type"] == "addendum"

    bad = client.get("/search", params={"q": "x", "config": "nope"})
    assert bad.status_code == 400 and "unknown retrieval config" in bad.json()["error"]
    assert client.get("/search", params={"q": "x", "doc_type": "memo"}).status_code == 400


def test_ask_returns_cited_answer(client):
    body = client.post("/ask", json={"question": "When is the bid due?"}).json()
    assert set(body) == {"question", "answer", "citations", "confidence", "bids"}
    assert "July 9, 2024" in body["answer"] and body["citations"] and body["bids"] == [BID]
    assert body["citations"][0]["chunk_id"] == "a:1:0"


def test_extract_runs_in_background_then_record_has_20_fields(client, workspace):
    started = client.post("/extract", json={"bid_id": BID})
    assert started.status_code == 202
    run_id = started.json()["run_id"]

    final = _wait_for_run(client, run_id)
    assert final["status"] == "done" and final["bid_id"] == BID
    assert [s["node"] for s in final["steps"]][-1] == "report"
    assert all(set(s) >= {"agent", "node", "latency_ms"} for s in final["steps"])

    record = client.get(f"/bids/{BID}/record").json()
    assert set(record["fields"]) == set(field_names())
    assert record["fields"]["Due Date"]["value"] == "July 9, 2024 at 2:00 PM CST"

    rows = {r["bid_id"]: r for r in client.get("/bids").json()}
    assert rows[BID]["due_date_changed_by"] == 2 and rows[BID]["agency"] == "Example County"
    assert rows[BID]["last_run"] == record["generated_at"] and rows[BID]["validation"] == record["validation"]

    assert client.get(f"/bids/Other/record").status_code == 404
    assert client.post("/extract", json={"bid_id": "Missing"}).status_code == 404
    assert client.get("/runs/nope").status_code == 404


def test_second_concurrent_extract_is_409(client):
    assert services._extract_lock.acquire(timeout=10)
    try:
        resp = client.post("/extract", json={"bid_id": BID})
    finally:
        services._extract_lock.release()
    assert resp.status_code == 409 and resp.json() == {"error": "an extraction is already running", "run_id": None}


def test_409_names_the_running_bid_and_its_run_id(client):
    """While a run is registered, the 409 says which bid holds the lock and returns its run_id."""
    services._runs["active-1"] = {"bid_id": "Other", "status": "running", "error": None}
    assert services._extract_lock.acquire(timeout=10)
    try:
        resp = client.post("/extract", json={"bid_id": BID})
    finally:
        services._extract_lock.release()
    assert resp.status_code == 409
    assert resp.json() == {"error": "an extraction is already running for bid 'Other' (run active-1)",
                           "run_id": "active-1"}
    assert services.active_run().run_id == "active-1"


def test_list_runs_newest_first_with_status(client):
    assert client.get("/runs").json() == []
    started = client.post("/extract", json={"bid_id": BID}).json()["run_id"]
    _wait_for_run(client, started)
    services._runs["later"] = {"bid_id": "Other", "status": "running", "error": None}
    rows = client.get("/runs").json()
    assert [r["run_id"] for r in rows] == ["later", started]
    assert rows[0] == {"run_id": "later", "bid_id": "Other", "status": "running"}
    assert rows[1]["status"] == "done" and rows[1]["bid_id"] == BID
    assert services.active_run().run_id == "later"


def test_run_status_from_trace_only(client, workspace):
    from rfp_intel.logging_utils import write_step
    from rfp_intel.schemas import StepLog

    log = dict(run_id="old-run", step=1, agent="Report", node="report", started_at="t", input_summary="",
               tool_calls=[], output_summary="", latency_ms=1)
    write_step(StepLog(**log))
    assert client.get("/runs/old-run").json()["status"] == "done"
    write_step(StepLog(**{**log, "run_id": "bad-run", "node": "extract_x", "error": "boom"}))
    assert client.get("/runs/bad-run").json()["status"] == "failed"


@pytest.mark.parametrize("name", ["..%2F..%2F.env", "../../.env", "..%2F.env", "../.env", "%2E%2E/%2E%2E/.env"])
def test_files_rejects_path_traversal(client, name):
    resp = client.get(f"/files/{BID}/{name}")
    assert resp.status_code in (400, 404)
    assert "super-secret" not in resp.text
    assert set(resp.json()) == {"error", "run_id"}


def test_files_serves_bid_file_and_404_for_missing(client):
    resp = client.get(f"/files/{BID}/rfp.pdf")
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert client.get(f"/files/{BID}/nope.pdf").status_code == 404
    assert client.get("/files/bad%20id/rfp.pdf").status_code == 400


def test_upload_validation_and_success(client, workspace):
    exe = client.post("/bids", data={"bid_id": "NewBid"}, files=[("files", ("run.exe", b"MZ", "application/octet-stream"))])
    assert exe.status_code == 400 and "unsupported" in exe.json()["error"]
    bad_id = client.post("/bids", data={"bid_id": "bad id!"}, files=[("files", ("a.pdf", b"%PDF", "application/pdf"))])
    assert bad_id.status_code == 400
    sneaky = client.post("/bids", data={"bid_id": "NewBid"}, files=[("files", ("..\\x.pdf", b"%PDF", "application/pdf"))])
    assert sneaky.status_code == 400
    assert not (workspace / "data" / "NewBid").exists()

    ok = client.post("/bids", data={"bid_id": "NewBid"},
                     files=[("files", ("a.pdf", b"%PDF", "application/pdf")),
                            ("files", ("page.html", b"<html></html>", "text/html"))])
    assert ok.status_code == 200
    assert set(ok.json()) >= {"bid_id", "documents", "chunks_added", "chunks_total"} and ok.json()["bid_id"] == "NewBid"
    assert sorted(p.name for p in (workspace / "data" / "NewBid").iterdir()) == ["a.pdf", "page.html"]


def test_index_by_bid_id_or_path(client, workspace):
    assert client.post("/index", json={"folder": BID}).json()["bid_id"] == BID
    assert client.post("/index", json={"folder": str(workspace / "data" / BID), "force": True}).status_code == 200
    assert client.post("/index", json={"folder": "Missing"}).status_code == 404


def test_bid_detail_and_chunks(client, workspace):
    doc = {"doc_id": "d1", "bid_id": BID, "file_name": "rfp.pdf", "doc_type": "rfp", "warnings": ["w"],
           "pages": [{"number": 1, "text": "hi", "tables": [[["a"]]]}, {"number": 2, "text": "x"}]}
    parsed = workspace / "outputs" / "parsed" / BID
    parsed.mkdir(parents=True)
    (parsed / "rfp.pdf.json").write_text(json.dumps(doc), encoding="utf-8")

    detail = client.get(f"/bids/{BID}").json()
    assert detail["indexed"] is True and detail["chunks"] == 3
    assert detail["documents"] == [{"file_name": "rfp.pdf", "doc_type": "rfp", "addendum_number": None,
                                    "pages": 2, "tables": 1, "warnings": ["w"]}]
    assert client.get("/bids/Missing").status_code == 404

    assert client.get("/chunks/a:1:0").json()["file_name"] == "addendum_2.pdf"
    assert client.get("/chunks/unknown").status_code == 404


def test_eval_results(client, workspace):
    assert client.get("/eval/retrieval").status_code == 404
    results = workspace / "eval_results"
    results.mkdir()
    (results / "retrieval.json").write_text(json.dumps({"recall_at_5": 0.9}), encoding="utf-8")
    assert client.get("/eval/retrieval").json() == {"recall_at_5": 0.9}
    assert client.get("/eval/extraction").status_code == 404


def test_global_error_handler_shape(client, monkeypatch):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(services, "list_bids", boom)
    resp = client.get("/bids")
    assert resp.status_code == 500 and resp.json() == {"error": "RuntimeError: boom", "run_id": None}
    missing = client.post("/ask", json={})
    assert missing.status_code == 422 and set(missing.json()) == {"error", "run_id"}
