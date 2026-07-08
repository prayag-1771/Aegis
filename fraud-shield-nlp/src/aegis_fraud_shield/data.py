"""Dataset loading for Fraud Shield.

Two sources, one training frame:

1. **UCI SMS Spam Collection** (5,574 real SMS, ham/spam) — the classic public
   baseline. Downloaded on demand into `data/` (gitignored per repo rules —
   never committed).
2. **Synthetic Indian-scam corpus** (`corpus.py`) — digital-arrest call scripts,
   KYC-freeze, lottery, loan and phishing messages plus hard legit negatives.
   The UCI set predates digital-arrest scams entirely; without augmentation the
   model would never see the flagship threat it exists to catch.

Output frame columns: `text`, `label` (1 = scam/spam, 0 = legit), `origin`.
"""

from __future__ import annotations

import hashlib
import io
import warnings
import zipfile
from pathlib import Path

import pandas as pd
import requests

from .config import DATA_DIR, SMS_SPAM_URL, CorpusConfig
from .corpus import generate_corpus

SMS_SPAM_FILE = DATA_DIR / "SMSSpamCollection"
# SHA-256 of the extracted SMSSpamCollection file (pinned 2026-07-07). A
# changed hash means UCI moved/altered the file — warn loudly, don't train
# silently on something else.
SMS_SPAM_SHA256 = "7d039a24a6083ed9ef0f806ebad56bbb976e3aeb8de05669173bfdc4996c239d"


def _verify_checksum(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SMS_SPAM_SHA256:
        warnings.warn(
            f"{path.name} checksum mismatch (got {digest[:12]}…, expected "
            f"{SMS_SPAM_SHA256[:12]}…). The UCI source may have changed — "
            "verify the data before trusting the trained model.",
            stacklevel=2,
        )


def download_sms_spam(force: bool = False) -> Path:
    """Fetch the UCI SMS Spam Collection into data/ (skips if already there)."""
    if SMS_SPAM_FILE.exists() and not force:
        return SMS_SPAM_FILE
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    resp = requests.get(SMS_SPAM_URL, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open("SMSSpamCollection") as src:
            SMS_SPAM_FILE.write_bytes(src.read())
    _verify_checksum(SMS_SPAM_FILE)
    return SMS_SPAM_FILE


def load_sms_spam() -> pd.DataFrame:
    """UCI set as (text, label, origin, group) — spam maps to label 1."""
    path = download_sms_spam()
    df = pd.read_csv(path, sep="\t", names=["raw_label", "text"], quoting=3)
    df["label"] = (df["raw_label"] == "spam").astype(int)
    df["origin"] = "uci_sms_spam"
    # Each real SMS is its own group (no template structure to leak).
    df["group"] = [f"uci_{i}" for i in range(len(df))]
    return df[["text", "label", "origin", "group"]]


def load_extra_corpus() -> pd.DataFrame | None:
    """Opt-in augmentation hook (self-improving classifier, innovation #2).

    Any CSV dropped into data/extra_corpus/ with columns text,label,origin,group
    is merged into training — e.g. LLM-generated scam variants written by the
    command-centre fusion layer (aegis_fusion.self_improve). Absent dir = no-op.
    """
    extra_dir = DATA_DIR / "extra_corpus"
    if not extra_dir.is_dir():
        return None
    frames = []
    for csv in sorted(extra_dir.glob("*.csv")):
        df = pd.read_csv(csv)
        missing = {"text", "label", "origin", "group"} - set(df.columns)
        if missing:
            raise ValueError(f"{csv} missing columns: {missing}")
        frames.append(df[["text", "label", "origin", "group"]])
    return pd.concat(frames, ignore_index=True) if frames else None


def load_training_frame(cfg: CorpusConfig | None = None) -> pd.DataFrame:
    """UCI + synthetic corpus (+ optional extra_corpus), shuffled deterministically."""
    cfg = cfg or CorpusConfig()
    uci = load_sms_spam()
    synth = generate_corpus(cfg)
    parts = [uci, synth]
    extra = load_extra_corpus()
    if extra is not None:
        parts.append(extra)
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.drop_duplicates(subset="text").reset_index(drop=True)
    return frame.sample(frac=1.0, random_state=cfg.seed).reset_index(drop=True)
