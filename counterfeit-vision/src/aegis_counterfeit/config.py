"""Central configuration for the Counterfeit Vision pipeline."""

from pathlib import Path

from pydantic import BaseModel

MODULE_ROOT = Path(__file__).resolve().parents[2]  # counterfeit-vision/
REPO_ROOT = MODULE_ROOT.parent  # Aegis/
DATA_DIR = MODULE_ROOT / "data"
MODELS_DIR = MODULE_ROOT / "models"
OUTPUT_DIR = MODULE_ROOT / "output"
CAPTURES_DIR = OUTPUT_DIR / "captures"
CONTRACT_SCHEMA = REPO_ROOT / "contracts" / "counterfeit.schema.json"

SCHEMA_VERSION = "1.0"

# Real Indian note dataset with BOTH real and fake photographed notes, split
# real/ and fake/ by denomination (₹10–₹2000). ~4,900 real + ~2,500 real
# counterfeit photos (mobile-camera, varied backgrounds/lighting). Public,
# downloads anonymously via kagglehub. This is genuine photographed-counterfeit
# data — the fake class is real fakes, not synthetic degradations.
REAL_DATASET = "preetrank/indian-currency-real-vs-fake-notes-dataset"

# Canonical working size for feature checks (w, h) — real ₹500 note is
# 150x66 mm, aspect ratio ~2.27.
NOTE_SIZE = (480, 212)


class SynthConfig(BaseModel):
    """Knobs for the synthetic note renderer.

    Fallback path locked early per the project plan: no Kaggle credentials on
    this machine, so v1 trains on rendered notes whose security features we
    control exactly — which also gives us *ground-truth labels per feature*,
    something no public dataset provides.
    """

    n_genuine: int = 300
    n_fake: int = 300
    seed: int = 42
    # Probability that a fake is missing each feature (independent draws; a
    # fake always misses at least one).
    p_missing_thread: float = 0.55
    p_missing_watermark: float = 0.45
    p_blurred_microprint: float = 0.50


class TrainConfig(BaseModel):
    """CNN training knobs (CPU-friendly transfer learning)."""

    backbone: str = "efficientnet_b0"  # or "mobilenet_v3_small" / "tiny" (fast unit tests)
    img_size: int = 224
    batch_size: int = 32
    epochs: int = 8
    lr: float = 3e-3
    val_fraction: float = 0.2
    seed: int = 42
    # Verdict-band FALLBACKS: the real thresholds are picked from the
    # validation PR curve at train time (precision-first, like the other
    # modules). These apply only if the curve search finds nothing usable.
    fake_threshold: float = 0.80
    genuine_threshold: float = 0.20
    # Keep at most this many demo captures on disk (oldest pruned first).
    max_captures: int = 200
