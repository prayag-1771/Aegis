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

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

from .config import DATA_DIR, SMS_SPAM_URL, CorpusConfig
from .corpus import generate_corpus

SMS_SPAM_FILE = DATA_DIR / "SMSSpamCollection"


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
    return SMS_SPAM_FILE


def load_sms_spam() -> pd.DataFrame:
    """UCI set as (text, label, origin) — spam maps to label 1."""
    path = download_sms_spam()
    df = pd.read_csv(path, sep="\t", names=["raw_label", "text"], quoting=3)
    df["label"] = (df["raw_label"] == "spam").astype(int)
    df["origin"] = "uci_sms_spam"
    return df[["text", "label", "origin"]]


def load_training_frame(cfg: CorpusConfig | None = None) -> pd.DataFrame:
    """UCI + synthetic corpus, shuffled deterministically."""
    cfg = cfg or CorpusConfig()
    uci = load_sms_spam()
    synth = generate_corpus(cfg)
    frame = pd.concat([uci, synth], ignore_index=True)
    frame = frame.drop_duplicates(subset="text").reset_index(drop=True)
    return frame.sample(frac=1.0, random_state=cfg.seed).reset_index(drop=True)
