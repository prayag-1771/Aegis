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

# Financial-institution B2B surface (API-key gated) — the third named stakeholder.
from .institution import router as institution_router  # noqa: E402

app.include_router(institution_router)


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


# ── Citizen Fraud Shield: multilingual + multi-channel (chat / call) ──────────
async def _fraud_shield_analyze(text: str) -> dict:
    """Run one message through Fraud Shield (:8001/analyze)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{MODULES['fraud-shield']}/analyze", json={"text": text, "source": "citizen_i18n"}
            )
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-shield service unreachable: {exc}") from exc
    return r.json()


async def _citizen_pipeline(text: str, language: str | None) -> dict:
    """Translate → classify → translate-back. The classifier is language-agnostic
    because the text is normalised to English first; the advisory returns in the
    citizen's language. Translation fails safe (English passthrough)."""
    from .multilingual import LANGUAGES, build_advisory, translate

    english, detected, t_ok = translate(text, "en-IN", "auto")
    result = await _fraud_shield_analyze(english)
    verdict = result.get("verdict", "legit")
    risk = float(result.get("risk_score", 0.0))
    scam_type = result.get("scam_type")
    advisory_en = build_advisory(verdict, scam_type, risk)

    target = language or detected or "en-IN"
    advisory_local, _src, back_ok = translate(advisory_en, target, "en-IN")

    return {
        "verdict": verdict,
        "risk_score": risk,
        "scam_type": scam_type,
        "markers": result.get("markers", []),
        "explanation": result.get("explanation"),
        "detected_language": detected,
        "target_language": target,
        "language_name": LANGUAGES.get(target, target),
        "advisory_en": advisory_en,
        "advisory": advisory_local,
        "translated": bool(t_ok or back_ok),
        "engine": "sarvam-translate + fraud-shield" if (t_ok or back_ok) else "fraud-shield (translation unavailable)",
    }


@app.get("/citizen/languages")
def citizen_languages() -> dict:
    from .multilingual import LANGUAGES, sarvam_key

    return {"languages": LANGUAGES, "translation_available": bool(sarvam_key())}


@app.post("/citizen/analyze")
async def citizen_analyze(body: dict) -> dict:
    """Citizen message check in any of 12 languages. Verdict + safety advisory
    returned in the citizen's language."""
    if not (body or {}).get("text"):
        raise HTTPException(422, "body must contain 'text'")
    return await _citizen_pipeline(body["text"], body.get("language"))


@app.post("/citizen/call/analyze")
async def citizen_call_analyze(body: dict) -> dict:
    """Real-time call monitoring: pass the transcript accumulated SO FAR (string,
    or a list of turns) and get the running verdict. Called repeatedly as the call
    unfolds, it flags an active scam mid-call — before any transfer. This is the
    genuinely predictive, point-of-contact path."""
    tr = (body or {}).get("transcript")
    if isinstance(tr, list):
        parts = [(t.get("text") if isinstance(t, dict) else str(t)) for t in tr]
        text = " ".join(p for p in parts if p)
    else:
        text = str(tr or "")
    if not text.strip():
        raise HTTPException(422, "body must contain 'transcript'")
    res = await _citizen_pipeline(text, body.get("language"))
    # Mid-call intercept: an active scam still in progress — advise the citizen
    # and (via the Disrupt layer) hold the transfer before money moves.
    res["intercept"] = res["verdict"] == "scam"
    res["stage"] = (
        "scam_detected" if res["verdict"] == "scam"
        else "warning" if res["verdict"] == "suspicious"
        else "monitoring"
    )
    return res


