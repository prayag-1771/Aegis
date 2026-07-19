"""FastAPI service the command centre calls.

Endpoints:
    GET  /health             liveness probe
    GET  /fraud-graph        latest detection result (contract JSON); runs the
                             pipeline on first call if no cached output exists
    POST /detect             force a fresh detection run
    POST /demo/inject-ring   stage demo: add a fresh 6-account ring + re-detect
    POST /demo/score-custom  fraud console: score human-designed transactions
    POST /demo/reset         drop injected rings, back to the base dataset
    GET  /rings/{id}/spectral  spectral second opinion for one detected ring
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import OUTPUT_DIR
from .data import load
from .demo import build_custom_dataset, inject_demo_ring
from .pipeline import run_detection

_OUTPUT_FILE = OUTPUT_DIR / "fraud_graph.json"
_STATE_LOCK = Lock()
_CURRENT_DATASET = load("synthetic")
_CURRENT_OUTPUT = None


def _load_output() -> dict | None:
    if _OUTPUT_FILE.exists():
        return json.loads(_OUTPUT_FILE.read_text(encoding="utf-8"))
    return None


def _current_output() -> dict:
    global _CURRENT_OUTPUT
    with _STATE_LOCK:
        if _CURRENT_OUTPUT is not None:
            return json.loads(_CURRENT_OUTPUT.model_dump_json())
        cached = _load_output()
        if cached is not None:
            return cached

    output = run_detection(ds=_CURRENT_DATASET)
    with _STATE_LOCK:
        _CURRENT_OUTPUT = output
    return json.loads(output.model_dump_json())


def _set_current_output(payload) -> None:
    global _CURRENT_OUTPUT
    with _STATE_LOCK:
        _CURRENT_OUTPUT = payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm at startup: a cold first GET /fraud-graph used to run the whole
    # detect pipeline inside the request and blow the command centre's 30 s
    # timeout on stage. Always recompute from the clean base dataset so a
    # restart also wipes any rings injected during a previous rehearsal
    # (the output file on disk may still contain them).
    _set_current_output(run_detection(ds=_CURRENT_DATASET))
    yield


app = FastAPI(
    title="Aegis Fraud Graph",
    description="Fraud-ring detection over transaction networks (graph features + XGBoost).",
    version=__version__,
    lifespan=lifespan,
)

# The dashboard runs on another port during development; allow it.
app.add_middleware(
    CORSMiddleware,
    # Local-origin browsers only (command centre + demo UIs).
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "module": "fraud-graph", "version": __version__}


@app.get("/fraud-graph")
def fraud_graph() -> dict:
    """Latest contract-compliant fraud_graph payload."""
    return _current_output()


@app.post("/detect")
def detect() -> dict:
    """Re-run detection and return the fresh payload."""
    global _CURRENT_OUTPUT
    out = run_detection(ds=_CURRENT_DATASET)
    _set_current_output(out)
    return json.loads(out.model_dump_json())


@app.post("/demo/inject-ring")
def demo_inject_ring(body: dict | None = None) -> dict:
    """Inject a fresh ring and rerun detection immediately.

    Body (all optional): district, topology (cycle|chain|fan_in), and
    accounts — 3-10 custom member names for the name-the-criminals moment.
    """
    global _CURRENT_DATASET, _CURRENT_OUTPUT

    payload = body or {}
    district = str(payload.get("district") or "Jamtara")
    topology = payload.get("topology") or "cycle"
    if topology not in {"cycle", "chain", "fan_in"}:
        topology = "cycle"
    raw_names = payload.get("accounts")
    if raw_names is not None and not isinstance(raw_names, list):
        raise HTTPException(422, "'accounts' must be a list of names")

    with _STATE_LOCK:
        current_dataset = _CURRENT_DATASET

    try:
        injected = inject_demo_ring(
            current_dataset, district=district, topology=topology, account_names=raw_names
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    output = run_detection(ds=injected)

    with _STATE_LOCK:
        _CURRENT_DATASET = injected
        _CURRENT_OUTPUT = output

    return json.loads(output.model_dump_json())


@app.post("/demo/score-custom")
def demo_score_custom(body: dict | None = None) -> dict:
    """Fraud console: score transactions a human designed by hand.

    Body: transactions [{source, target, amount}] (1-40), district?, speed?
    ("minutes" fast / "days" slow), commit? (default true — a caught ring is
    kept on the live map; uncaught activity never pollutes state).
    """
    global _CURRENT_DATASET, _CURRENT_OUTPUT

    from .config import RingConfig
    from .export import build_output
    from .graph import compute_features
    from .model import load_model, score_all
    from .rings import detect_rings

    payload = body or {}
    txs = payload.get("transactions")
    if not isinstance(txs, list) or not 1 <= len(txs) <= 40:
        raise HTTPException(422, "provide 1-40 transactions")
    district = str(payload.get("district") or "Jamtara")
    speed = payload.get("speed") if payload.get("speed") in {"minutes", "days"} else "minutes"
    commit = bool(payload.get("commit", True))

    with _STATE_LOCK:
        base = _CURRENT_DATASET

    try:
        eval_ds, user_accounts = build_custom_dataset(base, txs, district=district, speed=speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    features = compute_features(eval_ds)
    clf = load_model()
    scores = score_all(clf, features)
    rings, accounts_df = detect_rings(eval_ds, scores, RingConfig())

    user_set = set(user_accounts)
    hit = next((r for r in rings if len(user_set & set(r.account_ids)) >= 3), None)

    committed = False
    if hit is not None and commit:
        output = build_output(eval_ds, rings, accounts_df, features)
        (OUTPUT_DIR / "fraud_graph.json").write_text(
            output.model_dump_json(indent=2), encoding="utf-8"
        )
        with _STATE_LOCK:
            _CURRENT_DATASET = eval_ds
            _CURRENT_OUTPUT = output
        committed = True

    return {
        "accounts": [
            {
                "account_id": a,
                "illicit_probability": round(float(scores.get(a, 0.0)), 4),
                "in_ring": hit is not None and a in set(hit.account_ids),
            }
            for a in user_accounts
        ],
        "ring": (
            {
                "ring_id": hit.ring_id,
                "label": hit.label,
                "size": hit.size,
                "risk_score": round(hit.risk_score, 4),
                "district": hit.district,
                "total_amount": hit.total_amount,
                "account_ids": hit.account_ids,
            }
            if hit
            else None
        ),
        "committed": committed,
        "rings_total": len(rings),
    }


# Per-community Rayleigh cache: the partition + eigendecompositions take a few
# seconds, and every ring click would repeat them for the same dataset.
_SPECTRAL_CACHE: dict = {"ds_id": None, "result": None}


def _community_rayleighs(ds) -> list[tuple[frozenset, float]]:
    """[(community nodes, Rayleigh)] using the SAME pipeline the research lab
    validated: build graph -> Leiden/Louvain partition -> per-community
    normalized Laplacian -> Rayleigh of the total_in signal. Never the degree
    fallback (documented to invert the shift)."""
    import networkx as nx

    from .graph import build_graph, compute_features
    from .spectral import (
        _leiden_or_louvain,
        _signal,
        build_normalized_laplacian,
        rayleigh_quotient,
    )

    if _SPECTRAL_CACHE["ds_id"] == id(ds):
        return _SPECTRAL_CACHE["result"]

    g_full = build_graph(ds)
    und = g_full.to_undirected()
    und.remove_edges_from(nx.selfloop_edges(und))
    features = compute_features(ds, g_full)
    if features.index.name != "account_id" and "account_id" in features.columns:
        features = features.set_index("account_id")

    result: list[tuple[frozenset, float]] = []
    for comm in _leiden_or_louvain(und):
        if len(comm) < 5:
            continue
        sub = und.subgraph(comm)
        if sub.number_of_edges() < 2:
            continue
        L, order = build_normalized_laplacian(sub)
        result.append((frozenset(comm), rayleigh_quotient(_signal(order, features, sub), L)))

    _SPECTRAL_CACHE["ds_id"] = id(ds)
    _SPECTRAL_CACHE["result"] = result
    return result


@app.get("/rings/{ring_id}/spectral")
def ring_spectral(ring_id: str) -> dict:
    """Spectral second opinion for one detected ring — the MATCHED PAIRWISE
    shift, which is the methodology spectral.py validates. Absolute
    cross-community ranking is explicitly documented there as unreliable
    (baseline Rayleigh varies with size/density), so this compares the ring's
    community against the clean community closest to it in size. Corroborating
    evidence only — the classifier's verdict already stands."""
    out = _current_output()
    members = {a["account_id"] for a in out.get("accounts", []) if a.get("ring_id") == ring_id}
    if not members:
        raise HTTPException(404, f"unknown ring_id {ring_id!r}")
    flagged = {a["account_id"] for a in out.get("accounts", [])}

    with _STATE_LOCK:
        ds = _CURRENT_DATASET

    comms = _community_rayleighs(ds)
    if not comms:
        raise HTTPException(422, "no communities large enough for a spectral measurement")

    # Home community = partition cell holding most of this ring's members.
    home_nodes, home_rq = max(comms, key=lambda c: len(members & c[0]))
    if not members & home_nodes:
        raise HTTPException(422, "ring members fall outside every measured community")

    # Matched clean community: no flagged accounts at all, closest in size.
    clean = [(n, rq) for n, rq in comms if not (n & flagged)]
    if not clean:
        raise HTTPException(422, "no clean community available for a matched comparison")
    matched_nodes, matched_rq = min(clean, key=lambda c: abs(len(c[0]) - len(home_nodes)))

    shift = home_rq - matched_rq
    return {
        "ring_id": ring_id,
        "ring_rayleigh": round(home_rq, 4),
        "ring_community_size": len(home_nodes),
        "matched_clean_rayleigh": round(matched_rq, 4),
        "matched_clean_size": len(matched_nodes),
        "shift": round(shift, 4),
        "agrees": shift > 0,
        "note": (
            "Matched pairwise Rayleigh shift (ring community vs the clean "
            "community closest in size) — the methodology spectral.py "
            "validates. Independent lens, corroboration only; absolute "
            "cross-community ranking is documented as unreliable."
        ),
    }


@app.post("/demo/reset")
def demo_reset() -> dict:
    """Drop all injected rings: reload the base dataset and rerun detection."""
    global _CURRENT_DATASET, _CURRENT_OUTPUT

    base = load("synthetic")
    output = run_detection(ds=base)

    with _STATE_LOCK:
        _CURRENT_DATASET = base
        _CURRENT_OUTPUT = output

    return json.loads(output.model_dump_json())
