"""The on-device scorer must agree with the Python model, exactly.

The edge port exists so a citizen's message can be scored without leaving their
phone (docs/privacy.md P3/P4/P6). That is only worth anything if the browser
reaches the SAME verdict the audited server model would have: a port that is
"close enough" silently changes who gets warned, and nobody would notice until a
real scam slipped through.

So the port is not trusted by inspection. These tests re-derive scores from the
scikit-learn pipeline and compare them against the JavaScript implementation
running in Node, message by message, including the cases most likely to expose a
tokenisation difference:

  * Devanagari and Tamil — their vowel signs are combining marks, which a naive
    accent-stripper deletes; sklearn's ASCII short-circuit is what saves them
  * accented Latin, where strip_accents DOES apply
  * irregular whitespace, which char_wb collapses before windowing
  * short and empty input, which hits the "word shorter than n" branch

Skips (rather than fails) when Node is unavailable, so the Python suite still
runs on a machine without it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from aegis_fraud_shield.edge.export_model import build_export
from aegis_fraud_shield.markers import detect_markers
from aegis_fraud_shield.model import MODEL_FILE, ScamClassifier

SCORER_JS = Path(__file__).resolve().parents[1] / "src" / "aegis_fraud_shield" / "ui" / "edge-scorer.js"

# Cases chosen to break a careless port, not to flatter it.
CASES = [
    "CBI officer speaking. FIR registered against your Aadhaar. Stay on video "
    "call and transfer to the safe account immediately.",
    "Dear customer, your KYC has expired. Update now at http://bit.ly/kyc-verify "
    "or your account will be blocked.",
    "Hi mom, reached office safely. Will call in the evening.",
    "Your OTP for HDFC txn is 445566. Do not share with anyone.",
    "Please share your OTP and CVV immediately to avoid suspension",
    # Devanagari: combining vowel signs must survive preprocessing
    "प्रिय ग्राहक, आपका बैंक KYC समाप्त हो गया है। 30 मिनट में अपडेट करें।",
    # Tamil: same risk, different script
    "உங்கள் வங்கி கணக்கு முடக்கப்படும். உடனே சரிபார்க்கவும்.",
    # Latin accents: here strip_accents genuinely applies
    "Café naïve résumé façade",
    "   spaced    out     text  with   irregular   whitespace   ",
    "a b c 1 2 3",
    "",
    "URGENT!!! Final warning. Pay 50000 USDT now or arrest warrant will be issued.",
]

_RUNNER = textwrap.dedent(
    """
    const fs = require('fs');
    const A = require(process.argv[2]);
    A.load(fs.readFileSync(process.argv[3], 'utf8'));
    const cases = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
    const out = cases.map((t) => {
      const r = A.score(t);
      return { risk: r.risk_score, verdict: r.verdict, markers: r.markers.slice().sort() };
    });
    fs.writeFileSync(process.argv[5], JSON.stringify(out));
    """
)


@pytest.fixture(scope="module")
def node() -> str:
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed — edge parity cannot be checked here")
    return exe


@pytest.fixture(scope="module")
def model() -> ScamClassifier:
    if not MODEL_FILE.exists():
        pytest.skip("model not trained")
    return ScamClassifier.load(MODEL_FILE)


@pytest.fixture(scope="module")
def js_results(node, model, tmp_path_factory) -> list[dict]:
    """Score every case through the JS implementation, via a real Node process."""
    tmp = tmp_path_factory.mktemp("edge")
    asset = tmp / "scam_model.json"
    asset.write_text(json.dumps(build_export(model), ensure_ascii=False), encoding="utf-8")
    cases = tmp / "cases.json"
    cases.write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")
    runner = tmp / "run.cjs"
    runner.write_text(_RUNNER, encoding="utf-8")
    out = tmp / "out.json"
    subprocess.run(
        [node, str(runner), str(SCORER_JS), str(asset), str(cases), str(out)],
        check=True, capture_output=True, timeout=180,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_risk_scores_match_python(model, js_results):
    """Same message, same probability — to floating-point epsilon."""
    worst = 0.0
    for text, js in zip(CASES, js_results):
        py = float(model.risk_score(text))
        worst = max(worst, abs(py - js["risk"]))
        assert abs(py - js["risk"]) < 1e-9, (
            f"score diverged on {text[:60]!r}: python {py!r} vs js {js['risk']!r}"
        )
    assert worst < 1e-9


def test_verdicts_match_python(model, js_results):
    """The verdict bands are what the citizen actually sees."""
    for text, js in zip(CASES, js_results):
        py = model.decide_verdict(model.risk_score(text), len(detect_markers(text)))
        assert py == js["verdict"], f"verdict diverged on {text[:60]!r}"


def test_markers_match_python(js_results):
    """Marker regexes are exported as data; the browser must resolve them the
    same way, or the 'why flagged' evidence would disagree with the score."""
    for text, js in zip(CASES, js_results):
        py = sorted({h.marker for h in detect_markers(text)})
        assert py == js["markers"], f"markers diverged on {text[:60]!r}"


def test_devanagari_survives_preprocessing(model, js_results):
    """Guards the specific bug this port could most easily introduce: stripping
    combining marks would gut Indic text and quietly zero its features."""
    idx = next(i for i, t in enumerate(CASES) if "प्रिय" in t)
    assert js_results[idx]["risk"] > 0.0
    assert abs(model.risk_score(CASES[idx]) - js_results[idx]["risk"]) < 1e-9
