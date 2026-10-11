"""SearchEngine: the single entry point to indexing and hybrid search (BUILD_PLAN 6.2).

    engine = SearchEngine()
    engine.index_bid(Path("data/Bid1"))          # incremental via storage/manifest.json
    engine.search("due date", SearchFilters(bid_id="Bid1"), top_k=5, config="hybrid_rerank")

Search: parse filters from the query -> expand the query -> vector and BM25
retrieval per query variant -> RRF -> cross-encoder re-rank -> top_k hits.
`search_many` does the same for several queries with one fusion and one
re-rank pass (the Retrieval agent uses it for every evidence request).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Protocol

from rfp_intel.config import settings
from rfp_intel.ingestion.loader import SUPPORTED_SUFFIXES, load_bid_folder
from rfp_intel.schemas import Chunk, IndexStats, SearchFilters, SearchHit
from rfp_intel.search.bm25_store import BM25Store
from rfp_intel.search.chunker import chunk_document, embed_text
from rfp_intel.search.embedder import make_embedder
from rfp_intel.search.fusion import rrf
from rfp_intel.search.query import expand_query, parse_filters
from rfp_intel.search.reranker import Reranker
from rfp_intel.search.vector_store import VectorStore, chunk_key

logger = logging.getLogger(__name__)
_QUERY_CACHE_SIZE = 512          # memoised query embeddings (query text -> vector)


class EmbedderLike(Protocol):
    """What the engine needs from an embedder (lets tests use a fake)."""

    @property
    def dim(self) -> int: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class RerankerLike(Protocol):
    """What the engine needs from a re-ranker."""

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class SearchEngine:
    """Indexes bid folders and answers hybrid searches over them."""

    def __init__(self, storage_dir: Path | None = None, embedder: EmbedderLike | None = None,
                 reranker: RerankerLike | None = None) -> None:
        self.storage_dir = Path(storage_dir or settings.path("storage_dir"))
        self.embedder: EmbedderLike = embedder or make_embedder()
        self.reranker: RerankerLike = reranker or Reranker()
        self.bm25 = BM25Store(self.storage_dir / "bm25")
        self.manifest_path = self.storage_dir / "manifest.json"
        self._vectors: VectorStore | None = None
        self._query_cache: dict[str, list[float]] = {}

    @property
    def vectors(self) -> VectorStore:
        """The Qdrant store, opened on first use.

        The vector size is remembered in the manifest so that skipping an
        unchanged bid does not load the embedding model just to open the store.
        """
        if self._vectors is None:
            manifest = self._read_manifest()
            dim = manifest.get("_dim") or self.embedder.dim
            self._vectors = VectorStore(self.storage_dir / "qdrant", settings.vector_store.collection, dim)
            if manifest.get("_dim") != dim:
                manifest["_dim"] = dim
                self._write_manifest(manifest)
        return self._vectors

    def warm_up(self) -> None:
        """Load the embedding and re-ranking models now (first use otherwise costs ~30 s)."""
        self.embedder.embed_queries(["warm up"])
        self.reranker.score("warm up", ["warm up"])

    def close(self) -> None:
        """Release the vector store's file lock."""
        if self._vectors is not None:
            self._vectors.close()
            self._vectors = None

    # ---------------------------------------------------------------- indexing

    def known_bids(self) -> list[str]:
        """Bids present in the manifest."""
        return sorted(key for key in self._read_manifest() if not key.startswith("_"))

    def index_bid(self, folder: Path, force: bool = False) -> IndexStats:
        """Index a bid folder; unchanged bids are skipped, changed bids are rebuilt."""
        started = time.perf_counter()
        folder = Path(folder)
        bid_id = folder.name
        state = {"files": _file_hashes(folder), "config": _index_config_key()}
        manifest = self._read_manifest()
        if not force and manifest.get(bid_id) == state:
            return IndexStats(bid_id=bid_id, documents=len(state["files"]), chunks_added=0,
                              chunks_total=self.vectors.count(bid_id), skipped=True,
                              seconds=round(time.perf_counter() - started, 2))

        documents = load_bid_folder(folder)
        chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
        texts = [embed_text(chunk) for chunk in chunks]
        vectors = self.embedder.embed_documents(texts)
        self.vectors.delete_by_bid(bid_id)
        self.vectors.upsert(chunks, vectors)
        self.bm25.save(bid_id, chunks, texts)
        manifest[bid_id] = state
        self._write_manifest(manifest)
        return IndexStats(
            bid_id=bid_id,
            documents=len(documents),
            chunks_added=len(chunks),
            chunks_total=self.vectors.count(bid_id),
            warnings=[f"{d.file_name}: {w}" for d in documents for w in d.warnings],
            seconds=round(time.perf_counter() - started, 2),
        )

    # ---------------------------------------------------------------- search

    def search(self, query: str, filters: SearchFilters | None = None, top_k: int | None = None,
               config: str | None = None) -> list[SearchHit]:
        """Hybrid search. Explicit `filters` win over filters parsed from the query."""
        return self.search_many([query], filters, top_k=top_k, config=config)

    def search_many(self, queries: list[str], filters: SearchFilters | None = None,
                    top_k: int | None = None, config: str | None = None) -> list[SearchHit]:
        """Hybrid search for several queries about the same topic, fused and re-ranked once.

        Every query (and its synonym variants) contributes a vector list and a
        BM25 list to one RRF fusion; the cross-encoder then scores the top
        `rerank_top_n` fused candidates against the first query. This costs one
        batched query embedding and one re-rank pass instead of one per query.
        """
        cfg = settings.retrieval_for(config)
        queries = [q for q in queries if q and q.strip()]
        if not queries:
            return []
        known = self.known_bids()
        variants: list[tuple[str, SearchFilters]] = []
        rerank_query = ""
        for query in queries:
            parsed, cleaned = parse_filters(query, known)
            merged = merge_filters(parsed, filters)
            rerank_query = rerank_query or cleaned
            variants.extend((variant, merged) for variant in expand_query(cleaned))

        chunks: dict[str, Chunk] = {}
        ranks: dict[str, dict[str, int]] = {}
        lists: list[list[str]] = []
        vectors = self._query_vectors([text for text, _ in variants])
        for (variant, merged), vector in zip(variants, vectors, strict=True):
            hits = self.vectors.search(vector, merged, cfg.candidates_per_retriever)
            lists.append(_collect(hits, "vector", chunks, ranks))
            if cfg.use_bm25:
                hits = self.bm25.search(variant, merged, cfg.candidates_per_retriever)
                lists.append(_collect(hits, "bm25", chunks, ranks))

        fused = rrf(lists, cfg.rrf_k)
        if cfg.use_reranker and settings.reranker.enabled and fused:
            top_n = min(cfg.rerank_top_n, settings.reranker.max_passages or cfg.rerank_top_n)
            fused = self._rerank(rerank_query, fused[:top_n], chunks, ranks)
        limit = top_k or cfg.final_top_k
        return [SearchHit(chunk=chunks[cid], score=score, ranks=ranks[cid]) for cid, score in fused[:limit]]

    def _query_vectors(self, texts: list[str]) -> list[list[float]]:
        """Query embeddings, memoised per query text; unseen texts are embedded in one batch."""
        missing = list(dict.fromkeys(t for t in texts if t not in self._query_cache))
        if missing:
            for text, vector in zip(missing, self.embedder.embed_queries(missing), strict=True):
                self._query_cache[text] = vector
            while len(self._query_cache) > _QUERY_CACHE_SIZE:
                self._query_cache.pop(next(iter(self._query_cache)))
        return [self._query_cache[t] for t in texts]

    def _rerank(self, query: str, fused: list[tuple[str, float]], chunks: dict[str, Chunk],
                ranks: dict[str, dict[str, int]]) -> list[tuple[str, float]]:
        """Re-order fused candidates by cross-encoder score."""
        ids = [cid for cid, _ in fused]
        scores = self.reranker.score(query, [embed_text(chunks[cid]) for cid in ids])
        ordered = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
        for rank, (cid, _) in enumerate(ordered, start=1):
            ranks[cid]["rerank"] = rank
        return ordered

    # ---------------------------------------------------------------- manifest

    def _read_manifest(self) -> dict:
        """bid_id -> {"files": {name: sha1}, "config": key}."""
        if not self.manifest_path.exists():
            return {}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("manifest unreadable; all bids will be re-indexed")
            return {}

    def _write_manifest(self, manifest: dict) -> None:
        """Write the manifest atomically."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.manifest_path)


def merge_filters(parsed: SearchFilters, explicit: SearchFilters | None) -> SearchFilters:
    """Explicit filter fields override the ones parsed from the query text."""
    if explicit is None:
        return parsed
    data = parsed.model_dump()
    data.update(explicit.model_dump(exclude_none=True))
    if explicit.bid_id or explicit.bid_ids:
        data["bid_id"], data["bid_ids"] = explicit.bid_id, explicit.bid_ids
    return SearchFilters(**data)


def _collect(hits: list[tuple[Chunk, float]], retriever: str, chunks: dict[str, Chunk],
             ranks: dict[str, dict[str, int]]) -> list[str]:
    """Record chunks and each chunk's best rank for a retriever; return the ranked ids."""
    ids: list[str] = []
    for rank, (chunk, _) in enumerate(hits, start=1):
        key = chunk_key(chunk)
        chunks.setdefault(key, chunk)
        best = ranks.setdefault(key, {})
        best[retriever] = min(best.get(retriever, rank), rank)
        ids.append(key)
    return ids


def _file_hashes(folder: Path) -> dict[str, str]:
    """sha1 of every supported file in a folder."""
    return {
        p.name: hashlib.sha1(p.read_bytes()).hexdigest()
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    }


def _index_config_key() -> str:
    """Hash of the settings that change chunks or vectors (re-index when they change)."""
    relevant = {
        "chunking": settings.chunking.model_dump(),
        "embedding_model": settings.embedding.model,
        "collection": settings.vector_store.collection,
    }
    return hashlib.sha1(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:12]