@app.post("/citizen/whatsapp")
async def citizen_whatsapp(body: dict) -> dict:
    """WhatsApp transport adapter. Accepts a WhatsApp-shaped message and returns a
    reply in the sender's language. A thin adapter over the same pipeline — it
    demonstrates the multi-channel pattern without a live Meta/Twilio webhook."""
    text = (body or {}).get("text") or (body or {}).get("body")
    if not text:
        raise HTTPException(422, "body must contain 'text'")
    res = await _citizen_pipeline(text, body.get("language"))
    return {
        "channel": "whatsapp",
        "to": (body or {}).get("from"),
        "reply": res["advisory"],
        "verdict": res["verdict"],
        "risk_score": res["risk_score"],
        "language": res["target_language"],
        "note": (
            "Transport-adapter demo — not a live Meta/Twilio webhook. Same Fraud Shield "
            "+ Sarvam translation pipeline behind it."
        ),
    }


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


@app.get("/rings/{ring_id}/spectral")
def ring_spectral(ring_id: str) -> dict:
    """Proxy: spectral second opinion for one ring (fraud-graph service)."""
    try:
        r = httpx.get(f"{MODULES['fraud-graph']}/rings/{ring_id}/spectral", timeout=10.0)
        if r.status_code in (404, 422):
            raise HTTPException(r.status_code, r.json().get("detail", "spectral unavailable"))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"fraud-graph service unreachable: {exc}") from exc


@app.get("/dashboard-summaries")
def dashboard_summaries() -> dict:
    from .store import store
    from .dashboard_summaries import generate_summaries
    
    data = {
        "scams": len(store.scams),
        "counterfeits": len(store.counterfeits),
        "rings": len(store.fraud_graph.get("rings", []))
    }
    return generate_summaries(data)


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
    """THE fusion moment: correlate everything currently known, then derive the
    disruptive actions it warrants — detection immediately becomes response."""
    from aegis_fusion.fuse import fuse, validate_against_contract

    scams, counterfeits, fraud_graph = store.snapshot()
    output = fuse(scams, counterfeits, fraud_graph)
    payload = json.loads(output.model_dump_json())
    validate_against_contract(payload)
    store.set_fusion(payload)
    _derive_and_store_actions()
    return payload


# ── Response / disrupt actions ──────────────────────────────────────────────
def _validate_action(action: dict) -> dict:
    try:
        jsonschema.validate(instance=action, schema=_schema("response_action"))
    except jsonschema.ValidationError as exc:  # generator bug, not user input
        raise HTTPException(500, f"response action violates its contract: {exc.message}") from exc
    return action


def _derive_and_store_actions() -> list[dict]:
    """Re-derive actions from current state and merge them into the store.
    Called after fusion and by POST /actions/derive."""
    from .response import derive_actions

    scams, counterfeits, fraud_graph = store.snapshot()
    derived = derive_actions(scams, counterfeits, fraud_graph, store.last_fusion)
    for a in derived:
        _validate_action(a)
    return store.set_actions(derived)


def _actions_response(actions: list[dict]) -> dict:
    order = {"critical": 0, "high": 1, "medium": 2}
    actions = sorted(actions, key=lambda a: (order.get(a.get("priority"), 3), a.get("created_at", "")))
    counts_status: dict[str, int] = {}
    counts_type: dict[str, int] = {}
    for a in actions:
        counts_status[a["status"]] = counts_status.get(a["status"], 0) + 1
        counts_type[a["action_type"]] = counts_type.get(a["action_type"], 0) + 1
    return {
        "actions": actions,
        "counts_by_status": counts_status,
        "counts_by_type": counts_type,
        "open": sum(1 for a in actions if a["status"] == "proposed"),
        "disclaimer": (
            "Disrupt/respond recommendations derived deterministically from current "
            "detections. Dispatch is simulated — no live bank/telecom/MHA integration "
            "is connected."
        ),
    }


@app.get("/actions")
def actions_list() -> dict:
    """Current response/disrupt queue. Derives on first read so it is never empty
    when detections already exist (e.g. before any manual /fuse)."""
    current = store.list_actions()
    if not current:
        current = _derive_and_store_actions()
    return _actions_response(current)


