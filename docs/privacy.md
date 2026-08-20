# Aegis — Privacy & Data-Exposure Audit

**Scope:** every module — `fraud-shield-nlp`, `counterfeit-vision`, `fraud-graph-ml`,
`command-centre/{backend,fusion,gateway,supply_trail,frontend}`.
**Method:** static trace of every outbound call, every persisted field, and every field
that crosses a contract boundary. Each finding cites the file and line it was read from.
Findings marked **verified clean** were checked and found *not* to leak.

**Why this document exists.** Aegis is pitched to government. The question "does this
take citizens' private data?" is not a footnote for that audience — under the DPDP Act
the answer determines whether the system is deployable at all. This file is the honest
answer, written before anyone asks.

---

## Severity summary

| ID | Exposure | Severity | Status |
|---|---|---|---|
| [P1](#p1) | No authentication on any endpoint; stored messages publicly readable | 🔴 Critical | ✅ **Fixed** |
| [P2](#p2) | Phone numbers sent to third-party LLMs in the case-file dossier | 🔴 Critical | ✅ **Fixed** |
| [P3](#p3) | Full message text sent to Anthropic by the verification agent | 🔴 High | ✅ **Fixed** |
| [P4](#p4) | Full message text sent to Sarvam AI for translation | 🔴 High  | — |
| [P5](#p5) | Scanned note images served publicly with no auth | 🔴 High | 🟡 Partial |
| [P6](#p6) | Message text stored server-side and shown on the dashboard | 🔴 High | 🟡 Partial |
| [P7](#p7) | Live-call audio streamed to Google by the browser | 🔴 High  | — |
| [P8](#p8) | GPS coordinates travel and persist with every scan | 🟠 Medium-High  | — |
| [P9](#p9) | WhatsApp message body + sender number transit Twilio | 🟠 Medium-High  | — |
| [P10](#p10) | Every place search is sent to OpenStreetMap (Nominatim) | 🟠 Medium  | — |
| [P11](#p11) | Map tiles leak the investigation viewport to three foreign CDNs | 🟠 Medium  | — |
| [P12](#p12) | FIR case references sent to third-party LLMs | 🟠 Medium  | — |
| [P13](#p13) | Backend fetches attacker-controlled URLs (IP disclosure + SSRF) | 🟠 Medium  | — |
| [P14](#p14) | IFSC codes sent to Razorpay | 🟡 Low  | — |
| [P15](#p15) | Message text transits the Express gateway | 🟡 Low  | — |

---

## 🔴 Critical

### P1 — No authentication on any endpoint {#p1}

**What.** No inbound authentication exists anywhere in the codebase. A repo-wide search for
`Depends(`, `HTTPBasic`, `jwt`, or `Authorization` handling on inbound requests returns
nothing — every match was an *outbound* provider API key. `GET /events`
([api.py:387](../command-centre/backend/src/aegis_command/api.py#L387)) returns stored scam
events, and those events carry `raw_text`. The services are on public Render URLs.

**Why it matters.** Anyone who knows the URL can read every citizen message the system has
processed. This is the finding that turns all the others from "data-sharing design choices"
into "a public disclosure". It also makes the store writable: `POST /ingest/scam` accepts
unauthenticated events, so anyone can poison the crime map.

*Not confirmed live only because the deployed backend is currently down (free-tier quota
exhausted); the code path is unambiguous.*

**Solution.**
1. Add a shared-secret header check as FastAPI dependency on every non-public route
   (`/events`, `/ingest/*`, `/intel/*`, `/case-file`). One `Depends(require_key)` function,
   applied at the router level so new endpoints inherit it.
2. Keep only the citizen-facing demo UIs and `/health` unauthenticated.
3. Rotate the key via env var; never commit it.
4. Combine with **P6** — once `raw_text` is no longer stored, a leak of `/events` is
   materially less damaging. Defence in depth: do both.

**Status: fixed.** Reads feed a PUBLIC dashboard and a browser cannot hold a secret, so reads
are protected by not returning private content rather than by a key: `_public_scam()` strips
`raw_text`, pseudonymises `phone_number` and redacts `explanation`. Writes are now guarded —
`/ingest/*`, `/demo/reset`, `/demo/inject-ring` and `/refresh/fraud-graph` require
`X-Aegis-Key`. Enforcement is opt-in (`AEGIS_API_KEY`) so a live demo cannot be broken by a
missing env var, and `/health` reports `write_auth: enforced|disabled` rather than implying a
protection that is not active. Verified: without a key ingest returns 200 and the demo path is
untouched; with a key, no/wrong key gives 401 and the correct key 200, while `/events` and
`/hotspots` stay 200.

---

### P2 — Phone numbers sent to third-party LLMs {#p2}

**What.** The case-file dossier includes the real phone number of every linked scam:
`{"ref": …, "phone": s.get("phone_number"), …}`
([case_officer.py:87](../command-centre/backend/src/aegis_command/case_officer.py#L87)).
That dossier is serialised and sent to Claude, Groq, or Gemini
([case_officer.py:205–242](../command-centre/backend/src/aegis_command/case_officer.py#L205)).

**Why it matters.** This is not message content — it is a **direct personal identifier** of
victims and suspects, leaving Indian jurisdiction to a US processor. Under DPDP this is the
hardest exposure to defend, and it is invisible to a reader of the UI.

**Solution.** The LLM never needs the digits. It needs to know a callback number *exists* so
it can recommend pulling CDRs. Replace with a salted hash plus a count:
`{"phone_ref": "ph_" + hmac(salt, number)[:8], "has_callback": true}`. The narrative is
unchanged; the investigator de-references the hash locally.

**Status: fixed.** Redaction lives in `intel.py` at the source, not at each consumer, so a new
caller cannot reintroduce the leak by forgetting to sanitise. `phone_ref()` is a keyed BLAKE2b
pseudonym — stable, so campaign clustering still links reports sharing a caller, and not
reversible without `AEGIS_PII_SALT`. `redact()` masks digit runs, emails, links and UPI handles
inside excerpts while keeping the scam wording. This covered a second leak path found during
the fix: campaign objects carried both a phone list and a 180-character message excerpt, and
those are embedded whole into the dossier *and* served by the unauthenticated
`/intel/campaigns`. Verified: the dossier and `/events` contain no phone digits, no UPI handle
and no `raw_text`. The dashboard renders `len(phone_numbers)` and `sample_text` only, so both
still work.

---

## 🔴 High

### P3 — Full message text sent to Anthropic {#p3}

**What.** The agentic verifier sends the citizen's message verbatim:
`payload = {"message": text, …}`
([verify/agent.py:95](../fraud-shield-nlp/src/aegis_fraud_shield/verify/agent.py#L95)).

**Why it matters.** Scam messages frequently quote the victim's name, bank, account tail, or
case number. All of it leaves the country.

**Solution.** The verifier's job is to explain *tool results* (a resolved shortlink, a
mismatched IFSC), not to read the message. Send only the extracted entities and the
deterministic verdict — never `text`. If a short quote genuinely helps the narrative, send a
redacted span with digits and names masked. The tool layer already extracts these entities,
so the change is to the payload only.

**Status: fixed.** The payload now carries `message_excerpt_redacted` (links, emails, UPI
handles and digit runs masked, capped at 200 characters) instead of `message`, so the model can
still judge tone without receiving the citizen's content.

### P4 — Full message text sent to Sarvam AI {#p4}

**What.** Translation posts the message body to `api.sarvam.ai/translate`
([multilingual.py](../command-centre/backend/src/aegis_command/multilingual.py)).

**Why it matters.** Every non-English message — precisely the citizens least able to assess
the risk — is sent to a third-party processor before it is ever classified.

**Solution — remove the need for runtime translation entirely.** The classifier already uses
`char_wb` 3–5-gram features
([model.py:76](../fraud-shield-nlp/src/aegis_fraud_shield/model.py#L76)), and character
n-grams are **script-agnostic**: they work on Devanagari, Tamil and Bengali exactly as on
Latin. Translate the *training corpus* once, offline (your own synthetic + public SMS data —
no citizen data involved), retrain, and the model detects natively in every language with
**zero runtime translation**. This removes the leak, removes the latency, and removes the
Sarvam dependency in one move. See [Edge plan](#edge).

### P5 — Scanned note images served publicly {#p5}

**What.** `app.mount("/captures", StaticFiles(directory=CAPTURES_DIR))`
([counterfeit api.py:55](../counterfeit-vision/src/aegis_counterfeit/api.py#L55)) with
`save_capture=True` on every scan. No authentication. Retention is a 200-file ring buffer
(`max_captures`, [config.py:64](../counterfeit-vision/src/aegis_counterfeit/config.py#L64)).

**Why it matters.** These are photographs taken by citizens and officers. They contain note
serial numbers and whatever the camera caught around the note — desks, documents, hands.
Filenames are guessable UUID stems returned in API responses, and the directory is world
-readable.

**Correction — EXIF is already stripped.** An earlier draft of this document recommended
stripping EXIF. That was wrong: PIL's `convert("RGB")` followed by `save()` drops the EXIF
block, verified empirically (a JPEG carrying Make/Model tags comes back with an empty EXIF
dict). Citizen photos therefore carry **no GPS or device identifiers**. Filenames also hold
48 bits of UUID, so they are not enumerable — the real exposure is limited to someone who
already holds a returned URL.

**Status: partially fixed.** `COUNTERFEIT_SAVE_CAPTURES=0` now disables persistence entirely
([api.py](../counterfeit-vision/src/aegis_counterfeit/api.py)). The scan UI degrades
gracefully — it falls back to the browser's own copy of the upload
(`r.image_ref || uploadDataUrl`), so only the server-rendered heatmap overlay is lost.
Default remains on because the demo shows that overlay.

**Remaining work.**
1. Serve captures through an authenticated route rather than a static mount.
2. Add a TTL so images are deleted after the alert's lifetime, not merely evicted once 200
   newer scans arrive.
3. If the demo needs a visible image, store a **downscaled crop of the note only**.

### P6 — Message text stored and displayed {#p6}

**What.** `raw_text` is written into every payload
([analyze.py:118](../fraud-shield-nlp/src/aegis_fraud_shield/analyze.py#L118)), ingested to
the command centre, held in a 500-item in-memory deque
([store.py:20](../command-centre/backend/src/aegis_command/store.py#L20)), and surfaced on
the dashboard as `sample_text`
([intel.py:272](../command-centre/backend/src/aegis_command/intel.py#L272)).

**Why it matters.** Operators see citizens' actual messages. Combined with **P1** so does
everyone else.

**Solution — metadata-only ingestion.** The crime map, fraud rings, hotspots and campaign
clustering need `verdict`, `scam_type`, `district`, `timestamp` and marker names. They do
**not** need the message. Drop `raw_text` at the ingest boundary. Campaign clustering
([intel.py:206–211](../command-centre/backend/src/aegis_command/intel.py#L206)) currently
tokenises `raw_text` — move that to the edge: the device computes the token/bigram
fingerprint locally and sends only the hashed shingles, which preserves clustering without
transmitting content.

### P7 — Live-call audio streamed to Google {#p7}

**What.** `window.SpeechRecognition || window.webkitSpeechRecognition`
([live-call.html:347](../fraud-shield-nlp/src/aegis_fraud_shield/ui/live-call.html#L347)).
In Chrome this API streams the microphone to Google's speech service.

**Why it matters.** This is the *voice* of a citizen mid-scam, plus the scammer's — the most
sensitive payload in the system, and it leaves before Aegis sees a single token.

**Solution.** Honest short term: disclose it in the UI ("speech recognition is provided by
your browser") and keep the scripted-replay demo as the default path. Real fix: on-device
STT via **Vosk** (~50 MB per language, WASM) or **whisper.cpp** WASM. Heavier and less
accurate for Indian languages, so treat it as a documented roadmap item rather than a claim.
**Do not claim the live-call feature is on-device until this ships.**

---

## 🟠 Medium

### P8 — GPS coordinates persist with every scan {#p8}

**What.** `location_hint: {district, lat, lon}` is part of both the scam and counterfeit
contracts and is stored with the event.

**Why it matters.** Precise coordinates are a personal identifier — they place a person at a
time. District-level is enough for every map, hotspot and corridor feature Aegis has.

**Solution.** Truncate at the edge: send `district` only, or round coordinates to ~2 decimals
(≈1 km) before they leave the device. Enforce it server-side too, so a malformed client
cannot re-introduce precision.

### P9 — WhatsApp body + sender via Twilio {#p9}

**What.** `/webhook/whatsapp` receives `Body` and `From` through Twilio
([api.py:213](../fraud-shield-nlp/src/aegis_fraud_shield/api.py#L213)).

**Why it matters.** Message and phone number transit a third-party processor.

**Solution.** Largely inherent to the WhatsApp transport — Meta and Twilio see the message
regardless. What you control: do not *persist* the sender number (see **P2**/**P6**), and
document the transport boundary honestly. Signature validation is already implemented
correctly ([api.py:197](../fraud-shield-nlp/src/aegis_fraud_shield/api.py#L197)) — keep
`TWILIO_AUTH_TOKEN` always set, since validation is skipped when it is empty.

### P10 — Place searches sent to OpenStreetMap {#p10}

**What.** Every search hits
`nominatim.openstreetmap.org/search?...&q=<query>`
([page.tsx:192](../command-centre/frontend/app/page.tsx#L192)).

**Why it matters.** This is not citizen data — it is **operational intelligence**. A
sustained pattern of searches tells a third party which districts Indian police are
investigating, and when interest spikes.

**Solution.** You already ship `DEMO_DISTRICT_COORDS` and a fuzzy resolver, so most searches
never need a network call. Resolve locally first and only fall back to Nominatim for genuine
misses — or drop the fallback entirely and ship a fuller district table (India has ~800
districts; that is a small JSON asset). Self-hosting Nominatim is the complete fix.

### P11 — Map tiles leak the viewport {#p11}

**What.** Tiles are fetched from `basemaps.cartocdn.com`, `tile.openstreetmap.org` and
`server.arcgisonline.com`.

**Why it matters.** Same class as P10: every pan and zoom tells three foreign CDNs which
area is being examined, at what magnification, from which IP.

**Solution.** Self-host a tile set for India (a country-level vector extract is a few GB and
serves from your own infrastructure), or use an offline `pmtiles`/`mbtiles` asset. For a
demo, the honest interim step is documenting it. For a government deployment this is a
requirement, not a nice-to-have.

### P12 — FIR references sent to LLMs {#p12}

**What.** `"firs_on_route": r.get("passes_fir", [])`
([narrate.py:84](../command-centre/supply_trail/src/aegis_supply_trail/narrate.py#L84)) is
serialised into the facts block sent to the narrator.

**Why it matters.** FIR numbers are real case identifiers linking to named individuals.

**Solution.** Replace with opaque per-session labels (`case A`, `case B`) and map back
locally when rendering. The narrative quality is unaffected — the model only needs to refer
to *a* case consistently.

### P13 — Backend fetches attacker-controlled URLs {#p13}

**What.** `resolve_url()` follows the scammer's shortlink from your server
([verify/tools.py:161](../fraud-shield-nlp/src/aegis_fraud_shield/verify/tools.py#L161)).

**Why it matters.** Two problems. It tells the attacker your server's IP and that their link
is under analysis — letting them cloak the payload. And it is an SSRF surface: a crafted URL
can probe internal addresses.

**Solution.** Block private/loopback/link-local address ranges before every request
*including after each redirect hop* (redirect-based SSRF is the usual bypass). Cap redirects
and body size — both already implemented. Route egress through a proxy so the origin IP is
not yours. Consider deferring resolution to an explicit investigator action rather than
running it automatically on every flagged message.

---

## 🟡 Low

### P14 — IFSC codes sent to Razorpay {#p14}

`https://ifsc.razorpay.com/{ifsc}` ([verify/tools.py:223](../fraud-shield-nlp/src/aegis_fraud_shield/verify/tools.py#L223)).
An IFSC is a public bank-branch code, not personal data; the leak is the *pattern* of which
branches are being checked. **Solution:** ship the IFSC prefix table locally (it is public and
small) and keep the network call only for branch-level detail — the offline fallback already
exists.

### P15 — Message text transits the gateway {#p15}

The Express gateway forwards request bodies verbatim
([server.js:91](../command-centre/gateway/src/server.js#L91)). No body logging was found —
**verified clean** on that point. **Solution:** keep it that way; add an explicit "never log
request bodies" comment so a future debugging session does not introduce it.

---

## ✅ Verified clean

These were checked and do **not** leak — worth stating, because they are the parts a reviewer
would most expect to be sloppy:

- **Fusion narrator** — the facts block carries counts, districts and threat levels. No
  `raw_text`, no phone numbers ([narrator.py](../command-centre/fusion/src/aegis_fusion/narrator.py)).
- **Dashboard summaries** (Groq/Gemini) — aggregates only.
- **Frontend localStorage** — a single UI flag, `aegis_has_searched`.
- **Fraud-graph account IDs** — synthetic data throughout.
- **Twilio signature validation** — correctly implemented, including tunnel-forwarding headers.
- **Ghost Ring** — already the strongest privacy story in the codebase: per-bank salted-hash
  pseudonyms and (ε=1.0, δ=1e-5) differential privacy on published embeddings, at **zero**
  measured accuracy cost.

---

## <a id="edge"></a>The edge-AI plan

The core detector moves to the device almost for free, and doing so removes P3, P4, P6 and
most of P8 at once.

**Measured feasibility.** The classifier is TF-IDF + LogisticRegression: 80,011 coefficients,
exporting to **1.12 MB raw / ~390 KB gzipped**. Scoring is one sparse dot product plus a
sigmoid — microseconds.

**There is no performance cost. It is a performance *gain*:** on-device scoring deletes a
network round-trip *and* Render's 50–90 s cold start. The regex markers and playbooks are
pure string operations and port directly.

**Multilingual comes free with it.** Because `char_wb` n-grams are script-agnostic,
retraining on a corpus translated **once, offline** yields native detection in all 22
scheduled languages with no runtime translation and no per-message network call.

**What genuinely cannot move to the edge:** speech-to-text (P7), live entity verification
(P13 — checking whether a link is a phishing page requires reaching out), and the national
aggregation that makes Aegis more than a phone app. That last one is a *feature*: the fix is
to send anonymised metadata, not to abandon the command centre.

---

## Recommended order

| Phase | Work | Fixes | Effort |
|---|---|---|---|
| **0** | Hash phone numbers in the case-file dossier | P2 | ~5 lines |
| **1** | Shared-secret auth on non-public endpoints | P1 | Small |
| **2** | Stop sending message text to the verifier; entities only | P3 | Small |
| **3** | Edge classifier (export + JS/WASM scorer) | P3, P6 | Medium |
| **4** | Metadata-only ingestion (drop `raw_text`, round GPS) | P6, P8 | Medium |
| **5** | Authenticated + ephemeral captures, EXIF strip | P5 | Small |
| **6** | Retrain multilingual; delete the translation hop | P4 | Medium |
| **7** | Local geocoding; self-hosted tiles | P10, P11 | Medium |
| **8** | SSRF hardening on redirects; opaque FIR labels | P12, P13 | Small |

Phases **0–2** are a single afternoon and remove the two critical findings and the worst
content leak. Phases **3–4** together earn the claim that matters:

> *The citizen's message never leaves their device. Only anonymised threat metadata reaches
> the government.*

---

## Additional recommendations

1. **Add a `PRIVACY.md` claim table to the UI.** A judge asking "is this private?" should be
   able to read the answer off the dashboard, the way the Research Lab already shows its own
   caveats. Aegis's credibility comes from stating limits, not hiding them.
2. **Data-retention policy.** The event store is a 500-item deque with no TTL, so a message
   can sit in memory indefinitely on a quiet day. Add an age-based eviction (e.g. 24 h)
   alongside the count cap.
3. **Rotate every exposed key.** `SARVAM_API_KEY`, the Groq keys, and the Atlas credentials
   have all appeared in chat/logs during development. Rotate before any public demo.
4. **Cross-border processing register.** For a government pitch, list which providers see
   what: Anthropic (US), Groq (US), Google (US), Sarvam (India), Twilio (US), Razorpay (India).
   The Indian-jurisdiction ones are a genuine advantage — say so explicitly.
5. **Prefer a sovereign deployment over pure edge for the backend.** Edge fixes the citizen's
   message; it does not fix where the *command centre* runs. On-prem or MeghRaj GovCloud
   keeps the aggregate inside government control, which is what DPDP actually cares about.
6. **Threat-model the operator, not just the citizen.** P10 and P11 are the reminder that an
   investigation leaks even when citizen data does not.
7. **Do not overclaim in the pitch.** Until the edge classifier ships, the accurate line is
   *"privacy-preserving by design, with a documented path to on-device scoring"* — not
   *"runs on your phone"*. The Ghost Ring DP result is already a genuinely strong, defensible
   privacy claim; lead with the thing that is true.
