"""Tests for the news ingester.

Everything here is offline: no network, no LLM. The one function that touches
the network (`fetch_all`) is exercised through `parse_feed`, which is the pure
part, on a fixture that mirrors a real Google News RSS document.

The commit tests write to a temporary corpus via monkeypatching, so the real
`fir_corpus.json` is never touched by the suite.
"""

from __future__ import annotations

import json

import pytest
from aegis_supply_trail.ingest import corpus as corpus_mod
from aegis_supply_trail.ingest.extract import (
    CRIME_TYPES,
    classify_crime_types,
    extract_deterministic,
    make_ref,
    prefilter,
)
from aegis_supply_trail.ingest.gazetteer import find_places, gazetteer, resolve
from aegis_supply_trail.ingest.sources import Article, google_news_rss, parse_feed

# ── fixtures ────────────────────────────────────────────────────────────────

RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Fake currency notes worth Rs 4 lakh seized in Dhanbad, two held - Times of India</title>
    <link>https://example.com/a1</link>
    <pubDate>Wed, 13 Mar 2024 06:30:00 GMT</pubDate>
    <description>&lt;a href="x"&gt;GRP recovered counterfeit notes at the
      railway station&lt;/a&gt;</description>
    <source url="https://timesofindia.com">Times of India</source>
  </item>
  <item>
    <title>Printing press producing fake notes busted in Asansol - Anandabazar</title>
    <link>https://example.com/a2</link>
    <pubDate>Mon, 29 Jan 2024 04:00:00 GMT</pubDate>
    <description>CID seized an offset printing press and partially printed sheets</description>
    <source url="https://anandabazar.com">Anandabazar</source>
  </item>
</channel></rss>"""


def _article(title: str, summary: str = "", published: str = "2024-05-01") -> Article:
    return Article(title=title, summary=summary, link="https://example.com/x",
                   published=published, publisher="Test Wire")


# ── sources ─────────────────────────────────────────────────────────────────

def test_google_news_rss_url_is_india_scoped_and_encoded():
    url = google_news_rss("fake currency seized")
    assert "news.google.com/rss/search" in url
    assert "fake%20currency%20seized" in url
    assert "gl=IN" in url


def test_parse_feed_extracts_fields_and_splits_publisher():
    articles = parse_feed(RSS_FIXTURE)
    assert len(articles) == 2

    first = articles[0]
    assert first.title == "Fake currency notes worth Rs 4 lakh seized in Dhanbad, two held"
    assert first.publisher == "Times of India"
    assert first.published == "2024-03-13"
    assert "<a href" not in first.summary  # HTML stripped
    assert "railway station" in first.summary


def test_parse_feed_decodes_entities_and_drops_headline_echo():
    """Google News repeats the headline in <description> and appends the
    publisher; a naive join produces a stuttering, entity-littered summary."""
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><item>
  <title>Fake notes seized in Ajmer - NDTV</title>
  <link>https://example.com/z</link>
  <pubDate>Wed, 13 Mar 2024 06:30:00 GMT</pubDate>
  <description>Fake notes seized in Ajmer&amp;nbsp;&amp;nbsp; NDTV</description>
  <source url="https://ndtv.com">NDTV</source>
</item></channel></rss>"""

    article = parse_feed(xml)[0]
    assert "&nbsp;" not in article.summary
    assert "\xa0" not in article.summary
    assert not article.summary.strip().lower().startswith("fake notes seized in ajmer")
    assert not article.summary.strip().endswith("NDTV")


def test_summary_has_no_stutter_and_ends_cleanly():
    from aegis_supply_trail.ingest.extract import _summarise

    article = Article(
        title="Fake notes worth Rs 13 lakh seized in Ajmer",
        summary="Police said the accused was remanded for one day.",
        link="https://example.com/x",
        published="2024-05-01",
        publisher="Test Wire",
    )
    text = _summarise(article)

    assert text.count("Fake notes worth Rs 13 lakh seized in Ajmer") == 1
    assert text.endswith(".")
    assert " ." not in text


def test_summary_truncates_at_a_sentence_boundary():
    from aegis_supply_trail.ingest.extract import _summarise

    article = Article(
        title="Counterfeit currency racket busted in Ahmedabad",
        summary=("Officers recovered notes during a raid. " + ("Extra detail. " * 40)),
        link="https://example.com/y",
        published="2024-05-01",
        publisher="Test Wire",
    )
    text = _summarise(article)

    assert len(text) <= 400
    # A clean cut ends on punctuation, never mid-word like "police rema".
    assert text.rstrip().endswith((".", "!", "?", "…"))