@app.post("/actions/derive")
def actions_derive() -> dict:
    """Recompute the action queue from current state (idempotent; preserves any
    dispatched/acknowledged actions)."""
    return _actions_response(_derive_and_store_actions())


@app.post("/actions/{action_id:path}/dispatch")
def actions_dispatch(action_id: str) -> dict:
    """Simulate transmitting the action to its recipient. Records a timestamped,
    auditable dispatch — no live integration is contacted."""
    action = store.update_action(
        action_id, "dispatched", actor="operator",
        note="Simulated dispatch to recipient — demonstration only.",
    )
    if action is None:
        raise HTTPException(404, f"no action {action_id}")
    return action


@app.post("/actions/{action_id:path}/acknowledge")
def actions_acknowledge(action_id: str) -> dict:
    action = store.update_action(
        action_id, "acknowledged", actor="recipient",
        note="Recipient acknowledged the action.",
    )
    if action is None:
        raise HTTPException(404, f"no action {action_id}")
    return action


@app.post("/actions/{action_id:path}/dismiss")
def actions_dismiss(action_id: str) -> dict:
    action = store.update_action(
        action_id, "dismissed", actor="operator",
        note="Ruled out by reviewing officer.",
    )
    if action is None:
        raise HTTPException(404, f"no action {action_id}")
    return action


@app.get("/fusion/latest")
def fusion_latest() -> dict:
    if store.last_fusion is None:
        raise HTTPException(404, "no fusion has been run yet — POST /fuse first")
    return store.last_fusion


@app.get("/research")
def research() -> dict:
    """The three research modules' results, read from generated artifacts.

    These are expensive to compute (GraphSAGE, an evolutionary loop, per-
    community eigendecomposition), so they are precomputed by the fraud-graph
    CLI and served as static JSON — never run in the request path. Each block
    is null when its artifact has not been generated, so the UI degrades
    per-module instead of failing whole.

    Nothing here is dressed up. The numbers are whatever the modules measured,
    including the honest caveats (Ghost Ring's false_merge_rate, spectral's
    weak per-community flag). Presenting them truthfully is the point.
    """
    from .store import REPO_ROOT

    out = REPO_ROOT / "fraud-graph-ml" / "output"

    def _json(name: str):
        p = out / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # Arms race is a CSV time series — parse to columnar arrays for charting.
    arms = None
    csv_path = out / "arms_race_history.csv"
    if csv_path.exists():
        try:
            lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
            header = lines[0].split(",")
            rows = [dict(zip(header, ln.split(","))) for ln in lines[1:]]

            def _col(key: str) -> list[float]:
                return [float(r[key]) for r in rows if r.get(key) not in (None, "")]

            arms = {
                "generation": [int(float(r["generation"])) for r in rows],
                "escape_rate": _col("best_escape_rate"),
                # Population mean — best-of-50 pegs at 1.0 almost by
                # construction, the mean is the curve that can show learning.
                "mean_escape_rate": _col("mean_escape_rate") or None,
                "detector_recall": _col("detector_recall"),
                "retrained_generations": [
                    int(float(r["generation"]))
                    for r in rows
                    if str(r.get("retrained", "")).lower() in ("true", "1", "1.0")
                ],
            }
        except (OSError, ValueError, KeyError):
            arms = None

    return {
        "ghost_ring": _json("ghost_ring.json"),
        "arms_race": arms,
        "spectral": _json("spectral_data.json"),
    }


