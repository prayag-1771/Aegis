"""Fraud Shield API — the live hand-off surface to the command centre.

Run from `fraud-shield-nlp/`:

    uvicorn aegis_fraud_shield.api:app --app-dir src --port 8001 --reload

Endpoints:
    GET  /            demo chat UI (the "watch it catch a scam" moment)
    GET  /live-call   Live Call Shield — scripted replay + live-mic call scoring
    GET  /whatsapp    WhatsApp bot simulator (same reply template the Twilio
                      webhook will send once /webhook/whatsapp lands)
    GET  /health      model status + thresholds
    POST /analyze     {text, source?, phone_number?, location_hint?}
                      -> contract-valid scam_detection JSON
    POST /webhook/whatsapp
                      Twilio inbound-message webhook (form-encoded) -> TwiML
                      reply. Point the Twilio WhatsApp sandbox "when a message
                      comes in" URL at https://<tunnel>/webhook/whatsapp

CORS is wide open on purpose: the command centre dashboard (different origin,
Pushkar's module) calls /analyze directly during integration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .analyze import analyze
from .model import MODEL_FILE, ScamClassifier

UI_DIR = Path(__file__).parent / "ui"
UI_FILE = UI_DIR / "index.html"


def _load_env_file() -> None:
    """Pick up TWILIO_* from fraud-shield-nlp/.env (gitignored) so the server
    works without exporting env vars by hand. Real env always wins."""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

app = FastAPI(title="Aegis Fraud Shield", version="0.1.0")
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

_model: ScamClassifier | None = None
_model_lock = Lock()


def get_model() -> ScamClassifier:
    global _model
    if _model is None:
        with _model_lock:  # concurrent first requests must not double-load
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

@app.get("/favicon.png")
def favicon() -> FileResponse:
    return FileResponse(UI_DIR / "favicon.png", media_type="image/png")


@app.get("/config.js")
def config_js() -> Response:
    """Runtime config for the static citizen pages: where the command centre
    lives. Env-driven so the same HTML works locally and on Render."""
    cc = os.environ.get("COMMAND_CENTRE_URL", "http://127.0.0.1:8000")
    return Response(
        f'window.AEGIS_COMMAND_CENTRE = "{cc}";', media_type="application/javascript"
    )


@app.get("/live-call")
def live_call_ui() -> FileResponse:
    return FileResponse(UI_DIR / "live-call.html", media_type="text/html")


@app.get("/whatsapp")
def whatsapp_ui() -> FileResponse:
    return FileResponse(UI_DIR / "whatsapp.html", media_type="text/html")


# --- Twilio WhatsApp webhook ------------------------------------------------

# Keep in sync with buildReply() in ui/whatsapp.html — the simulator promises
# citizens the exact reply the real bot sends.
_WA_TYPE_LABEL = {
    "digital_arrest": "digital arrest", "phishing": "phishing",
    "lottery": "lottery", "loan": "loan", "kyc": "KYC",
}

_WA_HELP = ("🛡️ Aegis Shield: forward any suspicious SMS or WhatsApp text "
            "here and I will check it for scam patterns.")


def build_whatsapp_reply(r: dict) -> str:
    """The bot's reply body (WhatsApp *bold* markup) for one analysis result."""
    pct = round(r["risk_score"] * 100)
    markers = ", ".join(m.replace("_", " ") for m in r["markers"])
    scam_type = _WA_TYPE_LABEL.get(r["scam_type"], "")
    if r["verdict"] == "scam":
        return (
            f"🚨 *HIGH RISK — {pct}%*\n"
            f"This message matches a *{scam_type + ' ' if scam_type else ''}scam*.\n"
            + (f"Detected: {markers}\n" if markers else "")
            + "\n⛔ Do NOT click any link\n⛔ Do NOT share OTP or bank details"
              "\n🚫 Block the sender · report at 1930"
        )
    if r["verdict"] == "suspicious":
        return (
            f"⚠️ *SUSPICIOUS — {pct}%*\n"
            f"This message shows warning signs{f' ({markers})' if markers else ''}.\n"
            "\n🔍 Verify with the organisation on their official app or number "
            "before acting. Do not use links or numbers from the message itself."
        )
    return (
        f"✅ *Looks safe — risk {pct}%*\n"
        "No scam patterns detected.\n"
        "\n🙏 Stay alert: never share OTPs, and check unexpected payment "
        "requests by calling the person directly."
    )


def _twilio_signature_ok(request: Request, form: dict[str, str], token: str) -> bool:
    """Validate X-Twilio-Signature: HMAC-SHA1 over the public URL plus the
    POST params sorted by name. Honour tunnel forwarding headers (ngrok /
    cloudflared) so the URL we hash matches the one Twilio signed."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    url = f"{proto}://{host}{request.url.path}"
    if request.url.query:
        url += "?" + request.url.query
    payload = url + "".join(k + v for k, v in sorted(form.items()))
    expected = base64.b64encode(
        hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, request.headers.get("x-twilio-signature", ""))


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    # Twilio posts application/x-www-form-urlencoded; parse by hand to avoid
    # a python-multipart dependency.
    raw = (await request.body()).decode("utf-8")
    form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if token and not _twilio_signature_ok(request, form, token):
        raise HTTPException(status_code=403, detail="invalid Twilio signature")

    text = (form.get("Body") or "").strip()
    if not text:
        reply = _WA_HELP
    else:
        sender = form.get("From", "").removeprefix("whatsapp:")
        result = analyze(
            text[:20000], get_model(), source="whatsapp",
            phone_number=sender or None,
        )
        reply = build_whatsapp_reply(result)

    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f"<Response><Message>{xml_escape(reply)}</Message></Response>")
    return Response(content=xml, media_type="text/xml")
