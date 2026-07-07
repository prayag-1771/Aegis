"""Counterfeit Vision API — the live hand-off surface to the command centre.

Run from `counterfeit-vision/`:

    uvicorn aegis_counterfeit.api:app --app-dir src --port 8002 --reload

Endpoints:
    GET  /            camera/upload demo UI (the "hold a note to the camera" moment)
    GET  /health      model status + thresholds
    POST /analyze     multipart image upload -> contract-valid counterfeit JSON
    POST /analyze_b64 {"image_b64": "..."} -> same (what the webcam UI sends)

CORS wide open on purpose: the command centre dashboard calls this directly.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel

from .analyze import analyze_image
from .model import META_FILE, CounterfeitModel

UI_FILE = Path(__file__).parent / "ui" / "index.html"

app = FastAPI(title="Aegis Counterfeit Vision", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_model: CounterfeitModel | None = None


def get_model() -> CounterfeitModel:
    global _model
    if _model is None:
        if not META_FILE.exists():
            raise HTTPException(
                status_code=503,
                detail="Model not trained. Run: python -m aegis_counterfeit.cli train",
            )
        _model = CounterfeitModel.load()
    return _model


class AnalyzeB64Request(BaseModel):
    image_b64: str
    location_hint: dict | None = None


def _analyze_pil(img: Image.Image, location_hint: dict | None = None) -> dict:
    return analyze_image(img, get_model(), location_hint=location_hint, save_capture=True)


@app.get("/health")
def health() -> dict:
    trained = META_FILE.exists()
    out: dict = {"status": "ok", "model_trained": trained}
    if trained:
        model = get_model()
        out.update(
            backbone=model.backbone,
            fake_threshold=model.fake_threshold,
            genuine_threshold=model.genuine_threshold,
            trained_at=model.trained_at,
        )
    return out


@app.post("/analyze")
async def analyze_upload(file: UploadFile = File(...)) -> dict:
    try:
        img = Image.open(io.BytesIO(await file.read()))
    except Exception as exc:  # noqa: BLE001 — any unreadable image is a 400
        raise HTTPException(status_code=400, detail=f"Not a readable image: {exc}") from exc
    return _analyze_pil(img)


@app.post("/analyze_b64")
def analyze_b64(req: AnalyzeB64Request) -> dict:
    try:
        raw = req.image_b64.split(",", 1)[-1]  # tolerate data: URL prefixes
        img = Image.open(io.BytesIO(base64.b64decode(raw)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Bad base64 image: {exc}") from exc
    return _analyze_pil(img, req.location_hint)


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(UI_FILE, media_type="text/html")
