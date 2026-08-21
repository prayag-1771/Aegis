"""Supply Trail news ingester — grows the FIR corpus from public reporting.

WHY THIS IS A BATCH TOOL AND NOT AN ENDPOINT
--------------------------------------------
The running system's defensibility rests on three properties:

  1. `audit_trail.inputs_hash` reproducibility — same inputs, same package.
  2. The demo cannot die — no request path depends on an external service.
  3. Nothing unverified reaches the evidence chain.

A live news fetch inside `/supply-trail` would break all three: the same
seizures would produce different trails depending on what got published that
morning, a slow feed would hang the request, and an LLM's reading of a headline
would become evidence with nobody having checked it.

So this package NEVER runs in the request path. It is a pipeline you invoke by
hand, whose only output is a reviewed, committed data file:

    fetch  ->  extract  ->  review  ->  commit
    (net)      (LLM or       (human)     (writes data/fir_corpus.json)
                rules)

The engine keeps reading `fir_corpus.json` exactly as it always has. It does not
know this package exists.

WHAT IT IS FOR — AND WHAT IT IS NOT
-----------------------------------
`/supply-trail/routes` can only originate a route at a FIR entry tagged
`printing_press`. The shipped corpus has three (Asansol, Vadodara, Deoghar), so
three is the total universe of possible origins. Every additional documented
press is a new answerable question — that is the capability this unlocks.

The ceiling that comes with the source: news is DOWNSTREAM of enforcement. A
press nobody raided and published cannot appear here, so this connects new
detections to KNOWN sources; it never discovers unknown ones. Reporting is also
lagged and publication-biased.

That is survivable because the corpus is not the detection signal. `compute_trail`
runs on seizures from the event store — Counterfeit Vision's own scans, which are
not police-mediated. Public reporting is a PRIOR that constrains where a corridor
might lead; the inference itself is computed from our own detections. Frame it
that way and the circular-reporting objection lands harmlessly.

USAGE
-----
    python -m aegis_supply_trail.ingest.cli fetch
    python -m aegis_supply_trail.ingest.cli extract
    python -m aegis_supply_trail.ingest.cli review        # interactive
    python -m aegis_supply_trail.ingest.cli commit

Run `status` at any point to see where the pipeline stands. Nothing is written
to the corpus until `commit`, and `commit` only takes records a human marked
approved.
"""

from __future__ import annotations

from .corpus import (
    STAGING_DIR,
    commit,
    dedupe_against_corpus,
    load_candidates,
    save_candidates,
    validate_record,
)
from .extract import extract, extract_deterministic, prefilter
from .gazetteer import find_places, gazetteer, resolve
from .sources import DEFAULT_QUERIES, Article, fetch_all, load_articles, save_articles

__all__ = [
    "DEFAULT_QUERIES",
    "STAGING_DIR",
    "Article",
    "commit",
    "dedupe_against_corpus",
    "extract",
    "extract_deterministic",
    "fetch_all",
    "find_places",
    "gazetteer",
    "load_articles",
    "load_candidates",
    "prefilter",
    "resolve",
    "save_articles",
    "save_candidates",
    "validate_record",
]
