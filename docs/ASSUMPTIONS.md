# Assumptions and decisions not covered by BUILD_PLAN.md

Each entry: decision, reason, phase it was made in.

## Phase 0

1. **Repository root.** The plan's layout uses `rfp-intel/` as the root; this
   repository's root folder (`task_job/`) plays that role.
2. **Input locations.** The bid folders arrived under `docs/data/` and were
   moved to `data/Bid1` and `data/Bid2`. The brief was renamed from
   `Assignment-AI Engineer.pdf` to `Assignment-AI_Engineer.pdf` to match CLAUDE.md.
3. **Python 3.12.** The plan names Python 3.11; the machine has 3.12.10, which
   satisfies the brief's "Python 3.10+" (T1). All pinned packages support 3.12.
4. **Windows venv activation.** CLAUDE.md shows `source .venv/bin/activate`;
   on Windows it is `.venv\Scripts\activate` (PowerShell/cmd) or
   `source .venv/Scripts/activate` (Git Bash). The README will list both.
5. **LLM provider and models.** `LLM_PROVIDER=openai`,
   `EXTRACT_MODEL=gpt-6-luna` (high-volume extraction, low cost),
   `REASON_MODEL=gpt-6-sol` (validation, reconciliation, Q&A, summary). Both
   were verified live to return valid strict JSON-schema output. Model names
   live only in `.env`; changing them needs no code change.
6. **Temperature.** `llm.temperature: 0` stays in config, but these reasoning
   models reject any temperature other than the default. `llm.py` sends the
   configured temperature and, if the API rejects it as unsupported for that
   model, retries once without it and remembers the model for the rest of the
   process. Consequence: outputs are not guaranteed to be identical between
   runs; the validator, citations check and `LLM_DEV_CACHE` reduce the impact.
7. **`llm.max_tokens` 2000 -> 4000.** Reasoning models count hidden reasoning
   tokens against the output limit, so 2000 risked truncated JSON on large
   field groups. OpenAI receives it as `max_completion_tokens`.
8. **Cost table filled.** `cost.usd_per_1k_input/output` contain published
   prices for gpt-6-luna ($0.10 / $0.50 per 1M) and gpt-6-sol ($2 / $10 per 1M)
   so every StepLog carries real cost. Unknown models cost 0.
9. **Structured output mechanism.** OpenAI: `response_format` with a strict
   `json_schema`. Anthropic: `output_config.format` JSON schema rather than a
   forced tool call, because forced `tool_choice` is rejected by current
   Claude models. Both are "JSON-schema mode" as allowed by Section 6.3.
10. **Strict schema conversion.** Strict mode needs every property required
    and no extra keys, so `llm.strict_json_schema()` derives a strict copy of
    the Pydantic schema (all properties required, `additionalProperties:
    false`, defaults and numeric/length constraints removed; Pydantic still
    enforces them on the reply). Models with open-ended dicts (e.g.
    `ValidationResult.checks`) cannot be strict; for those the schema is put
    in the system prompt and non-strict JSON is validated as usual. The
    models in `schemas.py` are unchanged from Section 5.
11. **`Usage` lives in `schemas.py`** (rule: all Pydantic models there).
    `LLMError` is an exception, not a model, and lives in `llm.py`.
12. **Settings models live in `config.py`.** The typed config sections
    (`Settings`, `FieldSpec`, `IngestionPatterns`, ...) describe YAML files,
    not messages between modules, so they stay with the loader.
13. **Dev-cache key** is sha256 of model + schema name + system prompt +
    prompt (the plan says prompt + model); including the system prompt and
    schema avoids returning a stale answer when only those change. Cached
    calls report zero tokens and cost because nothing was spent.
14. **Not-yet-implemented CLI commands** print which phase delivers them and
    exit with code 1, so scripts cannot mistake a placeholder for success.
15. **`pytest.ini`** (not in the layout) sets `pythonpath = .` and
    `testpaths = tests` so `pytest -q` works from the root without installing
    the package.

## Plan corrections

21. **`config/fields.yaml` YAML fix.** The `contact_info` description in
    Section 4 ("Procurement contact(s): name, email, phone. ...") contains
    `": "` in an unquoted value, which YAML rejects. The value is now quoted;
    the text is unchanged.
22. **Numeric search hints.** YAML parses the search hint `1295` (Texas
    Form 1295, in the Additional Documentation field) as an integer;
    `FieldSpec` converts every search hint to text instead of editing the
    plan's YAML.
