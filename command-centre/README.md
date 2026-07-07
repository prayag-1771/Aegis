# Command Centre — Integration, Geospatial & Gen AI Fusion

**Lead:** Pushkar · **Co-lead (fusion layer):** Prayag
**AI type:** Gen AI / agentic — the innovation core of Aegis

## Goal
The **command centre**: one unified dashboard that pulls the three module outputs into a single
view, adds a geospatial crime map, and runs the **Gen AI fusion layer** that turns three raw
outputs into one human-readable intelligence summary — and suggests autonomous next steps.

## Sub-folders
```
frontend/    # React/Next.js dashboard — scam card, note-scan card, fraud-ring graph, map
backend/     # FastAPI/Node — aggregates the module results, serves the UI, calls the fusion layer
fusion/      # Gen AI: LLM prompt + logic that correlates the 3 signals -> fusion_output JSON
geospatial/  # map layer + hotspot clustering (DBSCAN) — cross-domain crime map
```

## Inputs / output
- **Consumes:** `scam_detection`, `counterfeit`, `fraud_graph` JSON (the `contracts/` samples
  are your dummy data — build the entire dashboard against them, don't wait for real models).
- **Produces:** `fusion_output` JSON —
  [`../contracts/fusion_output.schema.json`](../contracts/fusion_output.schema.json).

## The three WOW moments to engineer for
1. Live scam call read out → scam card flags it instantly.
2. Note held to camera → note card flags missing security feature.
3. **Fusion moment:** dashboard auto-writes *"This scam call is linked to a fraud ring active
   in this district, and a counterfeit note was seized nearby."*

## The 3 defensible innovations (build hooks for these)
1. **The fusion itself** — no product combines scam + counterfeit + fraud graph.
2. **Self-improving classifier** — LLM generates new scam variants → retrains Fraud Shield
   (before/after accuracy demo). Coordinate with Sudarsan.
3. **Cross-domain crime map** — plot counterfeit seizures + scam origins on one map; overlapping
   clusters = coordinated hub. Cheap, reuses the map infra.

## Plan (per PROJECT_PLAN.md)
- **Phase 2–3:** build dashboard shell + map base in parallel; test LLM fusion with dummy data.
- **Phase 4 (crunch):** wire real module outputs, build fusion layer, add geospatial hotspots.
- Owns the **architecture diagram** and **demo video**.

## Tech
React / Next.js · FastAPI / Node · PostgreSQL · Mapbox · Claude / GPT API (fusion)

> **Use the latest Claude model for the fusion layer** — `claude-opus-4-8` for best quality, or
> `claude-haiku-4-5` if you need speed/cost. See [`fusion/`](fusion/) for the prompt.

## Definition of done
- [ ] Dashboard renders all 3 cards from sample JSON
- [ ] Cross-domain map with hotspot clustering
- [ ] Fusion layer emits valid `fusion_output` JSON with a correlated summary
- [ ] Live end-to-end demo of all 3 wow moments
- [ ] Architecture diagram + demo video done
