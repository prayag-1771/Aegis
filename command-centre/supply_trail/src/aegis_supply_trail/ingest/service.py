"""Service layer for the Intel Feed review UI.

The CLI drives the pipeline from a terminal; this drives the *review and commit*
half of it from the dashboard. Both call the same `corpus.commit()`, so a record
approved in the browser goes through exactly the same validation, de-duplication,
backup and reload-guard as one approved at a prompt. There is no second, laxer
path into the corpus.

Deliberately absent: fetching. `fetch` and `extract` stay in the CLI, run ahead
of time. Nothing here touches the network, so the review page cannot hang on a
slow feed mid-demo and `inputs_hash` reproducibility is untouched.

Reversibility (what makes this safe to demo):
  * `undo_last()`  — restores the most recent commit's backup, one step at a time.
  * `reset_baseline()` — restores the corpus as it stood before the FIRST ingest.

The baseline is captured automatically the first time anything mutates the
corpus, so a rehearsal can always get back to a known-good state without git.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..engine import FIR_FILE, load_fir_corpus
from .corpus import BACKUP_DIR, STAGING_DIR, commit, load_candidates, save_candidates

BASELINE_FILE = STAGING_DIR / "baseline_fir_corpus.json"
BASELINE_CANDIDATES = STAGING_DIR / "baseline_candidates.json"


# ── baseline / history ──────────────────────────────────────────────────────

def ensure_baseline() -> Path:
    """Snapshot the corpus AND the review queue before the first mutation.

    Both halves matter for a repeatable rehearsal: restoring the corpus alone
    would leave the queue consumed, so the second run-through would have nothing
    left to approve. Snapshotting the queue too means `reset` returns the whole
    surface to its opening state. Idempotent.
    """
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not BASELINE_FILE.exists():
        shutil.copy2(FIR_FILE, BASELINE_FILE)
    if not BASELINE_CANDIDATES.exists():
        save_candidates(load_candidates(), BASELINE_CANDIDATES)
    return BASELINE_FILE


def _backups(newest_first: bool = True) -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("fir_corpus.*.json"), reverse=newest_first)


def _read_corpus() -> list[dict]:
    try:
        return json.loads(FIR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _restore(source: Path) -> dict:
    """Atomically replace the corpus with `source` — BYTE-FOR-BYTE.

    Deliberately a byte copy, not a parse-and-reserialise. The corpus is a
    hand-maintained file tracked in git: re-serialising it would expand the
    compact inline arrays the team wrote by hand and rewrite line endings,
    leaving a 74-line diff after an operation whose entire purpose is "put it
    back exactly as it was". Restoring bytes means a reset leaves no diff at
    all — and no merge conflict for whoever else edits this file.

    The content is still parsed first, so a corrupt backup is caught before it
    can replace a working corpus.
    """
    payload = source.read_bytes()
    records = json.loads(payload.decode("utf-8"))  # validate before writing

    temp = FIR_FILE.with_suffix(".json.tmp")
    temp.write_bytes(payload)
    temp.replace(FIR_FILE)
    load_fir_corpus()  # raises if the restored file is unreadable
    return {"entries": len(records), "restored_from": source.name}


# ── read model for the UI ───────────────────────────────────────────────────

def corpus_stats() -> dict:
    corpus = _read_corpus()
    presses = [e for e in corpus if "printing_press" in (e.get("crime_types") or [])]
    ingested = [e for e in corpus if str(e.get("ref", "")).startswith("NEWS-")]
    return {
        "entries": len(corpus),
        "presses": [p.get("district") for p in presses],
        "press_count": len(presses),
        "ingested_count": len(ingested),
        "ingested_refs": [e.get("ref") for e in ingested],
    }


def _candidate_view(record: dict) -> dict:
    """Shape one candidate for the review UI — evidence forward, no internals."""
    review = record.get("_review", {})
    crime_types = record.get("crime_types", [])
    return {
        "ref": record.get("ref"),
        "district": record.get("district"),
        "state": record.get("state"),
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "date": record.get("date"),
        "source": record.get("source"),
        "text": record.get("text"),
        "places": record.get("places", []),
        "crime_types": crime_types,
        # The UI highlights these: a printing_press record becomes a route ORIGIN,
        # so it deserves the most scrutiny from the reviewer.
        "is_printing_press": "printing_press" in crime_types,
        "headline": review.get("headline"),
        "link": review.get("link"),
        "confidence": review.get("confidence"),
        "extractor": review.get("extractor"),
        "places_unresolved": review.get("places_unresolved", []),
        "notes": review.get("notes"),
    }


def feed_state() -> dict:
    """Everything the review page renders in one call."""
    candidates = [c for c in load_candidates() if c.get("approved") is not True]
    return {
        "corpus": corpus_stats(),
        "candidates": [_candidate_view(c) for c in candidates],
        "candidate_count": len(candidates),
        "can_undo": bool(_backups()),
        "can_reset": BASELINE_FILE.exists(),
        "undo_steps": len(_backups()),
        "disclaimer": (
            "Public reporting is a PRIOR, not a finding. It constrains where a "
            "corridor might lead; the seizures that actually drive a trail come "
            "from Counterfeit Vision's own scans, which are not police-mediated. "
            "Because news is downstream of enforcement, this corpus can only ever "
            "connect new detections to sources someone already raided and "
            "published — it cannot surface an unreported one, and districts that "
            "publicise busts more will look denser than districts that do not. "
            "Candidates are fetched and structured by an offline batch job "
            "(fetch → extract), never during a request, and nothing enters the "
            "corpus until approved here. Ingested records carry a NEWS- reference "
            "so they stay distinguishable from curated FIR- entries."
        ),
    }


# ── mutations ───────────────────────────────────────────────────────────────

def ingest(refs: list[str]) -> dict:
    """Approve the named candidates and commit them through the normal path."""
    if not refs:
        return {"committed": 0, "error": "no records selected"}

    wanted = set(refs)
    candidates = load_candidates()
    selected = [c for c in candidates if c.get("ref") in wanted]
    if not selected:
        return {"committed": 0, "error": "none of the selected refs are staged"}

    ensure_baseline()
    for record in selected:
        record["approved"] = True

    report = commit(selected)

    # Drop what landed so a second click cannot double-add it; anything that
    # failed validation stays staged with its problems reported.
    committed = set(report.get("refs", []))
    if committed:
        save_candidates([c for c in candidates if c.get("ref") not in committed])
    else:
        # Roll the approval flags back — nothing was written, so the queue
        # should look exactly as it did before the attempt.
        for record in selected:
            record["approved"] = False
        save_candidates(candidates)

    report["corpus"] = corpus_stats()
    return report


def undo_last() -> dict:
    """Restore the most recent backup — one ingest step back."""
    backups = _backups()
    if not backups:
        return {"restored": False, "error": "nothing to undo"}

    latest = backups[0]
    before = len(_read_corpus())
    result = _restore(latest)
    latest.unlink(missing_ok=True)  # consumed, so undo walks back one step at a time

    return {
        "restored": True,
        "entries_before": before,
        "entries_after": result["entries"],
        "undo_steps_left": len(_backups()),
        "corpus": corpus_stats(),
    }


def reset_baseline() -> dict:
    """Restore the corpus to its pre-first-ingest state and clear the history."""
    if not BASELINE_FILE.exists():
        return {"restored": False, "error": "no baseline recorded — nothing has been ingested"}

    before = len(_read_corpus())
    result = _restore(BASELINE_FILE)
    for backup in _backups():
        backup.unlink(missing_ok=True)

    # Put the review queue back too, so the page opens exactly as it did the
    # first time — a rehearsal can be run start-to-finish again immediately.
    restored_candidates = 0
    if BASELINE_CANDIDATES.exists():
        queue = load_candidates(BASELINE_CANDIDATES)
        for record in queue:
            record["approved"] = False
        save_candidates(queue)
        restored_candidates = len(queue)

    return {
        "restored": True,
        "entries_before": before,
        "entries_after": result["entries"],
        "candidates_restored": restored_candidates,
        "corpus": corpus_stats(),
        "note": "Corpus and review queue restored to their state before the first ingest.",
    }


def snapshot_note() -> str:
    """Human-readable provenance line for the UI footer."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Corpus read live from fir_corpus.json — no cache, no restart needed ({stamp})."
