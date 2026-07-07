# 🖥️ Command-Centre Dashboard (Next.js 15)

The police/analyst-facing dashboard — full-bleed dark crime map with floating glass panels
(styled after the team's reference design).

## Stack
Next.js 15 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · MapLibre GL JS
(keyless CARTO dark + Esri satellite tiles — no map token needed, ever).

## Run

```bash
# 1. backend (Python, :8000) — from command-centre/backend
uvicorn aegis_command.api:app --port 8000
# 2. gateway (Express, :4000) — from command-centre/gateway
npm run dev
# 3. dashboard (:3000) — from this folder
npm install
npm run dev
```

Open http://localhost:3000. The backend seeds itself from `contracts/samples/`, so the
dashboard is never empty even with zero real modules running.

## What's on screen

| Region | Panel |
|---|---|
| Top | Nav pills, search, backend-connectivity dot, alert bell |
| Left | Signal counts · module online/offline · signal-confidence sparkline · latest scam-call + note-scan cards · fraud-ring risk bars |
| Centre | MapLibre crime map — pulsing signal dots (red scam / amber counterfeit / violet ring), DBSCAN hub circles, red **COORDINATED HUB** rings for cross-domain clusters, dark/satellite toggle |
| Right | Warning feed — fusion verdict, coordinated hubs (click ⇒ fly-to), recent detections |
| Bottom | **Run Fusion** panel (typewriter reveal of the Gen AI summary + audit hash) · live signal-volume bars |

## Config
`NEXT_PUBLIC_API_BASE` — gateway base URL, defaults to `http://127.0.0.1:4000`
(see `.env.example`).

## Where the data comes from
Polls the Express gateway: `/api/events` (5s), `/api/health` (10s), `/api/hotspots` (8s);
`POST /api/fuse` triggers the existing Python Gen AI fusion layer (this app only *renders*
its output — the fusion logic lives in `command-centre/fusion/`).
