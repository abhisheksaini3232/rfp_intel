"""Local sentence-transformers embedder (normalized vectors; query prefix on queries only)."""

from __future__ import annotations

from functools import cached_property
from typing import Any, Callable

from rfp_intel.config import settings


def load_cached(factory: Callable[..., Any], model_name: str) -> Any:
    """Load a Hugging Face model from the local cache; download only if it is missing."""
    try:
        return factory(model_name, local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet (first run): download it
        return factory(model_name)


class Embedder:
    """Embeds chunk texts and queries with a local model (loaded on first use)."""

    def __init__(self, model_name: str | None = None, batch_size: int | None = None,
                 query_prefix: str | None = None) -> None:
        cfg = settings.embedding
        self.model_name = model_name or cfg.model
        self.batch_size = batch_size or cfg.batch_size
        self.query_prefix = cfg.query_prefix if query_prefix is None else query_prefix

    @cached_property
    def _model(self):  # noqa: ANN202 - SentenceTransformer, imported lazily (slow import)
        """The sentence-transformers model, from the local cache when available."""
        from sentence_transformers import SentenceTransformer

        return load_cached(SentenceTransformer, self.model_name)

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        model = self._model
        getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        return int(getter())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Normalized embeddings for chunk texts (no prefix)."""
        if not texts:
            return []
        vectors = self._model.encode(texts, batch_size=self.batch_size,
                                     normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Normalized embeddings for several queries in one model call (retrieval prefix added)."""
        if not texts:
            return []
        vectors = self._model.encode([self.query_prefix + t for t in texts], batch_size=self.batch_size,
                                     normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Normalized embedding for a query, with the retrieval prefix."""
        return self.embed_queries([text])[0]
