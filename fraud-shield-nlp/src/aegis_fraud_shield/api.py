"""Fraud Shield API — the live hand-off surface to the command centre.

Run from `fraud-shield-nlp/`:

    uvicorn aegis_fraud_shield.api:app --app-dir src --port 8001 --reload

Endpoints:
    GET  /            demo chat UI (the "watch it catch a scam" moment)
    GET  /health      model status + thresholds
    POST /analyze     {text, source?, phone_number?, location_hint?}
                      -> contract-valid scam_detection JSON

CORS is wide open on purpose: the command centre dashboard (different origin,
Pushkar's module) calls /analyze directly during integration.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .analyze import analyze
from .model import MODEL_FILE, ScamClassifier

UI_FILE = Path(__file__).parent / "ui" / "index.html"

app = FastAPI(title="Aegis Fraud Shield", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_model: ScamClassifier | None = None


def get_model() -> ScamClassifier:
    global _model
    if _model is None:
        if not MODEL_FILE.exists():
            raise HTTPException(
                status_code=503,
                detail="Model not trained. Run: python -m aegis_fraud_shield.cli train",
            )
        _model = ScamClassifier.load()
    return _model


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    source: str = Field(
        default="manual_demo",
        pattern="^(sms|call_transcript|whatsapp|email|manual_demo)$",
    )
    phone_number: str | None = None
    location_hint: dict | None = None


@app.get("/health")
def health() -> dict:
    trained = MODEL_FILE.exists()
    out: dict = {"status": "ok", "model_trained": trained}
    if trained:
        model = get_model()
        out["scam_threshold"] = model.scam_threshold
        out["suspicious_threshold"] = model.suspicious_threshold
        out["trained_at"] = model.trained_at
    return out


@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> dict:
    return analyze(
        req.text,
        get_model(),
        source=req.source,
        phone_number=req.phone_number,
        location_hint=req.location_hint,
    )


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(UI_FILE, media_type="text/html")
