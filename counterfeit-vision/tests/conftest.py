"""Test-wide hermeticity.

Every test in this suite must behave identically on a machine with provider
keys and one without. Without this, the suite silently changes meaning the
moment somebody drops a real key into `counterfeit-vision/.env`: the semantic
layer starts making live API calls mid-test, verdicts depend on a remote
model's mood, and assertions about `vision_review.available` flip. That is
exactly how `test_serial_block_in_contract_payload` began failing the instant a
GROQ_API_KEY existed — the test was fine, its isolation was not.

So: strip every provider key and stub the .env loader for ALL tests. A test
that wants the semantic layer active injects a fake review explicitly (see
`test_wrong_portrait_convicts`), never by reaching for the network.
"""

from __future__ import annotations

import pytest

PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "MONGODB_URI")


@pytest.fixture(autouse=True)
def _hermetic_providers(monkeypatch):
    for key in PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)

    # Stub the loader itself, or it would read the real .env straight back in.
    import aegis_counterfeit.env as env_mod
    import aegis_counterfeit.prescreen as prescreen_mod
    import aegis_counterfeit.serials as serials_mod
    import aegis_counterfeit.vision_agent as vision_mod

    noop = lambda force=False: None
    monkeypatch.setattr(env_mod, "load_env", noop)
    monkeypatch.setattr(vision_mod, "load_env", noop)
    monkeypatch.setattr(prescreen_mod, "_load_env_keys", lambda: None)
    monkeypatch.setattr(serials_mod, "_load_env", lambda: None)
