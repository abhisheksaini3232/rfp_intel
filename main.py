"""RFP Intelligence Platform CLI.

    python main.py --bid ./data/Bid1              index + extract + results table
    python main.py --bid ./data/Bid1 --ask "..."  answer one question
    python main.py parse|index|search|extract|ask|run|compare ...
    python main.py eval retrieval|extraction
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from rfp_intel.config import settings

logging.basicConfig(level=logging.WARNING, format="%(message)s", handlers=[RichHandler(show_path=False)])
for _noisy in ("sentence_transformers", "transformers", "huggingface_hub", "httpx"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

app = typer.Typer(
    help="RFP Intelligence Platform: parse, index, search, extract and ask over bid folders.",
    no_args_is_help=False,
    add_completion=False,
)
eval_app = typer.Typer(help="Run evaluations and write eval/results/.")
app.add_typer(eval_app, name="eval")

console = Console()


def _not_ready(command: str, phase: str) -> None:
    """Report that a command is planned for a later phase and exit non-zero."""
    console.print(f"[yellow]`{command}` is not implemented yet (BUILD_PLAN {phase}).[/yellow]")
    raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    bid: Optional[str] = typer.Option(None, "--bid", help="Bid folder, e.g. ./data/Bid1"),
    ask: Optional[str] = typer.Option(None, "--ask", help="Answer one question about the bid"),
) -> None:
    """Default: index + extract the bid and print a results table (or --ask a question)."""
    if ctx.invoked_subcommand is not None:
        return
    if bid is None:
        console.print(ctx.get_help())
        raise typer.Exit(code=0)
    _not_ready("--bid --ask" if ask else "--bid", "Phase 6a/6b")


def _bid_folder(bid: str) -> Path:
    """Resolve --bid: an existing folder path, or a bid id under data_dir."""
    path = Path(bid)
    if path.is_dir():
        return path
    candidate = settings.path("data_dir") / bid
    if candidate.is_dir():
        return candidate
    console.print(f"[red]Bid folder not found: {bid}[/red]")
    raise typer.Exit(code=2)


@app.command()
def parse(bid: str = typer.Option(..., "--bid", help="Bid folder or id")) -> None:
    """Parse a bid folder and write outputs/parsed/<bid>/<file>.json."""
    from rfp_intel.ingestion.loader import load_bid_folder

    folder = _bid_folder(bid)
    documents = load_bid_folder(folder)
    out_dir = settings.path("outputs_dir") / "parsed" / folder.name
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (out_dir / f"{doc.file_name}.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    table = Table(title=f"Parsed {folder.name} -> {out_dir}")
    for column in ("file", "doc_type", "addendum", "pages", "tables", "warnings"):
        table.add_column(column)
    for doc in documents:
        table.add_row(
            doc.file_name,
            doc.doc_type.value,
            str(doc.addendum_number or ""),
            str(len(doc.pages)),
            str(sum(len(page.tables) for page in doc.pages)),
            "; ".join(doc.warnings),
        )
    parsed = {doc.file_name for doc in documents}
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.name not in parsed):
        table.add_row(path.name, "skipped", "", "", "", "unsupported type or duplicate")
    console.print(table)


@app.command()
def index(
    bid: str = typer.Option(..., "--bid", help="Bid folder or id"),
    force: bool = typer.Option(False, "--force", help="Re-index even if unchanged"),
) -> None:
    """Index a bid folder into the hybrid search engine (incremental)."""
    from rfp_intel.search.engine import SearchEngine

    engine = SearchEngine()
    try:
        stats = engine.index_bid(_bid_folder(bid), force=force)
    finally:
        engine.close()
    state = "unchanged, skipped" if stats.skipped else "indexed"
    console.print(
        f"[bold]{stats.bid_id}[/bold]: {state} | documents={stats.documents} "
        f"chunks_added={stats.chunks_added} chunks_total={stats.chunks_total} ({stats.seconds}s)"
    )
    for warning in stats.warnings:
        console.print(f"  [yellow]warning:[/yellow] {warning}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    bid: Optional[str] = typer.Option(None, "--bid", help="Bid id filter, e.g. Bid1"),
    doc_type: Optional[str] = typer.Option(None, "--type", help="Doc type filter, e.g. addendum"),
    addendum: Optional[int] = typer.Option(None, "--addendum", help="Addendum number filter"),
    top_k: Optional[int] = typer.Option(None, "--top-k", help="Number of hits"),
    config: Optional[str] = typer.Option(None, "--config", help="vector | hybrid | hybrid_rerank"),
) -> None:
    """Search indexed bids and print ranked hits with citations."""
    from rfp_intel.schemas import DocType, SearchFilters
    from rfp_intel.search.engine import SearchEngine

    try:
        doc_types = [DocType(doc_type)] if doc_type else None
        settings.retrieval_for(config)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    filters = SearchFilters(bid_id=Path(bid).name if bid else None, doc_types=doc_types,
                            addendum_number=addendum)
    engine = SearchEngine()
    try:
        hits = engine.search(query, filters, top_k=top_k, config=config)
    finally:
        engine.close()

    table = Table(title=f"{query!r} ({config or 'default'})", show_lines=True)
    for column in ("rank", "score", "file", "page", "doc_type", "ranks", "text"):
        table.add_column(column)
    for rank, hit in enumerate(hits, start=1):
        c = hit.chunk
        kind = c.doc_type.value + (f" {c.addendum_number}" if c.addendum_number else "")
        table.add_row(str(rank), f"{hit.score:.3f}", c.file_name, str(c.page), kind,
                      " ".join(f"{k}={v}" for k, v in hit.ranks.items()),
                      c.text[:200].replace("\n", " "))
    console.print(table if hits else "[yellow]No results.[/yellow]")


@app.command()
def extract(bid: str = typer.Option(..., "--bid", help="Bid folder or id")) -> None:
    """Run the extraction graph and write outputs/<bid>.json."""
    _not_ready("extract", "Phase 6a")


@app.command(name="ask")
def ask_command(
    question: str = typer.Argument(..., help="Question to answer"),
    bid: Optional[list[str]] = typer.Option(None, "--bid", help="Bid id(s) to scope the question"),
) -> None:
    """Answer a free-form question with citations."""
    _not_ready("ask", "Phase 6b")


@app.command()
def run(bid: str = typer.Option(..., "--bid", help="Bid folder")) -> None:
    """Index (if needed) and extract one bid end to end."""
    _not_ready("run", "Phase 6a")


@app.command()
def compare(
    bid_a: str = typer.Argument(..., help="First bid id"),
    bid_b: str = typer.Argument(..., help="Second bid id"),
) -> None:
    """Compare two bids side by side (bonus)."""
    _not_ready("compare", "Phase 9")


@eval_app.command("retrieval")
def eval_retrieval() -> None:
    """Recall@k and MRR for each retrieval config -> eval/results/retrieval.md."""
    _not_ready("eval retrieval", "Phase 4")


@eval_app.command("extraction")
def eval_extraction() -> None:
    """Field accuracy against gold answers -> eval/results/extraction.md."""
    _not_ready("eval extraction", "Phase 5")


if __name__ == "__main__":
    app()
