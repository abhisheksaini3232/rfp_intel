"""Deterministic stand-ins for the embedding and re-ranking models (no downloads, fast)."""

import hashlib
import math

from rfp_intel.search.bm25_store import tokenize

FAKE_DIM = 64


def _bucket(token: str) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % FAKE_DIM


class FakeEmbedder:
    """Hashed bag-of-words vectors, L2-normalized."""

    dim = FAKE_DIM

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * FAKE_DIM
        for token in tokenize(text):
            vec[_bucket(token)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeReranker:
    """Score = number of distinct query tokens found in the passage."""

    def score(self, query: str, passages: list[str]) -> list[float]:
        wanted = set(tokenize(query))
        return [float(len(wanted & set(tokenize(p)))) for p in passages]
