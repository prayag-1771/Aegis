"""Command-line interface.

    fraud-graph train              # train + persist model (synthetic source)
    fraud-graph detect             # score, cluster rings, write output/fraud_graph.json
    fraud-graph demo               # train + detect + validate, one shot
    fraud-graph serve              # start the FastAPI server for the command centre
    fraud-graph ghost-ring         # federated cross-bank detection
    fraud-graph arms-race          # adversarial evolutionary loop
    fraud-graph spectral           # spectral analysis + sonification
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


@app.command(name="ghost-ring")
def ghost_ring(
    source: str = typer.Option("synthetic", help="Data source"),
    n_banks: int = typer.Option(4, help="Number of bank partitions"),
):
    """Ghost Ring: federated cross-bank fraud detection.

    Partitions the graph into N isolated banks, trains GraphSAGE per bank,
    matches boundary nodes via embeddings, and fuses for ring detection.
    Reports the recall gap (per-bank vs fused) — that IS the result.
    """
    from .ghost_ring import run_ghost_ring

    report = run_ghost_ring(source=source, n_banks=n_banks)
    
    out_path = OUTPUT_DIR / "ghost_ring.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    
    typer.echo(f"Written: {out_path}")
    typer.echo(f"\n{'='*50}")
    typer.echo(f"RECALL GAP (fused - per-bank): {report.recall_gap:+.4f}")
    typer.echo(f"Matching precision: {report.matching_precision:.4f}")
    typer.echo(f"False-merge rate: {report.false_merge_rate:.4f}")


@app.command(name="arms-race")
def arms_race(
    generations: int = typer.Option(30, help="Number of evolutionary generations"),
    population: int = typer.Option(50, help="Population size"),
    retrain_every: int = typer.Option(5, help="Retrain detector every N generations"),
    source: str = typer.Option("synthetic"),
):
    """Criminal Trains the Cop: adversarial evolutionary arms race.

    Evolves criminal strategies to evade the XGBoost detector; retrains the
    detector periodically. Outputs arms_race.png with escape rate + recall.
    """
    from .adversarial import run_arms_race
    from .adversarial_plots import plot_arms_race

    history = run_arms_race(
        n_generations=generations,
        population_size=population,
        retrain_every=retrain_every,
        source=source,
    )

    # Save history
    history.to_csv(OUTPUT_DIR / "arms_race_history.csv", index=False)
    typer.echo(f"History saved: {OUTPUT_DIR / 'arms_race_history.csv'}")

    # Plot
    try:
        plot_path = plot_arms_race(history)
        typer.echo(f"Plot saved: {plot_path}")
    except ImportError:
        typer.echo("matplotlib not available — skipping plot")

    # Summary
    last = history.iloc[-1]
    typer.echo(f"\nFinal generation {int(last['generation'])}:")
    typer.echo(f"  Criminal escape rate: {last['best_escape_rate']:.4f}")
    typer.echo(f"  Detector recall:      {last['detector_recall']:.4f}")


@app.command()
def spectral(
    source: str = typer.Option("synthetic"),
    sonify: bool = typer.Option(True, help="Generate WAV audio files"),
    export_json: bool = typer.Option(True, help="Export SED data for browser sonifier"),
):
    """Frequency of Fraud: spectral graph analysis + sonification.

    Runs per-community eigendecomposition, measures spectral shift between
    clean and ring communities, and optionally generates audio WAV files.
    """
    from .spectral import export_sed_json, run_spectral_analysis

    report = run_spectral_analysis(source=source)
    typer.echo(json.dumps(report.to_dict(), indent=2))

    if sonify:
        from .spectral_audio import sonify_communities
        wavs = sonify_communities(report)
        for name, path in wavs.items():
            typer.echo(f"  WAV: {name} -> {path}")

    if export_json:
        json_path = export_sed_json(report)
        typer.echo(f"  SED JSON: {json_path}")
        typer.echo(f"  Open output/spectral_sonifier.html in a browser to listen!")


if __name__ == "__main__":
    app()
