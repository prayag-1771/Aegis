"""Central configuration for the Fraud Shield pipeline."""

from pathlib import Path

from pydantic import BaseModel

MODULE_ROOT = Path(__file__).resolve().parents[2]  # fraud-shield-nlp/
REPO_ROOT = MODULE_ROOT.parent  # Aegis/
DATA_DIR = MODULE_ROOT / "data"
MODELS_DIR = MODULE_ROOT / "models"
OUTPUT_DIR = MODULE_ROOT / "output"
CONTRACT_SCHEMA = REPO_ROOT / "contracts" / "scam_detection.schema.json"

SCHEMA_VERSION = "1.0"

# UCI SMS Spam Collection (5,574 labelled SMS; ham/spam).
SMS_SPAM_URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"


class CorpusConfig(BaseModel):
    """Knobs for the synthetic digital-arrest / Indian-scam corpus generator.

    The public SMS Spam Collection predates digital-arrest scams entirely, so we
    augment it with template-generated scripts of the scams we actually need to
    catch (CBI/ED impersonation, fake FIRs, KYC freezes...) plus *hard legit
    negatives* (real bank/courier/police-verification messages) so the model
    can't win by keyword-matching "bank" or "police".
    """

    variants_per_template: int = 6
    seed: int = 42


class ModelConfig(BaseModel):
    """Training knobs for the TF-IDF + Logistic Regression baseline."""

    test_size: float = 0.2
    seed: int = 42
    max_word_features: int = 30000
    max_char_features: int = 50000
    # C for LogisticRegression; mild regularisation works well on TF-IDF.
    C: float = 4.0
    # Verdict thresholds are picked from the precision-recall curve at train
    # time (precision-first — a false "this is a scam" erodes citizen trust).
    # These are fallbacks if the curve search fails.
    scam_threshold_fallback: float = 0.80
    suspicious_threshold_fallback: float = 0.45
    # Precision floors the verdict bands must clear on held-out data. The 0.90
    # suspicious floor keeps genuine bank OTP messages out of the warning band.
    min_scam_precision: float = 0.97
    min_suspicious_precision: float = 0.90


class TranslateConfig(BaseModel):
    """Input normalisation for the 22 scheduled Indian languages (8th Schedule).

    The classifier is English-only (TF-IDF over an English / Indian-English
    corpus), so a message in a native script scores as noise — a real Hindi
    KYC-freeze scam lands at risk 0.06 and is cleared. Before classifying, a
    non-Latin message is translated to English via the command centre, which
    holds SARVAM_API_KEY; Fraud Shield never needs the key itself. A wrapper,
    not a retrain — the deterministic verdict is unchanged, only the language of
    the input is normalised. Fail-safe throughout: any error / no key /
    unreachable centre → the original text is classified (today's behaviour)."""

    enabled: bool = True
    # Where the Sarvam key lives — the same centre the citizen UIs already
    # ingest to. Overridden at runtime by the COMMAND_CENTRE_URL env var.
    command_centre_url: str = "http://127.0.0.1:8000"
    # Translation must return within this budget or we classify the original.
    timeout_s: float = 12.0
    # Sarvam caps input length; a scam SMS / call transcript fits well under.
    max_chars: int = 900


class VerifyConfig(BaseModel):
    """Knobs for the agentic verification layer (additive; never overrides the
    deterministic verdict). See verify/ — an LLM agent investigates a *flagged*
    message with real verification tools, then narrates only tool-confirmed
    findings. Runtime-flippable so the whole layer can be switched off without
    a code change."""

    enabled: bool = True
    # Per-tool network timeout (seconds). Each live tool call must return or
    # fall back to offline heuristics within this budget.
    tool_timeout_s: float = 4.0
    # Hard overall wall-clock budget for the whole verification pass. /analyze
    # answers in ~100 ms today; this caps how much the (synchronous) agent can
    # add. On expiry we return whatever findings completed.
    total_budget_s: float = 6.0
    # LLM used only for the final synthesis sentence (never for the verdict).
    model: str = "claude-opus-4-8"
    # Follow at most this many URL redirect hops (SSRF hardening).
    max_redirects: int = 5
    # Cap bytes read from a resolved page.
    max_body_bytes: int = 2048
