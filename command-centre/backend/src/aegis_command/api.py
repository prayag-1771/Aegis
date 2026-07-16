"""Command-centre API — the one service the dashboard talks to.

Endpoints:
    GET  /health                    liveness + which detection modules are up
    POST /ingest/scam               Fraud Shield pushes a detection (contract JSON)
    POST /ingest/counterfeit        Counterfeit Vision pushes a scan (contract JSON)
    POST /analyze/scam              proxy: text -> Fraud Shield -> auto-ingest
    POST /analyze/counterfeit       proxy: base64 image -> Counterfeit Vision -> auto-ingest
    POST /refresh/fraud-graph       pull latest rings from the fraud-graph service
    GET  /events                    everything the dashboard renders (cards + map)
    POST /fuse                      run the Gen AI fusion over current signals
    GET  /fusion/latest             last fusion package (for the fusion-moment reveal)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import jsonschema
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .store import store

MODULES = {
    "fraud-shield": "http://127.0.0.1:8001",
    "counterfeit-vision": "http://127.0.0.1:8002",
    "fraud-graph": "http://127.0.0.1:8003",
}

CONTRACTS = Path(__file__).resolve().parents[3].parent / "contracts"
_SCHEMAS: dict[str, dict] = {}


def _schema(kind: str) -> dict:
    """Contract schema, cached. kind: scam_detection | counterfeit."""
    if kind not in _SCHEMAS:
        _SCHEMAS[kind] = json.loads((CONTRACTS / f"{kind}.schema.json").read_text(encoding="utf-8"))
    return _SCHEMAS[kind]


def _validated(kind: str, event: dict) -> dict:
    """Reject contract-breaking payloads at the door — junk that gets past
    ingest reaches the fusion LLM and the dashboard unchecked."""
    try:
        jsonschema.validate(instance=event, schema=_schema(kind))
    except jsonschema.ValidationError as exc:
        raise HTTPException(422, f"payload violates the {kind} contract: {exc.message}") from exc
    return event


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.seed_demo_data()
    yield


app = FastAPI(title="Aegis Command Centre", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Local-origin browsers only (the dashboard). Real security would need
    # auth — CORS just stops random LAN pages from calling us.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    store.add_scam(_validated("scam_detection", event))
    return {"accepted": event["event_id"]}


@app.post("/ingest/counterfeit")
def ingest_counterfeit(event: dict) -> dict:
    store.add_counterfeit(_validated("counterfeit", event))
    return {"accepted": event["event_id"]}


@app.post("/analyze/scam")
async def analyze_scam(body: dict) -> dict:
    """Live-demo path: forward text to Fraud Shield (:8001/analyze), auto-ingest
    the contract JSON it returns, so the detection is instantly visible on the
    dashboard and available to the next fusion run."""
    if not body.get("text"):
        raise HTTPException(422, "body must contain 'text'")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{MODULES['fraud-shield']}/analyze", json=body)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-shield service unreachable: {exc}") from exc
    event = _validated("scam_detection", r.json())
    store.add_scam(event)
    return event


@app.post("/analyze/counterfeit")
async def analyze_counterfeit(body: dict) -> dict:
    """Live-demo path for notes: forward a base64 image to Counterfeit Vision
    (:8002/analyze_b64), auto-ingest the contract JSON it returns."""
    if not body.get("image_b64"):
        raise HTTPException(422, "body must contain 'image_b64'")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{MODULES['counterfeit-vision']}/analyze_b64", json=body)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"counterfeit-vision service unreachable: {exc}") from exc
    event = _validated("counterfeit", r.json())
    store.add_counterfeit(event)
    return event


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


@app.post("/demo/inject-ring")
async def demo_inject_ring(body: dict | None = None) -> dict:
    """Inject a fresh ring into the fraud graph, then refresh dashboard state."""
    payload = body or {}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{MODULES['fraud-graph']}/demo/inject-ring", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-graph service unreachable: {exc}") from exc
    if r.status_code >= 400:
        # Pass module validation errors (e.g. "need at least 3 names") through
        # as-is instead of masking them as a 502 "unreachable".
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise HTTPException(r.status_code, detail)
    graph = r.json()
    store.set_fraud_graph(graph)
    return graph


@app.post("/demo/score-custom")
async def demo_score_custom(body: dict | None = None) -> dict:
    """Fraud console proxy: forward human-designed transactions for scoring;
    if the engine caught a ring (and committed it), refresh dashboard state."""
    payload = body or {}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{MODULES['fraud-graph']}/demo/score-custom", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-graph service unreachable: {exc}") from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise HTTPException(r.status_code, detail)
    result = r.json()
    if result.get("committed"):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                g = await client.get(f"{MODULES['fraud-graph']}/fraud-graph")
                if g.status_code == 200:
                    store.set_fraud_graph(g.json())
        except httpx.HTTPError:
            pass  # scoring succeeded; the dashboard will catch up on next refresh
    return result


@app.post("/demo/reset")
async def demo_reset() -> dict:
    """Drop injected rings (rehearsal cleanup), then refresh dashboard state."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{MODULES['fraud-graph']}/demo/reset")
            r.raise_for_status()
            graph = r.json()
            store.set_fraud_graph(graph)
            return {"reset": True, "rings": len(graph.get("rings", []))}
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


