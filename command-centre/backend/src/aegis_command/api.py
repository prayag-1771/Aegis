"""Command-centre API — the one service the dashboard talks to.

Endpoints:
    GET  /health                    liveness + which detection modules are up
    POST /ingest/scam               Fraud Shield pushes a detection (contract JSON)
    POST /ingest/counterfeit        Counterfeit Vision pushes a scan (contract JSON)
    POST /refresh/fraud-graph       pull latest rings from the fraud-graph service
    GET  /events                    everything the dashboard renders (cards + map)
    POST /fuse                      run the Gen AI fusion over current signals
    GET  /fusion/latest             last fusion package (for the fusion-moment reveal)
"""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .store import store

MODULES = {
    "fraud-shield": "http://127.0.0.1:8001",
    "counterfeit-vision": "http://127.0.0.1:8002",
    "fraud-graph": "http://127.0.0.1:8003",
}

app = FastAPI(title="Aegis Command Centre", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon setting
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def seed() -> None:
    store.seed_demo_data()


@app.get("/health")
async def health() -> dict:
    """Own liveness + probe each detection module."""
    modules = {}
    async with httpx.AsyncClient(timeout=1.5) as client:
        for name, base in MODULES.items():
            try:
                r = await client.get(f"{base}/health")
                modules[name] = "up" if r.status_code == 200 else f"error({r.status_code})"
            except httpx.HTTPError:
                modules[name] = "down"
    return {"status": "ok", "service": "command-centre", "version": __version__, "modules": modules}


@app.post("/ingest/scam")
def ingest_scam(event: dict) -> dict:
    if "event_id" not in event or "verdict" not in event:
        raise HTTPException(422, "not a valid scam_detection payload (see contracts/)")
    store.add_scam(event)
    return {"accepted": event["event_id"]}


@app.post("/ingest/counterfeit")
def ingest_counterfeit(event: dict) -> dict:
    if "event_id" not in event or "verdict" not in event:
        raise HTTPException(422, "not a valid counterfeit payload (see contracts/)")
    store.add_counterfeit(event)
    return {"accepted": event["event_id"]}


@app.post("/refresh/fraud-graph")
async def refresh_fraud_graph() -> dict:
    """Pull the latest ring detection from the fraud-graph service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{MODULES['fraud-graph']}/fraud-graph")
            r.raise_for_status()
            store.set_fraud_graph(r.json())
            return {"refreshed": True, "rings": len(store.fraud_graph.get("rings", []))}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-graph service unreachable: {exc}") from exc


@app.get("/events")
def events() -> dict:
    """Everything the dashboard needs to render cards, graph, and map."""
    scams, counterfeits, fraud_graph = store.snapshot()
    return {
        "scams": scams,
        "counterfeits": counterfeits,
        "fraud_graph": fraud_graph,
        "last_fusion": store.last_fusion,
    }


@app.post("/fuse")
def fuse_now() -> dict:
    """THE fusion moment: correlate everything currently known."""
    from aegis_fusion.fuse import fuse, validate_against_contract

    scams, counterfeits, fraud_graph = store.snapshot()
    output = fuse(scams, counterfeits, fraud_graph)
    payload = json.loads(output.model_dump_json())
    validate_against_contract(payload)
    store.set_fusion(payload)
    return payload


@app.get("/fusion/latest")
def fusion_latest() -> dict:
    if store.last_fusion is None:
        raise HTTPException(404, "no fusion has been run yet — POST /fuse first")
    return store.last_fusion


@app.get("/hotspots")
def hotspots() -> dict:
    """Cross-domain crime map: DBSCAN hubs over all located signals.
    A cross_domain=true hub is the coordinated-crime-hub signal (innovation #3)."""
    from aegis_fusion.correlator import correlate
    from aegis_geospatial import cluster_hotspots

    scams, counterfeits, fraud_graph = store.snapshot()
    correlation = correlate(scams, counterfeits, fraud_graph)
    hubs = cluster_hotspots(correlation.map_hotspots)
    return {
        "hubs": [h.to_dict() for h in hubs],
        "n_cross_domain": sum(1 for h in hubs if h.cross_domain),
        "points": correlation.map_hotspots,
    }
