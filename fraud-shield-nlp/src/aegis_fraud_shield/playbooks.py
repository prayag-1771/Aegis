"""Scam playbooks — the reasoning-chain layer.

The markers (markers.py) are a flat bag: they say *which* tricks appear in a
message, not that the tricks form a **script**. Real scams follow one: a
digital arrest establishes authority, then fabricates a case, then isolates
the victim, then coerces payment — in that order, because each stage sets up
the next. This module encodes those scripts as small, finite ontologies and
matches a message against them.

Why encoded rather than learned: no labelled reasoning chains exist to train
on, and a generated chain can hallucinate — fatal for the legal-admissibility
criterion. An encoded playbook match is deterministic: every stage cites the
exact span that satisfied it, so the output *is* a reasoning chain a court
can replay.

Consumers:
- model.py     -> completeness + canonical-order become classifier features
                  ("4 markers forming a coherent script" now scores differently
                  from "4 unrelated markers")
- analyze.py   -> the explanation renders the matched chain stage by stage
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .markers import (
    AUTHORITY_IMPERSONATION,
    CRYPTO_OR_GIFTCARD_DEMAND,
    FAKE_FIR_OR_CASE,
    PERSONAL_DATA_REQUEST,
    SUSPICIOUS_LINK,
    URGENCY_PRESSURE,
    VIDEO_CALL_ISOLATION,
    MarkerHit,
)


@dataclass(frozen=True)
class Stage:
    """One step of a scam script. Satisfied by any listed marker, or by the
    stage's own patterns (for cues the marker vocabulary doesn't cover)."""

    name: str
    label: str  # verb phrase used in the rendered chain
    markers: frozenset[str] = frozenset()
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    name: str
    scam_type: str  # contract scam_type this playbook implies
    stages: tuple[Stage, ...]
    min_stages: int  # report a match only at/above this many satisfied stages


@dataclass
class StageMatch:
    stage: Stage
    evidence: str | None = None
    position: int | None = None  # char offset — used for order checking

    @property
    def satisfied(self) -> bool:
        return self.evidence is not None


@dataclass
class PlaybookMatch:
    playbook: Playbook
    stages: list[StageMatch]

    @property
    def n_satisfied(self) -> int:
        return sum(1 for s in self.stages if s.satisfied)

    @property
    def completeness(self) -> float:
        return self.n_satisfied / len(self.stages)

    @property
    def in_canonical_order(self) -> bool:
        """Do the satisfied stages appear in the text in script order?"""
        positions = [s.position for s in self.stages if s.satisfied]
        return positions == sorted(positions)

    def chain(self) -> list[str]:
        """Human-readable reasoning chain, one fragment per satisfied stage."""
        return [
            f"stage {i + 1} {m.stage.label} ('{m.evidence}')"
            for i, m in enumerate(self.stages)
            if m.satisfied
        ]


PLAYBOOKS: tuple[Playbook, ...] = (
    Playbook(
        name="digital_arrest",
        scam_type="digital_arrest",
        min_stages=2,
        stages=(
            Stage("establish_authority", "establishes authority",
                  markers=frozenset({AUTHORITY_IMPERSONATION})),
            Stage("fabricate_case", "fabricates a legal case",
                  markers=frozenset({FAKE_FIR_OR_CASE})),
            Stage("isolate_victim", "isolates the victim",
                  markers=frozenset({VIDEO_CALL_ISOLATION})),
            Stage("coerce_payment", "coerces payment",
                  markers=frozenset({CRYPTO_OR_GIFTCARD_DEMAND})),
        ),
    ),
    Playbook(
        name="kyc_fraud",
        scam_type="kyc",
        min_stages=2,
        stages=(
            Stage("threaten_service_loss", "threatens loss of service",
                  markers=frozenset({URGENCY_PRESSURE}),
                  patterns=(r"\bKYC\b.{0,40}\b(?:expired?|pending|update|verify)\b",)),
            Stage("harvest", "harvests credentials or pushes a link",
                  markers=frozenset({PERSONAL_DATA_REQUEST, SUSPICIOUS_LINK})),
        ),
    ),
    Playbook(
        name="advance_fee",
        scam_type="lottery",
        min_stages=2,
        stages=(
            Stage("bait", "baits with a prize or windfall",
                  patterns=(
                      r"\b(?:lottery|lucky\s+draw|jackpot|prize|winner|won\s+(?:rs|₹|\$|\d))\b",
                      r"\b(?:pre[- ]?approved|sanctioned)\s+loan\b",
                  )),
            Stage("collect", "demands an advance fee or personal data",
                  markers=frozenset({CRYPTO_OR_GIFTCARD_DEMAND, PERSONAL_DATA_REQUEST,
                                     SUSPICIOUS_LINK}),
                  patterns=(r"\b(?:processing|registration|file|insurance)\s+(?:fee|charge)\b",)),
        ),
    ),
)

_COMPILED_STAGE_PATTERNS: dict[tuple[str, str], list[re.Pattern[str]]] = {
    (pb.name, st.name): [re.compile(p, re.IGNORECASE) for p in st.patterns]
    for pb in PLAYBOOKS
    for st in pb.stages
    if st.patterns
}


def _match_stage(playbook: Playbook, stage: Stage, text: str,
                 hits_by_marker: dict[str, MarkerHit]) -> StageMatch:
    # earliest satisfying evidence wins (keeps order checks meaningful)
    best: tuple[int, str] | None = None
    for marker in stage.markers:
        hit = hits_by_marker.get(marker)
        if hit and (best is None or hit.first_pos < best[0]):
            best = (hit.first_pos, hit.evidence[0])
    for pattern in _COMPILED_STAGE_PATTERNS.get((playbook.name, stage.name), []):
        m = pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.group(0).strip())
    if best is None:
        return StageMatch(stage=stage)
    return StageMatch(stage=stage, evidence=best[1], position=best[0])


def match_playbook(text: str, hits: list[MarkerHit]) -> PlaybookMatch | None:
    """Best playbook the message follows, or None if no script reaches its
    minimum stage count. Ties break toward completeness, then declaration
    order (digital arrest first — the flagship threat)."""
    hits_by_marker = {h.marker: h for h in hits}
    best: PlaybookMatch | None = None
    for playbook in PLAYBOOKS:
        match = PlaybookMatch(
            playbook=playbook,
            stages=[_match_stage(playbook, st, text, hits_by_marker) for st in playbook.stages],
        )
        if match.n_satisfied < playbook.min_stages:
            continue
        if best is None or match.completeness > best.completeness:
            best = match
    return best
