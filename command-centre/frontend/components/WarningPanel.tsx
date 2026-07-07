"use client";

import type { EventsResponse, FusionOutput, HotspotsResponse } from "@/lib/api";
import { clockTime, titleCase } from "@/lib/format";
import { AlertTriangle, Banknote, MapPin, Phone } from "./Icons";

export default function WarningPanel({
  events,
  hotspots,
  fusion,
  onLocate,
}: {
  events: EventsResponse | null;
  hotspots: HotspotsResponse | null;
  fusion: FusionOutput | null;
  onLocate: (p: { lat: number; lon: number }) => void;
}) {
  const crossHubs = (hotspots?.hubs ?? []).filter((h) => h.cross_domain);
  const scams = (events?.scams ?? []).filter((s) => s.verdict !== "safe").slice(-3).reverse();
  const notes = (events?.counterfeits ?? []).filter((c) => c.verdict === "fake").slice(-3).reverse();

  return (
    <aside className="pointer-events-auto absolute right-4 top-16 z-20 flex max-h-[62vh] w-80 flex-col gap-2 overflow-y-auto scroll-thin">
      <div className="glass p-4">
        <div className="flex items-center gap-2 text-sm text-zinc-200">
          <AlertTriangle className="h-4 w-4 text-red-400" />
          Warning
          <span className="ml-auto text-[10px] text-zinc-500">live</span>
        </div>

        {/* fusion verdict */}
        {fusion && (
          <div className="mt-3 rounded-xl border border-red-500/30 bg-red-950/40 p-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-widest text-red-300">
                threat {fusion.threat_level}
              </span>
              <span className="text-[10px] text-zinc-500">{clockTime(fusion.generated_at)}</span>
            </div>
            <p className="mt-1.5 line-clamp-3 text-[11px] leading-relaxed text-red-100/90">
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

        {/* coordinated hubs */}
        {crossHubs.map((h) => (
          <button
            key={h.hub_id}
            onClick={() => onLocate({ lat: h.lat, lon: h.lon })}
            className="mt-2 w-full rounded-xl border border-amber-500/25 bg-amber-950/30 p-3 text-left transition hover:border-amber-400/50"
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

        {/* recent detections */}
        <div className="mt-3 space-y-1.5">
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
          {scams.length === 0 && notes.length === 0 && !fusion && (
            <div className="text-[11px] text-zinc-600">no active warnings</div>
          )}
        </div>
      </div>
    </aside>
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
