"""In-memory event store.

Hackathon-grade by design: a bounded deque per signal type, thread-safe enough
for uvicorn's default worker. Swap for PostgreSQL after the demo if needed —
the interface (add/list/latest) is deliberately tiny so nothing else changes.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
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
        # Response/disrupt actions, keyed by stable action_id. Insertion order is
        # preserved; the derive-merge keeps an officer's dispatch/ack state.
        self.actions: dict[str, dict] = {}

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

    # ---- response / disrupt actions ----
    def set_actions(self, derived: list[dict]) -> list[dict]:
        """Merge freshly-derived actions over the current set.

        An action an officer has already dispatched/acknowledged/dismissed keeps
        its status and audit trail (history is never rewritten). A still-`proposed`
        action is replaced by the fresh derivation so the queue tracks current
        state. Actions no longer derived are dropped only if still `proposed`.
        """
        with self._lock:
            merged: dict[str, dict] = {}
            derived_ids = set()
            for a in derived:
                aid = a["action_id"]
                derived_ids.add(aid)
                existing = self.actions.get(aid)
                if existing and existing.get("status") != "proposed":
                    merged[aid] = existing  # preserve officer state + audit
                else:
                    merged[aid] = a
            # Keep acted-on actions that current state no longer re-derives.
            for aid, a in self.actions.items():
                if aid not in derived_ids and a.get("status") != "proposed":
                    merged[aid] = a
            self.actions = merged
            return list(self.actions.values())

    def list_actions(self) -> list[dict]:
        with self._lock:
            return list(self.actions.values())

    def update_action(self, action_id: str, status: str, actor: str, note: str) -> dict | None:
        """Transition an action and append an immutable audit entry."""
        with self._lock:
            action = self.actions.get(action_id)
            if action is None:
                return None
            action["status"] = status
            if status == "dispatched":
                action["dispatched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            action.setdefault("audit", []).append(
                {
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "actor": actor,
                    "event": status,
                    "note": note,
                }
            )
            return action

    # ---- reads ----
    def snapshot(self) -> tuple[list[dict], list[dict], dict | None]:
        with self._lock:
            return list(self.scams), list(self.counterfeits), self.fraud_graph

    def seed_demo_data(self) -> None:
        """Load contract samples so the dashboard is never empty. The live
        fraud-graph output is preferred over the sample when it exists."""
        self.add_scam(json.loads((SAMPLES / "scam_detection.sample.json").read_text(encoding="utf-8")))
        # Second sample carries reported_payment — fusion traces it into a
        # collector account of the live graph (the money-trail demo).
        traced = SAMPLES / "scam_detection.sample2.json"
        if traced.exists():
            self.add_scam(json.loads(traced.read_text(encoding="utf-8")))
        # Seed the three Jharkhand counterfeit detections so Supply Trail has
        # a cluster to work with from the moment the demo starts.
        self.add_counterfeit(json.loads((SAMPLES / "counterfeit.sample.json").read_text(encoding="utf-8")))
        for extra in ("counterfeit.sample2.json", "counterfeit.sample3.json"):
            path = SAMPLES / extra
            if path.exists():
                self.add_counterfeit(json.loads(path.read_text(encoding="utf-8")))
        live = REPO_ROOT / "fraud-graph-ml" / "output" / "fraud_graph.json"
        source = live if live.exists() else SAMPLES / "fraud_graph.sample.json"
        self.set_fraud_graph(json.loads(source.read_text(encoding="utf-8")))



store = EventStore()