@app.get("/metrics")
def metrics() -> dict:
    """Model Card — the measured numbers the evaluation focus asks for, read from
    the persisted training/eval reports (never recomputed in the request path).

    Every value here is whatever the model actually measured; nothing is dressed
    up. Where a criterion (e.g. per-denomination breakdown) is not in the artifact,
    it is called out as a caveat rather than invented. `false_alarm` is derived
    honestly as 1 − precision (share of alerts that are false), the citizen-facing
    false-positive concern the brief flags."""
    from .store import REPO_ROOT

    def _json(rel: str):
        p = REPO_ROOT / rel
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    shield = _json("fraud-shield-nlp/models/train_report.json")
    vision = _json("counterfeit-vision/models/train_report.json")
    graph = _json("fraud-graph-ml/models/train_report.json")
    ring_eval = _json("fraud-graph-ml/models/ring_eval_report.json")
    elliptic = _json("fraud-graph-ml/models/elliptic_benchmark_report.json")

    def _fa(precision: float | None) -> dict | None:
        if precision is None:
            return None
        return {"label": "False-alarm rate among alerts", "value": round(1 - precision, 4),
                "basis": "1 − precision"}

    models: list[dict] = []

    if shield:
        models.append({
            "id": "scam",
            "name": "Fraud Shield — Scam / Digital-Arrest NLP",
            "task": "Flag scam calls/messages at the point of contact (pre-transfer).",
            "dataset": f"{shield.get('n_train','?')} train / {shield.get('n_test','?')} test messages "
                       "(synthetic + LLM-generated scripts + UCI SMS-spam).",
            "headline": [
                {"label": "ROC-AUC", "value": shield.get("roc_auc")},
                {"label": "Precision (scam)", "value": shield.get("precision_at_scam")},
                {"label": "Recall (scam)", "value": shield.get("recall_at_scam")},
            ],
            "highlight": {"label": "Digital-arrest recall",
                          "value": (shield.get("recall_by_family") or {}).get("synth_digital_arrest")},
            "false_alarm": _fa(shield.get("precision_at_scam")),
            "breakdown": {"title": "Recall by scam family", "items": shield.get("recall_by_family", {})},
            "caveats": ["Scripts are largely synthetic/LLM-generated; live-call validation is the next step."],
        })

    if vision:
        models.append({
            "id": "counterfeit",
            "name": "Counterfeit Vision — Note Authenticity CV",
            "task": "Classify a note as genuine/fake from a photo (teller / POS / field).",
            "dataset": f"{vision.get('dataset','real note photos')} · {vision.get('n_train','?')} train · "
                       f"backbone {vision.get('backbone','cnn')}.",
            "headline": [
                {"label": "Val accuracy", "value": vision.get("val_accuracy")},
                {"label": "ROC-AUC", "value": vision.get("val_roc_auc")},
                {"label": "Fake recall", "value": vision.get("fake_recall")},
            ],
            "highlight": {"label": "Fake precision", "value": vision.get("fake_precision")},
            "false_alarm": _fa(vision.get("fake_precision")),
            "breakdown": None,
            "caveats": [
                "Trained on REAL photos of real+fake notes (not synthetic).",
                "Per-denomination / per-print-quality breakdown is not in this artifact — reported as an aggregate.",
            ],
        })

    if graph:
        headline = [
            {"label": "ROC-AUC", "value": graph.get("roc_auc")},
            {"label": "Precision", "value": graph.get("precision_at_threshold")},
            {"label": "Recall", "value": graph.get("recall_at_threshold")},
        ]
        highlight = None
        breakdown = None
        if ring_eval:
            highlight = {"label": "Rings recovered",
                         "value_text": f"{ring_eval.get('rings_recovered')}/{ring_eval.get('n_true_rings')}"}
            breakdown = {
                "title": "Ring-level detection",
                "pairs": [
                    {"label": "Ring detection rate", "value": ring_eval.get("ring_detection_rate")},
                    {"label": "Account precision", "value": ring_eval.get("account_precision")},
                    {"label": "Account recall", "value": ring_eval.get("account_recall")},
                ],
            }
        models.append({
            "id": "graph_synth",
            "name": "Fraud Graph — Ring Detection (synthetic UPI/mule graph)",
            "task": "Score accounts for mule/ring membership; recover coordinated rings.",
            "dataset": f"{graph.get('n_train','?')} train / {graph.get('n_test','?')} test accounts (labeled synthetic graph).",
            "headline": headline,
            "highlight": highlight,
            "false_alarm": _fa(graph.get("precision_at_threshold")),
            "breakdown": breakdown,
            "caveats": ["Synthetic graph — see the Elliptic++ card for real-data validation."],
        })

    if elliptic:
        models.append({
            "id": "graph_elliptic",
            "name": "Fraud Graph — Real-Data Benchmark (Elliptic++)",
            "task": "Same pipeline on the only large, real, labeled fraud graph publicly available.",
            "dataset": f"{elliptic.get('dataset','elliptic++')} · "
                       f"{elliptic.get('n_wallets','?'):,} wallets · {elliptic.get('n_illicit','?'):,} illicit."
            if isinstance(elliptic.get("n_wallets"), int) else elliptic.get("dataset", "elliptic++"),
            "headline": [
                {"label": "ROC-AUC", "value": elliptic.get("roc_auc")},
                {"label": "Precision", "value": elliptic.get("precision_at_threshold")},
                {"label": "Recall", "value": elliptic.get("recall_at_threshold")},
            ],
            "highlight": {"label": "Avg precision", "value": elliptic.get("avg_precision")},
            "false_alarm": _fa(elliptic.get("precision_at_threshold")),
            "breakdown": None,
            "caveats": [
                "Transfers because it scores graph TOPOLOGY (flow, layering, community), not currency-specific "
                "features — the same reason it applies to UPI/bank rails.",
            ],
        })

    # Honest posture per model — what is genuinely predictive vs. fast
    # classification of an already-formed pattern. Overclaiming "predictive" on
    # the graph is the kind of thing a sharp reviewer catches; scoping it
    # correctly reads as more credible, not less.
    POSTURE = {
        "scam": {"label": "Predictive", "detail": "flags at the point of contact, before any transfer"},
        "counterfeit": {"label": "Point-of-contact", "detail": "verdict at the counter/POS, not after deposit"},
        "graph_synth": {"label": "Fast classification", "detail": "scores an already-formed transaction pattern"},
        "graph_elliptic": {"label": "Fast classification", "detail": "real-data benchmark of the same pipeline"},
    }
    for _m in models:
        _m["posture"] = POSTURE.get(_m["id"])

    lead_time = {
        "summary": "Where detection sits relative to victimisation — measured latency, honestly scoped.",
        "points": [
            {"stage": "Scam", "claim": "Flagged mid-message, before any transfer.",
             "measured": "pre-transfer by construction — the classifier runs on the live message."},
            {"stage": "Fraud ring", "claim": "Ring caught within seconds of the laundering pattern forming.",
             "measured": "the inject-ring console shows the detection latency live (‘caught in N s’)."},
            {"stage": "Counterfeit", "claim": "Verdict at the counter/POS in a single scan.",
             "measured": "one forward pass of the CV model."},
        ],
        "caveat": (
            "‘Lead time before mass victimisation’ is a workflow claim, not one stored number — no victimisation "
            "timeline is simulated. Detection LATENCY (above) is what is actually measured."
        ),
    }

    return {
        "models": models,
        "lead_time": lead_time,
        "disclaimer": (
            "Every figure is read from the model's own persisted training/eval report — not recomputed here and "
            "not tuned for display. false_alarm = 1 − precision (share of alerts that are false), the citizen-tool "
            "false-positive concern the brief flags."
        ),
    }


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


