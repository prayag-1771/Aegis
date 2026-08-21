"""Supply Trail ingest CLI.

    python -m aegis_supply_trail.ingest.cli fetch     # network -> articles.json
    python -m aegis_supply_trail.ingest.cli extract   # articles -> candidates.json
    python -m aegis_supply_trail.ingest.cli review    # human approves/rejects
    python -m aegis_supply_trail.ingest.cli commit    # approved -> fir_corpus.json
    python -m aegis_supply_trail.ingest.cli status    # where the pipeline stands

Each stage reads the previous stage's file, so you can stop, inspect, hand-edit
and resume at any point. `commit --dry-run` shows exactly what would change
without touching the corpus.
"""

from __future__ import annotations

import argparse
import json
import sys

from ..engine import FIR_FILE
from .corpus import (
    ARTICLES_FILE,
    CANDIDATES_FILE,
    commit,
    dedupe_against_corpus,
    load_candidates,
    save_candidates,
    validate_record,
)
from .extract import extract, llm_available
from .sources import DEFAULT_QUERIES, fetch_all, load_articles, save_articles


def _corpus() -> list[dict]:
    try:
        return json.loads(FIR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


# ── fetch ───────────────────────────────────────────────────────────────────

def cmd_fetch(args: argparse.Namespace) -> int:
    queries = args.query or list(DEFAULT_QUERIES)
    print(f"Fetching {len(queries)} quer{'y' if len(queries) == 1 else 'ies'} "
          f"(limit {args.limit} each)...")
    articles = fetch_all(queries, limit_per_query=args.limit)
    if not articles:
        print("\nNo articles fetched. Check connectivity — nothing was written.")
        return 1
    save_articles(articles, ARTICLES_FILE)
    print(f"\n{len(articles)} unique articles -> {ARTICLES_FILE}")
    print("Next: python -m aegis_supply_trail.ingest.cli extract")
    return 0


# ── extract ─────────────────────────────────────────────────────────────────

def cmd_extract(args: argparse.Namespace) -> int:
    articles = load_articles(ARTICLES_FILE)
    if not articles:
        print(f"No articles at {ARTICLES_FILE}. Run `fetch` first.")
        return 1

    print(f"Extracting from {len(articles)} articles...")
    candidates = extract(articles, use_llm=not args.no_llm)
    if not candidates:
        print("\nNo usable candidates. Every article was either irrelevant or "
              "mentioned no place the gazetteer can locate.")
        save_candidates([], CANDIDATES_FILE)
        return 0

    new, duplicates = dedupe_against_corpus(candidates)
    save_candidates(new, CANDIDATES_FILE)

    presses = sum(1 for c in new if "printing_press" in c.get("crime_types", []))
    print(f"\n{len(new)} candidates -> {CANDIDATES_FILE}")
    print(f"  {len(duplicates)} skipped as duplicates of the existing corpus")
    print(f"  {presses} tagged printing_press (these become route ORIGINS — "
          f"review them hardest)")
    print("\nNothing is in the corpus yet. Next:")
    print("  python -m aegis_supply_trail.ingest.cli review")
    return 0


# ── review ──────────────────────────────────────────────────────────────────

def _show(record: dict, index: int, total: int) -> None:
    review = record.get("_review", {})
    print("\n" + "=" * 72)
    print(f"[{index}/{total}]  {record.get('ref')}   confidence={review.get('confidence')}"
          f"  extractor={review.get('extractor')}")
    print("=" * 72)
    print(f"  headline : {review.get('headline', '')}")
    print(f"  district : {record.get('district')}  ({record.get('state')})"
          f"   lat={record.get('lat')}  lon={record.get('lon')}")
    print(f"  date     : {record.get('date')}")
    print(f"  source   : {record.get('source')}")
    print(f"  types    : {', '.join(record.get('crime_types', []))}")
    print(f"  places   : {', '.join(record.get('places', []))}")
    if review.get("places_unresolved"):
        print(f"  UNPLACED : {', '.join(review['places_unresolved'])}")
    print(f"  link     : {review.get('link', '')}")
    print(f"\n  text: {record.get('text', '')}")
    if "printing_press" in record.get("crime_types", []):
        print("\n  *** printing_press: this location becomes a supply ORIGIN for "
              "route ranking. Only approve if the article actually reports a "
              "press/printing facility being found. ***")
    problems = validate_record(record)
    if problems:
        print(f"\n  VALIDATION PROBLEMS: {problems}")


def cmd_review(args: argparse.Namespace) -> int:
    candidates = load_candidates(CANDIDATES_FILE)
    if not candidates:
        print(f"No candidates at {CANDIDATES_FILE}. Run `extract` first.")
        return 1

    pending = [c for c in candidates if c.get("approved") is not True]
    print(f"{len(candidates)} candidates, {len(pending)} awaiting review.")
    if not pending:
        print("All reviewed. Next: commit")
        return 0

    if args.list:
        for i, record in enumerate(pending, 1):
            _show(record, i, len(pending))
        print("\n" + "=" * 72)
        print(f"Listing only — nothing changed. Edit {CANDIDATES_FILE} by hand "
              f'(set "approved": true), or run `review` without --list.')
        return 0

    print("For each: [y] approve  [n] reject  [s] skip  [q] save and quit\n")
    changed = 0
    for i, record in enumerate(pending, 1):
        _show(record, i, len(pending))
        while True:
            try:
                answer = input("\n  approve? [y/n/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nInterrupted — saving progress.")
                save_candidates(candidates, CANDIDATES_FILE)
                return 0
            if answer in ("y", "n", "s", "q"):
                break
            print("  please answer y, n, s or q")

        if answer == "q":
            break
        if answer == "y":
            record["approved"] = True
            changed += 1
        elif answer == "n":
            record["approved"] = False
            record["_review"]["rejected"] = True

    # Rejected records are dropped so a re-run does not re-ask about them.
    kept = [c for c in candidates if not c.get("_review", {}).get("rejected")]
    save_candidates(kept, CANDIDATES_FILE)
    approved_total = sum(1 for c in kept if c.get("approved") is True)
    print(f"\n{changed} approved this session; {approved_total} approved in total.")
    print("Next: python -m aegis_supply_trail.ingest.cli commit --dry-run")
    return 0


# ── commit ──────────────────────────────────────────────────────────────────

def cmd_commit(args: argparse.Namespace) -> int:
    candidates = load_candidates(CANDIDATES_FILE)
    if not candidates:
        print(f"No candidates at {CANDIDATES_FILE}. Run `extract` first.")
        return 1

    before = len(_corpus())
    report = commit(candidates, dry_run=args.dry_run)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("error"):
        print(f"\nFAILED: {report['error']}")
        return 1

    if args.dry_run:
        print(f"\nDRY RUN — corpus untouched ({before} entries). "
              f"{report['committed']} would be added.")
        return 0

    after = len(_corpus())
    print(f"\nCorpus: {before} -> {after} entries.")
    if report["backup"]:
        print(f"Backup: {report['backup']}")
    if report["committed"]:
        # Drop committed records so a second commit cannot double-add them.
        remaining = [c for c in candidates if c.get("ref") not in set(report["refs"])]
        save_candidates(remaining, CANDIDATES_FILE)
        print("Restart the backend for the new corpus to take effect.")
    return 0


# ── status ──────────────────────────────────────────────────────────────────

def cmd_status(_: argparse.Namespace) -> int:
    corpus = _corpus()
    presses = [e for e in corpus if "printing_press" in (e.get("crime_types") or [])]
    ingested = [e for e in corpus if str(e.get("ref", "")).startswith("NEWS-")]
    articles = load_articles(ARTICLES_FILE)
    candidates = load_candidates(CANDIDATES_FILE)
    approved = [c for c in candidates if c.get("approved") is True]

    print("FIR corpus")
    print(f"  entries          : {len(corpus)}")
    print(f"  printing presses : {len(presses)}  "
          f"({', '.join(p['district'] for p in presses) or 'none'})")
    print(f"  news-ingested    : {len(ingested)}")
    print("\nStaging")
    print(f"  articles fetched : {len(articles)}   ({ARTICLES_FILE})")
    print(f"  candidates       : {len(candidates)} ({len(approved)} approved)")
    print("\nExtractor")
    print(f"  LLM available    : {llm_available()}")
    print("\nReminder: only `printing_press` entries can originate a route in "
          "/supply-trail/routes.")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ and en-dashes on cp1252 consoles
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(
        prog="aegis-supply-trail-ingest", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="pull articles from Google News RSS")
    p_fetch.add_argument("--query", action="append", help="override queries (repeatable)")
    p_fetch.add_argument("--limit", type=int, default=25, help="items per query")
    p_fetch.set_defaults(fn=cmd_fetch)

    p_extract = sub.add_parser("extract", help="articles -> candidate records")
    p_extract.add_argument("--no-llm", action="store_true",
                           help="force the deterministic extractor")
    p_extract.set_defaults(fn=cmd_extract)

    p_review = sub.add_parser("review", help="approve/reject candidates")
    p_review.add_argument("--list", action="store_true",
                          help="print all candidates without prompting")
    p_review.set_defaults(fn=cmd_review)

    p_commit = sub.add_parser("commit", help="write approved records to the corpus")
    p_commit.add_argument("--dry-run", action="store_true",
                          help="report what would change; write nothing")
    p_commit.set_defaults(fn=cmd_commit)

    sub.add_parser("status", help="show pipeline state").set_defaults(fn=cmd_status)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
