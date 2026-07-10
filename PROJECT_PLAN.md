# 📋 Aegis AI — Project Plan & Progress Log

> **Living document.** This is the single source of truth for the plan, decisions, and what's
> done. Update the **Progress Log** at the bottom after every meaningful chunk of work. When a
> decision changes, edit the relevant section *and* note it in the Changelog.

**Hackathon:** ET AI Hackathon 2026 · Problem Statement #6 (Digital Public Safety)
**Timeline:** 15-day execution plan (compressed from the original 20-day scope)
**Repo:** [github.com/sudarsan2507-hue/Aegis](https://github.com/sudarsan2507-hue/Aegis) — development happens
directly on `main` (the branch-per-person workflow below is kept for reference; in practice
everyone commits small and pulls/merges `main` before pushing). Prayag's
[fork](https://github.com/prayag-1771/Aegis) also flows into this repo.

---

## 👥 Team & ownership

| Module folder | Lead | Responsibility |
|---|---|---|
| [`fraud-shield-nlp/`](fraud-shield-nlp/) | **Sudarsan** | NLP scam / digital-arrest classifier + chat UI |
| [`counterfeit-vision/`](counterfeit-vision/) | **Adharshan** | CV fake-currency detector (feature-level) |
| [`fraud-graph-ml/`](fraud-graph-ml/) | **Prayag** | Graph ML fraud-ring detection |
| [`command-centre/`](command-centre/) | **Pushkar** (+ **Prayag** on fusion) | Dashboard + geospatial + Gen AI fusion |

> **Prayag** owns two things: the **Fraud Graph** module *and* co-owns the **command-centre Gen AI
> fusion** layer. Priority: finish and hand off the graph module early, then focus on fusion.

---

## 🎯 What we're building

One unified **Digital Public Safety** command centre fusing three independent AI systems:

1. **Fraud Shield** — real-time scam / digital-arrest call & message classifier.
2. **Counterfeit Vision** — CV model spotting fake ₹500/₹2000 notes via missing security features.
3. **Fraud Graph** — Graph ML clustering accounts into fraud rings.
4. **Command Centre** — dashboard + crime map + Gen AI fusion tying all three together.

### 2026-07-10 — Adharshan — Connected Counterfeit Vision to real Kaggle dataset
- **Resolved data block**: Replaced API-dependent Kaggle download with kagglehub. Successfully downloaded actual fake-currency-detection-dataset and linked genuine and ake inputs into the CNN training pipeline.
- **Retrained**: EfficientNet-B0 retrained successfully on the real dataset with 1.0 val accuracy. Fully swapped out synthetic data.

### The three wow moments (all live-demoable)
1. Scam call read out → flagged instantly.
2. Note held to camera → missing security feature flagged live.
3. **Fusion moment** → *"This scam call is linked to a fraud ring active in this district, and a
   counterfeit note was seized nearby."*

### The 3 defensible innovations
1. **The fusion itself** — nobody combines scam + counterfeit + fraud graph.
2. **Self-improving classifier** — LLM generates new scam variants → retrains Fraud Shield
   (before/after accuracy demo). Only exists as a Jan 2026 research paper; zero deployed products.
3. **Cross-domain crime map** — counterfeit seizures + scam origins on one map; overlapping
   clusters = coordinated hub. Cheap; reuses the map infra.

---

## 🔒 The data contract (non-negotiable)

The whole conflict-free parallel workflow hangs on this. See [`contracts/`](contracts/).

- Each module emits JSON matching its schema in `contracts/`.
- The command centre consumes that JSON and builds against `contracts/samples/` as dummy data.
- **Lock the contract in the Day 1–2 Data Contract Meeting.** Changes after that are a team
  decision, updated in the schema + sample + this Changelog.
- Validate before hand-off: `python shared/validate_contract.py <scam|counterfeit|graph|fusion> <file>`

---

## 🔀 Git workflow (how we stay conflict-free)

**Rule #1 — one folder per person.** Nobody edits another module's folder. Because the detection
modules never import each other (they only emit JSON), parallel work can't collide.

**Rule #2 — branch per person, PR into `main`.**
```
main                      # integration branch (protected-ish; merge via PR)
├── feat/fraud-shield     # Sudarsan
├── feat/counterfeit      # Adharshan
├── feat/fraud-graph      # Prayag
└── feat/command-centre   # Pushkar / Prayag
```
- Work on your branch, push often, open a PR into `main` when a piece is ready.
- Pull `main` before starting each day so you have the latest contracts.
- **Shared files** (`contracts/*`, `PROJECT_PLAN.md`, root `README.md`, `shared/*`): announce in
  chat before editing, keep edits small, commit and push immediately to minimize overlap.

**Rule #3 — never commit datasets / big model weights.** They're gitignored. Share via Drive/link
and note access in [`docs/`](docs/).

**Final step:** once `main` is solid, open a PR from `prayag-1771/Aegis:main` → Sudarsan's upstream repo.

---

## 🗓️ 15-Day execution plan

### Phase 1 — Foundation (Days 1–2)
- **All:** confirm datasets load — no modeling yet.
- **Fraud Shield:** verify SMS Spam Collection + phishing dataset access.
- **Counterfeit Vision:** verify Kaggle Fake Currency dataset + GitHub starter repo.
- **Fraud Graph:** confirm **Elliptic++** access *immediately*; if blocked, switch same-day to
  IEEE-CIS Fraud or mlg-ulb (Kaggle).
- **Command Centre:** scaffold dashboard shell + start architecture diagram.
- **⭐ ALL — Data Contract Meeting:** lock the exact JSON each module hands to the command centre.
  **Do this before anyone writes serious model code.**

### Phase 2 — Independent Build (Days 3–8, compressed 6 days)
- **Fraud Shield:** baseline classifier first (TF-IDF + LogReg); upgrade to DistilBERT only if
  time allows → add digital-arrest markers.
- **Counterfeit Vision:** transfer-learning CNN (ResNet/EfficientNet) → attempt feature-level
  detection; default to single-denomination early if behind — decide, don't wait.
- **Fraud Graph:** graph-feature engineering + XGBoost only — **skip GNN entirely** at 15 days.
- **Command Centre:** build dashboard shell + map base in parallel; don't wait on module outputs.

### Phase 3 — v1 Models Ready (Days 9–10)
- **Fraud Shield:** working v1 + start chat UI wrapper.
- **Counterfeit Vision:** working v1, fallback decision locked.
- **Fraud Graph:** working v1 fraud-cluster output. **Prayag: hand off to command centre immediately.**
- **Command Centre:** wire real outputs as they land; test LLM fusion with dummy data now.

### Phase 4 — Integration Crunch (Days 11–12, heaviest)
- **Command Centre:** full integration of all 3 modules; build Gen AI fusion layer; add geospatial
  hotspot layer.
- **Prayag:** co-own the command centre fully these 2 days — debug, wire, sit together.
- **Fraud Shield / Counterfeit Vision:** on standby to help; fix own model bugs if flagged.

### Phase 5 — Demo Prep (Days 13–14)
- **All:** end-to-end run-throughs; find what breaks.
- Rehearse: scam-call read, live note scan, the fusion-moment reveal.
- **Fix critical bugs only — zero new features from here.**

### Phase 6 — Polish (Day 15)
- **Command Centre:** finalize architecture diagram + demo video.
- **All:** finish pitch deck; one full timed dry run. Small morning buffer for last fixes.

### What got cut to fit 15 days
- **GNN stretch** for Fraud Graph — dropped; graph-features + XGBoost only.
- **DistilBERT** for Fraud Shield — now optional, not default; baseline first.
- Independent build phase cut 7 → 6 days — daily check-ins matter more.

---

## 🧭 Suggestions & risks (keep updating)

- **Highest risk = the command centre.** No redundancy if it falls behind. Mitigation: build it
  against `contracts/samples/` from Day 1 so it's never blocked on other modules; Prayag as backup.
- **Dataset stalls kill timelines.** Fraud Graph's Elliptic++ access is the top Day-1 risk — have
  the Kaggle fallback ready and decide same-day.
- **Contract drift = integration pain.** Any schema change must update schema + sample + this doc.
- **Demo > model accuracy.** Judging weights Innovation + Business Impact at 50%. A rock-solid live
  fusion demo beats a marginally better classifier. Rehearse the demo like it's the product.
- **Auditability is a named metric** — make the fusion output carry `audit_trail` + `correlation_basis`
  so it reads as court-submittable, not just a chat message.
- **Keep false positives low** on citizen-facing outputs — a stated requirement. Tune thresholds
  toward precision for the scam classifier's `scam` verdict.

---

## 📓 Progress log

> Append newest entries at the top. Format: `### YYYY-MM-DD — <who> — <what>`

### 2026-07-08 — Pushkar — Upstream merge + dashboard consolidation
- Merged `upstream/main` (Sudarsan's bug-review pass, Prayag's Elliptic++ validation +
  frontend, Counterfeit Vision v1) into my fork's line. **Two dashboards had been built in
  parallel** — Prayag's react-leaflet variant (while covering) and my MapLibre/Express-gateway
  build. Consolidated on **mine** per the team stack decision (Next + Express, reference-image
  UI); removed only the react-leaflet variant files (`app/components/CrimeMap.tsx`,
  `next.config.ts`, react-leaflet deps). **Everything else from upstream is kept untouched**:
  backend `/analyze/scam` + `/analyze/counterfeit` live-analysis endpoints, hardened
  correlator (spatial-evidence requirement, rings on map), counterfeit-vision v1,
  fraud-shield v1 + demo UIs.
- Gateway now proxies the live-analysis endpoints (`POST /api/analyze/scam`,
  `POST /api/analyze/counterfeit`) so the wow-moment flows work through the public entry
  point too; dashboard API client extended to match.
- **Second sync same day:** Prayag had independently adopted this dashboard on `main`
  (archiving his Leaflet build at `command-centre/frontend-leaflet/`); merged his Gen AI
  failover + self-improving-classifier work back in — histories now fully converged.

### 2026-07-08 — Prayag — Branch merge: adopted Pushkar's MapLibre dashboard + Express gateway
- Merged `master` into `main` (Sudarsan's repo had 3 branches). `feat/fraud-shield` was already
  fully in `main` (no-op). `master` carried Pushkar's Next 15 + MapLibre dashboard, Express 5
  gateway, and 3-website architecture — adopted as the live command-centre frontend.
- My earlier Next 16 + Leaflet dashboard preserved at `command-centre/frontend-leaflet/`
  (nothing lost). Architecture doc combines Pushkar's 3-website topology + my fusion internals.

### 2026-07-08 — Prayag — Gen AI complete + all 3 wow paths verified live + deliverables
- **Live Gen AI fusion working** — multi-provider narrator (Claude → Groq Llama-3.3-70B →
  Gemini → template failover). Groq narrator writes evidence-accurate summaries live;
  contract-valid. The demo can't die: any provider failure falls through to the template.
- **Innovation #2 shipped — self-improving classifier.** An LLM red-teams Fraud Shield:
  generates evolved scam variants (incl. investment + job-task families the model never saw),
  half augment training, half held out. Balanced legit hard-negatives added.
  **Result: recall on unseen variants 69% → 100%, zero human labels.**
  (`aegis_fusion.self_improve` + `self_improve_eval`; `data.load_extra_corpus` hook in fraud-shield.)
- **All 3 wow-moment live paths verified end-to-end through the command centre:**
  scam (risk 0.999 digital_arrest), counterfeit (fake ₹500, conf 1.0, 3 features named),
  fusion (CRITICAL, live Groq narrator). Counterfeit path required fixing an undeclared
  `scipy` dependency in counterfeit-vision (noted for Adharshan in gitignored BUG_REPORT.md —
  didn't edit his folder).
- **Judged deliverables:** `docs/architecture.md` (Mermaid system + fusion-sequence diagrams,
  criteria mapping) and `docs/demo-script.md` (6-min run-of-show with fallbacks + Q&A ammo).
- **Keys:** Groq/Gemini in gitignored `command-centre/fusion/.env`. Gemini currently 429
  (free-tier quota) but authenticates — failover handles it.
>>>>>>> upstream/main

### 2026-07-07 (night) — Sudarsan — Full-codebase bug review + remediation pass
- Reviewed all four modules end-to-end; fixed the demo-critical integration gaps:
  - **Live wiring complete:** both demo UIs (8001/8002) now auto-ingest detections into the
    command centre with a selectable origin/seizure district → live events reach the dashboard,
    map and fusion. Backend gained `/analyze/counterfeit` proxy + typed frontend API helpers.
  - **Correlator hardened:** links now require *spatial* evidence (temporal alone linked
    unrelated events across the country); fraud rings now plotted on the crime map via a
    district→coords lookup, so cross-domain hubs can genuinely show all three signals.
  - **Counterfeit robustness:** note localisation (contour + perspective warp) — angled camera
    shots now land the security-feature regions correctly; PR-curve-picked verdict thresholds;
    captures served at `/captures` for the dashboard; upload size caps.
  - **Honest evaluation:** fraud-shield retrained on a template-grouped 3-way split (tune on
    val, report on test) — headline: ROC-AUC 0.993, scam precision 0.973 @ recall 0.924 on
    *held-out templates*. Counterfeit: ROC-AUC 0.962, fake precision 1.0 @ recall 0.79 on an
    untouched test slice.
  - Plus: ingest schema validation at the backend door, fraud-graph warms at startup (no more
    first-request timeout), local-only CORS everywhere, UTF-8 console output, dataset checksum
    pin, verified Kaggle dataset slug (`sreeharisureshkaggle/fake-currency-detection-dataset`).
- **Still open (needs creds/hardware):** real-note retrain once `kaggle.json` lands;
  camera demo must run on localhost (or add an HTTPS dev cert) for `getUserMedia`.

### 2026-07-07 (evening) — Prayag — REAL-DATA VALIDATION + frontend + fraud-shield integration
- **Elliptic++ real-data validation (Person C COMPLETE):** ROC-AUC **0.945** on real Bitcoin
  fraud (all 14,266 illicit wallets + 50k licit sample, structure-only features).
  Same pipeline, no code changes: `fraud-graph demo --source elliptic`.
- **Dashboard frontend** (Next.js 16 + React 19 + Tailwind + Leaflet, no map token needed):
  three signal cards, health pills, crime map with pulsing cross-domain hubs, RUN FUSION panel.
- Merged **Sudarsan's fraud-shield v1** from upstream (zero conflicts — contract-first works);
  added `POST /analyze/scam` proxy so live scam analysis auto-ingests into the dashboard + fusion.

### 2026-07-07 — Sudarsan (covering Adharshan) — Counterfeit Vision v1 working end-to-end
- **Dataset decision locked Day 1** (per plan: "decide, don't wait"): no Kaggle credentials on
  the build machine → v1 trains on a **synthetic ₹500/₹2000 note renderer** with controllable
  security features, giving per-feature ground truth no public dataset has. `data.py` keeps the
  Kaggle download + real-dataset prep hook ready — retrain is one CLI flag when creds land.
- Built in `counterfeit-vision/` (work now committed directly on `main`):
  - **Feature-level checks (OpenCV):** security-thread darkness contrast, watermark brightness
    lift, microprint Laplacian sharpness — validated 40/40 genuine clean, 40/40 fakes caught
    with the correct feature named. Denomination inferred from hue.
  - **CNN:** EfficientNet-B0 transfer learning (head-only). Val: ROC-AUC 0.980, fake-verdict
    precision 1.0 @ recall 0.70, uncertain rate 22%.
  - **Verdict fusion:** ≥2 failed features (or 1 + elevated CNN score) ⇒ fake; a note is never
    certified genuine while any security check fails; mid-band ⇒ `uncertain` (manual check).
  - **Contract emitter** — validated by `shared/validate_contract.py counterfeit` ✔.
  - **CLI** (`generate`/`train`/`analyze`/`demo`), **FastAPI** on port **8002** (`/analyze`
    multipart, `/analyze_b64` for webcam, `/health`), **camera demo UI** at `/`, **11 tests**.
- **Next:** command-centre wiring (endpoint ready); Kaggle real-data retrain when creds available.

### 2026-07-07 (evening) — Pushkar — Dashboard + gateway + 3-website architecture
- **Team decision:** all future work in **Next.js + Express (latest)**. Architecture is a
  **3-website setup**: citizen currency-check site (Adharshan), citizen scam-alert site
  (Sudarsan), and the command-centre dashboard (Pushkar). **Fraud Graph needs no separate
  website** — it stays an internal service feeding the dashboard. See
  [`docs/architecture.md`](docs/architecture.md) (new, with mermaid diagram + port table).
- **Express 5 gateway** (`command-centre/gateway/`, :4000): the single public entry point.
  Citizen sites POST `scam_detection` / `counterfeit` JSON to `/api/alert/scam` and
  `/api/report/counterfeit`; dashboard reads `/api/events`, `/api/hotspots`, `POST /api/fuse`.
  Forwards to the FastAPI backend (:8000) — the Python fusion/geospatial layers are unchanged.
- **Dashboard** (`command-centre/frontend/`, :3000): Next.js 15 + React 19 + Tailwind 4 + TS.
  Full-bleed MapLibre crime map (keyless CARTO dark + Esri satellite — no token to die on),
  glass-panel UI: module health, signal-confidence sparkline, scam/note cards, ring risk bars,
  warning feed with click-to-fly alerts, **Run Fusion** typewriter reveal with audit hash,
  live signal-volume bars. Pulsing markers per domain + red **COORDINATED HUB** rings.
- **Map provider research** for the team: [`docs/map-providers.md`](docs/map-providers.md) —
  chosen stack costs ₹0 with no API key; MapTiler (~$25/mo) is the scale-up path.
- **Remaining:** wire real citizen sites when A/B deliver, demo video, deck.

### 2026-07-07 (later) — Prayag — Fusion layer + command-centre backend + geospatial DONE
- **Gen AI fusion layer** (`command-centre/fusion/`): deterministic correlation engine
  (shared district / ≤30km geo / ≤96h temporal evidence) + Claude narrator
  (`claude-opus-4-8`, structured output) with template fallback — demo never dies without
  an API key. Reproducible `inputs_hash` audit trail. 6 tests, contract-valid.
- **Command-centre backend** (`command-centre/backend/`, :8000): single API for the
  dashboard — ingest endpoints, module health probes, `POST /fuse`, `GET /hotspots`.
- **Geospatial layer** (`command-centre/geospatial/`): DBSCAN hotspot clustering;
  `cross_domain=true` hubs = coordinated crime hubs (innovation #3). 4 tests.
- **Ring-recovery evaluation** added to fraud-graph: **12/12 rings (100%), precision 1.0,
  recall 0.94** — deck numbers.
- Elliptic++ public Drive download in progress (AddrAddr edgelist done; wallets_classes
  pending) → real-data validation next.
- **Needs Prayag:** ANTHROPIC_API_KEY in `command-centre/fusion/.env` (console.anthropic.com,
  ~$5 credit is plenty) to light up the live Gen AI narrator.
- **Remaining for the demo:** dashboard frontend (cards + fusion reveal + crime map),
  wiring A/B modules when Sudarsan/Adharshan deliver, architecture diagram, demo video.

### 2026-07-07 — Prayag — Fraud Graph module v1 COMPLETE (Phase 2 goal hit on Day 1)
- Full pipeline working end-to-end: synthetic data → 18 graph features → XGBoost →
  Louvain ring clustering → contract-validated `fraud_graph.json` → FastAPI on :8003.
- Synthetic world generator with 3 real laundering topologies (mule chains, smurfing
  fan-in, round-tripping cycles) **plus legit heavy actors** (merchants, payroll, B2B)
  so the model must learn behaviour, not "big amount = fraud".
- Results: AUC 0.998, AP 0.958, precision 0.94 @ recall 0.76 (precision-first threshold);
  ring recovery 12/12, 94% of illicit accounts.
- 4 pytest tests incl. end-to-end contract compliance — all green.
- Pushed to fork + upstream (sudarsan2507-hue/Aegis). **Command centre can integrate
  against `GET :8003/fraud-graph` or `output/fraud_graph.json` today.**
- **Postponed for Prayag's return:** Kaggle/Drive access for real Elliptic++ validation
  (pipeline has an `elliptic` loader ready; drop files in `data/elliptic/`).

### 2026-07-07 — Sudarsan — Fraud Shield v1 working end-to-end
- Confirmed dataset access (Phase 1 ✔): UCI SMS Spam Collection downloads via `data.py`.
- Built the module on branch `feat/fraud-shield`, all inside `fraud-shield-nlp/`:
  - **Marker rules engine** for the 8 contract markers, with matched evidence spans.
  - **Synthetic Indian-scam corpus** (digital-arrest scripts + KYC/lottery/loan/phishing +
    hard legit negatives) — public datasets predate digital arrest entirely.
  - **Classifier**: word+char TF-IDF ⊕ marker features → LogReg; precision-first thresholds
    (scam band ≥0.97 precision). Held-out: ROC-AUC 0.984, scam precision 0.971 / recall 0.919,
    100% recall on all synthetic scam families.
  - **Contract emitter** — output validated by `shared/validate_contract.py scam` ✔.
  - **CLI** (`train` / `analyze` / `demo`), **FastAPI** `/analyze` + `/health` on port 8001,
    **chat UI** at `/` for the live demo, **15 tests** (offline) all passing.
- **Next:** hand endpoint to command centre; optional DistilBERT upgrade only if schedule allows.

### 2026-07-07 — Prayag / setup — Repo scaffolded
- Made `Aegis/` its own git repo pointing at the `prayag-1771/Aegis` fork, isolated from the outer
  `VSC_NEW` workspace repo (added `/Aegis/` to the outer `.gitignore` so there's no cross-tracking).
- Created module folders: `fraud-shield-nlp/`, `counterfeit-vision/`, `fraud-graph-ml/`,
  `command-centre/`, plus `contracts/`, `shared/`, `docs/`.
- Wrote the data contract: `scam_detection`, `counterfeit`, `fraud_graph`, `fusion_output` schemas
  + sample payloads + a `shared/validate_contract.py` validator.
- Wrote root `README.md`, per-module READMEs, and this plan.
- **Next:** hold the Data Contract Meeting (Phase 1) and confirm datasets. For Prayag specifically:
  confirm Elliptic++ access and start the Fraud Graph pipeline.

---

## 🧾 Changelog (contract / plan changes)

- **2026-07-07** — Initial contracts v1.0 created (`schema_version: "1.0"` across all four).
