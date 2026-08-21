"""Article -> candidate FIR record.

Two extractors, same output shape, mirroring the pattern the rest of Aegis
already uses (deterministic floor, LLM on top):

  * `extract_deterministic` — keyword rules + the offline gazetteer. Needs no
    key, no network, and always runs. This is the floor: with zero API keys the
    pipeline still works end to end.
  * `extract_llm` — an LLM reads headline+snippet and returns the same fields,
    with a better one-line summary and cleaner place extraction. Optional.

Neither one writes to the corpus. Both emit CANDIDATES carrying `approved:
false` and a `_review` block explaining what was inferred and how confident the
extractor is, so a human can judge each record quickly. That review step is the
whole point — an LLM's reading of a headline is not evidence until someone has
checked it.

The `crime_types` vocabulary matches the existing corpus exactly; `printing_press`
is the load-bearing tag, because `/supply-trail/routes` originates routes only
at entries carrying it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

from .gazetteer import find_places, resolve, state_code
from .sources import Article

# ── crime-type vocabulary (must match the shipped corpus) ───────────────────
CRIME_TYPES: tuple[str, ...] = (
    "counterfeit_currency",
    "printing_press",
    "transport",
    "distribution",
    "hawala",
    "money_laundering",
    "digital_arrest_ring",
)

_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "counterfeit_currency": re.compile(
        r"\b(?:fake|counterfeit|forged|ficn)\b.{0,30}\b(?:currenc|note|cash|rupee)", re.IGNORECASE
    ),
    "printing_press": re.compile(
        r"\b(?:printing\s+press|offset\s+press|press\s+(?:seized|raid|busted)|"
        r"printing\s+(?:unit|machine|facility)|minting)\b", re.IGNORECASE
    ),
    "transport": re.compile(
        r"\b(?:transport|courier|carrying|smuggl\w+|consignment|parcel|"
        r"railway\s+station|train|truck|bus)\b", re.IGNORECASE
    ),
    "distribution": re.compile(
        r"\b(?:distribut\w+|circulat\w+|supply\s+chain|racket|network|peddl\w+)\b", re.IGNORECASE
    ),
    "hawala": re.compile(r"\bhawala\b", re.IGNORECASE),
    "money_laundering": re.compile(r"\bmoney\s+launder\w+\b", re.IGNORECASE),
    "digital_arrest_ring": re.compile(r"\bdigital\s+arrest\b", re.IGNORECASE),
}

# An article must look like a counterfeit-currency story at all before we spend
# an LLM call — or a reviewer's attention — on it.
_RELEVANCE = re.compile(
    # FICN = "Fake Indian Currency Notes" — the acronym IS the subject, so it
    # needs no accompanying currency word ("FICN worth lakhs recovered").
    r"\bficn\b"
    r"|\b(?:fake|counterfeit|forged)\b.{0,40}\b(?:currenc|note|cash|rupee|money)"
    r"|\b(?:currenc|note)\w*\b.{0,40}\b(?:fake|counterfeit|forged)\b",
    re.IGNORECASE,
)
# Stories that merely *mention* fake notes without an event we can locate.
_NOISE = re.compile(
    r"\b(?:opinion|editorial|how\s+to\s+spot|explainer|quiz|movie|film)\b", re.IGNORECASE
)

# Court-outcome coverage: real, on-topic, and useless to this corpus. An
# acquittal reports a VERDICT, not a seizure with a place and a date we can put
# on a corridor — and its district is the court's, not the crime's. Filtered
# unless the same story also reports a fresh recovery.
_COURT_OUTCOME = re.compile(
    r"\b(?:acquit\w*|convict\w*|verdict|sentenc\w*|bail|discharg\w+|"
    r"chargesheet|charge\s*sheet|trial|hearing|tribunal|high\s+court|"
    r"supreme\s+court)\b",
    re.IGNORECASE,
)

# A record needs a concrete enforcement EVENT to be locatable evidence.
_EVENT = re.compile(
    r"\b(?:seiz\w+|recover\w+|bust\w+|raid\w+|arrest\w+|apprehend\w+|nab\w+|"
    r"caught|held|detain\w+|confiscat\w+|smuggl\w+|intercept\w+)\b",
    re.IGNORECASE,
)


def prefilter(article: Article) -> bool:
    """Cheap relevance gate. False = never shown to the LLM or the reviewer.

    Three conditions, all necessary:
      1. it is about counterfeit currency at all
      2. it reports an enforcement EVENT (seizure/raid/arrest), not commentary
      3. it is not primarily court-outcome coverage

    (2) is what keeps a locatable seizure in and a "court acquits man in fake
    currency case" out — the latter is on-topic but carries the court's district,
    not the crime's, so committing it would pin a false point on a corridor.
    """
    text = article.text
    if _NOISE.search(text):
        return False
    if not _RELEVANCE.search(text):
        return False
    if not _EVENT.search(text):
        return False
    # A court story is only kept if it ALSO reports a fresh recovery. VERB forms
    # only: "Seizure documents mentioned an FIR number" is paperwork in an
    # acquittal write-up, not a recovery, and the noun form let exactly that
    # story through.
    if _COURT_OUTCOME.search(text) and not re.search(
        r"\b(?:seized|seizes|seizing|recovered|recovers|recovering|"
        r"busted|busts|busting|raided|raids|raiding|confiscated|confiscates)\b",
        text,
        re.IGNORECASE,
    ):
        return False
    return True


def classify_crime_types(text: str) -> list[str]:
    """Every crime type whose pattern fires, in canonical order."""
    found = [name for name, pattern in _TYPE_PATTERNS.items() if pattern.search(text)]
    # A story that reached here is about counterfeit currency by construction.
    if "counterfeit_currency" not in found:
        found.insert(0, "counterfeit_currency")
    return [t for t in CRIME_TYPES if t in found]


def make_ref(district: str, state: str | None, date: str, seed: str) -> str:
    """Stable id. `NEWS-` prefix (not `FIR-`) so ingested records stay visually
    distinguishable from the hand-curated ones in every UI and log line."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    year = (date or "")[:4] or "0000"
    return f"NEWS-{state_code(state)}-{year}-{digest}"


