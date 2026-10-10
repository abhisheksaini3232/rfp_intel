"""RFP Intelligence Platform CLI.

    python main.py --bid ./data/Bid1              index + extract + results table
    python main.py --bid ./data/Bid1 --ask "..."  answer one question
    python main.py parse|index|search|extract|ask|run|compare ...
    python main.py eval retrieval|extraction
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

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


@app.command()
def parse(bid: str = typer.Option(..., "--bid", help="Bid folder")) -> None:
    """Parse a bid folder and write outputs/parsed/<bid>/<file>.json."""
    _not_ready("parse", "Phase 2")


@app.command()
def index(
    bid: str = typer.Option(..., "--bid", help="Bid folder"),
    force: bool = typer.Option(False, "--force", help="Re-index even if unchanged"),
) -> None:
    """Index a bid folder into the hybrid search engine (incremental)."""
    _not_ready("index", "Phase 3")


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
    _not_ready("search", "Phase 3")


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
