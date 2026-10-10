"""SearchEngine tests with fake models: filters, configs, ranks and citations."""

import shutil

import pymupdf
import pytest

from rfp_intel.schemas import DocType, SearchFilters
from rfp_intel.search.engine import SearchEngine
from tests.search_fakes import FakeEmbedder, FakeReranker


@pytest.fixture
def bids(tmp_path, mini_bid):
    """Two bids: a copy of mini_bid and a one-file bid with a spec sheet."""
    first = tmp_path / "data" / "MiniBid"
    shutil.copytree(mini_bid, first)
    second = tmp_path / "data" / "OtherBid"
    second.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate([
        "Product Specification Sheet for the docking station order",
        "Processor: Intel Core i7 with vPro, SKU 999-ZZZZ, sixteen gigabytes of memory",
        "Docking station WD99 with power adapter and two year warranty coverage",
    ]):
        page.insert_text((50, 60 + 20 * i), line)
    doc.save(second / "Product_Specs.pdf")
    return first, second


@pytest.fixture
def engine(tmp_path, bids):
    eng = SearchEngine(storage_dir=tmp_path / "storage", embedder=FakeEmbedder(), reranker=FakeReranker())
    for folder in bids:
        eng.index_bid(folder)
    yield eng
    eng.close()


def test_hits_carry_citation_fields(engine):
    hits = engine.search("Laptop Quantity", SearchFilters(bid_id="MiniBid"))
    assert hits
    top = hits[0].chunk
    assert top.file_name and top.page >= 1 and top.text and top.chunk_id
    assert any("Laptop 100" in h.chunk.text for h in hits)


def test_bid_filter(engine):
    hits = engine.search("docking station processor", SearchFilters(bid_id="OtherBid"), top_k=10)
    assert hits and {h.chunk.bid_id for h in hits} == {"OtherBid"}
    assert engine.search("anything", SearchFilters(bid_id="NoSuchBid")) == []


def test_doc_type_and_addendum_filters(engine):
    hits = engine.search("due date", SearchFilters(bid_id="MiniBid", doc_types=[DocType.ADDENDUM]), top_k=10)
    assert hits and all(h.chunk.doc_type is DocType.ADDENDUM for h in hits)
    hits = engine.search("due date", SearchFilters(addendum_number=1), top_k=10)
    assert hits and all(h.chunk.addendum_number == 1 for h in hits)


def test_filters_parsed_from_query(engine):
    hits = engine.search("only search OtherBid specs processor", top_k=10)
    assert hits and all(h.chunk.bid_id == "OtherBid" and h.chunk.doc_type is DocType.SPECS for h in hits)


def test_configs_fill_expected_ranks(engine):
    vector = engine.search("Laptop", SearchFilters(bid_id="MiniBid"), config="vector")
    assert all(set(h.ranks) == {"vector"} for h in vector)
    hybrid = engine.search("Laptop", SearchFilters(bid_id="MiniBid"), config="hybrid")
    assert any("bm25" in h.ranks for h in hybrid) and all("rerank" not in h.ranks for h in hybrid)
    reranked = engine.search("Laptop", SearchFilters(bid_id="MiniBid"), config="hybrid_rerank")
    assert [h.ranks["rerank"] for h in reranked] == list(range(1, len(reranked) + 1))


def test_top_k_and_unknown_config(engine):
    assert len(engine.search("the", top_k=2)) <= 2
    with pytest.raises(ValueError):
        engine.search("x", config="nope")


def test_search_on_empty_index_returns_nothing(tmp_path):
    eng = SearchEngine(storage_dir=tmp_path / "empty", embedder=FakeEmbedder(), reranker=FakeReranker())
    try:
        assert eng.search("due date") == []
    finally:
        eng.close()