def _summarise(article: Article, limit: int = 400) -> str:
    """One-paragraph record text in the corpus's existing style.

    The hand-curated entries read as clean report prose ("Dhanbad railway GRP
    arrested two persons at platform 3 with..."), so a machine-made record should
    too — a stuttering, entity-littered snippet reads as untrustworthy even when
    the underlying facts are fine.

    Trims at a SENTENCE boundary rather than mid-word, because a record cut at
    "...police rema" looks broken next to the curated entries.
    """
    headline = article.title.strip().rstrip(" .")
    body = article.summary.strip()

    text = f"{headline}. {body}".strip() if body else f"{headline}."
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)  # no space before punctuation
    if not text.endswith((".", "!", "?")):
        text += "."

    if len(text) <= limit:
        return text

    # Prefer the last complete sentence that fits; fall back to a word boundary.
    window = text[:limit]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > limit // 2:
        return window[: cut + 1]
    return window.rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def extract_deterministic(article: Article) -> dict | None:
    """Rules + gazetteer -> candidate record, or None if unusable.

    Returns None when no mentioned place can be resolved to coordinates: a FIR
    entry without a location is inert (it can corroborate no corridor node and
    originate no route), so an unplaceable article is dropped rather than stored
    with a guessed position.
    """
    if not prefilter(article):
        return None

    places = find_places(article.text)
    located = [(p, resolve(p)) for p in places]
    located = [(p, c) for p, c in located if c is not None]
    if not located:
        return None

    district, (lat, lon, state) = located[0]
    crime_types = classify_crime_types(article.text)

    return {
        "ref": make_ref(district, state, article.published, article.link or article.title),
        "district": district,
        "state": state or "Unknown",
        "lat": lat,
        "lon": lon,
        "date": article.published,
        "source": f"{article.publisher}, {article.published}",
        "text": _summarise(article),
        "places": [p for p, _ in located],
        "crime_types": crime_types,
        "approved": False,
        "_review": {
            "extractor": "deterministic",
            "confidence": "high" if len(located) > 1 and "printing_press" in crime_types
            else "medium" if len(located) > 1 else "low",
            "link": article.link,
            "headline": article.title,
            "places_unresolved": [p for p in places if resolve(p) is None],
            "notes": (
                "District inferred as the first resolvable place mentioned — "
                "verify it is the SEIZURE location, not a destination or an "
                "unrelated place in the same sentence."
            ),
        },
    }


# ── optional LLM extractor ──────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You extract structured records from Indian news about counterfeit-currency crime,
for a police intelligence corpus.

For the article given, return JSON:
{"relevant": true|false,
 "district": "<the district/city where the SEIZURE or RAID happened>",
 "places": ["<every place named>"],
 "crime_types": ["counterfeit_currency","printing_press","transport",
                 "distribution","hawala","money_laundering"],
 "summary": "<2-3 factual sentences, no speculation>"}

RULES
- relevant=false unless a concrete counterfeit-currency EVENT occurred (seizure,
  raid, arrest, press bust). Opinion pieces, explainers and how-to-spot-fakes
  articles are relevant=false.