@app.get("/intel/plate-families")
def intel_plate_families() -> dict:
    """Plate-family linkage — group fake notes by shared printing-defect
    signature (missing_features). Same defects + same denomination is
    consistent with a common production source: standard currency-forensics
    practice (counterfeit "classes"), framed as an investigative lead."""
    from .intel import plate_families, plate_family_summary

    _, counterfeits, _ = store.snapshot()
    families = plate_families(counterfeits)
    return {
        "families": families,
        "summary": plate_family_summary(families),
        "disclaimer": (
            "Defect-signature matching is an investigative lead based on shared "
            "printing defects — not forensic proof of common origin."
        ),
    }


@app.get("/supply-trail")
def supply_trail(mode: str | None = None) -> dict:
    """Supply Trail — infer counterfeit note provenance along transport corridors.

    Takes all fake-note seizures currently in the store (location_hint required),
    snaps them to the closest rail/road/ship/air corridor, traces the cluster
    toward the likely injection point, and corroborates with the FIR corpus.

    Returns the highest-confidence trail, plus trails for all other modes that
    had at least one seizure snap.

    Query param:
        mode: optional filter — one of rail | road | ship | air
              (omit to return the best trail regardless of mode)

    Response:
        {
          "best_trail": <TrailObject | null>,
          "all_trails": [<TrailObject>, ...],   // sorted by confidence desc
          "seizures_used": N,
          "disclaimer": "..."
        }
    """
    from aegis_supply_trail import compute_trail, compute_trails_all_modes

    _, counterfeits, _ = store.snapshot()

    # Only use fake/uncertain verdicts with a known location
    seizures = [
        {
            "event_id": c.get("event_id", "unknown"),
            "lat": c["location_hint"]["lat"],
            "lon": c["location_hint"]["lon"],
            "district": c["location_hint"].get("district", "unknown"),
            "denomination": c.get("denomination", "unknown"),
            "timestamp": c.get("timestamp", ""),
        }
        for c in counterfeits
        if c.get("verdict") in ("fake", "uncertain")
        and c.get("location_hint")
        and c["location_hint"].get("lat")
        and c["location_hint"].get("lon")
    ]

    if not seizures:
        return {
            "best_trail": None,
            "all_trails": [],
            "seizures_used": 0,
            "disclaimer": (
                "No located fake-note seizures in the store yet. "
                "Analyse a note with a location_hint set to fake/uncertain to generate a trail."
            ),
        }

    best = compute_trail(seizures, mode_filter=mode)
    all_trails = compute_trails_all_modes(seizures) if mode is None else ([best] if best else [])

    return {
        "best_trail": best,
        "all_trails": all_trails,
        "seizures_used": len(seizures),
        "disclaimer": (
            "Supply Trail is an investigative hypothesis — a weighted inference "
            "from seizure locations, transport geodata, and public intelligence. "
            "Not forensic proof. FIR corpus is representative sample data pending "
            "law-enforcement integration."
        ),
    }
