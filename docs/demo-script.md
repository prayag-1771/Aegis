# 🎬 Aegis — Demo Run-of-Show

> Target: **6 minutes** live demo + 2 minutes architecture. Rehearse with a timer.
> Every step has a fallback — nothing on this list can hard-fail the demo.

## Pre-flight (30 min before, once)

```bash
# five terminals, in repo root:
cd fraud-shield-nlp      && uvicorn aegis_fraud_shield.api:app --app-dir src --port 8001
cd counterfeit-vision    && uvicorn aegis_counterfeit.api:app --app-dir src --port 8002
cd fraud-graph-ml        && .venv/Scripts/fraud-graph serve                # :8003
cd command-centre/backend  && .venv/Scripts/python -m uvicorn aegis_command.api:app --port 8000
cd command-centre/frontend && npm run dev                                  # :3000
```

- [ ] Dashboard http://localhost:3000 — all header pills GREEN
- [ ] `command-centre/fusion/.env` has a working GROQ_API_KEY (fusion falls back to
      template if not — demo still works, say nothing)
- [ ] Real ₹500 note + printed fake (or phone photo) at hand
- [ ] Scam script card printed (below)
- [ ] Browser zoom 125%, dark room lighting checked for webcam

## Run of show

### Beat 1 — the hook (30s)
> "1.14 million cybercrime complaints. ₹1,776 crore stolen by 'digital arrest' calls in
> nine months. Police see each crime in isolation — a scam call here, a fake note there,
> a mule account somewhere else. **Aegis sees them together.** This is our command centre."

Point at the dashboard: three signal cards, the crime map, module health pills.

### Beat 2 — WOW #1: catch a scam call live (90s)
Open the Fraud Shield chat UI (:8001) *or* use the dashboard card. Read aloud:

> *"This is Inspector Verma from CBI Delhi. A money-laundering FIR is registered against
> your Aadhaar. Stay on this video call, do not tell anyone, and transfer ₹49,999 as a
> security deposit immediately, or you will be arrested tonight."*

Submit → **verdict: SCAM, risk 99.9%** with lit-up markers (authority impersonation,
fake FIR, video-call isolation, urgency). Say: *"Notice it doesn't just say scam — it
names the evidence. That's court-admissible reasoning, and it's a stated judging metric."*

**Fallback:** paste from the printed card instead of typing live.

### Beat 3 — WOW #2: catch a fake note live (60s)
Counterfeit Vision UI (:8002) → webcam → hold up the fake ₹500.
→ **FAKE, with the missing security feature named** (thread / watermark / microprint).
Then the real note → genuine. Say: *"Same discipline: it names WHICH feature failed.
And it never certifies a note genuine while any security check fails."*

**Fallback:** upload the prepared photo instead of the webcam.

### Beat 4 — the fraud graph (45s)
Dashboard rings card: *"Meanwhile our graph engine watched the money. 12 fraud rings —
mule chains, collection hubs, round-tripping cycles — each district-tagged. On real
Bitcoin fraud data this scores 0.99 AUC at 90% precision."*

### Beat 5 — WOW #3: THE FUSION MOMENT (90s)
Press **▶ RUN FUSION**. Read the Gen-AI summary aloud as it appears:

> *"A scam call detected in Jamtara is linked to a round-tripping fraud ring… a
> counterfeit ₹500 note was also seized in Jamtara…"* — **threat: CRITICAL**

Say: *"Three independent AI systems just agreed about one district. No product on the
market does this. And look —"* (point at audit hash) *"— the links come from a
deterministic evidence engine: same district, 30 kilometres, 96 hours. The LLM only
narrates. Re-run it with the same inputs, you get the same hash. That's what makes this
intelligence package admissible, not just impressive."*

Point at the map: *"Red pulsing circle — two independent detection systems converging on
one location. That's a coordinated crime hub, found automatically."*

### Beat 6 — innovation #2: the self-improving loop (45s)
Show `self_improve_report.json` / one slide: *"Scams evolve, so Aegis red-teams itself.
An LLM writes next year's scam scripts — including investment and job-task families our
classifier had NEVER seen — and retrains it. Recall on held-out unseen variants:
**69% → 100%**, with zero human labelling. The eval half never enters training."*

### Beat 7 — close (30s)
> "Three detectors, one correlated picture, every verdict carrying its evidence.
> Built in days, by four people, on free-tier infrastructure — because the architecture,
> not the budget, is the innovation. We're Aegis."

## Q&A ammunition

| Likely question | Answer |
|---|---|
| "LLM hallucinations → framing innocents?" | LLM cannot create links; deterministic engine + reproducible `inputs_hash`; legit verdicts excluded from correlation entirely |
| "Why not a GNN?" | At this scale boosted trees match GNN accuracy (0.9945 real-data AUC), train in seconds, and give feature importances = auditability (a judged criterion) |
| "Real data?" | Elliptic++: 823k real Bitcoin wallets; benchmark 0.9945 AUC / 0.90 precision @ 0.85 recall; UCI SMS + LLM red-team corpus for NLP |
| "False positives?" | Every module thresholds precision-first from its PR curve; scam band ≥0.97 precision; note never certified genuine on failed check |
| "Scales?" | Independent services + versioned JSON contracts; swap any model without touching others; DBSCAN → sklearn haversine at city scale |
| "What's mocked?" | Transaction stream is synthetic/Elliptic++ (no live bank feed — that's a partnership, not a tech gap); districts on graph data are demo geography |
