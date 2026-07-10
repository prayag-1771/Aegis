"""Dataset acquisition for Counterfeit Vision.

v1 trains on the synthetic renderer (see synth.py for why — fallback locked
early, per plan). This module keeps the **real-data hook** ready: when Kaggle
API credentials exist (`%USERPROFILE%/.kaggle/kaggle.json`), `download_kaggle()`
pulls the real note dataset into `data/kaggle/` and `prepare_real_dataset()`
reshapes it into the same `{genuine,fake}/` layout the trainer reads — so
swapping datasets is one CLI flag, zero pipeline changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import DATA_DIR, KAGGLE_DATASET
from .synth import SynthConfig, generate_dataset

KAGGLE_DIR = DATA_DIR / "kaggle"


def kaggle_available() -> bool:
    return (Path(os.path.expanduser("~")) / ".kaggle" / "kaggle.json").exists()


def download_kaggle(dataset: str = KAGGLE_DATASET, out_dir: Path = KAGGLE_DIR) -> Path:
    """Download + unzip a Kaggle dataset (requires kaggle API credentials)."""
    import kagglehub
    import shutil
    
    out_dir.mkdir(parents=True, exist_ok=True)
    # Download dataset using kagglehub
    path = kagglehub.dataset_download(dataset)
    
    # Move files from cache path to out_dir
    for item in Path(path).iterdir():
        dest = out_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
            
    return out_dir


def prepare_synth_dataset(cfg: SynthConfig | None = None) -> Path:
    """Render the synthetic training set into data/synth/ (idempotent-ish)."""
    return generate_dataset(cfg)


def prepare_real_dataset(src_dir: Path = KAGGLE_DIR, out_dir: Path | None = None) -> Path:
    """Reshape a downloaded real dataset into <out>/{genuine,fake}/*.png.

    Kaggle currency datasets vary in layout; this walks `src_dir` and buckets
    images by whether their path mentions fake/counterfeit or real/genuine.
    Anything unmatched is skipped (better to drop than mislabel).
    """
    import shutil

    out_dir = out_dir or (DATA_DIR / "real")
    counts = {"genuine": 0, "fake": 0}
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for p in src_dir.rglob(ext):
            hint = str(p.relative_to(src_dir)).lower()
            if any(k in hint for k in ("fake", "counterfeit", "forged")):
                bucket = "fake"
            elif any(k in hint for k in ("real", "genuine", "original")):
                bucket = "genuine"
            else:
                continue
            dest = out_dir / bucket / f"{bucket}_{counts[bucket]:05d}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            counts[bucket] += 1
    if not any(counts.values()):
        raise RuntimeError(f"No labellable images found under {src_dir}.")
    print(f"Prepared real dataset: {counts}")
    return out_dir
