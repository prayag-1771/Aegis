# Aegis Command Centre — Dashboard (Next.js)

The single screen a police officer watches: three signal cards (scam / counterfeit /
fraud rings), module health pills, the cross-domain crime map (Leaflet, no token needed),
and the **RUN FUSION** panel that reveals the Gen AI intelligence summary.

## Run it

```bash
npm install
npm run dev          # http://localhost:3000
```

The dashboard talks **only** to the command-centre backend (default
`http://127.0.0.1:8000`; override with `NEXT_PUBLIC_COMMAND_API`). Start the backend
first — and any detection services you want live:

| Service | Port | Start |
|---|---|---|
| backend (required) | 8000 | `uvicorn aegis_command.api:app --app-dir src --port 8000` (from `../backend`) |
| fraud-shield | 8001 | see `fraud-shield-nlp/README.md` |
| counterfeit-vision | 8002 | see `counterfeit-vision/README.md` |
| fraud-graph | 8003 | see `fraud-graph-ml/README.md` |

Without the detection services the dashboard still renders from the backend's seeded
contract samples — it is never blocked on other modules.

## Structure
- `app/page.tsx` — the dashboard (cards, health, fusion panel); polls `/events` + `/hotspots` every 5 s
- `app/components/CrimeMap.tsx` — Leaflet map; pulsing markers for cross-domain hubs
- `lib/api.ts` — typed backend client (`api.events()`, `api.fuse()`, `api.analyzeScam()`, …)

## Stack
Next.js 16 · React 19 · Tailwind 4 · Leaflet (OpenStreetMap tiles — no API key)
