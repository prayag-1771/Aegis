"""Intel Feed — the human review surface for news-ingested intelligence.

The Supply Trail FIR corpus is grown from public reporting by an OFFLINE batch
job (`aegis_supply_trail.ingest.cli`: fetch → extract). This router exposes the
half of that pipeline a human must do — reviewing candidates and deciding which
ones become evidence — so it can happen in the dashboard instead of a terminal.

What this surface deliberately does NOT do:
  * fetch news (no network call in any request path — the demo cannot hang)
  * bypass validation (approving here runs the same commit path as the CLI)
  * auto-approve anything

Every mutation is reversible: `undo` walks back one ingest, `reset` returns the
corpus to its state before the first ingest ever happened. That makes the page
safe to drive repeatedly during rehearsal, matching the existing `/demo/reset`
idiom for injected fraud rings.

The corpus is re-read from disk on every `/supply-trail` request (no caching
anywhere in the serving path), so an ingest is visible on the dashboard
immediately — no backend restart.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/intel-feed", tags=["intel-feed"])


def _service():
    """Imported lazily so the backend still boots if supply_trail is absent."""
    try:
        from aegis_supply_trail.ingest import service
    except ImportError as exc:  # pragma: no cover - install-time problem only
        raise HTTPException(
            503, f"supply-trail ingest package unavailable: {exc}"
        ) from exc
    return service


@router.get("")
@router.get("/")
def feed() -> dict:
    """Staged candidates + current corpus stats — everything the page renders."""
    return _service().feed_state()


@router.post("/ingest")
def ingest(body: dict) -> dict:
    """Commit the selected candidates into the FIR corpus.

    Body: {"refs": ["NEWS-RJ-2026-9695EF", ...]}

    Records run through the same validation, de-duplication, backup and
    reload-guard as the CLI path. A record that fails validation stays staged
    with its problems reported rather than being silently dropped.
    """
    refs = (body or {}).get("refs") or []
    if not isinstance(refs, list) or not refs:
        raise HTTPException(422, "body must contain a non-empty 'refs' array")

    report = _service().ingest([str(r) for r in refs])
    if report.get("error"):
        raise HTTPException(422, report["error"])
    return report


@router.post("/undo")
def undo() -> dict:
    """Reverse the most recent ingest by restoring its backup."""
    result = _service().undo_last()
    if not result.get("restored"):
        raise HTTPException(409, result.get("error", "nothing to undo"))
    return result


@router.post("/reset")
def reset() -> dict:
    """Restore the corpus to its state before the first ingest."""
    result = _service().reset_baseline()
    if not result.get("restored"):
        raise HTTPException(409, result.get("error", "no baseline recorded"))
    return result
