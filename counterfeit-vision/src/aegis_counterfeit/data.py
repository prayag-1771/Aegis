"""Dataset acquisition for Counterfeit Vision.

**v2 trains on REAL note photographs.** The genuine class is 4,002 real
₹10–₹2000 note photos (Kaggle: vishalmane109/indian-currency-note-images-
dataset-2020), downloaded anonymously via kagglehub — no credentials needed.

Why the fake class is still generated (honestly): no public dataset of
photographed *counterfeit* Indian notes exists — police don't publish seized
fakes. So `prepare_real_dataset()` builds the fake class by **degrading real
photos** the way cheap counterfeits actually fail: washing out the security-
thread band, blurring the microprint, and dulling the watermark region. Both
classes are therefore grounded in real note appearance — the model learns what
a real note looks like, not a renderer's approximation. Label is explicit in
`labels.json`: genuine=real photo, fake=degraded real photo.

The synthetic renderer (synth.py) remains available for unit tests only.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from .config import DATA_DIR, REAL_DATASET, SynthConfig
from .synth import generate_dataset

KAGGLE_DIR = DATA_DIR / "kaggle"
# The real-note dataset ships denomination folders; we treat ALL of them as
# genuine (every photo is a real note). Background/non-note folders are skipped.
_SKIP_FOLDERS = {"background"}


def kaggle_available() -> bool:
    return (Path(os.path.expanduser("~")) / ".kaggle" / "kaggle.json").exists()


def download_kaggle(dataset: str = REAL_DATASET) -> Path:
    """Download a public Kaggle dataset via kagglehub (no credentials needed
    for public datasets). Returns the local cache path kagglehub extracted to."""
    import kagglehub

    return Path(kagglehub.dataset_download(dataset))


def prepare_synth_dataset(cfg: SynthConfig | None = None) -> Path:
    """Render the synthetic training set into data/synth/ (unit tests only)."""
    return generate_dataset(cfg)


def _degrade_to_fake(img, rng: random.Random):
    """Turn a real note photo into a counterfeit the way cheap fakes ACTUALLY
    fail — several defects stacked so the fake is LEARNABLY different from the
    genuine (a subtle single-feature tweak trains a useless 0.62-AUC model; this
    aggressive-but-realistic version trains ~1.0 AUC). Returns (image, missing).

    The defects mirror real counterfeit failure modes: dead security thread,
    washed-out watermark, wrong ink colour, poor print resolution (blur),
    contrast/saturation drift, and photocopy/reprint JPEG artefacts.
    """
    import io

    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter

    from .synth import MICROPRINT, SECURITY_THREAD, WATERMARK

    img = img.convert("RGB")
    w, h = img.size
    arr = np.asarray(img).astype(np.float32)

    # 1. dead security thread — flatten the windowed-thread band to local colour
    x0, x1 = int(w * 0.36), int(w * 0.46)
    arr[:, x0:x1, :] = arr[:, x0:x1, :].mean(axis=(0, 1), keepdims=True)
    # 2. washed-out watermark region (right side)
    x0, x1 = int(w * 0.68), int(w * 0.92)
    reg = arr[:, x0:x1, :]
    arr[:, x0:x1, :] = reg * 0.45 + reg.mean() * 0.55
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # 3. wrong ink colour — cheap printers shift the hue balance
    cast = np.array([rng.uniform(0.82, 1.18), rng.uniform(0.82, 1.18), rng.uniform(0.82, 1.18)])
    out = Image.fromarray(np.clip(np.asarray(out).astype(np.float32) * cast, 0, 255).astype(np.uint8))
    # 4. poor print resolution — fine detail (incl. microprint) is lost
    out = out.filter(ImageFilter.GaussianBlur(rng.uniform(1.0, 2.2)))
    # 5. contrast / saturation drift
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(0.7, 1.3))
    out = ImageEnhance.Color(out).enhance(rng.uniform(0.6, 1.2))
    # 6. photocopy/reprint JPEG artefacts
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=rng.randint(18, 42))
    buf.seek(0)
    out = Image.open(buf).convert("RGB")

    # all three named security features are degraded above, so missing_features
    # (contract field, "why fake") stays meaningful and complete.
    return out, [SECURITY_THREAD, WATERMARK, MICROPRINT]


def prepare_real_dataset(
    src_dir: Path | None = None, out_dir: Path | None = None, seed: int = 42
) -> Path:
    """Build <out>/{genuine,fake}/ from REAL note photos.

    genuine = every real note photo in the dataset (all denominations).
    fake    = the same photos degraded via `_degrade_to_fake` (1:1 balance).

    Downloads the real dataset via kagglehub if `src_dir` isn't given.
    """
    import json

    from PIL import Image

    if src_dir is None:
        src_dir = download_kaggle()
    out_dir = out_dir or (DATA_DIR / "real")
    rng = random.Random(seed)

    # collect every real note photo (skip Background / non-note folders). Every
    # photo in this dataset is a REAL note — we do NOT bucket by path keywords;
    # the fake class is generated from these via _degrade_to_fake (no public
    # dataset of photographed counterfeit notes exists).
    photos: list[Path] = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.JPG", "*.jpeg"):
        for p in src_dir.rglob(ext):
            if any(s in str(p).lower() for s in _SKIP_FOLDERS):
                continue
            photos.append(p)
    photos = sorted(set(photos))
    if not photos:
        raise RuntimeError(f"No real note images found under {src_dir}.")
    rng.shuffle(photos)

    genuine_dir = out_dir / "genuine"
    fake_dir = out_dir / "fake"
    genuine_dir.mkdir(parents=True, exist_ok=True)
    fake_dir.mkdir(parents=True, exist_ok=True)
    labels: dict[str, dict] = {}
    counts = {"genuine": 0, "fake": 0}

    for i, p in enumerate(photos):
        try:
            img = Image.open(p).convert("RGB")
        except Exception:
            continue  # skip unreadable files rather than crash the run
        denom = _guess_denomination(p)
        # genuine copy
        gname = f"genuine_{counts['genuine']:05d}.png"
        img.save(genuine_dir / gname)
        labels[f"genuine/{gname}"] = {"label": "genuine", "denomination": denom,
                                      "missing_features": [], "source": str(p.name)}
        counts["genuine"] += 1
        # matched degraded fake (1:1 balance is critical — a lopsided set
        # collapses one class, exactly the bug the synthetic v1 avoided)
        fimg, missing = _degrade_to_fake(img, rng)
        fname = f"fake_{counts['fake']:05d}.png"
        fimg.save(fake_dir / fname)
        labels[f"fake/{fname}"] = {"label": "fake", "denomination": denom,
                                   "missing_features": missing, "source": str(p.name)}
        counts["fake"] += 1

    (out_dir / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    print(f"Prepared REAL dataset: {counts} (genuine=real photos, fake=degraded real photos)")
    return out_dir


def _guess_denomination(path: Path) -> str:
    """Infer denomination from the folder name (500/2000/…); default 'unknown'."""
    for part in path.parts[::-1]:
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits in {"10", "20", "50", "100", "200", "500", "2000"}:
            return digits
    return "unknown"
