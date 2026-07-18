"use client";

/**
 * SupplyTrailPanel — the side panel that shows counterfeit note provenance.
 *
 * Props:
 *   trail      — the active SupplyTrail (best trail from the backend)
 *   allTrails  — every mode's trail (for the mode-switcher tabs)
 *   loading    — whether a fetch is in-flight
 *   onClose    — close handler
 *   onFlyTo    — request the map to fly to a location
 *   onSelectTrail — user switched to a different trail (mode)
 */

import { useEffect, useRef, useState } from "react";
import type { SupplyTrail } from "@/lib/api";
import { playPanelExit, usePanelEntrance } from "@/lib/gsap";

const MODE_ICONS: Record<string, string> = {
  rail: "🚂",
  road: "🛣️",
  ship: "🚢",
  air: "✈️",
};

const BAND_COLOR: Record<string, string> = {
  high: "text-red-400 border-red-500/40 bg-red-500/10",
  medium: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  low: "text-zinc-400 border-zinc-500/40 bg-zinc-500/10",
};

const EVIDENCE_ICON: Record<string, string> = {
  corridor_snap: "📍",
  seizure_cluster: "🔴",
  corridor_terminus: "⚑",
  fir_mention: "📄",
  transport_gap: "⋯",
  temporal_flow: "➤",
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 60 ? "bg-red-500" : pct >= 35 ? "bg-amber-500" : "bg-zinc-500";
  return (
    <div className="relative h-1.5 w-full bg-white/10 overflow-hidden">
      <div
        className={`absolute left-0 top-0 h-full transition-all duration-700 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function SupplyTrailPanel({
  trail,
  allTrails,
  loading,
  onClose,
  onFlyTo,
  onSelectTrail,
}: {
  trail: SupplyTrail | null;
  allTrails: SupplyTrail[];
  loading: boolean;
  onClose: () => void;
  onFlyTo: (lat: number, lon: number, label: string) => void;
  onSelectTrail: (t: SupplyTrail) => void;
}) {
  const [expandedEvidence, setExpandedEvidence] = useState<number | null>(null);
  const scope = useRef<HTMLDivElement>(null);
  // Header, then body. Re-runs on trail change so switching mode (rail → road)
  // reveals the new content instead of swapping it silently.
  usePanelEntrance(scope, ".gsap-panel", [trail?.trail_id, loading]);
  const close = () => playPanelExit(scope, onClose);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div ref={scope} className="flex flex-col h-full overflow-hidden">
      {/* ── Header ── */}
      <div className="gsap-panel flex items-center justify-between border-b border-white/10 px-5 py-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center bg-orange-500/20">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              className="h-5 w-5 text-orange-400"
            >
              <path d="M3 12h18M12 3l9 9-9 9" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              Supply Trail
            </h2>
            <p className="text-[10px] text-zinc-500">
              Counterfeit note provenance inference
            </p>
          </div>
        </div>
        <button
          onClick={close}
          className="group relative p-1.5 text-zinc-500 transition hover:bg-white/10 hover:text-zinc-200"
          aria-label="Close"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-4 w-4"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          <span className="pointer-events-none absolute right-full top-1/2 mr-2 -translate-y-1/2 whitespace-nowrap rounded border border-white/10 bg-zinc-800/90 px-2 py-1 text-[10px] text-zinc-300 opacity-0 shadow-lg backdrop-blur-sm transition-opacity group-hover:opacity-100">
            Close (Esc)
          </span>
        </button>
      </div>

      {/* ── Body ── */}
      <div className="gsap-panel flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {loading && (
          <div className="flex flex-col gap-4 animate-pulse px-1 pt-4">
            <div className="flex gap-2 mb-2">
              <div className="h-6 w-16 bg-white/10 rounded-full"></div>
              <div className="h-6 w-16 bg-white/10 rounded-full"></div>
            </div>
            <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
              <div className="h-full w-1/3 bg-white/10"></div>
            </div>
            
            <div className="flex justify-center my-4">
              <div className="h-3 w-24 bg-white/10 rounded"></div>
            </div>
            
            <div className="space-y-4 relative">
              <div className="absolute left-2.5 top-6 bottom-6 w-px border-l border-dashed border-white/10 z-0"></div>
              {[...Array(4)].map((_, i) => (
                <div key={i} className="relative z-10 flex gap-4">
                  <div className="mt-4 h-5 w-5 rounded-full bg-zinc-800 shrink-0 border border-white/10 flex items-center justify-center">
                     <div className="h-2 w-2 rounded-full bg-white/10"></div>
                  </div>
                  <div className="flex-1 bg-white/5 border border-white/5 rounded-lg p-4 flex justify-between items-center">
                    <div className="space-y-2 flex-1">
                      <div className="h-4 w-32 bg-white/10 rounded"></div>
                      <div className="h-3 w-48 bg-white/5 rounded"></div>
                    </div>
                    <div className="h-6 w-6 rounded-full bg-white/5 shrink-0"></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && !trail && (
          <div className="flex flex-col items-center gap-4 py-10 text-center">
            <div className="text-4xl opacity-40">🗺️</div>
            <div>
              <p className="text-sm font-medium text-zinc-300">
                No trail yet
              </p>
              <p className="mt-1 text-[11px] text-zinc-600 max-w-[220px] mx-auto">
                Scan a counterfeit note — fake verdicts with a location will
                generate a provenance trail automatically.
              </p>
            </div>
          </div>
        )}

        {!loading && trail && (
          <>
            {/* Mode switcher */}
            {allTrails.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {allTrails.map((t) => (
                  <button
                    key={t.trail_id}
                    onClick={() => onSelectTrail(t)}
                    className={`flex items-center gap-1 px-3 py-1 text-[10px] font-medium transition border ${
                      t.trail_id === trail.trail_id
                        ? "border-orange-500/60 bg-orange-500/15 text-orange-300"
                        : "border-white/10 bg-white/5 text-zinc-400 hover:border-white/20 hover:text-zinc-200"
                    }`}
                  >
                    {MODE_ICONS[t.mode] ?? "🚦"} {t.mode.toUpperCase()}
                    <span className="ml-1 opacity-60">
                      {Math.round(t.confidence * 100)}%
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* Corridor title */}
            <div className="border border-white/10 bg-white/5 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-base">
                      {MODE_ICONS[trail.mode] ?? "🚦"}
                    </span>
                    <span className="text-xs font-semibold text-zinc-100 leading-snug">
                      {trail.corridor.name}
                    </span>
                  </div>
                  <div className="mt-1 text-[10px] text-zinc-500">
                    {trail.seizures.length} seizure
                    {trail.seizures.length !== 1 ? "s" : ""} detected on this
                    corridor
                  </div>
                </div>
                <span
                  className={`shrink-0 border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    BAND_COLOR[trail.confidence_band]
                  }`}
                >
                  {trail.confidence_band}
                </span>
              </div>
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-[9px] text-zinc-500">
                  <span>Confidence</span>
                  <span>{Math.round(trail.confidence * 100)}%</span>
                </div>
                <ConfidenceBar value={trail.confidence} />
              </div>
            </div>

            {/* Seizure cluster → inferred origin flow */}
            <div className="border border-white/10 bg-white/5 p-4 space-y-3">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
                Provenance flow
              </div>

              {/* Seizures */}
              <div className="flex flex-col gap-2">
                {trail.seizures.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => onFlyTo(s.lat, s.lon, s.district)}
                    className="flex items-center gap-2 border border-red-500/20 bg-red-500/10 px-3 py-2 text-left transition hover:border-red-500/40 hover:bg-red-500/15 group"
                  >
                    <span className="h-2 w-2 rounded-full bg-red-400 animate-pulse shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-medium text-red-300 truncate">
                        Seizure — {s.district}
                      </div>
                      {s.denomination && s.denomination !== "unknown" && (
                        <div className="text-[9px] text-zinc-600">
                          ₹{s.denomination} note
                        </div>
                      )}
                    </div>
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className="h-3 w-3 shrink-0 text-zinc-600 group-hover:text-zinc-300 transition"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v4l3 3" />
                    </svg>
                  </button>
                ))}
              </div>

              {/* Arrow */}
              <div className="flex justify-center">
                <div className="flex flex-col items-center gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-1.5 w-0.5 bg-orange-500/60"
                      style={{ opacity: 1 - i * 0.25 }}
                    />
                  ))}
                  <svg
                    viewBox="0 0 10 6"
                    fill="currentColor"
                    className="h-2 w-2 text-orange-500"
                  >
                    <path d="M5 6 0 0h10z" />
                  </svg>
                  <span className="text-[8px] uppercase tracking-widest text-orange-500/70 mt-0.5">
                    corridor trace
                  </span>
                </div>
              </div>

              {/* Inferred origin */}
              <button
                onClick={() =>
                  onFlyTo(
                    trail.inferred_origin.lat,
                    trail.inferred_origin.lon,
                    trail.inferred_origin.name
                  )
                }
                className="w-full flex items-center gap-3 border border-orange-500/30 bg-orange-500/10 px-4 py-3 text-left transition hover:border-orange-500/50 hover:bg-orange-500/15 group"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center bg-orange-500/20 text-base">
                  ⚑
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-semibold text-orange-300">
                    Likely Origin
                  </div>
                  <div className="text-xs font-medium text-zinc-100 mt-0.5 truncate">
                    {trail.inferred_origin.name}
                  </div>
                  <div className="text-[9px] text-zinc-500 mt-0.5 line-clamp-2">
                    {trail.inferred_origin.reasoning}
                  </div>
                </div>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-4 w-4 shrink-0 text-zinc-600 group-hover:text-orange-400 transition"
                >
                  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
                  <circle cx="12" cy="9" r="2.5" />
                </svg>
              </button>

              {/* Temporal flow — direction & speed proven from seizure timing */}
              {trail.flow && (
                <div className="border border-red-500/25 bg-red-500/5 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] font-semibold text-red-300">
                      Movement flow
                    </div>
                    <span className="text-[9px] uppercase tracking-widest text-zinc-500">
                      R² {Math.round(trail.flow.consistency * 100)}%
                    </span>
                  </div>
                  <div className="text-xs text-zinc-100">
                    ➤ toward <span className="font-medium">{trail.flow.direction_toward}</span>
                    {" "}at ~{Math.round(trail.flow.speed_km_per_day)} km/day
                    {trail.flow.origin_consistent && (
                      <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[9px] text-emerald-300 border border-emerald-500/30">
                        corroborates origin
                      </span>
                    )}
                  </div>
                  {trail.flow.next_hub_at_risk && (
                    <button
                      onClick={() =>
                        onFlyTo(
                          trail.flow!.next_hub_at_risk!.lat,
                          trail.flow!.next_hub_at_risk!.lon,
                          trail.flow!.next_hub_at_risk!.name
                        )
                      }
                      className="w-full rounded-lg border border-red-500/30 bg-red-950/40 px-3 py-2 text-left transition hover:border-red-400/50"
                    >
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-red-300">
                        Next hub at risk
                      </div>
                      <div className="text-xs text-zinc-100 mt-0.5">
                        {trail.flow.next_hub_at_risk.name} ·{" "}
                        {Math.round(trail.flow.next_hub_at_risk.distance_km)} km ahead · ETA{" "}
                        {trail.flow.next_hub_at_risk.eta_days_min}–
                        {trail.flow.next_hub_at_risk.eta_days_max} days
                      </div>
                    </button>
                  )}
                  <p className="text-[9px] leading-relaxed text-zinc-500">{trail.flow.note}</p>
                </div>
              )}
            </div>

            {/* Evidence chain */}
            <div className="space-y-2">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500 px-1">
                Evidence chain
              </div>
              {trail.evidence.map((ev, i) => (
                <button
                  key={i}
                  className="w-full text-left rounded-xl border border-white/10 bg-white/5 p-3 transition hover:border-white/20 hover:bg-white/[0.07]"
                  onClick={() =>
                    setExpandedEvidence(expandedEvidence === i ? null : i)
                  }
                >
                  <div className="flex items-start gap-2">
                    <span className="shrink-0 text-sm leading-none mt-0.5">
                      {EVIDENCE_ICON[ev.type] ?? "•"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                          {ev.type.replace(/_/g, " ")}
                        </span>
                        {ev.ref && (
                          <span className="text-[9px] text-zinc-600 truncate max-w-[100px]">
                            {ev.ref}
                          </span>
                        )}
                      </div>
                      <p
                        className={`mt-1 text-[11px] leading-relaxed text-zinc-300 ${
                          expandedEvidence === i ? "" : "line-clamp-2"
                        }`}
                      >
                        {ev.detail}
                      </p>
                    </div>
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className={`h-3 w-3 shrink-0 text-zinc-600 transition-transform ${
                        expandedEvidence === i ? "rotate-180" : ""
                      }`}
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </div>
                </button>
              ))}
            </div>

            {/* Disclaimer */}
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 mt-2">
              <div className="flex items-start gap-2">
                <span className="text-sm shrink-0">⚠️</span>
                <p className="text-[10px] leading-relaxed text-amber-500/80">
                  {trail.disclaimer}
                </p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Footer — corridor node list ── */}
      {!loading && trail && (
        <div className="shrink-0 border-t border-white/10 px-5 py-3">
          <div className="text-[9px] uppercase tracking-widest text-zinc-600 mb-2">
            Corridor nodes
          </div>
          <div className="flex flex-wrap gap-1">
            {trail.corridor.node_path.map((n, i) => (
              <button
                key={i}
                onClick={() => onFlyTo(n.lat, n.lon, n.name)}
                className={`rounded px-2 py-0.5 text-[9px] transition border ${
                  n.is_major_hub
                    ? "border-zinc-600 bg-zinc-700/50 text-zinc-300 hover:border-orange-500/40 hover:text-orange-300"
                    : "border-white/5 bg-white/5 text-zinc-600 hover:text-zinc-400"
                }`}
              >
                {n.is_major_hub ? "●" : "·"} {n.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
