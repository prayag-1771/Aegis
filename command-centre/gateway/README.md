# 🚪 Aegis API Gateway (Express 5)

The single public entry point of the 3-website setup. The two citizen websites POST here;
the dashboard reads through here. Internal Python services are never exposed directly.

## Run

```bash
npm install
npm run dev        # :4000, forwards to the FastAPI backend on :8000
```

`COMMAND_API` env var overrides the backend URL (default `http://127.0.0.1:8000`).

## Endpoints

| Method & path | Caller | Purpose |
|---|---|---|
| `POST /api/alert/scam` | Sudarsan's alert site | ingest `scam_detection` JSON |
| `POST /api/report/counterfeit` | Adharshan's currency site | ingest `counterfeit` JSON |
| `GET /api/events` | dashboard | everything renderable (cards, rings, last fusion) |
| `GET /api/hotspots` | dashboard | DBSCAN hubs + map points |
| `GET /api/health` | dashboard | backend + module liveness |
| `POST /api/fuse` | dashboard | trigger the Gen AI fusion moment |
| `GET /api/fusion/latest` | dashboard | last fusion package |
| `POST /api/refresh/fraud-graph` | dashboard/ops | pull latest rings from :8003 |
| `GET /api/gateway/health` | ops | gateway's own liveness |

Payloads must match [`contracts/`](../../contracts/) — the gateway does a cheap shape check
(`event_id` + `verdict`) and the backend/fusion layer does full schema validation.
