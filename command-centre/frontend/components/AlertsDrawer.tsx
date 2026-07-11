"use client";

import type { EventsResponse, FusionOutput, HotspotsResponse } from "@/lib/api";
import { clockTime, inr, titleCase } from "@/lib/format";
import { AlertTriangle, Banknote, MapPin, Network, Phone } from "./Icons";

export type RingAlert = {
  id: string;
  district: string;
  label: string;
  size: number;
  total: number | null;
  at: string;
  lat?: number;
  lon?: number;
};

const THREAT_COLOR: Record<string, string> = {
  critical: "bg-red-500/15 text-red-300 border-red-500/40",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  elevated: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  low: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
};

export default function AlertsDrawer({
  events,
  hotspots,
  fusion,
  ringAlerts = [],
  onLocate,
}: {
  events: EventsResponse | null;
  hotspots: HotspotsResponse | null;
  fusion: FusionOutput | null;
  ringAlerts?: RingAlert[];
  onLocate: (p: { lat: number; lon: number }) => void;
}) {
  const crossHubs = (hotspots?.hubs ?? []).filter((h) => h.cross_domain);
  const scams = (events?.scams ?? []).filter((s) => s.verdict !== "legit").reverse();
  const notes = (events?.counterfeits ?? []).filter((c) => c.verdict === "fake").reverse();

  return (
    <div className="flex flex-col gap-3 p-4">
      {/* fusion verdict */}
      {fusion && (
        <div className="rounded-xl border border-red-500/30 bg-red-950/40 p-3">
          <div className="flex items-center justify-between">
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                THREAT_COLOR[fusion.threat_level] ?? "bg-white/5 text-zinc-300 border-white/10"
              }`}
            >
              threat {fusion.threat_level}
            </span>
            <span className="text-[10px] text-zinc-500">{clockTime(fusion.generated_at)}</span>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-red-100/90">
            {fusion.summary}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {fusion.correlation_basis.map((b) => (
              <span
                key={b}
                className="rounded-full bg-red-500/10 px-1.5 py-0.5 text-[9px] text-red-300"
              >
                {b.replaceAll("_", " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ring alerts */}
      {ringAlerts.map((a) => (
        <button
          key={a.id}
          onClick={a.lat != null ? () => onLocate({ lat: a.lat!, lon: a.lon! }) : undefined}
          className="w-full rounded-xl border border-violet-500/30 bg-violet-950/40 p-3 text-left transition hover:border-violet-400/60"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-violet-300">
              <Network className="h-3.5 w-3.5" /> new fraud ring
            </span>
            <span className="text-[10px] text-zinc-500">{clockTime(a.at)}</span>
          </div>
          <div className="mt-1 text-[11px] text-violet-100/90">
            {a.district} — {a.label} · {a.size} accounts
            {a.total != null ? ` · ${inr(a.total)}` : ""}
          </div>
          {a.lat != null && (
            <div className="mt-1.5 flex items-center gap-1 text-[9px] text-violet-400/70">
              <MapPin className="h-3 w-3" /> locate on map
            </div>
          )}
        </button>
      ))}

      {/* coordinated hubs */}
      {crossHubs.map((h) => (
        <button
          key={h.hub_id}
          onClick={() => onLocate({ lat: h.lat, lon: h.lon })}
          className="w-full rounded-xl border border-amber-500/25 bg-amber-950/30 p-3 text-left transition hover:border-amber-400/50"
        >
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-200">
            <MapPin className="h-3.5 w-3.5" />
            Coordinated hub — {h.district ?? "unknown"}
          </div>
          <div className="mt-1 text-[10px] text-zinc-400">
            {h.n_points} signals · {h.domains.map(titleCase).join(" + ")}
          </div>
        </button>
      ))}

      {/* ALL scam detections */}
      {scams.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
            Scam detections ({scams.length})
          </div>
          {scams.map((s) => (
            <Row
              key={s.event_id}
              icon={<Phone className="h-3.5 w-3.5 text-red-400" />}
              text={`${titleCase(s.scam_type ?? "scam")} flagged — ${s.location_hint?.district ?? "?"}`}
              time={clockTime(s.timestamp)}
              onClick={
                s.location_hint?.lat != null
                  ? () => onLocate({ lat: s.location_hint!.lat!, lon: s.location_hint!.lon! })
                  : undefined
              }
            />
          ))}
        </div>
      )}

      {/* ALL counterfeit detections */}
      {notes.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
            Counterfeit detections ({notes.length})
          </div>
          {notes.map((c) => (
            <Row
              key={c.event_id}
              icon={<Banknote className="h-3.5 w-3.5 text-amber-400" />}
              text={`Fake ₹${c.denomination} seized — ${c.location_hint?.district ?? "?"}`}
              time={clockTime(c.timestamp)}
              onClick={
                c.location_hint?.lat != null
                  ? () => onLocate({ lat: c.location_hint!.lat!, lon: c.location_hint!.lon! })
                  : undefined
              }
            />
          ))}
        </div>
      )}

      {/* empty state */}
      {scams.length === 0 && notes.length === 0 && !fusion && ringAlerts.length === 0 && crossHubs.length === 0 && (
        <div className="flex items-center gap-2 text-[11px] text-zinc-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          no active warnings
        </div>
      )}
    </div>
  );
}

function Row({
  icon,
  text,
  time,
  onClick,
}: {
  icon: React.ReactNode;
  text: string;
  time: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition enabled:hover:bg-white/5"
    >
      {icon}
      <span className="flex-1 truncate text-[11px] text-zinc-300">{text}</span>
      <span className="text-[10px] text-zinc-600">{time}</span>
    </button>
  );
}