def test_parse_feed_survives_garbage():
    assert parse_feed("not xml at all") == []
    assert parse_feed("") == []


# ── gazetteer ───────────────────────────────────────────────────────────────

def test_gazetteer_is_built_from_shipped_data():
    table = gazetteer()
    assert len(table) > 40, "corridor nodes should populate the gazetteer"
    for place in ("dhanbad", "asansol", "jamtara", "new delhi"):
        assert place in table, f"{place} missing from gazetteer"


def test_resolve_handles_station_decoration():
    assert resolve("Kanpur Central") is not None
    assert resolve("Kanpur") is not None, "cleaned form should also resolve"
    assert resolve("Kolkata (CCU)") is not None
    assert resolve("Atlantis") is None


def test_resolve_returns_coordinates_inside_india():
    lat, lon, _state = resolve("Dhanbad")
    assert 6.0 <= lat <= 37.5
    assert 68.0 <= lon <= 97.5


def test_find_places_prefers_longest_match():
    found = find_places("Seizure reported in New Delhi last week")
    assert "New Delhi" in found
    # "delhi" is a substring of the accepted "new delhi" and must not double-report
    assert "Delhi" not in found


def test_find_places_respects_word_boundaries():
    assert find_places("Gayathri temple festival") == []


# ── prefilter + classification ──────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Fake currency notes seized in Dhanbad",
    "Counterfeit notes racket busted in Asansol",
    "FICN worth lakhs recovered near Gaya",
])
def test_prefilter_accepts_real_stories(title):
    assert prefilter(_article(title)) is True


@pytest.mark.parametrize("title", [
    "How to spot fake currency notes: an explainer",
    "Opinion: the economics of counterfeit money",
    "Stock market closes higher on Tuesday",
])
def test_prefilter_rejects_noise_and_irrelevant(title):
    assert prefilter(_article(title)) is False


@pytest.mark.parametrize("title", [
    "Delhi court acquits man in fake currency case",
    "Court grants bail to accused in counterfeit notes case",
    "High court verdict in fake currency trial reserved",
])
def test_prefilter_rejects_court_outcome_stories(title):
    """On-topic but unusable: a verdict carries the COURT's district, not the
    crime's, so committing it would pin a false point on a corridor."""
    assert prefilter(_article(title)) is False


def test_prefilter_keeps_court_story_that_also_reports_a_seizure():
    article = _article(
        "Court remands accused as police seize fake notes worth Rs 5 lakh in Ajmer",
        "Officers recovered the counterfeit currency during a raid.",
    )
    assert prefilter(article) is True


def test_prefilter_rejects_acquittal_that_merely_mentions_seizure_paperwork():
    """The noun "seizure" in an acquittal write-up is paperwork, not a recovery.

    Real headline that slipped through an earlier version of this filter.
    """
    article = _article(
        "Seizure documents mentioned FIR number before case was even registered: "
        "Delhi court acquits man in fake currency case",
    )
    assert prefilter(article) is False


def test_prefilter_requires_an_enforcement_event():
    """Counterfeit-related commentary with no seizure/raid/arrest is not evidence."""
    assert prefilter(_article("Fake currency remains a problem for Indian banks")) is False


def test_classify_always_includes_counterfeit_currency():
    assert "counterfeit_currency" in classify_crime_types("fake notes seized")


def test_classify_detects_printing_press():
    types = classify_crime_types("Police busted a printing press making fake notes")
    assert "printing_press" in types


def test_classify_does_not_invent_printing_press():
    types = classify_crime_types("Fake notes seized from a hawker at the bus stand")
    assert "printing_press" not in types


def test_crime_types_are_returned_in_canonical_order():
    types = classify_crime_types(
        "printing press busted, notes were being transported and distributed"
    )
    assert types == sorted(types, key=CRIME_TYPES.index)


# ── deterministic extraction ────────────────────────────────────────────────

def test_extract_deterministic_builds_a_valid_record():
    article = _article(
        "Fake currency notes seized in Dhanbad, two held",
        "GRP recovered counterfeit notes at Dhanbad railway station while being "
        "transported towards Delhi.",
        published="2024-03-13",
    )
    record = extract_deterministic(article)

    assert record is not None
    assert record["district"] == "Dhanbad"
    assert record["date"] == "2024-03-13"
    assert record["approved"] is False, "nothing is pre-approved"
    assert record["ref"].startswith("NEWS-"), "ingested refs stay distinguishable"
    assert "counterfeit_currency" in record["crime_types"]
    assert corpus_mod.validate_record(record) == []


