# Demo video script (about 3 minutes)

Before recording: API running (`uvicorn rfp_intel.api.server:app --port 8000`,
or `--port 8001` with `VITE_API_URL=http://localhost:8001` in `frontend/.env`),
web app running (`cd frontend && npm run dev`), both bids already indexed and
extracted (`python main.py --bid ./data/Bid1`, `... Bid2`).

| time | show | say |
|---|---|---|
| 0:00 | Terminal: `python main.py --bid ./data/Bid2` | "One command: it indexes the folder incrementally, runs the LangGraph agents and prints the 20 fields with status, confidence and citation counts. Every value is cited; missing ones are null and 'Not found in documents'." |
| 0:40 | Terminal: `python main.py search "due date" --bid Bid1` | "The hybrid search engine: dense vectors plus BM25, fused with RRF and re-ranked. Addendum 2 is the first hit, and each hit carries file, page and the chunk text." |
| 1:00 | Web app, Bids page | "Both bids, with the due date flagged 'changed by Addendum 2'." |
| 1:15 | Bid1 detail, Fields tab, click Due Date | "July 9, 2024 2:00 PM Central, cited to Addendum 2; the drawer shows the exact quote and the original June 27 date in the notes. 'Open PDF at page' opens the source." |
| 1:40 | Addendum changes tab | "The reconciler's change log: what each addendum overrode, clarified or added." |
| 1:55 | Ask page, suggested question "What changed in Addendum 2 compared to the original RFP?" | "Question mode: the answer names June 27 -> July 9 and cites both the RFP and the addendum. Ask about a bid bond and it says Not found: no invented amounts." |
| 2:25 | Evaluation page | "Retrieval eval over 20 questions: Recall@5 goes from 0.85 (vector) to 1.0 (hybrid + re-ranker). Extraction accuracy against gold answers, baseline vs the agent graph." |
| 2:45 | Run trace page (the last run) | "Every step is traced: the Retrieval agent runs before each extractor, the three extractors run in parallel, and the validator's retries are visible with tokens and cost." |
| 3:00 | Terminal: `pytest -q` | "218 tests, and the same pipeline runs unchanged on a folder it has never seen." |
