"""Command-line interface.

    fraud-graph train              # train + persist model (synthetic source)
    fraud-graph detect             # score, cluster rings, write output/fraud_graph.json
    fraud-graph demo               # train + detect + validate, one shot
    fraud-graph serve              # start the FastAPI server for the command centre
"""

from __future__ import annotations

import json

import typer

from .config import OUTPUT_DIR
from .pipeline import run_all, run_detection, run_training, validate_against_contract

app = typer.Typer(help="Aegis Fraud Graph — fraud-ring detection over transaction networks.")


@app.command()
def train(source: str = typer.Option("synthetic", help="Data source: synthetic | elliptic")):
    """Train the XGBoost illicit-account classifier and save it."""
    report = run_training(source)
    typer.echo(json.dumps(report.to_dict(), indent=2))


@app.command()
def detect(source: str = typer.Option("synthetic", help="Data source: synthetic | elliptic")):
    """Run detection with the saved model; write contract JSON."""
    out = run_detection(source)
    typer.echo(f"rings={len(out.rings)} accounts={len(out.accounts)} edges={len(out.edges)}")
    typer.echo(f"written: {OUTPUT_DIR / 'fraud_graph.json'}")


@app.command()
def demo(source: str = typer.Option("synthetic")):
    """Full pipeline: train -> detect -> validate against the shared contract."""
    report, out = run_all(source)
    validate_against_contract()
    typer.echo(f"AUC={report.roc_auc:.4f} AP={report.avg_precision:.4f}")
    typer.echo(f"rings={len(out.rings)} accounts={len(out.accounts)} edges={len(out.edges)}")
    typer.echo("contract validation: PASS")


@app.command()
def evaluate(source: str = typer.Option("synthetic")):
    """Ring-recovery metrics vs ground truth (deck numbers: detection rate etc.)."""
    from .evaluate import run_evaluation

    report = run_evaluation(source)
    d = report.to_dict()
    typer.echo(json.dumps({k: v for k, v in d.items() if k != "per_ring"}, indent=2))
    for row in d["per_ring"]:
        mark = "OK " if row["recovered"] else "MISS"
        typer.echo(f"  [{mark}] {row['true_ring']} size={row['size']:2d} "
                   f"overlap={row['member_overlap']:.0%} -> {row['matched_detected_ring']}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8003, help="Fraud Graph service port (A=8001, B=8002, C=8003)"),
):
    """Serve the fraud-graph API for the command centre."""
    import uvicorn

    uvicorn.run("aegis_fraud_graph.api:app", host=host, port=port)


if __name__ == "__main__":
    app()
