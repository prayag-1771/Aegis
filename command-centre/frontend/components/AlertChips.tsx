"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { EventsResponse, HotspotsResponse } from "@/lib/api";
import { clockTime, titleCase } from "@/lib/format";
import { MapPin, Phone } from "./Icons";

/** The 2–3 most urgent live alerts, as compact glass chips in the top-right —
 *  the declutter of the old tall Warning panel. Full history lives in AlertsDrawer. */
export default function AlertChips({
  events,
  hotspots,
  onLocate,
  onOpenAll,
}: {
  events: EventsResponse | null;
  hotspots: HotspotsResponse | null;
  onLocate: (p: { lat: number; lon: number }) => void;
  onOpenAll?: () => void;
}) {
  const crossHubs = (hotspots?.hubs ?? []).filter((h) => h.cross_domain).slice(0, 2);
  const topScam = (events?.scams ?? []).filter((s) => s.verdict !== "legit").at(-1) ?? null;

  const hasAny = crossHubs.length > 0 || topScam;
  const container = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!hasAny) return;
    gsap.from(".gsap-chip", {
      x: 50,
      opacity: 0,
      duration: 0.5,
      stagger: 0.1,
      ease: "power2.out",
    });
  }, { scope: container, dependencies: [hasAny, crossHubs.length, topScam?.event_id] });

  if (!hasAny) return null;

  return (
    <div ref={container} className="pointer-events-auto absolute right-4 top-16 z-20 flex w-[19rem] max-w-[calc(100vw-2rem)] flex-col gap-2 overflow-hidden">
      {crossHubs.map((h, i) => {
        // scam-bearing hubs read as critical (red), others as warning (amber)
        const critical = h.domains.includes("scam") || h.domains.includes("fraud_ring");
        return (
          <button
            key={h.hub_id}
            onClick={() => onLocate({ lat: h.lat, lon: h.lon })}
            className={`gsap-chip glass w-full border-l-2 p-3 text-left transition hover:brightness-125 ${
              critical ? "!border-l-red-500/70" : "!border-l-amber-500/70"
            }`}
          >
            <div className="flex items-center gap-1.5">
              <MapPin className={`h-3.5 w-3.5 ${critical ? "text-red-400" : "text-amber-400"}`} />
              <span className="text-[12px] font-medium text-zinc-100">
                Coordinated hub — {h.district ?? "unknown"}
              </span>
              {i === 0 && (
                <span className="ml-auto text-[9px] uppercase tracking-widest text-zinc-500">
                  live
                </span>
              )}
            </div>
            <div className="mt-1 text-[10px] text-zinc-400">
              {h.n_points} signals · {h.domains.map(titleCase).join(" + ")}
            </div>
          </button>
        );
      })}

      {topScam && (
        <button
          onClick={
            topScam.location_hint?.lat != null
              ? () => onLocate({ lat: topScam.location_hint!.lat!, lon: topScam.location_hint!.lon! })
              : onOpenAll
          }
          className="gsap-chip glass w-full border-l-2 !border-l-red-500/70 p-3 text-left transition hover:brightness-125"
        >
          <div className="flex items-center gap-1.5">
            <Phone className="h-3.5 w-3.5 text-red-400" />
            <span className="text-[12px] font-medium text-zinc-100">
              {titleCase(topScam.scam_type ?? "scam")} flagged — {topScam.location_hint?.district ?? "?"}
            </span>
            <span className="ml-auto text-[10px] text-zinc-500">{clockTime(topScam.timestamp)}</span>
          </div>
        </button>
      )}

      {onOpenAll && (
        <button
          onClick={onOpenAll}
          className="gsap-chip self-end rounded-full px-2 py-0.5 text-[10px] text-zinc-500 transition hover:text-zinc-300"
        >
          view all alerts →
        </button>
      )}
    </div>
  );
}
