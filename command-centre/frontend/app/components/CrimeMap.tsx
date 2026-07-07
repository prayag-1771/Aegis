"use client";

/**
 * Cross-domain crime map (innovation #3).
 * CircleMarkers (no icon assets -> nothing to break in bundling):
 *   - signal points colored by domain
 *   - hub rings sized by intensity; cross-domain hubs pulse red
 */

import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Hub, MapPoint } from "@/lib/api";

const DOMAIN_COLOR: Record<string, string> = {
  scam: "#f59e0b", // amber — scam call origins
  counterfeit: "#22d3ee", // cyan — note seizures
  fraud_ring: "#a78bfa", // violet — ring districts
};

export default function CrimeMap({ points, hubs }: { points: MapPoint[]; hubs: Hub[] }) {
  return (
    <MapContainer
      center={[22.8, 80.5]}
      zoom={5}
      className="h-full w-full rounded-lg"
      style={{ background: "#0b1117" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      {points.map((p, i) => (
        <CircleMarker
          key={`pt-${i}`}
          center={[p.lat, p.lon]}
          radius={5 + (p.weight ?? 0.5) * 4}
          pathOptions={{
            color: DOMAIN_COLOR[p.type] ?? "#94a3b8",
            fillColor: DOMAIN_COLOR[p.type] ?? "#94a3b8",
            fillOpacity: 0.7,
            weight: 1,
          }}
        >
          <Popup>
            <b>{p.type}</b> — {p.district ?? "unknown district"}
            <br />
            weight {(p.weight ?? 0.5).toFixed(2)}
          </Popup>
        </CircleMarker>
      ))}

      {hubs.map((h) => (
        <CircleMarker
          key={h.hub_id}
          center={[h.lat, h.lon]}
          radius={14 + h.intensity * 6}
          pathOptions={{
            color: h.cross_domain ? "#ef4444" : "#64748b",
            fillColor: h.cross_domain ? "#ef4444" : "#64748b",
            fillOpacity: 0.15,
            weight: h.cross_domain ? 3 : 1.5,
            dashArray: h.cross_domain ? undefined : "4 6",
          }}
        >
          <Popup>
            <b>{h.hub_id}</b> {h.cross_domain ? "⚠ COORDINATED HUB" : "cluster"}
            <br />
            {h.district ?? "unknown"} · domains: {h.domains.join(" + ")}
            <br />
            {h.n_points} signals · intensity {h.intensity.toFixed(2)}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
