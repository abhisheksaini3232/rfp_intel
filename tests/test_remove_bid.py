"""Removing a bid: search engine stores, service clean-up, DELETE /bids/{id} and the CLI."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import main
from rfp_intel import services
from rfp_intel.agents import runtime
from rfp_intel.api.server import app
from rfp_intel.config import settings
from rfp_intel.search.engine import SearchEngine
from tests.graph_fakes import FakeEngine, ScriptedLLM, install
from tests.search_fakes import FakeEmbedder, FakeReranker

BID = "BidT"


# ---------------------------------------------------------------- engine (real stores in tmp)

def test_engine_remove_bid_clears_both_stores_and_the_manifest(tmp_path, mini_bid):
    folder = tmp_path / "data" / "MiniBid"
    shutil.copytree(mini_bid, folder)
    engine = SearchEngine(storage_dir=tmp_path / "storage", embedder=FakeEmbedder(), reranker=FakeReranker())
    try:
        stats = engine.index_bid(folder)
        assert stats.chunks_total > 0 and engine.known_bids() == ["MiniBid"]
        assert engine.remove_bid("MiniBid") is True
        assert engine.known_bids() == [] and engine.vectors.count("MiniBid") == 0
        assert engine.bm25.bids() == []
        assert engine.remove_bid("MiniBid") is False          # already gone: no error
        again = engine.index_bid(folder)                      # can be indexed afresh
        assert not again.skipped and again.chunks_added == stats.chunks_total
    finally:
        engine.close()


# ---------------------------------------------------------------- service + API + CLI (fake engine)

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / BID).mkdir(parents=True)
    (data / BID / "rfp.pdf").write_bytes(b"%PDF-1.4 fake")
    outputs = tmp_path / "outputs"
    (outputs / "parsed" / BID).mkdir(parents=True)
    (outputs / "parsed" / BID / "rfp.pdf.json").write_text("{}", encoding="utf-8")
    for name in (f"{BID}.json", f"{BID}_summary.md", f"{BID}_go_no_go.json", f"{BID}_go_no_go.md",
                 "Other.json", f"{BID}2.json"):
        (outputs / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings.paths, "data_dir", str(data))
    monkeypatch.setattr(settings.paths, "outputs_dir", str(outputs))
    monkeypatch.setattr(settings.paths, "logs_dir", str(tmp_path / "logs"))
    runtime.set_engine(FakeEngine(bid=BID))
    monkeypatch.setattr(runtime, "close_engine", lambda: None)
    install(monkeypatch, ScriptedLLM())
    services._runs.clear()
    yield tmp_path
    runtime.set_engine(None)


def test_service_removes_index_outputs_and_folder_only_for_that_bid(workspace):
    result = services.remove_bid(BID)
    assert result.indexed and result.folder_removed and result.outputs_removed == 5
    outputs = workspace / "outputs"
    assert not (workspace / "data" / BID).exists()
    assert not (outputs / f"{BID}.json").exists() and not (outputs / "parsed" / BID).exists()
    assert (outputs / "Other.json").exists() and (outputs / f"{BID}2.json").exists()   # other bids untouched


def test_service_errors(workspace):
    with pytest.raises(ValueError):
        services.remove_bid("../etc")
    with pytest.raises(FileNotFoundError):
        services.remove_bid("Nope")
    services._register_run("run-1", "extract", BID)
    with pytest.raises(RuntimeError):
        services.remove_bid(BID)


def test_delete_endpoint(workspace):
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.delete("/bids/bad%20id").status_code == 400
        assert client.delete("/bids/Nope").status_code == 404
        response = client.delete(f"/bids/{BID}")
        assert response.status_code == 200
        assert response.json() == {"bid_id": BID, "indexed": True, "outputs_removed": 5, "folder_removed": True}
        assert client.delete(f"/bids/{BID}").status_code == 404


def test_cli_remove(workspace):
    runner = CliRunner(env={"COLUMNS": "200"})
    result = runner.invoke(main.app, ["remove", BID])
    assert result.exit_code == 0, result.output
    assert "removed" in result.output and "outputs_removed=5" in result.output
    assert runner.invoke(main.app, ["remove", BID]).exit_code == 2
