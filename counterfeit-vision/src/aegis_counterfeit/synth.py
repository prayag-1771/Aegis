"""Synthetic bank-note renderer (the locked v1 fallback dataset).

Why synthetic (decided Day 1, per the plan's "decide early, don't wait"):
- No Kaggle API credentials on the build machine; `data.py` keeps the download
  hook ready to swap the real dataset in without touching the pipeline.
- Rendering notes ourselves gives **per-feature ground truth** — we know
  exactly which security feature each fake is missing, so the OpenCV feature
  checks are directly validatable. No public dataset labels that.

The renderer draws a simplified but geometrically faithful note: base tint per
denomination, dashed dark-green security thread at the real thread position,
a bright watermark oval, a microprint band, corner numerals and a serial
number — then applies camera-style perturbations (rotation, brightness, blur,
sensor noise). Fakes omit/degrade features the way real counterfeits do.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import DATA_DIR, NOTE_SIZE, SynthConfig

# Feature names and note geometry are OWNED BY features.py — the module that
# describes the real Mahatma Gandhi (New) Series layout. The renderer follows
# the real layout; the checks must never follow the renderer. (They used to:
# features.py imported these coordinates from here, which made "is the thread
# where a real note's thread is" mean "does this look like our own drawing".)
from .features import (
    CHECKABLE_FEATURES,
    MICROPRINT,
    MICROPRINT_Y,
    SECURITY_THREAD,
    THREAD_X,
    WATERMARK,
    WATERMARK_X,
    WATERMARK_Y,
)

_BASE_COLOR = {
    "500": (152, 150, 140),   # stone grey
    "2000": (205, 125, 165),  # magenta
}


@dataclass
class NoteSpec:
    """Everything needed to render one note + its ground truth."""

    denomination: str = "500"
    is_fake: bool = False
    missing_features: list[str] = field(default_factory=list)
    seed: int = 0


def _noise(img: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    arr = np.asarray(img, dtype=np.float32)
    arr += rng.normal(0.0, sigma, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def render_note(spec: NoteSpec) -> Image.Image:
    """Render one note per spec. Deterministic for a given spec."""
    rng = random.Random(spec.seed)
    nprng = np.random.default_rng(spec.seed)
    w, h = NOTE_SIZE
    base = _BASE_COLOR[spec.denomination]

    img = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(img)

    # Paper texture: soft horizontal tone bands.
    for y in range(0, h, 4):
        delta = int(6 * np.sin(y / 17.0))
        draw.line([(0, y), (w, y)], fill=tuple(c + delta for c in base))

    # Border + ornament block. Kept CLEAR of all three inspected regions: the
    # watermark window (x 0.105-0.335), the thread band (x 0.34-0.50) and the
    # microprint band (y 0.84). On a real note the watermark area is unprinted,
    # and an ornament drawn across it darkens the check's comparison ring — a
    # removed watermark then still measures a positive brightness lift and goes
    # undetected. (It used to sit at x 0.06-0.30, which was "left of the
    # watermark area" only while the watermark was mis-placed at x=0.80.)
    draw.rectangle([4, 4, w - 5, h - 5], outline=(60, 60, 60), width=2)
    draw.rectangle([int(w * 0.60), int(h * 0.20), int(w * 0.78), int(h * 0.66)],
                   outline=(90, 85, 70), width=3)

    # --- security thread (dashed dark-green vertical stripe) ---
    if SECURITY_THREAD not in spec.missing_features:
        tx = int(w * THREAD_X)
        for y0 in range(8, h - 8, 18):
            draw.rectangle([tx - 3, y0, tx + 3, y0 + 11], fill=(20, 60, 45))

    # --- watermark (subtle bright oval, right side) ---
    if WATERMARK not in spec.missing_features:
        wx, wy = int(w * WATERMARK_X), int(h * WATERMARK_Y)
        overlay = Image.new("L", (w, h), 0)
        odraw = ImageDraw.Draw(overlay)
        odraw.ellipse([wx - 38, wy - 52, wx + 38, wy + 52], fill=85)
        overlay = overlay.filter(ImageFilter.GaussianBlur(7))
        img = Image.composite(
            Image.new("RGB", (w, h), tuple(min(c + 42, 255) for c in base)), img, overlay
        )
        draw = ImageDraw.Draw(img)

    # --- microprint band (tiny repeated text; sharp when genuine) ---
    font_small = ImageFont.load_default(size=7)
    my = int(h * MICROPRINT_Y)
    micro_text = ("RBI" + spec.denomination) * 14
    draw.text((int(w * 0.08), my), micro_text, fill=(45, 45, 45), font=font_small)
    draw.text((int(w * 0.08), my + 8), micro_text, fill=(45, 45, 45), font=font_small)

    # --- denomination numerals + serial ---
    font_big = ImageFont.load_default(size=34)
    font_serial = ImageFont.load_default(size=12)
    draw.text((int(w * 0.87), int(h * 0.06)), spec.denomination, fill=(40, 40, 40), font=font_big)
    draw.text((int(w * 0.05), int(h * 0.05)), spec.denomination, fill=(40, 40, 40), font=font_big)
    # Real RBI format: digit + 2 letters + 6 digits, never I or O in the prefix
    # (serials.validate enforces exactly this). The renderer used to draw
    # "<letter><letter><6 digits>", which its own validator then classified as
    # `nonsense` — every rendered demo note flagged itself as a prop.
    serial = (f"{rng.randint(1, 9)}{rng.choice('ABCDEFGH')}{rng.choice('ABCDEFGH')}"
              f"{rng.randint(100000, 999999)}")
    draw.text((int(w * 0.62), int(h * 0.90)), serial, fill=(30, 30, 60), font=font_serial)

    # Blur the microprint band only — how cheap counterfeits actually fail.
    if MICROPRINT in spec.missing_features:
        band = img.crop((0, my - 4, w, my + 20)).filter(ImageFilter.GaussianBlur(2.8))
        img.paste(band, (0, my - 4))

    # --- camera-style perturbations (applied to every note) ---
    img = img.rotate(rng.uniform(-2.0, 2.0), expand=False, fillcolor=base)
    brightness = rng.uniform(0.90, 1.10)
    img = Image.fromarray(
        np.clip(np.asarray(img, dtype=np.float32) * brightness, 0, 255).astype(np.uint8)
    )
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 0.6)))
    return _noise(img, nprng, sigma=3.0)


def _draw_missing(cfg: SynthConfig, rng: random.Random) -> list[str]:
    probs = {
        SECURITY_THREAD: cfg.p_missing_thread,
        WATERMARK: cfg.p_missing_watermark,
        MICROPRINT: cfg.p_blurred_microprint,
    }
    missing = [f for f, p in probs.items() if rng.random() < p]
    return missing or [rng.choice(CHECKABLE_FEATURES)]  # a fake misses >= 1


def generate_dataset(cfg: SynthConfig | None = None, out_dir: Path | None = None) -> Path:
    """Write data/synth/{genuine,fake}/*.png + labels.json; returns the dir."""
    cfg = cfg or SynthConfig()
    out_dir = out_dir or (DATA_DIR / "synth")
    rng = random.Random(cfg.seed)
    labels: dict[str, dict] = {}

    for label, count in (("genuine", cfg.n_genuine), ("fake", cfg.n_fake)):
        subdir = out_dir / label
        subdir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            denom = rng.choice(["500", "2000"])
            missing = _draw_missing(cfg, rng) if label == "fake" else []
            spec = NoteSpec(
                denomination=denom,
                is_fake=(label == "fake"),
                missing_features=missing,
                seed=rng.randrange(2**31),
            )
            name = f"{label}_{i:04d}.png"
            render_note(spec).save(subdir / name)
            labels[f"{label}/{name}"] = {
                "label": label,
                "denomination": denom,
                "missing_features": missing,
            }

    (out_dir / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    return out_dir