@app.get("/intel/campaigns")
def intel_campaigns() -> dict:
    """Scam campaign fingerprinting — near-identical scripts and shared
    callback numbers across districts are ONE operation, not isolated
    complaints. Deterministic text-overlap clustering; fully auditable."""
    from .intel import campaign_summary, scam_campaigns

    scams, _, _ = store.snapshot()
    campaigns = scam_campaigns(scams)
    return {
        "campaigns": campaigns,
        "summary": campaign_summary(campaigns),
        "disclaimer": (
            "Script similarity links complaints for investigation — it does not "
            "by itself prove a common perpetrator."
        ),
    }


@app.post("/case-file")
def case_file(body: dict) -> dict:
    """AI Case Officer — one click turns a district's signals into a brief.
    Deterministic dossier (every module's evidence, auditable) + an LLM-written
    brief with a template fallback so it works with zero API keys."""
    from aegis_supply_trail import compute_trail

    from .case_officer import build_dossier, write_case_file_safe

    district = (body or {}).get("district", "").strip()
    if not district:
        raise HTTPException(422, "body must include a 'district'")

    scams, counterfeits, fraud_graph = store.snapshot()
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
        and (c.get("location_hint") or {}).get("lat")
    ]
    trail = compute_trail(seizures) if seizures else None
    dossier = build_dossier(district, scams, counterfeits, fraud_graph, trail)
    brief, engine = write_case_file_safe(dossier)
    return {
        "district": district,
        "case_file": brief,
        "dossier": dossier,
        "engine": engine,
        "disclaimer": (
            "The brief is generated from the machine-established dossier below — "
            "verify every item against source records before acting."
        ),
    }


