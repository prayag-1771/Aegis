"""Article fetching — stdlib only, no API key.

Uses Google News RSS, which needs no key, no signup, and is India-scopeable
(`hl=en-IN&gl=IN&ceid=IN:en`). Parsing is `xml.etree` rather than `feedparser`
so the module keeps its `dependencies = []` promise.

Deliberately NOT scraping article bodies. We take the headline, the snippet,
the publisher and the date — which is the same shape as the summaries already
in the corpus (each existing entry is one to three sentences). Fetching full
article text would mean per-publisher scrapers that rot, and would add a legal
question this project does not need to answer.

Everything here is offline-testable: `fetch_all` is the only function that
touches the network, and the pipeline reads its output from a staging file.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

# Queries aimed at the two things the corpus actually needs: seizures (which
# corroborate corridors) and printing presses (which become route ORIGINS).
DEFAULT_QUERIES: tuple[str, ...] = (
    "fake currency notes seized India",
    "counterfeit currency printing press busted India",
    "FICN fake Indian currency notes arrested",
    "fake notes seized railway station India",
    "counterfeit notes racket arrested police India",
)

_USER_AGENT = "AegisSupplyTrail/0.1 (hackathon research; contact: team@aegis.local)"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Article:
    """One news item, normalised. `published` is ISO-8601 date (YYYY-MM-DD)."""

    title: str
    summary: str
    link: str
    published: str
    publisher: str

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def text(self) -> str:
        """Headline + snippet — what the extractors read."""
        return f"{self.title}. {self.summary}".strip()


def google_news_rss(query: str, *, hl: str = "en-IN", gl: str = "IN",
                    ceid: str = "IN:en") -> str:
    """Build a keyless Google News RSS search URL for `query`."""
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + f"&hl={hl}&gl={gl}&ceid={urllib.parse.quote(ceid)}"
    )


def _strip_html(raw: str) -> str:
    """Tags out, entities decoded, whitespace collapsed.

    `html.unescape` matters: Google News descriptions are entity-encoded, so
    without it the stored summary carries literal "&nbsp;" and "&amp;" into the
    corpus and out onto the review page.
    """
    import html as _html

    text = _TAG_RE.sub(" ", raw or "")
    text = _html.unescape(text)
    text = text.replace("\xa0", " ")  # nbsp -> real space, post-unescape
    return _WS_RE.sub(" ", text).strip()


def _dedupe_summary(title: str, summary: str, publisher: str) -> str:
    """Drop the headline echo and trailing publisher from an RSS snippet.

    Google News sets <description> to the headline again, then the publisher —
    so the naive "title. summary" join reads as a stutter:
    "X seized in Ajmer. X seized in Ajmer   NDTV". Strip both.
    """
    if not summary:
        return ""

    cleaned = summary.strip()
    if publisher and cleaned.endswith(publisher):
        cleaned = cleaned[: -len(publisher)].strip()

    # Remove a leading repeat of the headline (case/punctuation tolerant).
    def _key(value: str) -> str:
        return _WS_RE.sub(" ", value.lower().replace("’", "'")).strip()

    if _key(cleaned).startswith(_key(title)):
        cleaned = cleaned[len(title):].lstrip(" .:-–—|")

    return cleaned.strip(" .:-–—|").strip()


def _iso_date(raw: str | None) -> str:
    """RFC-2822 pubDate -> YYYY-MM-DD. Falls back to today on anything odd."""
    if raw:
        try:
            return parsedate_to_datetime(raw).date().isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _split_publisher(title: str, fallback: str) -> tuple[str, str]:
    """Google News appends ' - Publisher' to the headline; separate them."""
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if head and len(tail) < 60:
            return head.strip(), tail.strip()
    return title.strip(), fallback


def parse_feed(xml_text: str) -> list[Article]:
    """Parse an RSS document into Articles. Pure function — no network."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    articles: list[Article] = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        if not raw_title:
            continue
        source_el = item.find("source")
        fallback_pub = (source_el.text or "").strip() if source_el is not None else "unknown"
        title, publisher = _split_publisher(raw_title, fallback_pub)
        articles.append(
            Article(
                title=title,
                summary=_dedupe_summary(
                    title, _strip_html(item.findtext("description") or ""), publisher
                ),
                link=(item.findtext("link") or "").strip(),
                published=_iso_date(item.findtext("pubDate")),
                publisher=publisher or "unknown",
            )
        )
    return articles


def fetch_feed(url: str, *, timeout: float = 20.0) -> list[Article]:
    """Fetch and parse one feed. Network errors return [] rather than raising —
    one dead feed must not abort a multi-query run."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"  [warn] feed failed ({type(exc).__name__}): {url[:80]}")
        return []
    return parse_feed(payload)


def fetch_all(
    queries: tuple[str, ...] | list[str] | None = None,
    *,
    limit_per_query: int = 25,
    timeout: float = 20.0,
) -> list[Article]:
    """Run every query and return de-duplicated articles (by title+publisher)."""
    queries = tuple(queries) if queries else DEFAULT_QUERIES
    seen: set[tuple[str, str]] = set()
    collected: list[Article] = []
    for query in queries:
        found = fetch_feed(google_news_rss(query), timeout=timeout)[:limit_per_query]
        print(f"  {len(found):>3} items  <- {query}")
        for article in found:
            key = (article.title.lower(), article.publisher.lower())
            if key not in seen:
                seen.add(key)
                collected.append(article)
    return collected


# ── staging I/O ─────────────────────────────────────────────────────────────

def save_articles(articles: list[Article], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([a.to_dict() for a in articles], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_articles(path: Path) -> list[Article]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Article(**item) for item in raw]
