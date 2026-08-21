# 📰 Supply Trail — News Ingester

Grows `data/fir_corpus.json` from public reporting, **as an offline batch job**.

> **Scope note:** everything in this document lives inside `command-centre/supply_trail/`.
> No other module is touched, and the running engine is unmodified — it reads
> `fir_corpus.json` exactly as it always has and does not know this package exists.

---

## Why batch, and not an endpoint

The platform's defensibility rests on three properties. A live news fetch inside
`/supply-trail` would break all three:

| Property | What a live fetch would do |
|---|---|
| `audit_trail.inputs_hash` reproducibility | The same seizures would yield different trails depending on the day's headlines |
| "The demo cannot die" | A slow or down feed would hang the request |
| Nothing unverified reaches the evidence chain | An LLM's reading of a headline would become evidence with nobody having checked it |

So the pipeline is invoked by hand and its **only** output is a reviewed, committed
data file. This is the same principle the project already applies to the research
modules: precompute to static JSON, never run in the request path.

## Why it's worth having

`/supply-trail/routes` can only originate a route at a FIR entry tagged
`printing_press`. The shipped corpus has **three** (Asansol, Vadodara, Deoghar) —
so three is the total universe of possible origins, and a district reachable from
none of them returns 404.

Every additional documented press is a new answerable question. That is the
capability this unlocks; it is not cosmetic.

---

## Pipeline

```
fetch  ──▶  extract  ──▶  review  ──▶  commit
(network)   (LLM or        (human)     (writes fir_corpus.json)
             rules)
```

Each stage reads the previous stage's file, so you can stop, inspect, hand-edit
and resume at any point.

```bash
cd command-centre/supply_trail
export PYTHONPATH=src          # PowerShell: $env:PYTHONPATH = "src"

python -m aegis_supply_trail.ingest.cli status
python -m aegis_supply_trail.ingest.cli fetch --limit 25
python -m aegis_supply_trail.ingest.cli extract
python -m aegis_supply_trail.ingest.cli review          # or --list to just print
python -m aegis_supply_trail.ingest.cli commit --dry-run
python -m aegis_supply_trail.ingest.cli commit
```

Restart the backend after a commit for the new corpus to take effect.

### `fetch`
Google News RSS — **no API key, no signup**, India-scoped (`hl=en-IN&gl=IN`).
Parsed with `xml.etree`, so the module keeps its `dependencies = []` promise.

Takes headline + snippet + publisher + date only. Article bodies are deliberately
**not** scraped: per-publisher scrapers rot, and the existing corpus entries are
one-to-three-sentence summaries anyway.

### `extract`
Two extractors, same output shape — mirroring the project's deterministic-floor
pattern:

- **deterministic** — keyword rules + the offline gazetteer. Always available.
- **LLM** — Groq → Gemini, JSON-constrained. Used when a key is present, with
  per-article fallback to the deterministic path.

**The LLM never invents a coordinate.** It chooses *which* named place is the event
location; the gazetteer supplies the lat/lon.

Articles mentioning no resolvable place are dropped rather than stored with a
guessed position — a FIR entry without a location is inert.

### `review` — the gate that makes this safe
Every candidate carries `approved: false` and a `_review` block (headline, link,
confidence, unresolved places). **Nothing is ever auto-approved.**

`printing_press` candidates are flagged loudly, because that tag turns a location
into a supply *origin* for route ranking — a wrong one is expensive.

You can use the interactive prompt or just hand-edit `candidates.json`.

### `commit`
Deliberately paranoid, since the corpus is live data:

- field-by-field validation against the `FirEntry` shape
- coordinates must fall inside India's bounding box
- `crime_types` must come from the existing corpus vocabulary
- duplicates skipped (same `ref`, or same district+date+text signature)
- timestamped backup, then an **atomic** temp-file replace
- the corpus is **re-parsed through the engine's own `load_fir_corpus()`** after
  writing — if it does not load, the backup is restored automatically

Committed records carry only corpus fields; `approved` and `_review` never leak in.

---

## Conventions

