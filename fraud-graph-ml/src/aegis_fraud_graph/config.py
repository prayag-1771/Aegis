"""Central configuration for the fraud-graph pipeline."""

from pathlib import Path

from pydantic import BaseModel

MODULE_ROOT = Path(__file__).resolve().parents[2]  # fraud-graph-ml/
REPO_ROOT = MODULE_ROOT.parent  # Aegis/
DATA_DIR = MODULE_ROOT / "data"
MODELS_DIR = MODULE_ROOT / "models"
OUTPUT_DIR = MODULE_ROOT / "output"
CONTRACT_SCHEMA = REPO_ROOT / "contracts" / "fraud_graph.schema.json"

SCHEMA_VERSION = "1.0"


class SynthConfig(BaseModel):
    """Knobs for the synthetic transaction generator."""

    n_legit_accounts: int = 2000
    n_rings: int = 12
    ring_size_min: int = 4
    ring_size_max: int = 10
    n_background_tx: int = 12000
    seed: int = 42
    # Districts double as demo geography for the cross-domain crime map.
    districts: list[str] = [
        "Jamtara",
        "Deoghar",
        "Alwar",
        "Bharatpur",
        "Nuh",
        "Chennai Central",
        "Mumbai South",
        "Delhi East",
    ]
    # Fraud rings cluster in the first `n_hotspots` districts (realistic: known scam hubs).
    n_hotspots: int = 4


class ModelConfig(BaseModel):
    """XGBoost training knobs."""

    test_size: float = 0.25
    seed: int = 42
    n_estimators: int = 400
    max_depth: int = 6
    learning_rate: float = 0.08
    # Fraud data is imbalanced; weight positives up (set at train time from data if None).
    scale_pos_weight: float | None = None


class RingConfig(BaseModel):
    """Ring-clustering knobs."""

    # Accounts above this illicit probability enter the high-risk subgraph.
    risk_threshold: float = 0.5
    # Discard singleton "rings" — a ring needs at least this many members.
    min_ring_size: int = 3
    # Cap edges exported to the command centre for render performance.
    max_export_edges: int = 500
    # Also export payments flowing INTO ring accounts from outside (victim ->
    # collector). These are the fusion money-trail evidence; capped separately
    # so they never crowd out the intra-ring edges.
    max_inflow_edges: int = 200
