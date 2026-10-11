# End-to-end smoke test

Generated 2026-10-11T10:48:54+00:00; API http://localhost:8001; bids Bid1, Bid2; 22/22 checks passed.

| check | result | detail | seconds |
|---|---|---|---|
| API: health lists the bids as indexed | PASS | indexed ['352', 'Bid1', 'Bid2', 'MiniBid', 'test'] | 3.8 |
| API: GET /bids | PASS | Bid1: 4 files, Bid2: 5 files | 3.7 |
| API: GET /bids/{id} documents and chunks | PASS | Bid1: 4 docs, 210 chunks; Bid2: 5 docs, 38 chunks | 6.4 |
| API: POST /index is incremental (0 chunks added) | PASS | Bid1: unchanged, 210 chunks; Bid2: unchanged, 38 chunks | 6.1 |
| API: search in all three retrieval configs | PASS | vector: 5 hits; hybrid: 5 hits; hybrid_rerank: 5 hits | 11.8 |
| API: search metadata filter and bad config | PASS | doc_type=addendum: 5 hits; bad config -> 400 | 9.8 |
| API: chunk lookup, file serving, path traversal rejected | PASS | chunk 451b4bcdc71c1838c49d76d319c75bb53d198259:1:0 and file served; traversal rejected (400) | 13.0 |
| API: saved records have 20 fields, every value cited | PASS | Bid1: {'passed': 13, 'failed': 2, 'not_found': 5}; Bid2: {'passed': 17, 'failed': 1, 'not_found': 2} | 5.8 |
| API: eval results endpoints | PASS | 20 questions, best recall@5=1.000; extraction bids=2 | 5.6 |
| API: oversized question rejected | PASS | oversized question -> 422 | 2.8 |
| CLI: --help lists every command | PASS | all commands listed | 2.4 |
| CLI: parse writes outputs/parsed | PASS | 4 parsed files | 54.7 |
| API: POST /ask with citations | PASS | 'The submission deadline after all addendums is July 9, 2024 at 2:00 PM CST. [E1]' (1 citations, cached=True) | 2.7 |
| API: semantic answer cache hit | PASS | cache hit in 2.5s | 5.0 |
| API: unanswerable question -> Not found | PASS | unanswerable question -> Not found, no citations | 38.3 |
| API: background question with trace and summary | PASS | served from the answer cache (no graph steps); run `python main.py cache clear` for a cold run | 5.1 |
| API: comparison agent | PASS | 19 differing rows, 8 highlights | 11.9 |
| API: go/no-go agent | PASS | Bid1: review (6 met/0 not/1 unknown); Bid2: review (5 met/0 not/2 unknown) | 15.0 |
| CLI: compare | PASS | table printed; outputs/comparison.md rewritten | 7.6 |
| CLI: go-no-go | PASS | report printed; unknown bid -> exit 2 | 9.2 |
| API: runs list and metrics | PASS | 4 runs; cache hits=4 misses=1 | 4.9 |
| Outputs on disk | PASS | 8 files present | 0.0 |
