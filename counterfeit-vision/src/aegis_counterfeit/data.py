"""Dataset acquisition for Counterfeit Vision.

**Trains on REAL photographed notes — real notes AND real counterfeits.**
The dataset (Kaggle: preetrank/indian-currency-real-vs-fake-notes-dataset,
downloaded anonymously via kagglehub) ships `real/` and `fake/` folders split
by denomination (₹10–₹2000): ~4,900 genuine + ~2,500 real counterfeit photos,
mobile-camera, varied backgrounds/lighting.

Both classes are real photographs — the fake class is genuine seized/collected
counterfeit notes, NOT synthetic degradations. `prepare_real_dataset()` reshapes
the split into the `{genuine,fake}/` layout the trainer reads, balancing the two
classes (the fake class is smaller) so neither collapses.

The synthetic renderer (synth.py) remains available for unit tests only.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from .config import DATA_DIR, REAL_DATASET, SynthConfig
from .synth import generate_dataset

KAGGLE_DIR = DATA_DIR / "kaggle"
# Denomination subfolders present under both real/ and fake/.
_DENOMS = ["10", "20", "50", "100", "200", "500", "2000"]
_IMG_EXTS = (".jpg", ".jpeg", ".png")


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


def _find_split_root(src_dir: Path) -> Path:
    """Locate the folder that directly contains real/ and fake/ subfolders
    (the dataset nests them a few levels deep under versions/N/data/data)."""
    for candidate in [src_dir, *src_dir.rglob("*")]:
        if candidate.is_dir() and (candidate / "real").is_dir() and (candidate / "fake").is_dir():
            return candidate
    raise RuntimeError(f"Could not find real/ and fake/ folders under {src_dir}.")


def _collect(root: Path, kind: str) -> list[Path]:
    """Every image under <root>/<kind>/<denom>/ (real or fake)."""
    photos: list[Path] = []
    for denom in _DENOMS:
        d = root / kind / denom
        if not d.is_dir():
            continue
        photos += [p for p in d.iterdir() if p.suffix.lower() in _IMG_EXTS]
    return sorted(set(photos))


def prepare_real_dataset(
    src_dir: Path | None = None, out_dir: Path | None = None, seed: int = 42, img_size: int = 224
) -> Path:
    """Build <out>/{genuine,fake}/ from REAL photographed notes.

    genuine = real note photos, fake = real COUNTERFEIT note photos (both classes
    are genuine photographs). Balanced to the smaller class so neither collapses.
    Downloads the dataset via kagglehub if `src_dir` isn't given.
    """
    import json

    from PIL import Image

    if src_dir is None:
        src_dir = download_kaggle()
    root = _find_split_root(src_dir)
    out_dir = out_dir or (DATA_DIR / "real")
    rng = random.Random(seed)

    real = _collect(root, "real")
    fake = _collect(root, "fake")
    if not real or not fake:
        raise RuntimeError(f"No real/fake images found under {root}.")
    # balance 1:1 — the fake class is smaller; a lopsided set collapses a class
    n = min(len(real), len(fake))
    rng.shuffle(real)
    rng.shuffle(fake)
    real, fake = real[:n], fake[:n]

    genuine_dir = out_dir / "genuine"
    fake_dir = out_dir / "fake"
    genuine_dir.mkdir(parents=True, exist_ok=True)
    fake_dir.mkdir(parents=True, exist_ok=True)
    labels: dict[str, dict] = {}
    counts = {"genuine": 0, "fake": 0}

    for label, files in (("genuine", real), ("fake", fake)):
        out = genuine_dir if label == "genuine" else fake_dir
        for p in files:
            try:
                img = Image.open(p).convert("RGB").resize((img_size, img_size))
            except Exception:
                continue  # skip unreadable files rather than crash the run
            name = f"{label}_{counts[label]:05d}.png"
            img.save(out / name)
            labels[f"{label}/{name}"] = {
                "label": label,
                "denomination": _guess_denomination(p),
                "source": str(p.name),
            }
            counts[label] += 1

    (out_dir / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    print(f"Prepared REAL dataset: {counts} (genuine=real notes, fake=real counterfeit notes)")
    return out_dir


def _guess_denomination(path: Path) -> str:
    """Infer denomination from the folder name (500/2000/…); default 'unknown'."""
    for part in path.parts[::-1]:
        if part in _DENOMS:
            return part
    return "unknown"
