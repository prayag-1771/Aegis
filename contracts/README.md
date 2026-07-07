# 📜 Aegis Data Contracts

**This folder is the single most important thing in the repo.** It defines the exact JSON
that the three detection modules hand to the command centre. Lock it in the **Day 1–2 Data
Contract Meeting** and treat every change afterward as a team decision — because a change here
can break someone else's integration.

## Why this exists

Fraud Shield, Counterfeit Vision, and Fraud Graph build **independently** and never import each
other's code. They only produce JSON that matches these schemas. The command centre consumes
that JSON. As long as everyone honors the contract, four people can work in parallel with
**zero git conflicts** and integration "just works" at the end.

## The contracts

| Module (lead) | Schema | Sample | Consumed by |
|---|---|---|---|
| **Fraud Shield** — NLP (Sudarsan) | [`scam_detection.schema.json`](scam_detection.schema.json) | [`samples/scam_detection.sample.json`](samples/scam_detection.sample.json) | Command Centre |
| **Counterfeit Vision** — CV (Adharshan) | [`counterfeit.schema.json`](counterfeit.schema.json) | [`samples/counterfeit.sample.json`](samples/counterfeit.sample.json) | Command Centre |
| **Fraud Graph** — Graph ML (Prayag) | [`fraud_graph.schema.json`](fraud_graph.schema.json) | [`samples/fraud_graph.sample.json`](samples/fraud_graph.sample.json) | Command Centre |
| **Command Centre** — Fusion (Pushkar/Prayag) | [`fusion_output.schema.json`](fusion_output.schema.json) | — | UI / demo |

## Rules

1. **Code against the sample files.** The command centre builds the whole dashboard using the
   `samples/` payloads as dummy data — no need to wait for the real models.
2. **`schema_version` is mandatory.** It's `"1.0"` everywhere for now. Bump it only if the
   whole team agrees to a breaking change.
3. **`location_hint` / `district` fields power the cross-domain crime map.** Fill them when
   you can — even mocked — because the geospatial overlap is a headline innovation.
4. **Don't add fields silently.** `additionalProperties` is `false`. If you need a new field,
   raise it, add it to the schema, and tell the command-centre lead.
5. **Validate before you hand off.** A tiny validator lives in [`../shared/`](../shared/).

## Changing a contract

Propose in the group chat → update the `.schema.json` **and** its sample → ping the command-centre
lead → note it in [`../PROJECT_PLAN.md`](../PROJECT_PLAN.md) changelog. Never change a schema quietly.
