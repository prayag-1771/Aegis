"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { EntryRoute, Hub, MapPoint, SupplyTrail } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { Layers } from "./Icons";

/* Free, keyless tiles — the demo can never die on a missing token. The dark and
   satellite tiles live on third-party CDNs that some networks / ad-blockers block,
   so OSM is kept as a universal fallback (darkened via CSS when used). */
const DARK_TILES = ["a", "b", "c", "d"].map(
  (s) => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`
);
const SAT_TILES = [
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
];
const OSM_TILES = ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"];

/* one small tile per provider, used to detect if the CDN is reachable/allowed */
const CARTO_PROBE = "https://a.basemaps.cartocdn.com/dark_all/3/5/3@2x.png";
const ESRI_PROBE =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/3/3/5";

/** Load a single tile as an <img>; resolves false on block / error / timeout.
 *  Ad-blockers and firewalls fail this the same way they fail the map's tiles. */
function probeTile(url: string, timeout = 3500): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    let done = false;
    const finish = (ok: boolean) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(ok);
    };
    const timer = setTimeout(() => finish(false), timeout);
    img.onload = () => finish(true);
    img.onerror = () => finish(false);
    img.src = url;
  });
}

// Map's default centre: Jamtara town. 23.795 fell ~19 km south, on Maithon reservoir.
const JAMTARA: [number, number] = [86.804, 23.963];

/* Markers scale with zoom so each keeps a fixed ground footprint.
   Mercator pixels-per-meter double per zoom level, hence 2^(zoom - ref). */
const ZOOM_REF = 10.3; // initial zoom — markers render at their base size here (k = 1)
const SCALE_MIN = 0.3;
const SCALE_MAX = 4;

export default function CrimeMap({
  points,
  hubs,
  focus,
  trail,
  entryRoute,
  suppressTrailFit,
}: {
  points: MapPoint[];
  hubs: Hub[];
  focus: { lat: number; lon: number } | null;
  trail?: SupplyTrail | null;
  /** Highest-plausibility route by which notes could have entered the searched
   *  city. Drawn from the source press to the seizure district. */
  entryRoute?: EntryRoute | null;
  /** Draw the trail without framing it. Set on search, where the searched city
   *  owns the viewport and the corridor is only context. */
  suppressTrailFit?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const libRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const scalablesRef = useRef<HTMLElement[]>([]);
  const modeRef = useRef<"dark" | "sat">("dark");
  const blockedRef = useRef({ dark: false, sat: false });
  const trailAnimRef = useRef<number | null>(null);   // rAF handle for trail dash animation
  const trailMarkersRef = useRef<any[]>([]);          // DOM markers owned by the trail (arrows, labels)
  const entryAnimRef = useRef<number | null>(null);   // rAF handle for entry-route flow animation
  const entryTimerRef = useRef<any>(null);            // pending setTimeout in that loop — cancelAnimationFrame does NOT cover it
  const entryAliveRef = useRef(false);                // false once cleanup ran; stops any in-flight callback re-queuing
  const entryMarkersRef = useRef<any[]>([]);          // DOM markers owned by the entry route
  const [ready, setReady] = useState(false);
  const [satellite, setSatellite] = useState(false);
  /* Bumped every time a map instance finishes loading. Every effect that DRAWS
     on the map depends on this, not just on `ready`: if the map is ever torn
     down and rebuilt, `ready` is already true, so nothing would re-run and the
     layers would silently stay missing on the new instance while markers (which
     rebuild on each poll) reappear — exactly "the route disappeared". */
  const [mapVersion, setMapVersion] = useState(0);

  /* Diagnostic: this component has thrown "reading 'y' of null" from inside
     MapLibre three times, and each fix addressed a real leak that turned out not
     to be the cause. Log the real stack rather than keep guessing at it. */
  useEffect(() => {
    const onErr = (e: ErrorEvent) => {
      if (!/reading '[xy]'/.test(e.message || "")) return;
      // eslint-disable-next-line no-console
      console.error("[CrimeMap diagnostic] map-projection error\n", e.error?.stack || e.message);
    };
    window.addEventListener("error", onErr);
    return () => window.removeEventListener("error", onErr);
  }, []);

  /* Drive layer visibility + the darken filter from the current mode and which
     CDNs are blocked. Falls back to (darkened) OSM whenever the chosen provider
     is unreachable, so the map is always dark and never blank. */
  const applyBasemap = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer?.("dark")) return;
    const mode = modeRef.current;
    const blocked = blockedRef.current;
    const showDark = mode === "dark" && !blocked.dark;
    const showSat = mode === "sat" && !blocked.sat;
    const useOsm = !showDark && !showSat; // blocked provider → OSM fallback
    map.setLayoutProperty("dark", "visibility", showDark ? "visible" : "none");
    map.setLayoutProperty("sat", "visibility", showSat ? "visible" : "none");
    map.setLayoutProperty("osm", "visibility", useOsm ? "visible" : "none");
    // invert the tile canvas only when the light OSM tiles are the visible base
    container.current?.classList.toggle("osm-dark", useOsm);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const maplibregl = (await import("maplibre-gl")).default;
      if (cancelled || !container.current) return;
      const map = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {
            osm: { type: "raster", tiles: OSM_TILES, tileSize: 256, attribution: "© OpenStreetMap contributors" },
            sat: { type: "raster", tiles: SAT_TILES, tileSize: 256, attribution: "Imagery © Esri" },
            dark: { type: "raster", tiles: DARK_TILES, tileSize: 256, attribution: "© OpenStreetMap · © CARTO" },
          },
          layers: [
            { id: "osm", type: "raster", source: "osm", layout: { visibility: "none" } },
            { id: "sat", type: "raster", source: "sat", layout: { visibility: "none" } },
            { id: "dark", type: "raster", source: "dark" },
          ],
        },
        center: JAMTARA,
        zoom: 10.3,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      // Attribution bottom-right (under the zoom buttons) — bottom-LEFT collided
      // with the Satellite toggle + compass. It stays collapsed to just the ⓘ
      // via CSS in globals.css (the credits show on hover); doing it in JS was
      // unreliable because MapLibre re-opens the <details> after load.
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      libRef.current = maplibregl;
      mapRef.current = map;

      // runtime backup: if a dark/sat tile fails to load, fall back immediately
      map.on("error", (e: any) => {
        const sid = e?.sourceId;
        if (sid === "dark" && !blockedRef.current.dark) {
          blockedRef.current.dark = true;
          applyBasemap();
        } else if (sid === "sat" && !blockedRef.current.sat) {
          blockedRef.current.sat = true;
          applyBasemap();
        }
      });

      map.on("load", () => {
        if (cancelled) return;
        setReady(true);
        setMapVersion((v) => v + 1); // new instance → every draw effect must redraw
        // proactively detect blocked CARTO CDN so the first paint is already correct.
        // We bypass the ESRI probe as it can falsely fail via img tags.
        probeTile(CARTO_PROBE).then((darkOk) => {
          if (cancelled) return;
          blockedRef.current = { dark: !darkOk, sat: false };
          applyBasemap();
        });
      });
    })();
    return () => {
      cancelled = true;
      // React runs effect cleanups in DEFINITION order, and this effect is
      // first — so map.remove() would destroy the map before any of the marker
      // effects below get to detach theirs, leaving markers registered on a
      // dead map's move/render events. That is the "reading 'y' of null" throw.
      // Tear every marker down here, where the ordering is guaranteed, rather
      // than relying on cleanups that run too late.
      [entryAnimRef, trailAnimRef].forEach((r) => {
        if (r.current !== null) cancelAnimationFrame(r.current);
        r.current = null;
      });
      if (entryTimerRef.current !== null) clearTimeout(entryTimerRef.current);
      entryTimerRef.current = null;
      entryAliveRef.current = false;
      [markersRef, trailMarkersRef, entryMarkersRef].forEach((ref) => {
        ref.current.forEach((m: any) => {
          try {
            m.remove();
          } catch {
            /* already detached */
          }
        });
        ref.current = [];
      });
      scalablesRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [applyBasemap]);

  // basemap toggle → re-derive visibility through the fallback logic
  useEffect(() => {
    modeRef.current = satellite ? "sat" : "dark";
    if (ready) applyBasemap();
  }, [satellite, ready, applyBasemap]);

  // markers: hotspot hubs underneath, signal dots on top
  useEffect(() => {
    const map = mapRef.current;
    const lib = libRef.current;
    if (!map || !lib || !ready) return;

    markersRef.current.forEach((m) => {
      try {
        m.remove();
      } catch {
        /* belonged to a previous map instance */
      }
    });
    markersRef.current = [];
    scalablesRef.current = [];

    for (const h of hubs) {
      // wrap: MapLibre owns the wrap's transform for positioning; we scale `inner`.
      const wrap = document.createElement("div");
      const inner = document.createElement("div");
      // Only a TRULY coordinated hub (all 3 crime types) gets the red badge;
      // a 2-domain overlap is an honest "multi-signal" hub, not "coordinated".
      const coordinated = h.tier === "coordinated";
      inner.className = `hub ${coordinated ? "hub-cross" : ""}`;
      const size = Math.round(Math.min(150, 64 + h.intensity * 32));
      inner.style.width = inner.style.height = `${size}px`;
      if (h.tier) {
        const label = document.createElement("span");
        label.className = "hub-label";
        const kind = coordinated ? "COORDINATED HUB" : "MULTI-SIGNAL HUB";
        label.textContent = `${kind}${h.district ? ` · ${h.district.toUpperCase()}` : ""}`;
        inner.appendChild(label);
      }
      wrap.appendChild(inner);
      scalablesRef.current.push(inner);

      // click-through popover: this hub's coordinated signals
      const signalRows = (h.points ?? [])
        .slice(0, 6)
        .map(
          (p) =>
            `<div style="display:flex;justify-content:space-between;gap:10px;margin-top:3px">` +
            `<span>${titleCase(p.type)}${p.district ? ` · ${p.district}` : ""}</span>` +
            (p.weight != null
              ? `<span style="color:#a1a1aa">${(p.weight * 100).toFixed(0)}%</span>`
              : "") +
            `</div>`
        )
        .join("");
      const hubTitle = h.tier === "coordinated" ? "Coordinated hub" : h.tier === "multi_signal" ? "Multi-signal hub" : "Signal cluster";
      const hubPopup = new lib.Popup({ offset: 18, closeButton: true, maxWidth: "260px" }).setHTML(
        `<strong>${hubTitle}${h.district ? ` — ${h.district}` : ""}</strong>` +
          `<div style="margin-top:2px;color:#a1a1aa">${h.n_points} signals · ${h.domains
            .map(titleCase)
            .join(" + ")}</div>` +
          signalRows
      );
      markersRef.current.push(
        new lib.Marker({ element: wrap }).setLngLat([h.lon, h.lat]).setPopup(hubPopup).addTo(map)
      );
    }

    for (const p of points) {
      if (p.lat == null || p.lon == null) continue;
      const wrap = document.createElement("div");
      const inner = document.createElement("div");
      inner.className = `sig sig-${p.type}`;
      inner.innerHTML = `<span class="sig-ring"></span><span class="sig-core"></span>`;
      wrap.appendChild(inner);
      scalablesRef.current.push(inner);
      const popup = new lib.Popup({ offset: 14, closeButton: false }).setHTML(
        `<strong>${titleCase(p.type)}</strong><br/>${p.district ?? "unknown district"}` +
          (p.weight != null ? `<br/>confidence ${(p.weight * 100).toFixed(0)}%` : "")
      );
      markersRef.current.push(
        new lib.Marker({ element: wrap }).setLngLat([p.lon, p.lat]).setPopup(popup).addTo(map)
      );
    }

    // resize every marker so its ground footprint stays fixed across zoom
    const applyScale = () => {
      const k = Math.min(SCALE_MAX, Math.max(SCALE_MIN, Math.pow(2, map.getZoom() - ZOOM_REF)));
      for (const el of scalablesRef.current) el.style.transform = `scale(${k})`;
    };
    applyScale();
    map.on("zoom", applyScale);
    return () => {
      map.off("zoom", applyScale);
      // These markers were only ever removed at the TOP of the next run. On
      // unmount there is no next run, so every hub, dot and attached popup
      // stayed bound to a map being destroyed — MapLibre then projects them
      // against a dead transform and throws "reading 'y'" of null. This effect
      // rebuilds on every poll, so it was the most frequent source of the leak.
      markersRef.current.forEach((m) => {
        try {
          m.remove();
        } catch {
          /* map already gone — nothing to detach from */
        }
      });
      markersRef.current = [];
      scalablesRef.current = [];
    };
  }, [points, hubs, ready, mapVersion]);

  // fly to a located alert / fusion hotspot.
  // The searched city is what the user asked to see, so it owns the viewport.
  // Routes draw around it at whatever zoom this lands on — the corridor runs
  // off-screen by design; it is context, not the subject. The trail's own
  // fitBounds is gated by suppressTrailFit, which the caller keys off the
  // trail's ORIGIN rather than off a slower fetch, so it cannot fire late and
  // yank the camera back out mid-flight.
  useEffect(() => {
    if (!mapRef.current || !ready || !focus) return;
    mapRef.current.flyTo({ center: [focus.lon, focus.lat], zoom: 9.4, duration: 2000 });
  }, [focus, ready]);

  // ── Supply Trail rendering ──────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    // Cancel any running trail animation
    if (trailAnimRef.current !== null) {
      cancelAnimationFrame(trailAnimRef.current);
      trailAnimRef.current = null;
    }

    // Remove old trail layers / sources / DOM markers
    ["trail-corridor", "trail-glow", "trail-dashes", "trail-seizures", "trail-origin"].forEach((id) => {
      if (map.getLayer(id)) map.removeLayer(id);
    });
    ["trail-line-src", "trail-seizures-src", "trail-origin-src"].forEach((id) => {
      if (map.getSource(id)) map.removeSource(id);
    });
    trailMarkersRef.current.forEach((m) => {
      try {
        m.remove();
      } catch {
        /* belonged to a previous map instance */
      }
    });
    trailMarkersRef.current = [];

    if (!trail) return;

    // Build corridor LineString
    const lineCoords = trail.corridor.node_path.map((n) => [n.lon, n.lat]);
    map.addSource("trail-line-src", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: lineCoords },
      },
    });

    // 1 — glow (wide, very transparent orange)
    map.addLayer({
      id: "trail-glow",
      type: "line",
      source: "trail-line-src",
      paint: {
        "line-color": "#f97316",
        "line-width": 14,
        "line-opacity": 0.12,
        "line-blur": 6,
      },
    });

    // 2 — solid underline
    map.addLayer({
      id: "trail-corridor",
      type: "line",
      source: "trail-line-src",
      paint: {
        "line-color": "#f97316",
        "line-width": 2.5,
        "line-opacity": 0.55,
      },
    });

    // 3 — animated dashes on top
    map.addLayer({
      id: "trail-dashes",
      type: "line",
      source: "trail-line-src",
      paint: {
        "line-color": "#fb923c",
        "line-width": 2.5,
        "line-dasharray": [4, 4],
        "line-opacity": 0.9,
      },
    });

    // Dash march direction follows the PROVEN flow when timestamps gave us one
    // (temporal analysis) — otherwise default to node order. The animation
    // itself becomes truthful instead of decorative.
    const nodes = trail.corridor.node_path;
    const flowReverse = trail.flow != null && trail.flow.direction_toward === nodes[0]?.name;

    // The dash head is QUANTIZED to a fixed cycle of exact values. The old
    // version marched a continuous float (offset ± 0.15, mod 8, abs), so every
    // frame produced a dasharray MapLibre had never seen — and each distinct
    // dasharray becomes a new row in its fixed-size LineAtlas texture. ~60 new
    // rows/second filled the atlas within minutes; getDash then returns null
    // and the RENDERER crashes reading '.y' in setConstantDashPositions,
    // killing the whole frame — the WebGL routes vanish while DOM markers
    // survive. A fixed cycle computed from an integer index reuses the same
    // handful of atlas rows forever. (The entry-flow loop below was always
    // bounded — 8 literal patterns — which is why it never poisoned the atlas.)
    const TRAIL_DASH_STEPS = 24;
    let stepIdx = 0;
    const animateDashes = () => {
      // A queued frame can land after the map is removed (unmount, StrictMode
      // remount), so re-check the map is still alive — not just the layer.
      try {
        if (mapRef.current === map && map.getLayer("trail-dashes")) {
          stepIdx = (stepIdx + (flowReverse ? 1 : TRAIL_DASH_STEPS - 1)) % TRAIL_DASH_STEPS;
          map.setPaintProperty("trail-dashes", "line-dasharray", [
            (stepIdx / TRAIL_DASH_STEPS) * 4, // exact repeat every cycle — same atlas key
            4,
          ]);
        } else {
          return; // map gone — stop rather than re-queue
        }
      } catch {
        return;
      }
      trailAnimRef.current = requestAnimationFrame(animateDashes);
    };
    trailAnimRef.current = requestAnimationFrame(animateDashes);

    // 4 — Seizure points (red circles)
    map.addSource("trail-seizures-src", {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: trail.seizures.map((s) => ({
          type: "Feature",
          properties: { district: s.district, denomination: s.denomination },
          geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        })),
      },
    });
    map.addLayer({
      id: "trail-seizures",
      type: "circle",
      source: "trail-seizures-src",
      paint: {
        "circle-radius": 8,
        "circle-color": "#ef4444",
        "circle-opacity": 0.85,
        "circle-stroke-width": 2,
        "circle-stroke-color": "#fca5a5",
      },
    });

    // 5 — Inferred origin (glowing orange pin)
    map.addSource("trail-origin-src", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: { name: trail.inferred_origin.name },
        geometry: {
          type: "Point",
          coordinates: [trail.inferred_origin.lon, trail.inferred_origin.lat],
        },
      },
    });
    map.addLayer({
      id: "trail-origin",
      type: "circle",
      source: "trail-origin-src",
      paint: {
        "circle-radius": 14,
        "circle-color": "#f97316",
        "circle-opacity": 0.9,
        "circle-stroke-width": 3,
        "circle-stroke-color": "#fed7aa",
        "circle-blur": 0.3,
      },
    });

    // 6 — Origin label (the origin pin alone doesn't explain itself)
    const lib = libRef.current;
    {
      const el = document.createElement("div");
      el.className = "trail-tag trail-tag-origin";
      el.textContent = `LIKELY ORIGIN · ${trail.inferred_origin.name.toUpperCase()}`;
      trailMarkersRef.current.push(
        new lib.Marker({ element: el, anchor: "bottom", offset: [0, -16] })
          .setLngLat([trail.inferred_origin.lon, trail.inferred_origin.lat])
          .addTo(map)
      );
    }

    // 7 — Temporal flow: direction arrows + the next hub at risk with its ETA
    if (trail.flow) {
      const flow = trail.flow;
      // cumulative km along node_path (flat-earth is fine at arrow scale)
      const seg: number[] = [0];
      for (let i = 1; i < nodes.length; i++) {
        const dx = (nodes[i].lon - nodes[i - 1].lon) * Math.cos((nodes[i].lat * Math.PI) / 180);
        const dy = nodes[i].lat - nodes[i - 1].lat;
        seg.push(seg[i - 1] + Math.hypot(dx, dy));
      }
      const total = seg[seg.length - 1];
      // three arrows at 30/50/70% along the corridor, rotated to flow direction
      for (const frac of [0.3, 0.5, 0.7]) {
        const target = total * frac;
        let i = seg.findIndex((s) => s >= target);
        if (i <= 0) i = 1;
        const t = (target - seg[i - 1]) / (seg[i] - seg[i - 1] || 1);
        const lat = nodes[i - 1].lat + t * (nodes[i].lat - nodes[i - 1].lat);
        const lon = nodes[i - 1].lon + t * (nodes[i].lon - nodes[i - 1].lon);
        let dx = (nodes[i].lon - nodes[i - 1].lon) * Math.cos((lat * Math.PI) / 180);
        let dy = nodes[i].lat - nodes[i - 1].lat;
        if (flowReverse) { dx = -dx; dy = -dy; }
        const deg = (Math.atan2(-dy, dx) * 180) / Math.PI; // CSS angle, screen y down
        const el = document.createElement("div");
        el.className = "trail-flow-arrow";
        el.style.transform = `rotate(${deg}deg)`;
        el.textContent = "➤";
        el.title = `Flow: toward ${flow.direction_toward} at ~${flow.speed_km_per_day} km/day (R²=${flow.consistency})`;
        trailMarkersRef.current.push(
          new lib.Marker({ element: el }).setLngLat([lon, lat]).addTo(map)
        );
      }
      // next hub at risk — pulsing warning ring + ETA tag
      const nxt = flow.next_hub_at_risk;
      if (nxt) {
        const ring = document.createElement("div");
        ring.className = "trail-next-hub";
        trailMarkersRef.current.push(
          new lib.Marker({ element: ring }).setLngLat([nxt.lon, nxt.lat]).addTo(map)
        );
        const tag = document.createElement("div");
        tag.className = "trail-tag trail-tag-risk";
        tag.textContent = `NEXT AT RISK · ${nxt.name.toUpperCase()} · ETA ${nxt.eta_days_min}–${nxt.eta_days_max}d`;
        trailMarkersRef.current.push(
          new lib.Marker({ element: tag, anchor: "bottom", offset: [0, -18] })
            .setLngLat([nxt.lon, nxt.lat])
            .addTo(map)
        );
      }
    }

    // Fly to show the full corridor — but only when the trail IS the subject
    // (the Supply Trail panel). On search the city owns the viewport and the
    // corridor is context, so framing it would zoom away from what was asked for.
    if (lineCoords.length >= 2 && !suppressTrailFit) {
      const lons = lineCoords.map((c) => c[0]);
      const lats = lineCoords.map((c) => c[1]);
      map.fitBounds(
        [
          [Math.min(...lons) - 0.5, Math.min(...lats) - 0.5],
          [Math.max(...lons) + 0.5, Math.max(...lats) + 0.5],
        ],
        { padding: 80, duration: 1800 }
      );
    }

    return () => {
      if (trailAnimRef.current !== null) {
        cancelAnimationFrame(trailAnimRef.current);
        trailAnimRef.current = null;
      }
      // Markers must come off here, not only at the top of the next run. On
      // unmount there IS no next run, so they stayed attached to a map being
      // torn down; MapLibre then projects a marker whose transform is already
      // gone and throws "Cannot read properties of null (reading 'y')".
      trailMarkersRef.current.forEach((m) => {
        try {
          m.remove();
        } catch {
          /* map already destroyed — nothing to detach from */
        }
      });
      trailMarkersRef.current = [];
    };
  }, [trail, ready, mapVersion]);

  // ── Entry route: how notes reached the searched city ────────────────────
  // Separate from the trail above. That one answers "which direction along a
  // corridor?" from cluster shape; this one answers "which channel got them
  // here?" and works from a single seizure. Different question, own layers.
  useEffect(() => {
    const map = mapRef.current;
    const lib = libRef.current;
    if (!map || !lib || !ready) return;

    const cleanup = () => {
      if (entryAnimRef.current !== null) {
        cancelAnimationFrame(entryAnimRef.current);
        entryAnimRef.current = null;
      }
      // The rAF handle alone is not enough: the loop below also parks in a
      // setTimeout, and a pending timer survives cancelAnimationFrame. It would
      // fire after teardown and queue an untracked frame that paints a dead map.
      if (entryTimerRef.current !== null) {
        clearTimeout(entryTimerRef.current);
        entryTimerRef.current = null;
      }
      entryAliveRef.current = false;
      ["entry-glow", "entry-line", "entry-flow"].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      if (map.getSource("entry-src")) map.removeSource("entry-src");
      entryMarkersRef.current.forEach((m) => {
        try {
          m.remove();
        } catch {
          /* map already gone */
        }
      });
      entryMarkersRef.current = [];
    };

    cleanup();
    if (!entryRoute || !entryRoute.legs?.length) return;

    const legs = entryRoute.legs;
    const coords: [number, number][] = [
      [legs[0].from_lon, legs[0].from_lat],
      ...legs.map((l) => [l.to_lon, l.to_lat] as [number, number]),
    ];

    map.addSource("entry-src", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: coords },
      },
    });

    // Violet distinguishes this from the orange corridor trail — a different
    // claim deserves a different colour, not a second orange line.
    map.addLayer({
      id: "entry-glow",
      type: "line",
      source: "entry-src",
      paint: { "line-color": "#a855f7", "line-width": 16, "line-opacity": 0.14, "line-blur": 7 },
    });
    map.addLayer({
      id: "entry-line",
      type: "line",
      source: "entry-src",
      paint: { "line-color": "#a855f7", "line-width": 3, "line-opacity": 0.6 },
    });
    map.addLayer({
      id: "entry-flow",
      type: "line",
      source: "entry-src",
      paint: {
        "line-color": "#d8b4fe",
        "line-width": 3,
        "line-dasharray": [0, 4, 3],
        "line-opacity": 0.95,
      },
    });

    // Dashes march source -> city: the direction notes are believed to travel.
    let step = 0;
    const seq: number[][] = [
      [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5],
      [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [3.5, 3.5, 0],
    ];
    entryAliveRef.current = true;
    const animate = () => {
      // Every re-entry checks the flag: a callback already in flight when
      // cleanup ran must not paint, and must not queue another.
      if (!entryAliveRef.current || mapRef.current !== map) return;
      try {
        if (!map.getLayer("entry-flow")) return;
        step = (step + 1) % seq.length;
        map.setPaintProperty("entry-flow", "line-dasharray", seq[step]);
      } catch {
        return;
      }
      // Park in a timer we can actually cancel, then take one frame. Both
      // handles are stored so cleanup can kill whichever stage is pending.
      entryTimerRef.current = setTimeout(() => {
        entryTimerRef.current = null;
        if (!entryAliveRef.current) return;
        entryAnimRef.current = requestAnimationFrame(animate);
      }, 55);
    };
    animate();

    // Source: the FIR-documented printing press the notes may have come from.
    const src = legs[0];
    const srcEl = document.createElement("div");
    srcEl.className = "entry-source-pin";
    srcEl.title = `${entryRoute.source} — printing press on record (${entryRoute.source_ref})`;
    entryMarkersRef.current.push(
      new lib.Marker({ element: srcEl }).setLngLat([src.from_lon, src.from_lat]).addTo(map),
    );

    const tag = document.createElement("div");
    tag.className = "entry-tag";
    tag.textContent = `SOURCE · ${entryRoute.source.toUpperCase()} · ${Math.round(
      entryRoute.plausibility * 100,
    )}%`;
    entryMarkersRef.current.push(
      new lib.Marker({ element: tag, anchor: "bottom", offset: [0, -20] })
        .setLngLat([src.from_lon, src.from_lat])
        .addTo(map),
    );

    // Transfer points — where the channel changes mode (rail -> road etc).
    // These are the concrete places an officer can actually go and check.
    legs.forEach((lg, i) => {
      if (i === 0 || lg.kind !== "access") return;
      const el = document.createElement("div");
      el.className = "entry-transfer";
      el.title = `${lg.from} → ${lg.to}: ${lg.distance_km} km by ${lg.mode}`;
      entryMarkersRef.current.push(
        new lib.Marker({ element: el }).setLngLat([lg.from_lon, lg.from_lat]).addTo(map),
      );
    });

    // No fitBounds here: this route is drawn in response to a search, and the
    // searched city already owns the viewport. Framing the route would zoom
    // away from the place the user asked to see.

    return cleanup;
  }, [entryRoute, ready, mapVersion]);

  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" />
      <button
        onClick={() => setSatellite((s) => !s)}
        className="glass pointer-events-auto absolute bottom-10 left-[60px] z-20 flex items-center gap-1.5 px-3 py-2 text-[11px] text-zinc-300 transition hover:text-white"
        title="toggle basemap"
      >
        <Layers className="h-3.5 w-3.5" />
        {satellite ? "Dark" : "Satellite"}
      </button>
    </div>
  );
}
