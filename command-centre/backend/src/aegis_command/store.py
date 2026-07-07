"""In-memory event store.

Hackathon-grade by design: a bounded deque per signal type, thread-safe enough
for uvicorn's default worker. Swap for PostgreSQL after the demo if needed —
the interface (add/list/latest) is deliberately tiny so nothing else changes.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from threading import Lock

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # command-centre/backend/
REPO_ROOT = BACKEND_ROOT.parents[1]  # Aegis/
SAMPLES = REPO_ROOT / "contracts" / "samples"

MAX_EVENTS = 500


class EventStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.scams: deque[dict] = deque(maxlen=MAX_EVENTS)
        self.counterfeits: deque[dict] = deque(maxlen=MAX_EVENTS)
        self.fraud_graph: dict | None = None
        self.last_fusion: dict | None = None

    # ---- writes ----
    def add_scam(self, event: dict) -> None:
        with self._lock:
            self.scams.append(event)

    def add_counterfeit(self, event: dict) -> None:
        with self._lock:
            self.counterfeits.append(event)

    def set_fraud_graph(self, payload: dict) -> None:
        with self._lock:
            self.fraud_graph = payload

    def set_fusion(self, payload: dict) -> None:
        with self._lock:
            self.last_fusion = payload

    # ---- reads ----
    def snapshot(self) -> tuple[list[dict], list[dict], dict | None]:
        with self._lock:
            return list(self.scams), list(self.counterfeits), self.fraud_graph

    def seed_demo_data(self) -> None:
        """Load contract samples so the dashboard is never empty. The live
        fraud-graph output is preferred over the sample when it exists."""
        self.add_scam(json.loads((SAMPLES / "scam_detection.sample.json").read_text(encoding="utf-8")))
        self.add_counterfeit(json.loads((SAMPLES / "counterfeit.sample.json").read_text(encoding="utf-8")))
        live = REPO_ROOT / "fraud-graph-ml" / "output" / "fraud_graph.json"
        source = live if live.exists() else SAMPLES / "fraud_graph.sample.json"
        self.set_fraud_graph(json.loads(source.read_text(encoding="utf-8")))


store = EventStore()
