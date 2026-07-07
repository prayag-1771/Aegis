# Fusion — the Gen AI intelligence layer

**Co-leads:** Pushkar · Prayag
The piece that makes Aegis more than three separate classifiers: it correlates
scam calls, counterfeit seizures, and fraud rings into ONE intelligence package.

## Architecture (why it's defensible)

```
scam JSON ──┐
note JSON ──┤→ correlator.py (deterministic, auditable) → facts + links
graph JSON ─┘                                                │
                                                             ▼
                                    narrator.py (Claude claude-opus-4-8,
                                    structured output; template fallback)
                                                             │
                                                             ▼
                                    fuse.py → fusion_output.json (contract-valid)
```

- **The correlation engine is NOT the LLM.** Links come from concrete evidence:
  shared district, geo proximity (≤30 km), temporal proximity (≤96 h). The LLM
  only *narrates* established facts — it's instructed to never invent links.
  That makes the intelligence package reproducible (`audit_trail.inputs_hash`)
  and defensible for the legal-admissibility judging criterion.
- **Threat levels:** all 3 domains linked → `critical`; 2 → `high`;
  unlinked signals → `medium`; nothing → `low`.
- **Never dies on stage:** without `ANTHROPIC_API_KEY` the deterministic
  template narrator produces the same JSON shape.

## Setup

```bash
cd command-centre/fusion
uv venv && uv pip install -e ".[dev]"

# optional — enables the live Gen AI narrator:
echo ANTHROPIC_API_KEY=sk-ant-... > .env      # gitignored, never commit

.venv/Scripts/python -m aegis_fusion.fuse     # demo (uses contract samples +
                                              #   live fraud-graph output if present)
.venv/Scripts/python -m pytest                # tests
```

## Output
`output/fusion_output.json`, validating against
[`../../contracts/fusion_output.schema.json`](../../contracts/fusion_output.schema.json).

## Wiring into the dashboard (for the backend)
Call `aegis_fusion.fuse.fuse(scams, counterfeits, fraud_graph)` with the raw
module payloads; render `summary`, `threat_level`, `recommended_actions`, and
plot `map_hotspots` on the crime map (overlapping clusters = coordinated hub —
innovation #3).
