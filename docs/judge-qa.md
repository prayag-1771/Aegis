# 🎓 Twenty Questions for Aegis — Judge Q&A Prep

> The questions a judge is most likely to ask about the architecture, the models, and the claims —
> with answers drawn from what the code actually does.
>
> **Every figure here is read from the persisted training reports in the repo, not from the README**
> (`fraud-shield-nlp/models/`, `counterfeit-vision/models/`, `fraud-graph-ml/models/`). The README has
> drifted. The corrections that drift requires are listed in the last section — **read that first.**

**At a glance:** 4 detection modules · 6 services · 0.9945 Elliptic++ ROC-AUC · 21 graph features

**Contents**

- [Part I — Architecture & system design](#part-i--architecture--system-design) (Q1–Q6)
- [Part II — The models](#part-ii--the-models) (Q7–Q12)
- [Part III — Trust, evidence, false positives](#part-iii--trust-evidence-false-positives) (Q13–Q16)
- [Part IV — Data, scale, and the path to real](#part-iv--data-scale-and-the-path-to-real) (Q17–Q20)
- [⚠️ Fix these before you present](#-fix-these-before-you-present)

---

## Part I — Architecture & system design

*How the pieces are separated, why, and what happens when one of them fails.*

---

### Q1. Walk me through exactly what happens when a citizen pastes a scam message into your site.

Six hops, and every one of them carries JSON validated against a schema.

1. The citizen site POSTs `{text, source}` to the **Express gateway** on `:4000`.
2. The gateway is a thin validate-and-forward layer holding no business logic — it proxies to
   `POST /analyze/scam` on the **FastAPI backend** (`:8000`).
3. The backend calls **Fraud Shield** (`:8001`), which runs the text through the regex marker layer
   and the TF-IDF ⊕ marker logistic-regression pipeline, and emits a `scam_detection` payload.
4. The backend **re-validates that payload** against `contracts/scam_detection.schema.json` *before it
   touches state* — junk that gets past ingest would otherwise reach the fusion LLM and the dashboard
   unchecked.
5. It **upserts** into the event store keyed by `event_id`, so a resubmission (a victim adding payment
   details later) updates rather than duplicates.
6. The dashboard picks it up on its next `/events` poll. The detection is now live to the crime map,
   the hotspot clusterer, the next fusion run, and the response-action queue.

A non-English citizen gets two extra hops: `/citizen/analyze` normalises the message to English through
Sarvam translate first and translates the safety advisory back into their language. That path **fails
safe** — no key, no network, or same-language all return the input unchanged with `translated: false`,
so the classifier still runs.

> **In code:** `gateway/src/server.js` · `backend/api.py` → `analyze_scam`, `_citizen_pipeline` ·
> `backend/store.py` → `add_scam`

---

### Q2. Why six services and a JSON contract layer instead of one application?

The contract layer is a **team-structure decision** as much as a technical one. Four people built in
parallel; the detection modules *never import each other*. They emit JSON validated against
`contracts/*.schema.json`, and the command centre consumes it. One folder per person, so parallel work
physically cannot collide.

Technically it buys three things:

- **Swappability.** Any model can be replaced without touching the rest. The Elliptic++ real-data
  validation ran through the identical pipeline with a different loader and *zero code changes* — that
  is the claim the architecture is making, demonstrated.
- **Dependency isolation.** Each module keeps its own virtualenv. PyTorch, XGBoost, and scikit-learn
  never have to co-resolve in one environment — which is where hackathon projects usually die.
- **Versioned interfaces.** Every schema carries `schema_version`, so a contract change is a
  deliberate, visible event rather than a silent break at 2 a.m.

The honest cost: six processes to start, and cross-service HTTP where a monolith would make an
in-process call. At demo scale that latency is invisible; the parallel-development gain was not.

> **In code:** `contracts/` (5 schemas + samples) · `shared/validate_contract.py`

---

### Q3. The gateway is Express and the backend is FastAPI. Isn't that hop redundant?

It's a **trust boundary**, not an accident. The gateway on `:4000` is the only thing meant to be
publicly reachable; `:8000`–`:8003` stay internal. It validates the shape of inbound citizen payloads,
enforces a 5 MB body limit, owns the CORS allow-list, and passes through the `X-API-Key` header the
bank-facing routes require.

It deliberately reimplements *none* of the fusion or geospatial logic — that stays in Python next to the
models. The gateway forwards and shields; it does not think.

> **⚡ If they push:** There is no authentication yet — CORS and the static institution API key are the
> only gates. Say so plainly, then say where it goes: the gateway is precisely the layer built to
> receive it, which is why the hop exists at all.

> **In code:** `gateway/src/server.js` → `forward()`, `apiKeyHeader()`

---

### Q4. Your "AI fusion" — is an LLM deciding which crimes are linked?

**No.** That separation is the single most important design decision in the project.

Correlation is a **deterministic engine** with machine-checkable rules: signals naming the same
district, haversine distance ≤ 30 km, timestamps within 96 h, and the money-trail match. Every link it
emits carries a `reason` string an officer can independently verify. Threat level is *computed, not
written* — it's the count of distinct signal domains that got linked, and all three converging is what
makes it `critical`.

Only then does the LLM appear. It receives a `facts` dictionary containing *only established links*,
under a system prompt that forbids inventing connections. It writes the prose and suggests next steps.
It has **no** access to raw events, **no** tool to query the store, and **no** path to write
`linked_signals`, `threat_level`, `correlation_basis`, or `money_trails`.

That's what makes the package defensible rather than merely impressive: re-run it on the same inputs and
you get the same links and the same `audit_trail.inputs_hash`.

> **In code:** `fusion/correlator.py` → `correlate()` · `fusion/narrator.py` → `SYSTEM_PROMPT` ·
> `fusion/fuse.py` → `_inputs_hash()`

---

### Q5. Show me your strongest link. How do you get from a scam call to a specific bank account?

**The money trail.** A `scam_detection` payload can carry `reported_payment.amount` — what the victim
says they paid. The fraud-graph export includes inflow edges: transactions from outside a ring landing
in a ring account. The correlator sorts those inflows deterministically and looks for one where the
amount matches within **±1%** and the timestamp falls between 2 h before and 96 h after the call. The
first qualifying match wins and the loop breaks — so the answer is reproducible, not "whichever one the
model liked".

The deliberate subtlety is what we **don't** require. **District is not a gate.** The `location_hint` on
a scam event is the *victim's* location, and mule networks operate far from their victims by design —
that is the entire point of layering. Gating on district would silently miss most real trails. It's
reported as a bonus signal when it lines up, and the narrator prompt explicitly forbids claiming the ring
and victim are co-located unless `same_district` is true.

The output is a **named account ID an officer can act on tonight**, which flows straight into a
`critical`-priority `account_freeze` action addressed to the beneficiary bank via NPCI.

> **In code:** `fusion/correlator.py` (scam → ring payment block) · `backend/response.py` rule 1

---

### Q6. What happens on stage when your LLM provider is rate-limited or a service goes down?

Every layer degrades instead of failing.

- **Narrator.** A provider chain — Claude → Groq → Gemini → two spare Groq keys → deterministic
  template. `narrate_safe` catches any exception, logs which provider failed and why, and falls
  through. A 429 carrying a short `retry-after` gets exactly **one bounded retry (≤ 12 s)**, because
  Groq's token budget refills continuously and falling straight to the template threw away a briefing
  that was seconds from arriving. Anything longer moves on.
- **Modules.** `/health` probes each service on a 1.5 s timeout; the dashboard renders per-module status
  pills. A down module degrades its own card, not the page.
- **Map.** Keyless tiles — CARTO dark and Esri imagery. There is no API token that can expire mid-demo.
- **Research panels.** The expensive modules are precomputed to static JSON; each block is independently
  nullable, so the UI degrades per-module rather than failing whole.

The important detail for a credibility question: `audit_trail.model` records **which** narrator actually
produced the text. A template-fallback run is visible in the output, not disguised as a live LLM one.

> **In code:** `fusion/narrator.py` → `_PROVIDER_CHAIN`, `narrate_safe()`, `_rate_limit_wait()`

---

## Part II — The models

*Why each algorithm was chosen, what it actually measures, and how the numbers were produced.*

---

### Q7. TF-IDF and logistic regression for scam detection, in 2026? Why not a transformer?

Baseline-first was the explicit plan, and the baseline held. The feature union is word n-grams (what is
said), character n-grams via `char_wb` 3–5 (which catches obfuscation like `K.Y.C` and `b1t.ly`), the
eight contract markers as explicit binary features, and two playbook-structure features so that N markers
forming a *coherent scam script* score differently from N unrelated ones. It trains in seconds and
reaches **ROC-AUC 0.998** with **0.942 scam precision at 0.952 recall** on a held-out, template-grouped
test split.

The stronger reason is **evidential**. The rule layer returns the *matched text spans* — that's what
powers the "why flagged" UI, feeds the fusion facts, and satisfies auditability, which is a named judging
criterion. A transformer gives a score with no spans. We would have had to build the marker layer anyway;
having built it, feeding it to the classifier as features was free.

There's also a safety net a pure model wouldn't give: a message scoring below both thresholds but
tripping **three or more markers** never renders as clean — it escalates to `suspicious`.

> **In code:** `fraud-shield-nlp/model.py` → `MarkerFeatures`, `decide_verdict()` · `markers.py`

---

### Q8. Why XGBoost instead of a GNN for the fraud graph?

At this scale, boosted trees on well-engineered graph features match GNN accuracy on Elliptic-style
tasks, train in seconds, and produce **feature importances** — and auditability is a named judging
criterion, not a nice-to-have. The GNN was explicitly cut on day one of a fifteen-day plan, as a *scope*
decision rather than a capability one.

The result backs the call: **0.9945 ROC-AUC at 0.90 precision / 0.85 recall** on the Elliptic++ benchmark.

And we didn't abandon deep learning where it earns its cost — **GraphSAGE appears in the Ghost Ring
federated experiment**, because cross-bank matching genuinely needs node embeddings to compare accounts
that no single bank can see. Heavy tool, real need.

> **In code:** `fraud-graph-ml/model.py` (module docstring states the trade-off) · `ghost_ring.py`

---

### Q9. Your demo lets us invent a gang and it gets caught in seconds. Why does that work if the model has never seen those accounts?

Because **the model never sees account identities.** It sees **21 behavioural features** computed from
the transaction graph:

- **Flow shape.** `throughput_ratio` ≈ 1 means money in ≈ money out — the textbook mule.
- **Tempo.** `burst_ratio` is the share of an account's transfers happening within 60 minutes of the
  previous one. Mule chains move in minutes; people don't.
- **Amount texture.** `round_amount_ratio` — fraud loves 10k / 25k / 50k figures.
- **Counterparty shape.** `fan_in_ratio` and `fan_out_ratio` separate a collector (many senders, few
  receivers) from a distributor.
- **Pure structure.** PageRank, degree centrality, clustering coefficient, k-core number.

None of that is identity. A new gang running a laundering topology produces the same feature signature,
so it scores high on the first pass with nothing retrained. It's also why the synthetic world generator
deliberately includes *legitimate heavy actors* — merchants, payroll, B2B — so the model is forced to
learn behaviour rather than "big amount = fraud".

> **⚡ If they push:** Three of the 21 features — `burst_ratio`, `fan_in_ratio`, `fan_out_ratio` — carry
> **0.0 importance** in the current synthetic training report; the tree found `avg_amount` and `tx_count`
> sufficient on that labelled set. **Concede it.** They matter on the real-data run and in the ring
> topology labelling, but on *this* dataset the classifier isn't leaning on them.

> **In code:** `fraud-graph-ml/graph.py` → `FEATURE_COLUMNS`, `compute_features()` ·
> `models/train_report.json`

---

### Q10. How do you get from per-account risk scores to a named "ring"?

Four deterministic steps, no LLM anywhere in the path:

1. Keep only accounts scoring at or above the ring threshold.
2. Induce the transaction subgraph over exactly that set.
3. Run **Louvain** community detection on the undirected, amount-weighted view with a **fixed seed**,
   falling back to connected components when there are no edges.
4. Keep communities meeting the minimum ring size; each becomes a ring scored by mean member probability
   and tagged with its dominant district.

Each ring then gets a **topology label** an investigator can read at a glance — *round-tripping cycle*,
*multi-hub laundering network*, *mule collection hub*, *layering chain*, or *mixed* — derived from cycle
detection and hub degree, not from a model.

Measured on the labelled synthetic graph: **12 of 12 rings recovered, account precision 1.0, account
recall 0.94.**

> **In code:** `fraud-graph-ml/rings.py` → `detect_rings()`, `_topology_label()` ·
> `models/ring_eval_report.json`

---

### Q11. Detecting a fake note is easy. How does yours name *which* security feature is missing?

Three layers, cheapest first — the same discipline as the NLP module.

1. **Pre-flight triage (OpenCV only, no ML).** Quality gates send unscannable photos back with rescan
   advice. Four obvious-fake tells — saturation collapse (photocopy), no high-frequency intaglio texture,
   impossible aspect ratio, a dominant hue no circulating denomination uses. It takes **two independent
   tells** to convict, because any single one can have an innocent explanation. Obvious fakes exit here
   and the CNN never runs.
2. **Feature checks on a perspective-corrected note.** Contour detection plus a warp, so an angled desk
   photo still lands the security-feature regions correctly.
   - *Security thread* = column-darkness contrast in the thread band
   - *Watermark* = brightness lift of the oval against a true annulus
   - *Microprint* = Laplacian variance after a 3×3 denoise, so sensor noise can't masquerade as sharp print

   Each returns **a measured number and its threshold** — that's the auditable artifact.
3. **EfficientNet-B0.** Scores the *original* image, deliberately **not** the warped one — the perspective
   warp mis-fires on out-of-distribution inputs like novelty notes and can distort them into looking
   genuine. Grad-CAM produces a heatmap overlay of the regions that drove the decision.

The verdicts compose conservatively: a note is **never certified genuine while any security check
fails**; the feature checks never flip the CNN verdict; and the serial-number registry and vision-LLM
layers can only *cap* a genuine call down to uncertain — never acquit, never convict.

Measured on real photographs of real and fake notes: **val accuracy 0.969, ROC-AUC 0.994, fake precision
0.976, fake recall 0.964.**

> **In code:** `counterfeit-vision/prescreen.py` · `features.py` → `locate_note()` · `analyze.py` →
> `_analyze_core()`

---

### Q12. How do I know these numbers aren't inflated by leakage?

Fraud Shield is the right one to interrogate, and the split is built for exactly that objection. The
synthetic corpus generates many variants per source template, so a naive random split puts siblings of
one template on both sides and inflates recall. We use **`GroupShuffleSplit` on a `group` column** so the
whole template group moves together, and we split **three ways**: train, validation, test. Thresholds are
picked from the *validation* PR curve; every reported metric comes from a test slice the tuning never
saw. Reporting on the tuning slice would be optimistically biased, and the code says so.

Elliptic++ carries its own trap: a wallet appears once per active time step, so the same address can land
on both sides of a split. We **deduplicate to the latest snapshot per address** first.

> **⚡ If they push:** The honest caveat, and the Model Card already states it: the scam corpus is largely
> synthetic and LLM-generated, because public datasets predate digital arrest entirely. The real
> validation gap is **live-call data**. Say it before they do.

> **In code:** `fraud-shield-nlp/model.py` → `_grouped_split()`, `train()` ·
> `fraud-graph-ml/elliptic_bench.py`

---

## Part III — Trust, evidence, false positives

*The questions that decide whether this could ever touch a real citizen.*

---

### Q13. A wrongly frozen account or a wrongly accused citizen is catastrophic. How do you control false positives?

Four independent mechanisms, at four different layers.

- **Precision-first thresholds everywhere.** No module uses a blind 0.5. Each picks the highest-recall
  threshold on its PR curve that still meets a precision floor — and when no threshold reaches that
  floor, the code **emits a warning rather than silently returning a default**, so a missed guarantee is
  visible instead of hidden.
- **Clean verdicts never enter correlation.** Only `scam`/`suspicious` detections and `fake` notes reach
  the correlator. A message judged legitimate cannot be linked into anybody's case file.
- **Spatial evidence is mandatory** for a scam ↔ counterfeit link. Temporal proximity alone was linking
  unrelated events across the country and flooding the package; it now only *strengthens* a spatial
  match, never establishes one. That was a real bug we found and fixed, not a hypothetical.
- **Conservative composition** in the vision path: two independent tells to convict on triage, never
  certify genuine on a failed check, secondary layers can only cap downward.

The Model Card also reports `false_alarm = 1 − precision` — the share of alerts that are false — because
for a citizen-facing tool that's the number that matters, not accuracy.

> **In code:** `model.py` → `_pick_threshold()` (both modules) · `correlator.py` spatial gate ·
> `backend/api.py` → `/metrics`

---

### Q14. What stops the LLM hallucinating a link that puts an innocent person in a case file?

**Structurally, it never gets the opportunity.** It sits downstream of the correlator, receives only
established facts, and has no write path to any decision field. Output is schema-constrained — pydantic
structured output for Claude, `response_format: json_object` for Groq and Gemini — and the whole package
is validated against `contracts/fusion_output.schema.json` before it is stored.

The same restraint is applied **everywhere** an LLM appears in this system, which is the part worth
pointing out:

- The Fraud Shield verification agent returns a separate `verification` object and is explicitly
  forbidden from writing verdict, risk score, scam type, or markers.
- The counterfeit triage narrator explains a decision that has already been made by measurement.
- The supply-trail narrator explains a ranking it cannot reorder.

In every case the LLM is a **writer, never a decider** — and every one of them has a deterministic
template floor. Remove every API key from the project and the prose changes; no verdict, link, score, or
action does.

> **In code:** `fusion/narrator.py` · `fraud-shield-nlp/verify/agent.py` → `SYSTEM_PROMPT` ·
> `counterfeit-vision/prescreen.py`

---

### Q15. You claim court admissibility. What actually goes in the file?

Each layer ships its own evidence, and the layers compose:

| Layer | Evidence emitted |
|---|---|
| **NLP** | The eight markers, each with the **matched text spans** that triggered it |
| **Vision** | Per-check measured score against its threshold — *"thread-band darkness contrast 4.2, needs ≥ 12"* — plus a Grad-CAM overlay of what the model looked at |
| **Graph** | Feature importances, per-account illicit probability, and a plain-language reading of the features an officer can follow |
| **Fusion** | `correlation_basis` (which rule types fired), a per-link `reason`, and `audit_trail` = `{model, inputs_hash, prompt_version}`. The hash is SHA-256 over canonicalised inputs — anyone can re-run the engine and verify the same package |
| **Actions** | `trigger.refs` is the evidence chain; `audit` is append-only. Officer state survives re-derivation — history is never rewritten |

And the posture is **deliberately modest**, which is what makes it credible. Every response carries its
own disclaimer: dispatch is simulated, actions are decision-support that do not assert guilt,
plate-family matching is an investigative lead and not forensic proof, and supply-trail `plausibility` is
a hypothesis score bounded in [0, 0.9] — never a probability of guilt.

**The claim is admissible *reasoning*, not automated conviction.**

> **In code:** `contracts/response_action.schema.json` · `backend/store.py` → `update_action()` ·
> `fusion/fuse.py` → `AuditTrail`

---

### Q16. Training a scam classifier on LLM-generated scam text — isn't that circular?

The design anticipates that, and the split is what makes it honest. The LLM generates variants per
family, then **even-indexed rows go to training and odd-indexed rows are held out as an eval set that
never enters the corpus**. The reported improvement is measured entirely on the half the model was never
trained on.

Two of the four scam families — **investment fraud and job-task scams** — are *entirely new categories*
the classifier had never seen in any form. So it tests generalisation to unseen scam **families**, not
memorisation of paraphrases.

There's a measured lesson baked into the code, too: an early run added 48 scam rows against only 10 legit
rows and drove legit accuracy from 0.9 down to **0.2**. Legit hard negatives now get their own families at
1:1 volume — realistic OTP notices, genuine KYC *completion* confirmations, real court cause-lists —
specifically to stop the retrained thresholds turning trigger-happy.

> **⚡ If they push:** The current report shows `llm_investment` recall at **0.50** on held-out rows. A
> brand-new family is the hardest case and the number says so. Quote the **69% → 100%** figure for the
> original held-out variants; do **not** claim blanket 100% across every family.

> **In code:** `fusion/self_improve.py` → `generate()`, `LEGIT_FAMILIES` ·
> `fraud-shield-nlp/models/train_report.json`

---

## Part IV — Data, scale, and the path to real

*Where the honesty is load-bearing — what's genuine, what's simulated, what breaks.*

---

### Q17. Be precise: what here is real data, and what is synthetic?

**Real.**
Elliptic++ — the Bitcoin fraud benchmark — at **265,354 labelled wallets** after deduplication, of which
**14,266 are illicit**, scored at 0.9945 ROC-AUC. Counterfeit Vision is trained on **real photographs**
of real and fake notes (3,508 training images); the synthetic renderer it started on was replaced
mid-project. The UCI SMS Spam Collection supplies legitimate and spam messages. The supply-trail FIR
corpus is drawn from **cited press and police reports**, and the printing-press locations it routes from
come from those citations, not from guesses.

**Synthetic.**
The UPI/mule transaction graph — built with three real laundering topologies *and* deliberately included
legitimate heavy actors. The scam corpus, because public datasets predate digital arrest entirely: Indian
scam scripts plus LLM red-team variants. District tagging on graph accounts is demo geography, and the
ring-to-coordinate lookup is a hardcoded eight-district table.

**Simulated.**
**Every dispatch.** There is no live bank, telecom, or MHA integration, and every action record says so in
its own payload. The WhatsApp endpoint is a transport adapter over the same pipeline, not a live Meta or
Twilio webhook.

That last category isn't a technical gap and shouldn't be conceded as one. *A live NPCI or telecom feed is
a partnership and a legal agreement, not an afternoon of coding.*

> **In code:** `fraud-graph-ml/synth.py` · `counterfeit-vision/models/train_report.json` ·
> `supply_trail/data/fir_corpus.json`

---

### Q18. Elliptic++ is Bitcoin. India's problem is UPI. Why does that transfer?

Because the pipeline scores **graph topology**, not currency-specific attributes. Flow shape, layering
depth, community structure, tempo, counterparty fan — these are properties of *how money moves through a
network*, and they are the same properties on Bitcoin rails and UPI rails. That reasoning is stated as a
caveat on the Model Card rather than glossed over.

There's a distinction worth drawing **before a judge draws it for you**: two separate runs answer two
separate questions.

| Run | Question it answers | Result |
|---|---|---|
| Induced-subgraph (our features) | Does *our* feature pipeline transfer to real data unchanged? | AUC 0.945 |
| 55-feature benchmark (authors' official features) | Is the *classifier* benchmark-competitive? | AUC 0.9945 |

Conflating them is the mistake; keeping them apart is the credibility.

The honest limit: Bitcoin illicit behaviour is not identical to UPI mule behaviour, and **no public
labelled Indian transaction graph exists** to validate against. Elliptic++ is the closest real proxy
available, and we call it a proxy.

> **In code:** `fraud-graph-ml/elliptic_bench.py` (module docstring makes the two-claims split explicit) ·
> `data.py` → `load_elliptic`

---

### Q19. What breaks at national scale?

Three things, and **we know which** — which is the point of the answer.

- **The event store is in-memory.** A bounded deque capped at 500 events per signal type; restart loses
  state. Hackathon-grade on purpose, and the interface (`add` / `snapshot` / `set`) is deliberately tiny
  so a PostgreSQL swap touches nothing else in the codebase.
- **The hotspot clusterer is a hand-written O(n²) DBSCAN.** Dependency-free by choice, fine at hundreds
  of points, and replaced by `sklearn.cluster.DBSCAN(metric="haversine")` when point counts grow. The
  module says so in its own docstring.
- **Correlation is pairwise** — scams × counterfeits × rings. Invisible at demo volume; at national
  volume it needs spatial indexing (R-tree or geohash buckets) ahead of the cross product, plus
  time-windowing so only a recent slice is ever correlated.

Scaling **in our favour**: the services are already independent and stateless apart from the store, so
each scales horizontally behind the gateway. The inference is cheap — one XGBoost score and one
EfficientNet-B0 forward pass, both milliseconds. And the genuinely expensive research modules (GraphSAGE,
the evolutionary arms race, per-community eigendecomposition) are precomputed to static JSON and **never
run in the request path**.

> **In code:** `backend/store.py` · `geospatial/hotspots.py` · `backend/api.py` → `/research`

---

### Q20. Who runs this, who pays for it, and what's the first real deployment?

The challenge names three stakeholders. **All three have a built surface:**

- **Law enforcement** — the command centre: correlated picture, crime map, case files, and the Disrupt
  queue where a finding becomes an addressed, SLA-tracked, auditable action (freeze via NPCI, number
  block via DoT/CEIR, national alert to I4C).
- **Financial institutions** — a machine-to-machine surface behind an API key.
  `/institution/screen-account` for AML triage and `/institution/verify-note` for a teller or POS
  terminal: terse pass/fail, no UI chrome, mapped onto procedure banks **already run** (STR filing,
  Enhanced Due Diligence, currency-chest escalation).
- **Citizens** — the scam-alert and currency-check sites, a multilingual path covering the 22 scheduled
  languages, and channel adapters for chat, live call, and WhatsApp.

The realistic first deployment is a **single district cybercrime cell**, because the value doesn't require
national scale — correlation is what makes one district's isolated complaints legible as a *single
operation*. The mid-call intercept path is where the business case is strongest: flagging a digital-arrest
call **before** the transfer is the only intervention that *prevents* the loss rather than investigating
it afterwards.

Honest framing to close on: everything after detection is currently simulated. The blocker between here
and a real account freeze is an NPCI or bank integration agreement — **an institutional problem, not an
engineering one.**

> **In code:** `backend/institution.py` · `backend/response.py` → `derive_actions()` · `backend/api.py` →
> `/citizen/*`

---

## ⚠️ Fix these before you present

Six places where the repo contradicts itself. A judge who opens the README beside the Model Card will
find them — and **a number that doesn't match its own source costs more credibility than a lower number
honestly reported.**

### 1. README scam metrics are stale

README claims ROC-AUC **0.984** and scam precision **0.97**. The current
`fraud-shield-nlp/models/train_report.json` says **0.998 / 0.942**.
The AUC is *better* than advertised and the precision is *lower*. Quote the report, and update the README.

### 2. README counterfeit metrics are stale

README claims ROC-AUC **0.96** and fake precision **1.0**. The current report says **0.994 / 0.976** on
the real-photo dataset. *"Precision 1.0"* is the number a sharp judge will challenge hardest — and you no
longer need it.

### 3. "18 graph features" is wrong

README and `PROJECT_PLAN.md` both say 18. `FEATURE_COLUMNS` has **21** — `fan_in_ratio`, `fan_out_ratio`,
and `mule_score` were added later.

### 4. "823k wallets" overstates the run

Elliptic++ has ~822k addresses; the benchmark actually scored **265,354 labelled wallets** after dropping
unknowns and deduplicating. Say *"265k labelled wallets from the 822k-address Elliptic++ dataset"* — it is
both accurate and still impressive.

### 5. Don't say "100% recall on all scam families"

`recall_by_family` shows `llm_investment` at **0.50** and `uci_sms_spam` at **0.94**. The 69% → 100%
self-improvement figure is real; a blanket all-families claim is not.

### 6. Hardcoded URL will break a deployed B2B demo

`backend/institution.py` pins `COUNTERFEIT_VISION` to `http://127.0.0.1:8002` while the rest of `api.py`
reads `COUNTERFEIT_URL` from the environment. Fine locally; broken the moment the demo runs off one
machine.

---

*Every metric on this page was read from the persisted training and evaluation reports in the repo —
`fraud-shield-nlp/models/`, `counterfeit-vision/models/`, and `fraud-graph-ml/models/` — rather than from
prose documentation, for the same reason the Model Card endpoint reads them rather than recomputing: the
artifact is the source of truth.*
