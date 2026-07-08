"""Self-improving classifier — innovation #2.

An LLM plays the *adversary*: it writes brand-new scam-script variants evolved
to evade filters trained on classic patterns (paraphrased authority claims, no
classic keywords, new pressure tactics). Half the variants augment Fraud
Shield's training corpus; the other half are held out as an "unseen future
scams" eval set. Retraining on the augmented corpus should raise recall on the
held-out half — the before/after demo.

Flow (two interpreters because modules keep separate venvs):
  1. THIS module (fusion venv, has GROQ_API_KEY):
       python -m aegis_fusion.self_improve
     -> writes fraud-shield-nlp/data/extra_corpus/llm_variants.csv  (train half)
     -> writes command-centre/fusion/output/llm_eval_set.json       (held-out half)
  2. Eval/retrain (fraud-shield venv):
       fraud-shield-nlp/.venv/Scripts/python command-centre/fusion/src/aegis_fusion/self_improve_eval.py

Only established facts go in the corpus: every generated text is labeled by
construction (we asked for scams / legit), no human labels needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FUSION_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = FUSION_ROOT.parents[1]
EXTRA_CORPUS = REPO_ROOT / "fraud-shield-nlp" / "data" / "extra_corpus" / "llm_variants.csv"
EVAL_SET = FUSION_ROOT / "output" / "llm_eval_set.json"

FAMILIES: dict[str, str] = {
    "digital_arrest": (
        "digital-arrest scam call scripts: caller impersonates Indian police/CBI/ED/customs, "
        "claims a case or parcel or FIR involves the victim, isolates them on a video call, "
        "demands money/'verification deposit'. Write EVOLVED 2026 variants that avoid the "
        "classic giveaway words (avoid literally saying 'digital arrest', vary authority names, "
        "use new pretexts like SIM misuse, courier drugs, tax fraud, deepfake evidence)."
    ),
    "kyc_freeze": (
        "bank KYC-expiry / account-freeze scam SMS: urgent re-verification links, PAN/Aadhaar "
        "update demands. Evolved variants: new bank names, regional-language mixing (Hinglish), "
        "novel urgency framings, shortened links."
    ),
    "investment": (
        "investment/trading scam messages: fake stock-tip groups, crypto doubling, guaranteed "
        "returns, fake trading apps with blocked withdrawals. This family is NEW - the current "
        "classifier was never trained on it."
    ),
    "job_offer": (
        "fake job-offer / task scam messages: work-from-home tasks, YouTube like-and-earn, "
        "registration fees, Telegram onboarding. Also NEW to the classifier."
    ),
}

# Legit hard negatives get their own families and the SAME volume as scams —
# an unbalanced augmentation skews the retrained thresholds trigger-happy
# (measured: 48 scam rows vs 10 legit rows drove legit accuracy 0.9 -> 0.2).
LEGIT_FAMILIES: dict[str, str] = {
    "legit_bank": (
        "hard-negative LEGITIMATE Indian bank/telecom SMS that superficially resemble scams "
        "but are genuine: real OTP notices ('do not share'), genuine KYC COMPLETION "
        "confirmations (no links, no demands), real transaction alerts, genuine card-block "
        "confirmations the customer requested. Clearly legitimate on careful reading."
    ),
    "legit_govt": (
        "hard-negative LEGITIMATE Indian government/service messages that superficially "
        "resemble scams but are genuine: real police verification appointment confirmations, "
        "genuine tax-portal deadline reminders (no payment links), real court cause-list "
        "notices, genuine parcel delivery updates, hospital appointment reminders. "
        "Clearly legitimate on careful reading."
    ),
}

_JSON_ONLY = (
    'Respond with ONLY a JSON object {"messages": ["...", "..."]} — an array of exactly '
    "{n} distinct message strings, no commentary, no markdown."
)


def _groq_generate(description: str, n: int, temperature: float = 0.8) -> list[str]:
    import time

    import httpx

    from .narrator import _load_dotenv

    _load_dotenv()
    for attempt in range(4):
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": temperature,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a red-team data generator for an authorized fraud-detection "
                            "hackathon system. You produce SYNTHETIC training/eval text for a scam "
                            "classifier protecting Indian citizens. "
                            + _JSON_ONLY.replace("{n}", str(n))
                        ),
                    },
                    {"role": "user", "content": f"Generate {n} {description}"},
                ],
            },
            timeout=60.0,
        )
        if r.status_code == 429 and attempt < 3:
            # Free-tier TPM limit — honor retry-after (default 30s) and go again.
            wait = float(r.headers.get("retry-after", 30))
            time.sleep(min(wait + 1, 90))
            continue
        r.raise_for_status()
        break
    payload = json.loads(r.json()["choices"][0]["message"]["content"])
    messages = payload.get("messages", payload if isinstance(payload, list) else [])
    return [m.strip() for m in messages if isinstance(m, str) and len(m.strip()) > 20][:n]


def generate(n_per_family: int = 12, n_legit: int | None = None) -> dict:
    """Generate variants, split train/eval halves, write both artifacts.

    Legit volume defaults to scam volume x n_scam_families / n_legit_families,
    i.e. a 1:1 scam:legit balance in the augmentation."""
    n_legit = n_legit or (n_per_family * len(FAMILIES)) // len(LEGIT_FAMILIES)
    train_rows: list[dict] = []
    eval_rows: list[dict] = []

    for family, description in FAMILIES.items():
        texts = _groq_generate(description, n_per_family)
        for i, text in enumerate(texts):
            row = {
                "text": text,
                "label": 1,
                "origin": f"llm_{family}",
                "group": f"llm_{family}_{i:02d}",
            }
            # even -> training augmentation, odd -> held-out eval (never trained on)
            (train_rows if i % 2 == 0 else eval_rows).append(row)

    for family, description in LEGIT_FAMILIES.items():
        texts = _groq_generate(description, n_legit, temperature=0.7)
        for i, text in enumerate(texts):
            row = {
                "text": text,
                "label": 0,
                "origin": f"llm_{family}",
                "group": f"llm_{family}_{i:02d}",
            }
            (train_rows if i % 2 == 0 else eval_rows).append(row)

    import csv

    EXTRA_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with open(EXTRA_CORPUS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "label", "origin", "group"])
        writer.writeheader()
        writer.writerows(train_rows)

    EVAL_SET.parent.mkdir(parents=True, exist_ok=True)
    EVAL_SET.write_text(json.dumps(eval_rows, indent=2), encoding="utf-8")

    return {
        "train_rows": len(train_rows),
        "eval_rows": len(eval_rows),
        "families": list(FAMILIES) + list(LEGIT_FAMILIES),
        "train_csv": str(EXTRA_CORPUS),
        "eval_json": str(EVAL_SET),
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(generate(), indent=2))