def test_extract_deterministic_drops_unplaceable_articles():
    article = _article("Fake currency notes seized in Nowhereville",
                       "No recognisable location mentioned.")
    assert extract_deterministic(article) is None


def test_extract_deterministic_drops_irrelevant_articles():
    assert extract_deterministic(_article("How to spot fake notes: explainer")) is None


def test_make_ref_is_stable_and_unique():
    a = make_ref("Dhanbad", "Jharkhand", "2024-03-13", "https://example.com/a1")
    b = make_ref("Dhanbad", "Jharkhand", "2024-03-13", "https://example.com/a1")
    c = make_ref("Dhanbad", "Jharkhand", "2024-03-13", "https://example.com/a2")
    assert a == b, "same article must yield the same ref"
    assert a != c, "different articles must not collide"
    assert a.startswith("NEWS-JHK-2024-")


# ── validation ──────────────────────────────────────────────────────────────

def _good_record() -> dict:
    return {
        "ref": "NEWS-JHK-2024-ABC123",
        "district": "Dhanbad",
        "state": "Jharkhand",
        "lat": 23.7957,
        "lon": 86.4304,
        "date": "2024-03-13",
        "source": "Times of India, 2024-03-13",
        "text": "GRP recovered counterfeit notes at Dhanbad railway station during a check.",
        "places": ["Dhanbad"],
        "crime_types": ["counterfeit_currency", "transport"],
        "approved": True,
    }


def test_validate_accepts_a_good_record():
    assert corpus_mod.validate_record(_good_record()) == []


@pytest.mark.parametrize("field", ["ref", "district", "date", "source", "text"])
def test_validate_rejects_missing_required_fields(field):
    record = _good_record()
    record[field] = ""
    assert any(field in problem for problem in corpus_mod.validate_record(record))


def test_validate_rejects_coordinates_outside_india():
    record = _good_record()
    record["lat"] = 51.5  # London
    problems = corpus_mod.validate_record(record)
    assert any("bounding box" in p for p in problems)


def test_validate_rejects_bad_date_format():
    record = _good_record()
    record["date"] = "13-03-2024"
    assert any("YYYY-MM-DD" in p for p in corpus_mod.validate_record(record))


def test_validate_rejects_unknown_crime_type():
    record = _good_record()
    record["crime_types"] = ["counterfeit_currency", "alien_invasion"]
    assert any("unknown crime_types" in p for p in corpus_mod.validate_record(record))


# ── commit ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_corpus(tmp_path, monkeypatch):
    """Redirect the corpus + staging at a temp dir so the real data is safe."""
    corpus_file = tmp_path / "fir_corpus.json"
    corpus_file.write_text(json.dumps([{
        "ref": "FIR-JHK-2024-0041",
        "district": "Dhanbad",
        "state": "Jharkhand",
        "lat": 23.7957, "lon": 86.4304,
        "date": "2024-03-12",
        "source": "Times of India, 2024-03-13",
        "text": "Existing seeded entry used to test de-duplication behaviour here.",
        "places": ["Dhanbad"],
        "crime_types": ["counterfeit_currency"],
    }]), encoding="utf-8")

    monkeypatch.setattr(corpus_mod, "FIR_FILE", corpus_file)
    monkeypatch.setattr(corpus_mod, "BACKUP_DIR", tmp_path / "backups")
    # The post-write reload guard must read the temp file too.
    monkeypatch.setattr(corpus_mod, "load_fir_corpus",
                        lambda: json.loads(corpus_file.read_text(encoding="utf-8")))
    return corpus_file


def test_commit_ignores_unapproved_records(temp_corpus):
    record = _good_record()
    record["approved"] = False
    report = corpus_mod.commit([record])

    assert report["committed"] == 0
    assert report["skipped_unapproved"] == 1
    assert len(json.loads(temp_corpus.read_text(encoding="utf-8"))) == 1


def test_commit_dry_run_writes_nothing(temp_corpus):
    report = corpus_mod.commit([_good_record()], dry_run=True)

    assert report["dry_run"] is True
    assert report["committed"] == 1, "dry run still reports what it would do"
    assert len(json.loads(temp_corpus.read_text(encoding="utf-8"))) == 1


def test_commit_appends_and_backs_up(temp_corpus):
    report = corpus_mod.commit([_good_record()])

    assert report["committed"] == 1
    assert report["backup"] is not None
    entries = json.loads(temp_corpus.read_text(encoding="utf-8"))
    assert len(entries) == 2
    # Pipeline metadata must not leak into the corpus.
    assert "approved" not in entries[1]
    assert "_review" not in entries[1]


