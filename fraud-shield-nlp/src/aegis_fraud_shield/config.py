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
    # Precision floor the "scam" verdict must clear on held-out data.
    min_scam_precision: float = 0.97
