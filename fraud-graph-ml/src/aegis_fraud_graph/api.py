"""FastAPI service the command centre calls.

Endpoints:
    GET  /health             liveness probe
    GET  /fraud-graph        latest detection result (contract JSON); runs the
                             pipeline on first call if no cached output exists
    POST /detect             force a fresh detection run
    POST /demo/inject-ring   stage demo: add a fresh 6-account ring + re-detect
    POST /demo/reset         drop injected rings, back to the base dataset
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import OUTPUT_DIR
from .data import load
from .demo import inject_demo_ring
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
    """Inject a fresh six-account ring and rerun detection immediately."""
    global _CURRENT_DATASET, _CURRENT_OUTPUT

    payload = body or {}
    district = str(payload.get("district") or "Jamtara")
    topology = payload.get("topology") or "cycle"
    if topology not in {"cycle", "chain", "fan_in"}:
        topology = "cycle"

    with _STATE_LOCK:
        current_dataset = _CURRENT_DATASET

    injected = inject_demo_ring(current_dataset, district=district, topology=topology)
    output = run_detection(ds=injected)

    with _STATE_LOCK:
        _CURRENT_DATASET = injected
        _CURRENT_OUTPUT = output

    return json.loads(output.model_dump_json())


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