- `district` must be where the event happened, NOT a destination the notes were
  headed to and NOT a place mentioned only as background.
- Include "printing_press" ONLY if a press/printing facility was actually found.
  This tag makes the location a supply ORIGIN, so a wrong one is expensive.
- Summarise only what the article states. Never infer a supply chain that is
  not reported.
- Output ONLY the JSON object. No markdown fences.
"""


def _load_dotenv() -> None:
    """Load LLM keys from the fusion .env (where the project already keeps them)
    or a local supply_trail .env. Never overrides an existing env var."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / ".env",            # command-centre/supply_trail/.env
        here.parents[4] / "fusion" / ".env",  # command-centre/fusion/.env
    ]
    for env_file in candidates:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def llm_available() -> bool:
    """True when an LLM extraction could actually run.

    `find_spec` rather than a throwaway import: supply_trail declares no
    dependencies, so httpx may genuinely be absent, and probing for it without
    importing keeps this cheap and side-effect-free.
    """
    _load_dotenv()
    if importlib.util.find_spec("httpx") is None:
        return False
    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def _call_llm(article_text: str, *, timeout: float = 30.0) -> dict | None:
    """One extraction call. Groq first, then Gemini. None on any failure —
    the caller falls back to the deterministic extractor."""
    import httpx

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "temperature": 0.1,
                    "max_tokens": 800,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": f"ARTICLE:\n{article_text}"},
                    ],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            return json.loads(response.json()["choices"][0]["message"]["content"])
        except Exception as exc:
            print(f"  [warn] groq extraction failed: {type(exc).__name__}: {exc}")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            response = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.0-flash:generateContent",
                headers={"x-goog-api-key": gemini_key},
                json={
                    "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                    "contents": [{"parts": [{"text": f"ARTICLE:\n{article_text}"}]}],
                    "generationConfig": {"temperature": 0.1,
                                         "responseMimeType": "application/json"},
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(payload)
        except Exception as exc:
            print(f"  [warn] gemini extraction failed: {type(exc).__name__}: {exc}")

    return None


def extract_llm(article: Article) -> dict | None:
    """LLM extraction, geocoded through the same offline gazetteer.

    The LLM chooses WHICH place is the event location; the gazetteer supplies
    the coordinates. The model never invents a latitude.
    """
    if not prefilter(article):
        return None
    parsed = _call_llm(article.text)
    if not parsed or not parsed.get("relevant"):
        return None

    district = (parsed.get("district") or "").strip()
    coords = resolve(district)
    if coords is None:
        # Fall back to any place the model named that we can actually place.
        for place in parsed.get("places", []):
            coords = resolve(str(place))
            if coords:
                district = str(place)
                break
    if coords is None:
        return None

    lat, lon, state = coords
    types = [t for t in CRIME_TYPES if t in (parsed.get("crime_types") or [])]
    if "counterfeit_currency" not in types:
        types.insert(0, "counterfeit_currency")

    return {
        "ref": make_ref(district, state, article.published, article.link or article.title),
        "district": district.title(),
        "state": state or "Unknown",
        "lat": lat,
        "lon": lon,
        "date": article.published,
        "source": f"{article.publisher}, {article.published}",
        "text": (parsed.get("summary") or _summarise(article)).strip(),
        "places": [str(p) for p in (parsed.get("places") or [district])],
        "crime_types": types,
        "approved": False,
        "_review": {
            "extractor": "llm",
            "confidence": "medium",
            "link": article.link,
            "headline": article.title,
            "places_unresolved": [
                str(p) for p in (parsed.get("places") or []) if resolve(str(p)) is None
            ],
            "notes": (
                "LLM-selected district, gazetteer-supplied coordinates. Verify the "
                "district against the article before approving, especially if "
                "printing_press is tagged."
            ),
        },
    }


def extract(articles: list[Article], *, use_llm: bool = True) -> list[dict]:
    """Run the best available extractor over every article.

    Falls back to the deterministic extractor per-article whenever the LLM is
    unavailable or declines, so a partial LLM outage degrades quality rather
    than emptying the batch.
    """
    use_llm = use_llm and llm_available()
    if use_llm:
        print("  extractor: LLM (deterministic fallback per-article)")
    else:
        print("  extractor: deterministic (no LLM key or httpx unavailable)")

    candidates: list[dict] = []
    for article in articles:
        record = extract_llm(article) if use_llm else None
        if record is None:
            record = extract_deterministic(article)
        if record is not None:
            candidates.append(record)
    return candidates