**Refs are prefixed `NEWS-`**, not `FIR-`, so ingested records stay visually
distinguishable from the hand-curated ones in every UI, log line and case file.
Format: `NEWS-{STATE}-{YEAR}-{HASH6}` — stable for a given article, so re-running
the pipeline cannot double-add.

**The gazetteer needs no geocoding API.** It is built from data the module already
ships — the 58 corridor nodes in `corridors.json` plus districts already in the
corpus (72 place keys). Station decoration is handled, so "Kanpur Central" in the
data matches "Kanpur" in a headline. This is the right trade: a seizure somewhere
the corridor network has never heard of cannot be snapped to a corridor anyway.

**Staging is gitignored** via `data/ingest/.gitignore` (self-contained, so the root
`.gitignore` — a shared file — needs no edit). Only reviewed records that reach
`fir_corpus.json` belong in git.

---

## Circular reporting — the objection to be ready for

> *"News about seizures is published when the authorities want it published. If
> your intelligence comes from news, aren't you just reflecting back what the
> police already knew?"*

**Largely yes, and the answer is to concede it precisely.** This corpus is
downstream of enforcement: lagged, publication-biased, and — for a police user —
often not new. Specifically, `/supply-trail/routes` can only originate a route at
an **already-raided, already-reported** press. A press nobody has busted does not
exist to this system.

What survives the objection:

- **The corpus is not the detection signal.** `compute_trail()` runs on seizures
  from the event store — Counterfeit Vision's own scans, which are not
  police-mediated. News only corroborates a corridor (25% of confidence) and
  supplies candidate origins. The novel claim — *"these seizures form a cluster
  pointing back toward X"* — is computed from our own detections.
- **Assembly is the work.** A Jharkhand officer does not read Gujarat CID press
  releases. Each fact is public; the assembled corridor model is not.
- **The join is new.** No article contains the sentence *"notes scanned in Jamtara
  today snap to a corridor from Asansol."*

The correct posture, and the standard one in OSINT: **public reporting is a prior,
not a finding.** It constrains hypotheses; it does not generate conclusions.

### Bias leaks into the confidence number

`fir_score = min(hits × 0.5, 1.0)` — two FIRs near a corridor max that component
out. If enforcement publicises more in some districts, those corridors score higher
**regardless of where crime actually concentrates**. Negligible at 8 entries;
document it at 80.

## What to tell a judge

> *"Our detections are the signal; public reporting is the prior. We assemble
> scattered press and police reports into a corridor model, then infer which
> corridor a **newly scanned** note travelled down. The inference is ours; the
> background is public. An LLM structures the reports, a human approves every
> record, and the request path makes no network call — so `inputs_hash`
> reproducibility holds."*

Do **not** claim live news monitoring, and do **not** claim the system discovers
unknown sources. It connects new detections to known ones. If pressed on the loop,
name the real fix: production ingests **CCTNS/NCRP FIR records**, which include the
cases that were never publicised — that is what breaks the publication loop. News
is the hackathon-legal stand-in for data we cannot access.

---

## Known limitations

- **Relevance filtering is imperfect.** A real run surfaced a court-acquittal story
  that merely *mentioned* seizure documents. The review gate is load-bearing, not
  decorative — do not skip it.
- **District inference picks the first resolvable place**, which may be a
  destination rather than the seizure location. The LLM extractor is better at this
  than the deterministic one; verify either way.
- **Coordinates are node-level, not district-level** for places that only exist as
  corridor nodes (e.g. "Delhi" resolves to the DEL airport node). Fine for corridor
  snapping at 60 km tolerance; not a survey-grade location.
- **Google News RSS returns redirect links**, not publisher URLs. Fine for
  provenance; the link is for a human to click during review.

## Tests

```bash
python -m pytest tests/test_ingest.py -q     # 37 tests, fully offline
python -m pytest tests/ -q                   # 66 tests, whole module
```

No network and no LLM are required: feed parsing is tested against a fixture, and
commit tests redirect the corpus to a temp directory so real data is never touched.
