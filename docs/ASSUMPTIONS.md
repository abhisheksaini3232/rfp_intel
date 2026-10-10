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

## Phase 1 (draft, pending approval)

16. **Eval models live in `eval/loaders.py`** (`RetrievalQuestion`,
    `GoldField`). They describe eval files, not messages between
    `rfp_intel` modules, and `eval/` is outside the package.
17. **Gold file shape.** `eval/gold/<bid>.json` maps each of the 20 field
    names to `{value, must_contain, status?, scoring?, notes?}`.
    `status` defaults to `ok`; `scoring: faithfulness` marks Bid Summary
    (judged for faithfulness, not exactness).
18. **Matching ignores case and all whitespace** (`normalize()` removes
    whitespace), so "16 GB" matches "16GB". Retrieval relevance and gold
    tokens use the same rule.
19. **Bid2 Installation gold is `not_found`.** The plan says "Not required
    (none stated)"; since nothing is stated in the documents, the
    guardrail rule (missing info = not_found) applies.
20. **`must_contain` tokens are short and as written in the source**, and
    `eval/verify_eval_data.py` checks every token exists in the bid's files.
    Date format differences (e.g. "July 9, 2024" vs "2024-07-09") are left to
    the Phase 5 scorer and LLM judge.

## Plan corrections

21. **`config/fields.yaml` YAML fix.** The `contact_info` description in
    Section 4 ("Procurement contact(s): name, email, phone. ...") contains
    `": "` in an unquoted value, which YAML rejects. The value is now quoted;
    the text is unchanged.
22. **Numeric search hints.** YAML parses the search hint `1295` (Texas
    Form 1295, in the Additional Documentation field) as an integer;
    `FieldSpec` converts every search hint to text instead of editing the
    plan's YAML.

## Phase 2

23. **PDF lines are rebuilt from spans** instead of plain
    `get_text("text", sort=True)`. Sorted text glued side-by-side columns
    together (`210-BLYZDell Latitude 5550`), which breaks BM25 on part
    numbers. Spans are grouped into rows by vertical position and joined
    with a space at visible horizontal gaps; a vertical gap larger than 0.8
    line heights becomes a paragraph break.
24. **Drop selectors spare containers of fields.** Portal pages wrap all
    content in a `<form>`; an element from `html_drop_selectors` is removed
    only if it contains none of the configured labels.
25. **HTML label value** = text of the label element's following siblings,
    stopping at the next sibling that holds another label (so "Contact
    Information" does not swallow "Description"); else the next string.
26. **Classification runs on the raw first page, before cleaning**, because
    the cleaner removes repeated headers such as "ADDENDUM No. 1". The file
    name is checked against all patterns first, then the first page text.
27. **Repeated header/footer detection** treats digits as interchangeable
    ("Page 3 of 40" = "Page 4 of 40"), needs >= 2 non-empty pages and >= 50%
    of them, and ignores lines shorter than 4 characters or without letters
    (so "Yes" or "50,000" are never removed). One-page documents are untouched.
28. **Document date fallback skips deadlines.** When no "Issue Date"/"Date:"
    is found, the first date in the first 500 chars is used unless the same
    sentence has a deadline word just before it (due, deadline, closing,
    extend..., no later than). Addendum 2 therefore has no doc_date rather
    than the due date.
29. **Title** = HTML `Title` field; for PDFs the metadata title (minus
    "Microsoft Word - " and extensions), else the first line with >= 3 words
    that is <= 20% digits (skips addresses and phone numbers).
30. **Failure reporting.** A file that cannot be parsed (empty, corrupt,
    password-protected) becomes a `Document` with no pages and a warning, so
    it is visible downstream; unsupported extensions and duplicate files are
    skipped and logged, and `parse` lists them as "skipped".
31. **`parse_pdf` / `parse_html` take an optional `warnings` list** in
    addition to the planned `(path)` argument, so non-fatal problems reach
    `Document.warnings`.
32. **Bid1 data notes.** The main RFP has 62 pages (the plan says 40; the
    RFP body is 40 pages plus attachments). Pages 54-59 are blank with no
    images, so they are flagged empty and OCR could not help. Spec lists can
    continue across a page break (Tier 3 runs from page 4 to 5); the Phase 3
    chunker must handle that. The portal shows Closing Date 03:00 PM EDT,
    which equals Addendum 2's 2:00 PM Central.

## Phase 3

33. **Chunking runs over each whole document**, not page by page, so Q&A
    pairs and spec lists that cross a page break stay whole; `page` is the
    page a chunk starts on (a cited quote may continue on the next page).
34. **Running headings inside a spec list** (heading lines at the top of a
    page followed by more bullets) are skipped, so the list continues.
35. **Q&A units** end at the next question number (n + 1) or a paragraph
    break after "Answer:"; page breaks do not end a unit, and a list that
    restarts at "1." inside an answer belongs to the answer.
36. **Only real tables become table chunks** (>= 50% of rows with 2+
    non-empty cells); layout grids are skipped because their text is already
    in the page text. Table/text duplication is accepted.
37. **min_tokens applies to every kind except qa and record** (plan rule);
    a heading only starts a new text chunk once the current one has
    min_tokens; a tiny tail joins the previous chunk; exact duplicate chunks
    within a document are dropped (20 empty response-form tables in Bid1).
38. **Uppercase heading rule** also needs letters to be >= 50% of visible
    characters, so date lines such as "06/01/2024 at 2:00 PM EDT" are not
    headings. Numbered bullets need whitespace after "1." / "a)" so "2.1 Line
    Information" is a heading, not a bullet.
39. **BM25 tokenizer** keeps IDs whole and also emits their parts
    ("ja-207652" + "ja" + "207652"); a trailing "#" is kept ("si#"). BM25
    returns chunks containing a query token ranked by score (not score > 0:
    small corpora give IDF 0 to terms in half the chunks). Multi-bid search
    builds one BM25 over the selected bids at query time.
40. **Doc-type filters from query text need scoping words** ("only search
    ... specs", "in the addendum", "from the RFP", "specs only"); a bare
    mention is a topic. Bid ids and "addendum N" always filter.
    `parse_filters` returns `(filters, cleaned_query)`. Explicit filters win.
41. **Query expansion** returns the query plus up to 3 synonym variants; each
    variant runs through vector and BM25 search and all lists are fused with
    RRF. No LLM rewriting (deterministic, free); widened retries in Phase 6.
42. **Vector point ids and fusion keys include the bid id**
    (`<bid>/<chunk_id>`): the plan's chunk_id comes from the file hash, and
    the same file in two bids would otherwise overwrite each other.
43. **`IndexStats`** (used but not defined by the plan) added to schemas.py.
    The manifest stores file hashes plus a hash of the chunking settings and
    embedding model, so changing those re-indexes automatically.
44. **Models load from the local Hugging Face cache first** and download only
    when missing (no network check on every run).