def test_commit_rejects_invalid_records(temp_corpus):
    record = _good_record()
    record["lat"] = 999.0
    report = corpus_mod.commit([record])

    assert report["committed"] == 0
    assert report["invalid"], "the problem should be reported, not silently dropped"


def test_commit_skips_near_duplicates(temp_corpus):
    duplicate = _good_record()
    duplicate["ref"] = "NEWS-DIFFERENT-REF"
    duplicate["date"] = "2024-03-12"
    duplicate["text"] = "Existing seeded entry used to test de-duplication behaviour here."

    report = corpus_mod.commit([duplicate])
    assert report["committed"] == 0
    assert report["duplicates"] == 1


def test_restore_is_byte_exact(tmp_path, monkeypatch):
    """A reset must leave the corpus byte-identical, not merely equivalent.

    Re-serialising would reformat a hand-maintained, git-tracked file and leave
    a spurious diff (and a merge-conflict surface) after an operation whose whole
    point is putting things back exactly as they were.
    """
    from aegis_supply_trail.ingest import service as service_mod

    # Hand-written style: compact inline arrays, CRLF — as the real file is.
    original = (
        b'[\r\n  {\r\n    "ref": "FIR-X-1",\r\n    "district": "Dhanbad",\r\n'
        b'    "lat": 23.7957,\r\n    "lon": 86.4304,\r\n    "date": "2024-03-12",\r\n'
        b'    "source": "Test, 2024-03-13",\r\n    "text": "A sufficiently long '
        b'sample text for the validator to accept.",\r\n'
        b'    "places": ["Dhanbad", "Asansol"],\r\n'
        b'    "crime_types": ["counterfeit_currency"]\r\n  }\r\n]\r\n'
    )

    corpus_file = tmp_path / "fir_corpus.json"
    corpus_file.write_bytes(original)
    backup = tmp_path / "backup.json"
    backup.write_bytes(original)

    monkeypatch.setattr(service_mod, "FIR_FILE", corpus_file)
    monkeypatch.setattr(service_mod, "load_fir_corpus", lambda: None)

    corpus_file.write_text('[{"ref": "mutated"}]', encoding="utf-8")
    service_mod._restore(backup)

    assert corpus_file.read_bytes() == original, "restore must be byte-for-byte"


def test_reset_restores_the_review_queue_too(tmp_path, monkeypatch):
    """Reset must return the whole surface, not just the corpus.

    Restoring the corpus alone would leave the queue consumed, so a second
    rehearsal run would have nothing left to approve.
    """
    from aegis_supply_trail.ingest import service as service_mod

    corpus_file = tmp_path / "fir_corpus.json"
    corpus_file.write_bytes(b"[]")
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b"[]")
    baseline_queue = tmp_path / "baseline_candidates.json"
    live_queue = tmp_path / "candidates.json"

    json_dump = lambda p, v: p.write_text(json.dumps(v), encoding="utf-8")
    json_dump(baseline_queue, [{"ref": "A", "approved": True}, {"ref": "B", "approved": False}])
    json_dump(live_queue, [])  # queue fully consumed by an ingest

    monkeypatch.setattr(service_mod, "FIR_FILE", corpus_file)
    monkeypatch.setattr(service_mod, "BASELINE_FILE", baseline)
    monkeypatch.setattr(service_mod, "BASELINE_CANDIDATES", baseline_queue)
    monkeypatch.setattr(service_mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(service_mod, "load_fir_corpus", lambda: None)
    monkeypatch.setattr(service_mod, "save_candidates",
                        lambda records, path=live_queue: json_dump(live_queue, records))
    monkeypatch.setattr(service_mod, "load_candidates",
                        lambda path=baseline_queue: json.loads(path.read_text(encoding="utf-8")))

    result = service_mod.reset_baseline()

    assert result["restored"] is True
    assert result["candidates_restored"] == 2
    restored = json.loads(live_queue.read_text(encoding="utf-8"))
    assert [r["ref"] for r in restored] == ["A", "B"]
    assert all(r["approved"] is False for r in restored), "queue must reopen unapproved"


def test_committed_corpus_still_matches_firentry_shape(temp_corpus):
    corpus_mod.commit([_good_record()])
    entries = json.loads(temp_corpus.read_text(encoding="utf-8"))
    for entry in entries:
        for field in ("ref", "district", "lat", "lon", "date", "source", "text",
                      "places", "crime_types"):
            assert field in entry, f"{field} missing — engine.load_fir_corpus would break"