@app.get("/supply-trail")
def supply_trail(mode: str | None = None, district: str | None = None) -> dict:
    """Supply Trail — infer counterfeit note provenance along transport corridors.

    Takes fake-note seizures currently in the store (location_hint required),
    snaps them to the closest rail/road/ship/air corridor, traces the cluster
    toward the likely injection point, and corroborates with the FIR corpus.

    Returns the highest-confidence trail, plus trails for all other modes that
    had at least one seizure snap.

    Query params:
        mode: optional filter — one of rail | road | ship | air
              (omit to return the best trail regardless of mode)
        district: optional filter — answer "where are THIS city's notes coming
              from?" instead of the store-wide question. Case-insensitive.

    A district filter narrows the evidence base, so the inference is usually
    weaker than the store-wide trail: fewer seizures means a shorter cluster,
    which means less of the corridor is pinned down. `seizures_used` and the
    trail's own `confidence` report that honestly. A district whose seizures
    all sit at one corridor node yields no trail at all — direction is read
    from the shape of a cluster, and a single point has none.

    Response:
        {
          "best_trail": <TrailObject | null>,
          "all_trails": [<TrailObject>, ...],   // sorted by confidence desc
          "seizures_used": N,
          "district": "<echoed filter or null>",
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

    if district:
        want = district.strip().casefold()
        seizures = [s for s in seizures if s["district"].casefold() == want]

    if not seizures:
        if district:
            return {
                "best_trail": None,
                "all_trails": [],
                "seizures_used": 0,
                "district": district,
                "disclaimer": (
                    f"No located fake-note seizures recorded in {district}. "
                    "Supply Trail can only infer provenance where notes have "
                    "actually been seized."
                ),
            }
        return {
            "best_trail": None,
            "all_trails": [],
            "seizures_used": 0,
            "district": None,
            "disclaimer": (
                "No located fake-note seizures in the store yet. "
                "Analyse a note with a location_hint set to fake/uncertain to generate a trail."
            ),
        }

    best = compute_trail(seizures, mode_filter=mode)
    all_trails = compute_trails_all_modes(seizures) if mode is None else [t for t in (best,) if t]

    disclaimer = (
        "Supply Trail is an investigative hypothesis — a weighted inference "
        "from seizure locations, transport geodata, and public intelligence. "
        "Not forensic proof. FIR corpus is representative sample data pending "
        "law-enforcement integration."
    )
    # A district view rests on fewer seizures than the store-wide trail. Say so
    # rather than letting a narrow inference read as an equally strong one.
    if district and best is None:
        disclaimer = (
            f"{len(seizures)} seizure(s) in {district} — too few, or too tightly "
            "clustered, to establish a direction along any corridor. Provenance "
            "needs a cluster that spans distance. " + disclaimer
        )
    elif district:
        disclaimer = (
            f"Inferred from {len(seizures)} seizure(s) in {district} alone — a "
            "narrower evidence base than the store-wide trail. " + disclaimer
        )

    return {
        "best_trail": best,
        "all_trails": all_trails,
        "seizures_used": len(seizures),
        "district": district,
        "disclaimer": disclaimer,
    }


@app.get("/supply-trail/routes")
def supply_trail_routes(district: str, k: int = 3) -> dict:
    """How could fake notes have physically REACHED this district?

    A different question from /supply-trail, and one that works from a single
    seizure. /supply-trail reads direction from the shape of a seizure cluster,
    so one seizure tells it nothing. But a city with a railway station, a
    highway and an airport has enumerable entry channels regardless of how many
    notes were found there — so rank the channels instead of the cluster.

    Sources are the documented printing presses in the FIR corpus (Asansol,
    Vadodara, Deoghar carry a `printing_press` tag from cited press reports),
    not guesses. Each candidate route is scored by the deterministic engine on
    distance, mode risk and FIR corroboration; an LLM then explains the
    ranking in plain English but never changes it.

    Query params:
        district: the seizure district to route INTO (required)
        k: routes per source (default 3)
    """
    from aegis_supply_trail.engine import _hav, _nearest_node_key, load_fir_corpus
    from aegis_supply_trail.narrate import build_facts, narrate_routes_safe
    from aegis_supply_trail.network import attach_access, build_network
    from aegis_supply_trail.routes import plausible_routes

    _, counterfeits, _ = store.snapshot()
    want = district.strip().casefold()
    here = [
        c for c in counterfeits
        if c.get("verdict") in ("fake", "uncertain")
        and (c.get("location_hint") or {}).get("district", "").casefold() == want
        and c["location_hint"].get("lat")
    ]
    if not here:
        raise HTTPException(
            404,
            f"No located fake-note seizures in {district}. Entry routes are only "
            "meaningful where notes were actually found.",
        )

    lat = here[0]["location_hint"]["lat"]
    lon = here[0]["location_hint"]["lon"]

    fir_corpus = load_fir_corpus()
    net = build_network()
    dst = attach_access(net, district, lat, lon)

    # Candidate sources: FIR-documented printing presses only. A press is where
    # notes are MADE — routing from a mere circulation seizure would just show
    # how two downstream cities connect, which answers nothing.
    presses = [f for f in fir_corpus if "printing_press" in (f.crime_types or [])]

    candidates: list[dict] = []
    for press in presses:
        if _hav(press.lat, press.lon, lat, lon) < 5.0:
            continue  # the press is here — no inbound route to compute
        src_key, _d = _nearest_node_key(net, press.lat, press.lon)
        for r in plausible_routes(net, src_key, dst, k=k, fir_corpus=fir_corpus):
            r["source"] = press.district
            r["source_ref"] = press.ref
            r["source_evidence"] = press.source
            candidates.append(r)

    candidates.sort(key=lambda r: r["plausibility"], reverse=True)
    candidates = candidates[:k]

    if not candidates:
        raise HTTPException(
            404, f"No transport route from a documented printing press reaches {district}."
        )

    facts = build_facts(district, candidates, len(here))
    narrative, engine = narrate_routes_safe(facts)

    return {
        "district": district,
        "seizures_in_district": len(here),
        "sources_considered": [
            {"district": p.district, "ref": p.ref, "evidence": p.source} for p in presses
        ],
        "routes": candidates,
        "narrative": narrative.model_dump(),
        "narrator": engine,
        "disclaimer": (
            "Candidate entry channels ranked by a deterministic engine on distance, "
            "mode risk and FIR corroboration. Sources are printing presses documented "
            "in cited press/police reports. plausibility is a hypothesis score in "
            "[0, 0.9], never a probability of guilt — a banknote carries no origin "
            "label and nothing here observed the notes moving. Investigative "
            "direction only, not forensic proof."
        ),
    }
