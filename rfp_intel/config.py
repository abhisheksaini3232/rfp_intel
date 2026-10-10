"""Settings loader: typed config from config/*.yaml plus secrets from .env.

Usage:
    from rfp_intel.config import settings
    settings.retrieval.rrf_k
    settings.retrieval_for("hybrid")   # a named retrieval config applied
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr, field_validator

from rfp_intel.schemas import DocType

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

load_dotenv(ROOT / ".env")


class PathsSettings(BaseModel):
    """Directories, relative to the project root unless absolute."""

    data_dir: str
    storage_dir: str
    outputs_dir: str
    logs_dir: str


class OcrSettings(BaseModel):
    """Optional OCR for scanned pages."""

    enabled: bool = False
    lang: str = "eng"


class IngestionSettings(BaseModel):
    """Parsing thresholds."""

    min_page_chars: int
    ocr: OcrSettings = OcrSettings()


class ChunkingSettings(BaseModel):
    """Chunk sizes in tokens."""

    max_tokens: int
    overlap_tokens: int
    min_tokens: int


class EmbeddingSettings(BaseModel):
    """Embedding model settings."""

    provider: str
    model: str
    batch_size: int
    query_prefix: str = ""


class VectorStoreSettings(BaseModel):
    """Vector store settings."""

    kind: str
    collection: str


class RetrievalSettings(BaseModel):
    """Search pipeline settings."""

    candidates_per_retriever: int
    rrf_k: int
    rerank_top_n: int
    final_top_k: int
    use_bm25: bool
    use_reranker: bool


class RetrievalOverride(BaseModel):
    """A named retrieval config: only the switches it changes."""

    use_bm25: bool | None = None
    use_reranker: bool | None = None


class RerankerSettings(BaseModel):
    """Cross-encoder model."""

    model: str


class LLMSettings(BaseModel):
    """LLM call settings."""

    temperature: float
    timeout_s: float
    max_json_retries: int
    max_tokens: int


class AgentSettings(BaseModel):
    """Multi-agent graph settings."""

    max_field_retries: int
    parallel_extractors: bool
    min_confidence: float
    evidence_top_k: int
    widened_top_k: int


class EvalSettings(BaseModel):
    """Evaluation settings."""

    recall_k: list[int]


class CostSettings(BaseModel):
    """USD per 1k tokens, keyed by model name."""

    usd_per_1k_input: dict[str, float] = {}
    usd_per_1k_output: dict[str, float] = {}


class CacheSettings(BaseModel):
    """Semantic answer cache (bonus)."""

    enabled: bool = False
    similarity_threshold: float = 0.95


class ApiSettings(BaseModel):
    """FastAPI settings."""

    cors_origins: list[str] = []


class EnvSettings(BaseModel):
    """Values that come from the environment / .env, never from YAML."""

    llm_provider: str = "openai"
    llm_api_key: SecretStr = SecretStr("")
    extract_model: str = ""
    reason_model: str = ""
    llm_dev_cache: bool = False


class Settings(BaseModel):
    """All settings: config/settings.yaml + environment."""

    paths: PathsSettings
    ingestion: IngestionSettings
    chunking: ChunkingSettings
    embedding: EmbeddingSettings
    vector_store: VectorStoreSettings
    retrieval: RetrievalSettings
    retrieval_configs: dict[str, RetrievalOverride]
    reranker: RerankerSettings
    llm: LLMSettings
    agents: AgentSettings
    precedence: list[DocType]
    eval: EvalSettings
    cost: CostSettings = CostSettings()
    cache: CacheSettings = CacheSettings()
    api: ApiSettings = ApiSettings()
    env: EnvSettings = EnvSettings()

    def path(self, name: str) -> Path:
        """Absolute path for a `paths` entry, e.g. path("logs_dir")."""
        return ROOT / getattr(self.paths, name)

    def retrieval_for(self, config_name: str | None) -> RetrievalSettings:
        """Retrieval settings with a named retrieval config applied."""
        if config_name is None:
            return self.retrieval
        if config_name not in self.retrieval_configs:
            known = ", ".join(sorted(self.retrieval_configs))
            raise ValueError(f"unknown retrieval config {config_name!r}; known: {known}")
        override = self.retrieval_configs[config_name].model_dump(exclude_none=True)
        return self.retrieval.model_copy(update=override)


class FieldSpec(BaseModel):
    """One of the 20 output fields from config/fields.yaml."""

    name: str
    group: str
    description: str
    search_hints: list[str] = []
    doc_types: list[DocType] | None = None

    @field_validator("search_hints", mode="before")
    @classmethod
    def _hints_as_text(cls, value: list | None) -> list[str]:
        """YAML reads bare numbers such as 1295 as int; hints are always text."""
        return [str(item) for item in value or []]


class IngestionPatterns(BaseModel):
    """Parsing patterns from config/ingestion.yaml."""

    html_labels: list[str]
    html_drop_selectors: list[str]
    filler_patterns: list[str]
    classifier: dict[str, str]


def _read_yaml(name: str) -> Any:
    """Parse one file from the config directory."""
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _env_settings() -> EnvSettings:
    """Read LLM provider settings from the environment."""
    return EnvSettings(
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        llm_api_key=SecretStr(os.getenv("LLM_API_KEY", "").strip()),
        extract_model=os.getenv("EXTRACT_MODEL", "").strip(),
        reason_model=os.getenv("REASON_MODEL", "").strip(),
        llm_dev_cache=os.getenv("LLM_DEV_CACHE", "0").strip() == "1",
    )


def load_settings() -> Settings:
    """Build Settings from config/settings.yaml and the environment."""
    return Settings(**_read_yaml("settings.yaml"), env=_env_settings())


@lru_cache(maxsize=1)
def load_fields() -> list[FieldSpec]:
    """The 20 output fields, in config order."""
    return [FieldSpec(**item) for item in _read_yaml("fields.yaml")]


def field_names() -> list[str]:
    """Names of the output fields, in config order."""
    return [spec.name for spec in load_fields()]


@lru_cache(maxsize=1)
def load_synonyms() -> dict[str, list[str]]:
    """Query-expansion synonyms from config/synonyms.yaml."""
    return {str(k): [str(v) for v in vals] for k, vals in _read_yaml("synonyms.yaml").items()}


@lru_cache(maxsize=1)
def load_ingestion() -> IngestionPatterns:
    """HTML labels, filler regexes and classifier patterns."""
    return IngestionPatterns(**_read_yaml("ingestion.yaml"))


settings = load_settings()
