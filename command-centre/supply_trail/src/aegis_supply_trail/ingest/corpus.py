"""Validation, de-duplication, and the commit into `fir_corpus.json`.

This is the only module that writes to the corpus, and it is deliberately
paranoid about it: the corpus is live data the engine reads on every
`/supply-trail` call, so a malformed write would break a running service.

Protections:
  * every record is validated field-by-field against the `FirEntry` shape
  * a record is never committed unless a human set `approved: true`
  * duplicates (same ref, or same district+date+near-identical text) are skipped
  * the write is atomic (temp file + replace) and takes a timestamped backup
  * after writing, the corpus is re-parsed through the engine's own loader —
    if it does not load, the backup is restored automatically
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..engine import FIR_FILE, load_fir_corpus
from .extract import CRIME_TYPES

# Staging lives beside the data it will eventually become, but is gitignored
# (see data/ingest/.gitignore) — these are working files, not deliverables.
STAGING_DIR = FIR_FILE.parent / "ingest"
ARTICLES_FILE = STAGING_DIR / "articles.json"
CANDIDATES_FILE = STAGING_DIR / "candidates.json"
BACKUP_DIR = STAGING_DIR / "backups"

_REQUIRED_FIELDS = ("ref", "district", "lat", "lon", "date", "source", "text")


def validate_record(record: dict) -> list[str]:
    """Return a list of problems. Empty list = the record is committable."""
    problems: list[str] = []

    for field in _REQUIRED_FIELDS:
        if record.get(field) in (None, "", []):
            problems.append(f"missing required field: {field}")

    for coord, lo, hi in (("lat", 6.0, 37.5), ("lon", 68.0, 97.5)):
        value = record.get(coord)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{coord} must be a number, got {type(value).__name__}")
        elif not lo <= float(value) <= hi:
            # India's bounding box. A coordinate outside it is a geocoding bug,
            # and it would snap to a corridor node it has no business near.
            problems.append(f"{coord}={value} is outside India's bounding box")

    date = record.get("date")
    if date:
        try:
            datetime.strptime(str(date), "%Y-%m-%d")
        except ValueError:
            problems.append(f"date must be YYYY-MM-DD, got {date!r}")

    types = record.get("crime_types") or []
    if not isinstance(types, list):
        problems.append("crime_types must be a list")
    else:
        unknown = [t for t in types if t not in CRIME_TYPES]
        if unknown:
            problems.append(f"unknown crime_types: {unknown}")

    if not isinstance(record.get("places", []), list):
        problems.append("places must be a list")

    text = record.get("text") or ""
    if text and len(text) < 40:
        problems.append("text is too short to be useful evidence (<40 chars)")

    return problems


def _fingerprint(record: dict) -> tuple[str, str, str]:
    """District + date + a coarse text signature, for near-duplicate detection."""
    text = " ".join((record.get("text") or "").lower().split())[:120]
    return (
        (record.get("district") or "").strip().lower(),
        str(record.get("date") or ""),
        text,
    )


def dedupe_against_corpus(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split candidates into (new, duplicates) against the committed corpus."""
    try:
        existing = json.loads(FIR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = []

    known_refs = {e.get("ref") for e in existing}
    known_prints = {_fingerprint(e) for e in existing}

    new: list[dict] = []
    duplicates: list[dict] = []
    for record in candidates:
        fingerprint = _fingerprint(record)
        if record.get("ref") in known_refs or fingerprint in known_prints:
            duplicates.append(record)
            continue
        known_refs.add(record.get("ref"))
        known_prints.add(fingerprint)
        new.append(record)
    return new, duplicates


def _strip_review_keys(record: dict) -> dict:
    """Committed records carry only corpus fields — no pipeline metadata."""
    return {
        "ref": record["ref"],
        "district": record["district"],
        "state": record.get("state", "Unknown"),
        "lat": float(record["lat"]),
        "lon": float(record["lon"]),
        "date": record["date"],
        "source": record["source"],
        "text": record["text"],
        "places": record.get("places", []),
        "crime_types": record.get("crime_types", []),
    }


def commit(candidates: list[dict], *, dry_run: bool = False) -> dict:
    """Append approved, valid, non-duplicate candidates to the FIR corpus.

    Returns a report dict. On `dry_run` nothing is written and the report shows
    exactly what a real run would do.
    """
    approved = [c for c in candidates if c.get("approved") is True]
    skipped_unapproved = len(candidates) - len(approved)

    valid: list[dict] = []
    invalid: list[dict] = []
    for record in approved:
        problems = validate_record(record)
        if problems:
            invalid.append({"ref": record.get("ref"), "problems": problems})
        else:
            valid.append(record)

    new, duplicates = dedupe_against_corpus(valid)

    report = {
        "candidates": len(candidates),
        "approved": len(approved),
        "skipped_unapproved": skipped_unapproved,
        "invalid": invalid,
        "duplicates": len(duplicates),
        "committed": len(new),
        "refs": [r["ref"] for r in new],
        "dry_run": dry_run,
        "backup": None,
    }

    if dry_run or not new:
        return report

    existing = json.loads(FIR_FILE.read_text(encoding="utf-8"))
    merged = existing + [_strip_review_keys(r) for r in new]

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"fir_corpus.{stamp}.json"
    shutil.copy2(FIR_FILE, backup)
    report["backup"] = str(backup)

    temp = FIR_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(FIR_FILE)

    # Re-parse through the engine's own loader. If the engine cannot read what
    # we just wrote, put the old file back before anything else touches it.
    try:
        load_fir_corpus()
    except Exception as exc:
        shutil.copy2(backup, FIR_FILE)
        report["committed"] = 0
        report["error"] = f"corpus failed to reload ({type(exc).__name__}: {exc}); backup restored"

    return report


# ── staging I/O ─────────────────────────────────────────────────────────────

def save_candidates(candidates: list[dict], path: Path = CANDIDATES_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_candidates(path: Path = CANDIDATES_FILE) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
