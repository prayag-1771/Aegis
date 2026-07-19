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
import os
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from .analyze import analyze_image
from .config import CAPTURES_DIR
from .model import META_FILE, CounterfeitModel

UI_FILE = Path(__file__).parent / "ui" / "index.html"

# Decompression-bomb guard: a hostile PNG can expand to gigabytes of pixels.
Image.MAX_IMAGE_PIXELS = 50_000_000
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Aegis Counterfeit Vision", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Local-origin browsers only (command centre + demo UIs).
    # Local dev + deployed frontends (Vercel) and sibling services (Render).
    allow_origin_regex=os.environ.get(
        "ALLOWED_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://[A-Za-z0-9-]+\.(vercel\.app|onrender\.com)",
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)
# Serve saved scans so the dashboard can display image_ref.
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/captures", StaticFiles(directory=CAPTURES_DIR), name="captures")

_model: CounterfeitModel | None = None
_model_lock = Lock()


def get_model() -> CounterfeitModel:
    global _model
    if _model is None:
        with _model_lock:  # concurrent first requests must not double-load
            if _model is None:
                if not META_FILE.exists():
                    raise HTTPException(
                        status_code=503,
                        detail="Model not trained. Run: python -m aegis_counterfeit.cli train",
                    )
                _model = CounterfeitModel.load()
    return _model


class AnalyzeB64Request(BaseModel):
    image_b64: str = Field(max_length=MAX_UPLOAD_BYTES * 4 // 3 + 128)
    location_hint: dict | None = None
    serial_number: str | None = Field(default=None, max_length=20)


def _open_image(raw: bytes) -> Image.Image:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="image too large (15 MB max)")
    try:
        return Image.open(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001 — unreadable/bomb images are a 400
        raise HTTPException(status_code=400, detail=f"Not a readable image: {exc}") from exc


def _analyze_pil(img: Image.Image, location_hint: dict | None = None,
                 serial_number: str | None = None) -> dict:
    return analyze_image(img, get_model(), location_hint=location_hint,
                         save_capture=True, serial_number=serial_number)


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
async def analyze_upload(file: UploadFile = File(...),
                         serial_number: str | None = Form(default=None)) -> dict:
    return _analyze_pil(_open_image(await file.read()), serial_number=serial_number)


@app.post("/analyze_b64")
def analyze_b64(req: AnalyzeB64Request) -> dict:
    try:
        raw = base64.b64decode(req.image_b64.split(",", 1)[-1])  # tolerate data: URLs
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Bad base64 image: {exc}") from exc
    return _analyze_pil(_open_image(raw), req.location_hint, req.serial_number)


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(UI_FILE, media_type="text/html")

@app.get("/favicon.png")
def favicon() -> FileResponse:
    return FileResponse(Path(__file__).parent / "ui" / "favicon.png", media_type="image/png")


@app.get("/config.js")
def config_js() -> Response:
    """Runtime config for the static scan page: where the command centre
    lives. Env-driven so the same HTML works locally and on Render."""
    cc = os.environ.get("COMMAND_CENTRE_URL", "http://127.0.0.1:8000")
    return Response(
        f'window.AEGIS_COMMAND_CENTRE = "{cc}";', media_type="application/javascript"
    )
