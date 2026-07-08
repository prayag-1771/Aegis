/**
 * Aegis API Gateway (Express 5) — the single public entry point.
 *
 * Ingest (called by the two citizen-facing websites):
 *   POST /api/alert/scam           Sudarsan's alert website  -> scam_detection JSON
 *   POST /api/report/counterfeit   Adharshan's currency site -> counterfeit JSON
 *
 * Live-demo analyze (text/image -> module -> auto-ingest, for the dashboard):
 *   POST /api/analyze/scam         { text, source?, location_hint? }
 *   POST /api/analyze/counterfeit  { image_b64, location_hint? }
 *
 * Dashboard reads (proxied to the FastAPI command backend, :8000):
 *   GET  /api/health | /api/events | /api/hotspots | /api/fusion/latest
 *   POST /api/fuse   | /api/refresh/fraud-graph
 *
 * The Gen AI fusion + geospatial clustering live in the Python backend and are
 * NOT reimplemented here — this layer only validates, forwards, and shields
 * internal services from the public internet.
 */

import express from "express";
import cors from "cors";

const PORT = process.env.PORT ?? 4000;
const COMMAND_API = process.env.COMMAND_API ?? "http://127.0.0.1:8000";

// Allowed browser origins. Defaults to the local dashboard + citizen sites;
// override with a comma-separated ALLOWED_ORIGINS when deployed. Set it to "*"
// only if you intend the gateway to be openly callable (there is no auth yet).
const ALLOWED_ORIGINS = (
  process.env.ALLOWED_ORIGINS ??
  "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
)
  .split(",")
  .map((o) => o.trim());

const app = express();
app.use(
  cors({
    origin: ALLOWED_ORIGINS.includes("*") ? true : ALLOWED_ORIGINS,
  })
);
app.use(express.json({ limit: "5mb" }));

/** Forward a request to the FastAPI command backend and relay its response. */
async function forward(res, path, { method = "GET", body } = {}) {
  try {
    const r = await fetch(`${COMMAND_API}${path}`, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = await r.json().catch(() => ({}));
    res.status(r.status).json(payload);
  } catch {
    res.status(502).json({ error: `command backend unreachable at ${COMMAND_API}` });
  }
}

app.get("/api/gateway/health", (_req, res) =>
  res.json({ status: "ok", service: "aegis-gateway", upstream: COMMAND_API })
);

// ---- ingest from the citizen websites ----
app.post("/api/alert/scam", (req, res) => {
  const e = req.body ?? {};
  if (!e.event_id || !e.verdict)
    return res.status(422).json({ error: "not a valid scam_detection payload (see contracts/)" });
  forward(res, "/ingest/scam", { method: "POST", body: e });
});

app.post("/api/report/counterfeit", (req, res) => {
  const e = req.body ?? {};
  if (!e.event_id || !e.verdict)
    return res.status(422).json({ error: "not a valid counterfeit payload (see contracts/)" });
  forward(res, "/ingest/counterfeit", { method: "POST", body: e });
});

// ---- live analysis (wow moments 1 & 2): backend proxies to Fraud Shield / Counterfeit Vision ----
// (body validation happens at the backend /analyze/* handlers)
app.post("/api/analyze/scam", (req, res) =>
  forward(res, "/analyze/scam", { method: "POST", body: req.body ?? {} })
);
app.post("/api/analyze/counterfeit", (req, res) =>
  forward(res, "/analyze/counterfeit", { method: "POST", body: req.body ?? {} })
);

// ---- dashboard reads / actions ----
app.get("/api/health", (_req, res) => forward(res, "/health"));
app.get("/api/events", (_req, res) => forward(res, "/events"));
app.get("/api/hotspots", (_req, res) => forward(res, "/hotspots"));
app.get("/api/fusion/latest", (_req, res) => forward(res, "/fusion/latest"));
app.post("/api/fuse", (_req, res) => forward(res, "/fuse", { method: "POST" }));
app.post("/api/refresh/fraud-graph", (_req, res) =>
  forward(res, "/refresh/fraud-graph", { method: "POST" })
);

app.listen(PORT, () => {
  console.log(`aegis-gateway listening on :${PORT} -> ${COMMAND_API}`);
});
