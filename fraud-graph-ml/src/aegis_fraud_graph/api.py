"""FastAPI service the command centre calls.

Endpoints:
    GET  /health          liveness probe
    GET  /fraud-graph     latest detection result (contract JSON); runs the
                          pipeline on first call if no cached output exists
    POST /detect          force a fresh detection run
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import OUTPUT_DIR
from .pipeline import run_detection

_OUTPUT_FILE = OUTPUT_DIR / "fraud_graph.json"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm at startup: a cold first GET /fraud-graph used to run the whole
    # train+detect pipeline inside the request and blow the command centre's
    # 30 s timeout on stage.
    if not _OUTPUT_FILE.exists():
        run_detection()
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
    if not _OUTPUT_FILE.exists():
        run_detection()
    return json.loads(_OUTPUT_FILE.read_text(encoding="utf-8"))


@app.post("/detect")
def detect() -> dict:
    """Re-run detection and return the fresh payload."""
    out = run_detection()
    return json.loads(out.model_dump_json())
