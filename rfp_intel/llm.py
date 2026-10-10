"""Provider-agnostic LLM wrapper (BUILD_PLAN 6.3). Every LLM call goes through here.

- `structured(prompt, model_cls, model, system)` -> (validated model, Usage)
- `text(prompt, model, system)` -> (str, Usage)

Provider comes from LLM_PROVIDER (openai | anthropic); models from
EXTRACT_MODEL / REASON_MODEL. Structured output uses the provider's
JSON-schema mode. Invalid output is retried `llm.max_json_retries` times with
the validation error appended; after that, and on timeouts or API errors,
`LLMError` is raised.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from rfp_intel.config import settings
from rfp_intel.logging_utils import record_llm_call
from rfp_intel.schemas import Usage

T = TypeVar("T", bound=BaseModel)

# JSON-schema keywords that strict structured-output modes reject; Pydantic
# still enforces them when the response is validated.
_UNSUPPORTED_KEYWORDS = {
    "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "format", "minItems", "maxItems",
}

# Models that rejected a `temperature` value; it is omitted for them afterwards.
_NO_TEMPERATURE: set[str] = set()


class LLMError(Exception):
    """An LLM call failed: timeout, API error, refusal or invalid output."""


@dataclass
class RawResponse:
    """What a provider returns before validation."""

    text: str
    tokens_in: int
    tokens_out: int


class Provider(Protocol):
    """Minimal interface each LLM provider implements."""

    def complete(
        self, prompt: str, system: str | None, model: str, schema: dict | None, schema_name: str
    ) -> RawResponse:
        """Run one completion; `schema` requests JSON output matching it."""
        ...


# ---------------------------------------------------------------- public API


def structured(
    prompt: str, model_cls: type[T], model: str, system: str | None = None
) -> tuple[T, Usage]:
    """Call the LLM and return a validated `model_cls` instance plus usage."""
    schema, is_strict = strict_json_schema(model_cls)
    system_text = system if is_strict else _with_schema_hint(system, schema)
    attempt_prompt, total = prompt, Usage()
    last_error = ""
    for _ in range(settings.llm.max_json_retries + 1):
        raw, usage = _call(attempt_prompt, system_text, model, schema if is_strict else None,
                           model_cls.__name__)
        total = total + usage
        try:
            return model_cls.model_validate_json(_strip_fences(raw)), total
        except ValidationError as exc:
            last_error = str(exc)[:2000]
            attempt_prompt = (
                f"{prompt}\n\nYour previous reply was not valid for the required schema:\n"
                f"{last_error}\nReply again with JSON that matches the schema exactly."
            )
    raise LLMError(f"invalid structured output for {model_cls.__name__}: {last_error}")


def text(prompt: str, model: str, system: str | None = None) -> tuple[str, Usage]:
    """Call the LLM for free text."""
    return _call(prompt, system, model, None, "text")


def strict_json_schema(model_cls: type[BaseModel]) -> tuple[dict, bool]:
    """JSON schema for strict structured output, and whether strict mode is possible.

    Strict mode needs every object to list all properties as required and to
    forbid extra keys. Free-form dicts (`dict[str, X]`) cannot be expressed
    that way, so such models fall back to non-strict JSON mode.
    """
    schema = copy.deepcopy(model_cls.model_json_schema())
    is_strict = _make_strict(schema)
    return schema, is_strict


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """USD cost from the `cost` table in settings.yaml (0 for unknown models)."""
    cost = settings.cost
    return (tokens_in / 1000) * cost.usd_per_1k_input.get(model, 0.0) + (
        tokens_out / 1000
    ) * cost.usd_per_1k_output.get(model, 0.0)


# ---------------------------------------------------------------- internals


def _call(
    prompt: str, system: str | None, model: str, schema: dict | None, schema_name: str
) -> tuple[str, Usage]:
    """One provider call with dev cache, usage accounting and trace recording."""
    if not model:
        raise LLMError("no model configured (set EXTRACT_MODEL / REASON_MODEL in .env)")
    cache_file = _cache_path(prompt, system, model, schema_name)
    if cache_file is not None and cache_file.exists():
        record_llm_call(model, Usage(), 0, schema=schema_name, cached=True)
        return json.loads(cache_file.read_text(encoding="utf-8"))["text"], Usage()

    t0 = time.perf_counter()
    raw = _provider().complete(prompt, system, model, schema, schema_name)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    usage = Usage(
        tokens_in=raw.tokens_in,
        tokens_out=raw.tokens_out,
        cost_usd=compute_cost(model, raw.tokens_in, raw.tokens_out),
    )
    record_llm_call(model, usage, latency_ms, schema=schema_name, cached=False)
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"text": raw.text}), encoding="utf-8")
    return raw.text, usage


def _cache_path(prompt: str, system: str | None, model: str, schema_name: str) -> Path | None:
    """Dev-cache file for this request, or None when LLM_DEV_CACHE is off."""
    if not settings.env.llm_dev_cache:
        return None
    key = hashlib.sha256(f"{model}\n{schema_name}\n{system or ''}\n{prompt}".encode()).hexdigest()
    return settings.path("storage_dir") / "llm_cache" / f"{key}.json"


def _provider() -> Provider:
    """The provider selected by LLM_PROVIDER."""
    name = settings.env.llm_provider
    api_key = settings.env.llm_api_key.get_secret_value()
    if not api_key:
        raise LLMError("LLM_API_KEY is not set")
    if name == "openai":
        return OpenAIProvider(api_key)
    if name == "anthropic":
        return AnthropicProvider(api_key)
    raise LLMError(f"unknown LLM_PROVIDER {name!r} (use openai or anthropic)")


def _make_strict(node: Any) -> bool:
    """Rewrite a schema in place for strict mode; False if it cannot be strict."""
    ok = True
    if isinstance(node, dict):
        for key in _UNSUPPORTED_KEYWORDS & node.keys():
            del node[key]
        if node.get("type") == "object" or "properties" in node:
            if "properties" not in node or isinstance(node.get("additionalProperties"), dict):
                ok = False  # dict / dict[str, X]: open-ended keys
            else:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
        for key, child in node.items():
            if key in {"properties", "$defs"} and isinstance(child, dict):
                ok = all([_make_strict(sub) for sub in child.values()]) and ok
            elif isinstance(child, (dict, list)):
                ok = _make_strict(child) and ok
    elif isinstance(node, list):
        ok = all([_make_strict(item) for item in node])
    return ok


def _with_schema_hint(system: str | None, schema: dict) -> str:
    """System prompt that asks for JSON matching `schema` (non-strict mode)."""
    hint = "Reply with only a JSON object matching this JSON schema:\n" + json.dumps(schema)
    return f"{system}\n\n{hint}" if system else hint


def _strip_fences(raw: str) -> str:
    """Remove ``` fences a model may wrap around JSON in non-strict mode."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _temperature_rejected(exc: Exception) -> bool:
    """True if an API error says the model does not accept `temperature`."""
    return getattr(exc, "param", None) == "temperature" or "temperature" in str(exc).lower()


# ---------------------------------------------------------------- providers


class OpenAIProvider:
    """OpenAI Chat Completions with strict JSON-schema response format."""

    def __init__(self, api_key: str) -> None:
        import openai

        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, timeout=settings.llm.timeout_s, max_retries=2)

    def complete(
        self, prompt: str, system: str | None, model: str, schema: dict | None, schema_name: str
    ) -> RawResponse:
        """Run one chat completion."""
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": settings.llm.max_tokens,
        }
        if schema is not None:
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        response = self._create_with_temperature_fallback(params)
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMError(f"model refused: {choice.message.refusal}")
        usage = response.usage
        return RawResponse(
            text=choice.message.content or "",
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
        )

    def _create_with_temperature_fallback(self, params: dict[str, Any]) -> Any:
        """Send with the configured temperature; drop it if the model rejects it."""
        model = params["model"]
        if model not in _NO_TEMPERATURE:
            try:
                return self._send({**params, "temperature": settings.llm.temperature})
            except self._openai.BadRequestError as exc:
                if not _temperature_rejected(exc):
                    raise LLMError(f"OpenAI bad request: {exc}") from exc
                _NO_TEMPERATURE.add(model)
        try:
            return self._send(params)
        except self._openai.BadRequestError as exc:
            raise LLMError(f"OpenAI bad request: {exc}") from exc

    def _send(self, params: dict[str, Any]) -> Any:
        """One API request with SDK errors mapped to LLMError (except 400s)."""
        try:
            return self._client.chat.completions.create(**params)
        except self._openai.APITimeoutError as exc:
            raise LLMError(f"OpenAI timeout after {settings.llm.timeout_s}s") from exc
        except self._openai.BadRequestError:
            raise
        except self._openai.APIError as exc:
            raise LLMError(f"OpenAI API error: {type(exc).__name__}: {exc}") from exc


class AnthropicProvider:
    """Anthropic Messages API with `output_config.format` JSON schema."""

    def __init__(self, api_key: str) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=settings.llm.timeout_s, max_retries=2
        )

    def complete(
        self, prompt: str, system: str | None, model: str, schema: dict | None, schema_name: str
    ) -> RawResponse:
        """Run one Messages API call."""
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": settings.llm.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            params["system"] = system
        if schema is not None:
            params["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        response = self._create_with_temperature_fallback(params)
        if response.stop_reason == "refusal":
            raise LLMError("model refused the request")
        text_out = "".join(block.text for block in response.content if block.type == "text")
        return RawResponse(
            text=text_out,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

    def _create_with_temperature_fallback(self, params: dict[str, Any]) -> Any:
        """Send with the configured temperature; drop it if the model rejects it."""
        model = params["model"]
        if model not in _NO_TEMPERATURE:
            try:
                return self._send({**params, "temperature": settings.llm.temperature})
            except self._anthropic.BadRequestError as exc:
                if not _temperature_rejected(exc):
                    raise LLMError(f"Anthropic bad request: {exc}") from exc
                _NO_TEMPERATURE.add(model)
        try:
            return self._send(params)
        except self._anthropic.BadRequestError as exc:
            raise LLMError(f"Anthropic bad request: {exc}") from exc

    def _send(self, params: dict[str, Any]) -> Any:
        """One API request with SDK errors mapped to LLMError (except 400s)."""
        try:
            return self._client.messages.create(**params)
        except self._anthropic.APITimeoutError as exc:
            raise LLMError(f"Anthropic timeout after {settings.llm.timeout_s}s") from exc
        except self._anthropic.BadRequestError:
            raise
        except self._anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {type(exc).__name__}: {exc}") from exc
