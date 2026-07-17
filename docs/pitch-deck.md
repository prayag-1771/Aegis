# 🛡️ Aegis — Pitch Deck Outline

> Slide-by-slide script for PS#6 (Digital Public Safety Intelligence). Every number here is
> read from a model's own persisted train/eval report — see `GET /metrics` / the Model Card in
> the dashboard (Modules → "Model Card — measured metrics"). Nothing is tuned for display.

---

### Slide 1 — Title
**Aegis · Digital Public Safety Intelligence Platform**
*Three AI systems. One correlated picture. Every verdict carries its evidence.*
PS#6 · Smart Cities / Public Safety / Digital Trust / Geospatial Law Enforcement.

### Slide 2 — The problem (their words, our target)
- 1.14M cybercrime complaints in 2023 (+60% YoY). Digital-arrest scams: ₹1,776 cr in 9 months of 2024.
- Record FICN ₹500 seizures (RBI 2025) that beat manual bank checks.
- **The gap:** police see each crime in isolation, *after* the complaint. No intelligence layer
  *before* mass victimisation. **Aegis is that layer.**

### Slide 3 — What we built (one line each)
Detect (3 domains) → Correlate (fusion) → **Disrupt/Respond** (action queue) — served to all
**three stakeholders**: law enforcement, financial institutions, citizens.

### Slide 4 — Architecture
Show `docs/architecture.md` diagrams: 3-website topology + the Detect→Disrupt→Respond flow.
Emphasise: modules are independent services speaking **versioned JSON contracts**; fusion's
LLM *narrates* deterministic evidence, it cannot invent links (`audit_trail.inputs_hash`).

### Slide 5 — DETECT: measured accuracy (the scored criteria)
Pull straight from the Model Card:

| Module | Headline | False-alarm (1−precision) | Posture |
|---|---|---|---|
| Fraud Shield (scam/digital-arrest) | ROC-AUC **0.998**, P/R@scam **0.942 / 0.952**, digital-arrest recall **1.00** | **5.8%** of alerts | Predictive (pre-transfer) |
| Counterfeit Vision | val-acc **0.969**, AUC **0.994**, fake P/R **0.976 / 0.964** | **2.4%** | Point-of-contact |
| Fraud Graph (synthetic) | AUC **0.9997**, **12/12** rings recovered, acct P/R **1.00 / 0.940** | 10% @ threshold | Fast classification |
| Fraud Graph (**Elliptic++**, real 265k-wallet graph) | AUC **0.994**, AP **0.950**, P/R **0.900 / 0.854** | ~10% | Fast classification |

> Note the **Elliptic++** row: we validated the graph pipeline on the only large, real, labeled
> fraud graph publicly available. It transfers because we score graph **topology** (fan-in/out,
> layering, community), not currency-specific features — the same reason it applies to UPI rails.

### Slide 6 — Low false positives + auditability (scored explicitly)
- **False-alarm rate** shown per module (citizen-tool concern): 5.8% scam / 2.4% counterfeit.
- **Auditability:** marker spans (NLP) · per-feature scores (CV) · feature importances (graph) ·
  correlation basis + reproducible `inputs_hash` (fusion) · **append-only audit log** on every
  response action. Built for legal admissibility, not just a score.

### Slide 7 — DISRUPT / RESPOND (the verb nothing else answered)
- Fusion crossing CRITICAL **auto-derives** concrete actions: freeze a mule account, block a
  scam number, alert I4C/MHA, **intercept a victim pre-transfer**, queue a review.
- Each action: priority + **SLA vs. the fraud clock**, evidence chain, append-only audit,
  dispatch/acknowledge/dismiss. **Dispatch is simulated** — we're explicit about that.
- Demo: open the **Disrupt** tab → dispatch a critical freeze → show the audit trail grow.

### Slide 8 — Financial institutions (the third stakeholder)
- **B2B, API-key-gated:** `POST /institution/screen-account` (AML risk → block / EDD / monitor /
  clear) and `POST /institution/verify-note` (teller/POS pass-fail). Same models, no citizen chrome.
- Demo: Modules → **Bank Partner** → screen a live ring account → high / BLOCK + file STR.

### Slide 9 — Predictive, honestly scoped
- **Predictive:** Fraud Shield flags mid-message before any transfer; Supply Trail predicts the
  next hub at risk. **Fast classification:** the graph scores an already-formed pattern.
- We label each module's posture in-product — scoping the claim correctly is more credible than
  calling everything "predictive."

### Slide 10 — Geospatial command centre (live)
Cross-domain DBSCAN hubs on the map; coordinated-hub tier when all 3 crime types converge;
per-district case files (AI officer over a deterministic dossier); Supply Trail provenance.

### Slide 11 — Resilience (it won't die on stage)
Keyless free map tiles; LLM failover chain ends in a deterministic template; dashboard degrades
per-module; everything works with **zero API keys**.

### Slide 12 — Roadmap (what we did NOT overclaim)
Live-call validation for Fraud Shield; per-denomination counterfeit breakdown; WhatsApp/IVR +
12-language citizen advisory (Sarvam AI translation pass — wrapper, not retrain); real
telecom/bank integration behind the already-built action contract.

### Slide 13 — Close
Detect → Disrupt → Respond, for law enforcement, banks, and citizens — every verdict carrying
its evidence, every action carrying its audit. **From point-of-complaint to point-of-contact.**

---

## Deliverables checklist
- [x] Working prototype (dashboard + 3 detection services + gateway)
- [x] Architecture diagram (`docs/architecture.md`)
- [x] Presentation deck (this outline → slides)
- [ ] Demo video (script: `docs/demo-script.md`)
