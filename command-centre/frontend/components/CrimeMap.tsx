"use client";

import { useEffect, useRef, useState } from "react";
import type { Hub, MapPoint } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { Layers } from "./Icons";

/* Free, keyless tiles — the demo can never die on a missing token. */
const DARK_TILES = ["a", "b", "c"].map(
  (s) => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`
);
const SAT_TILES = [
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
];

const JAMTARA: [number, number] = [86.803, 23.795];

/* Markers scale with zoom so each keeps a fixed ground footprint.
   Mercator pixels-per-meter double per zoom level, hence 2^(zoom - ref). */
const ZOOM_REF = 10.3; // initial zoom — markers render at their base size here (k = 1)
const SCALE_MIN = 0.3;
const SCALE_MAX = 4;

export default function CrimeMap({
  points,
  hubs,
  focus,
}: {
  points: MapPoint[];
  hubs: Hub[];
  focus: { lat: number; lon: number } | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const libRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const scalablesRef = useRef<HTMLElement[]>([]);
  const [ready, setReady] = useState(false);
  const [satellite, setSatellite] = useState(false);

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
            dark: { type: "raster", tiles: DARK_TILES, tileSize: 256, attribution: "© OpenStreetMap · © CARTO" },
            sat: { type: "raster", tiles: SAT_TILES, tileSize: 256, attribution: "Imagery © Esri" },
          },
          layers: [
            { id: "sat", type: "raster", source: "sat", layout: { visibility: "none" } },
            { id: "dark", type: "raster", source: "dark" },
          ],
        },
        center: JAMTARA,
        zoom: 10.3,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      libRef.current = maplibregl;
      mapRef.current = map;
      map.on("load", () => !cancelled && setReady(true));
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // basemap toggle
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setLayoutProperty("dark", "visibility", satellite ? "none" : "visible");
    map.setLayoutProperty("sat", "visibility", satellite ? "visible" : "none");
  }, [satellite, ready]);

  // markers: hotspot hubs underneath, signal dots on top
  useEffect(() => {
    const map = mapRef.current;
    const lib = libRef.current;
    if (!map || !lib || !ready) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    scalablesRef.current = [];

    for (const h of hubs) {
      // wrap: MapLibre owns the wrap's transform for positioning; we scale `inner`.
      const wrap = document.createElement("div");
      const inner = document.createElement("div");
      inner.className = `hub ${h.cross_domain ? "hub-cross" : ""}`;
      const size = Math.round(Math.min(150, 64 + h.intensity * 32));
      inner.style.width = inner.style.height = `${size}px`;
      if (h.cross_domain) {
        const label = document.createElement("span");
        label.className = "hub-label";
        label.textContent = `COORDINATED HUB${h.district ? ` · ${h.district.toUpperCase()}` : ""}`;
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
      const hubPopup = new lib.Popup({ offset: 18, closeButton: true, maxWidth: "260px" }).setHTML(
        `<strong>Coordinated hub${h.district ? ` — ${h.district}` : ""}</strong>` +
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
    return () => map.off("zoom", applyScale);
  }, [points, hubs, ready]);

  // fly to a located alert / fusion hotspot
  useEffect(() => {
    if (!mapRef.current || !ready || !focus) return;
    mapRef.current.flyTo({ center: [focus.lon, focus.lat], zoom: 12.2, duration: 2200 });
  }, [focus, ready]);

  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" />
      <button
        onClick={() => setSatellite((s) => !s)}
        className="glass pointer-events-auto absolute bottom-32 left-[60px] z-20 flex items-center gap-1.5 px-3 py-2 text-[11px] text-zinc-300 transition hover:text-white"
        title="toggle basemap"
      >
        <Layers className="h-3.5 w-3.5" />
        {satellite ? "Dark" : "Satellite"}
      </button>
    </div>
  );
}
