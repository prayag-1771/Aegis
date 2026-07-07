# 🗺️ Map API / tile-provider comparison (July 2026)

> Research for the team's map decision. TL;DR — **we use MapLibre GL JS (free, open-source
> renderer) + keyless free tiles (CARTO dark + Esri imagery)**: ₹0, no signup, no token to
> leak on stage.

## Completely free (no API key)

| Provider | What you get | Limits / notes |
|---|---|---|
| **OpenFreeMap** | Full vector tiles (OSM), self-hostable | Genuinely unlimited & keyless; styles are limited |
| **CARTO basemaps** | Raster `dark_all` / `light_all` — the classic dashboard look | Free with attribution for non-heavy use ← **our dark layer** |
| **Esri World Imagery** | Satellite raster tiles | Free with attribution for dev/demo ← **our satellite toggle** |
| **OpenStreetMap.org tiles** | Standard OSM raster | Fair-use only; not for production traffic |
| **MapLibre GL JS / Leaflet** | The rendering libraries themselves | Fully open-source (Mapbox-GL fork / classic raster lib) |

## Free tier with a key (upgrade path if we need nicer styles)

| Provider | Free tier | Cheapest paid |
|---|---|---|
| **MapTiler** | 100k tile loads/mo | ~$25/mo — best styles for the money |
| **Stadia Maps** | 200k credits/mo (non-commercial) | ~$20/mo — cheapest paid entry |
| **Geoapify** | 3k credits/day | ~$49/mo |
| **LocationIQ** | 5k requests/day | ~$49/mo |
| **Mapbox** | 50k map loads/mo | Pay-as-you-go after; beautiful but priciest mid-tier |
| **HERE** | generous transaction quota | enterprise-oriented pricing |
| **Google Maps Platform** | monthly free credit only | most expensive per load — skip for this project |

## Recommendation

1. **Demo & hackathon:** MapLibre + CARTO dark + Esri satellite (current setup) — zero cost,
   zero keys, zero rate-limit risk on stage.
2. **If judges ask about scale:** swap the style URL to MapTiler ($25/mo) — one-line change,
   MapLibre stays.
3. Avoid Google Maps: highest per-load cost and requires billing setup from day one.
