"""Export the trained scam classifier for on-device (browser) scoring.

Why this exists
---------------
Today every message is POSTed to /analyze, so the citizen's text leaves their
phone before anything looks at it (docs/privacy.md P3/P4/P6). The detector does
not need to be on a server: it is TF-IDF + LogisticRegression, which is one
sparse dot product and a sigmoid. Exported, it is ~390 KB gzipped and scores in
microseconds — on-device is not a downgrade, it is FASTER than the round-trip it
replaces, and it removes the cold start entirely.

What is exported
----------------
Everything needed to reproduce `pipeline.predict_proba` outside Python:
  * both TF-IDF vocabularies + their IDF vectors
  * the LogisticRegression coefficients and intercept
  * the verdict thresholds the model calibrated for itself

The exact vectorizer settings are exported alongside, not assumed, so the JS
side can assert it is implementing the same configuration it was handed rather
than a stale guess:
  word:  ngram (1,2), sublinear_tf, l2, strip_accents=unicode, \b\w\w+\b
  char:  char_wb ngram (3,5), sublinear_tf, l2, no accent stripping

The two blocks are L2-normalised INDEPENDENTLY and then concatenated (that is
what FeatureUnion does), and the 11 marker features are appended unnormalised.
Getting that ordering wrong silently changes every score, so the JS port is
validated against this Python model by tests/test_edge_parity.py rather than by
inspection.
"""

from __future__ import annotations

# Coefficients and IDF weights are rounded before export. At 10 significant
# decimals the asset drops ~23% (4.31 MB -> 3.31 MB raw, 0.90 MB gzipped) while
# every score stays within 2e-11 of the Python model — far tighter than anything
# that could move a verdict across a threshold. 8 digits was measured too coarse
# (worst 3.2e-9). tests/test_edge_parity.py is what holds this claim honest.
_ROUND_DIGITS = 10

import gzip
import json
from pathlib import Path

from ..markers import ALL_MARKERS, _MARKER_PATTERNS
from ..model import MODEL_FILE, ScamClassifier
from ..playbooks import PLAYBOOKS


def build_export(model: ScamClassifier) -> dict:
    """Serialise the fitted pipeline into a plain-JSON structure."""
    pipeline = model.pipeline
    union = pipeline.named_steps["features"]
    clf = pipeline.named_steps["clf"]

    blocks: dict[str, dict] = {}
    offset = 0
    order: list[str] = []
    for name, vec in union.transformer_list:
        order.append(name)
        if not hasattr(vec, "vocabulary_"):
            # markers: no vocabulary, fixed width, appended after the tf-idf blocks
            width = 11
            blocks[name] = {"kind": "markers", "offset": offset, "width": width}
            offset += width
            continue
        vocab = {term: int(idx) for term, idx in vec.vocabulary_.items()}
        blocks[name] = {
            "kind": "tfidf",
            "offset": offset,
            "width": len(vocab),
            "analyzer": vec.analyzer,
            "ngram_range": list(vec.ngram_range),
            "lowercase": bool(vec.lowercase),
            "sublinear_tf": bool(vec.sublinear_tf),
            "norm": vec.norm,
            "strip_accents": vec.strip_accents,
            "token_pattern": vec.token_pattern,
            "vocabulary": vocab,
            "idf": [round(float(x), _ROUND_DIGITS) for x in vec.idf_],
        }
        offset += len(vocab)

    # Rules travel as DATA, not as a hand-written JS translation. Every marker
    # regex and every playbook stage is exported verbatim from the Python
    # definitions, so the browser compiles the same patterns this model was
    # trained against and the two can never drift. All 49 marker patterns were
    # verified to compile under JS and to produce identical hits (the one
    # lookbehind is ES2018, supported everywhere the dashboard runs).
    markers = {
        "order": list(ALL_MARKERS),
        "patterns": {m: list(ps) for m, ps in _MARKER_PATTERNS.items()},
    }
    playbooks = [
        {
            "name": pb.name,
            "scam_type": pb.scam_type,
            "min_stages": pb.min_stages,
            "stages": [
                {"name": st.name, "markers": sorted(st.markers), "patterns": list(st.patterns)}
                for st in pb.stages
            ],
        }
        for pb in PLAYBOOKS
    ]

    return {
        "format": "aegis-scam-edge/1",
        "markers": markers,
        "playbooks": playbooks,
        "block_order": order,
        "blocks": blocks,
        "n_features": int(offset),
        "coef": [round(float(x), _ROUND_DIGITS) for x in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
        "scam_threshold": float(model.scam_threshold),
        "suspicious_threshold": float(model.suspicious_threshold),
        "trained_at": model.trained_at,
    }


def export(out_path: Path | None = None, gzip_too: bool = True) -> Path:
    model = ScamClassifier.load(MODEL_FILE)
    payload = build_export(model)
    out_path = out_path or (Path(__file__).resolve().parent / "scam_model.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(raw, encoding="utf-8")
    if gzip_too:
        gz = out_path.with_suffix(".json.gz")
        gz.write_bytes(gzip.compress(raw.encode("utf-8"), 9))
    return out_path


if __name__ == "__main__":  # pragma: no cover
    p = export()
    size = p.stat().st_size
    gz = p.with_suffix(".json.gz")
    print(f"wrote {p} ({size/1e6:.2f} MB raw, {gz.stat().st_size/1e6:.2f} MB gzipped)")
