"""Single .env loader for the module.

Three near-identical copies of this used to live in `prescreen`, `serials` and
`vision_agent`'s import of prescreen's private helper. They all failed the same
way — silently succeeding when no file exists — which is how a missing
ANTHROPIC_API_KEY turned the whole semantic-review layer into a no-op that
nothing reported. One loader now, and `keys_available()` so callers can tell
the difference between "checked and found nothing" and "never looked".

`setdefault` throughout: a real environment variable always beats the file.
"""

from __future__ import annotations

import os
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]  # counterfeit-vision/

# Module-local first, then the shared fusion env the rest of Aegis uses.
ENV_CANDIDATES = (
    MODULE_ROOT / ".env",
    MODULE_ROOT.parent / "command-centre" / "fusion" / ".env",
)

_loaded = False


def load_env(force: bool = False) -> None:
    """Populate os.environ from the candidate .env files. Idempotent."""
    global _loaded
    if _loaded and not force:
        return
    _loaded = True
    for env_file in ENV_CANDIDATES:
        try:
            if not env_file.exists():
                continue
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        except OSError:
            continue


def has_key(*names: str) -> bool:
    """True when any of the named provider keys is set (after loading)."""
    load_env()
    return any(os.environ.get(n) for n in names)
