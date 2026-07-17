"use client";

import { useMemo, useRef } from "react";
import { gsap, useGSAP, prefersReducedMotion } from "@/lib/gsap";
import type { EventsResponse, HotspotsResponse } from "@/lib/api";
import { clockTime, titleCase } from "@/lib/format";
import { Banknote, MapPin, Network, Phone } from "./Icons";

const ICONS = {
  hub: MapPin,
  scam: Phone,
  counterfeit: Banknote,
  ring: Network,
} as const;

/** One live alert, whatever domain produced it. */
type Notice = {
  id: string;
  kind: "hub" | "scam" | "counterfeit" | "ring";
  title: string;
  detail: string;
  /** How many INDEPENDENT domains back this finding. Ranks before score:
   *  three domains converging on one place is stronger evidence than any
   *  single detector's confidence, however high. */
  corroboration: number;
  /** The producing engine's own score, 0–1. Not invented here. */
  score: number;
  at?: string;
  locate?: { lat: number; lon: number };
};

/** Rank every live signal and show the top 3, in the top-right.
 *  Full history lives in AlertsDrawer.
 *
 *  Ordering is derived, never fixed. This previously hardcoded the slots —
 *  always two cross-domain hubs plus whichever scam happened to arrive last —
 *  so counterfeits and fraud rings could never appear no matter how severe,
 *  and a 0.4 scam outranked a 0.99 one purely by arriving later.
 *
 *  Now every domain competes on evidence: first on corroboration (how many
 *  independent domains agree), then on the detecting engine's own score. Both
 *  numbers come from the data. Nothing here decides a hub matters more than a
 *  ring — the evidence does, and a quiet hub loses to a strong ring. */
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
  const notices = useMemo<Notice[]>(() => {
    const all: Notice[] = [];

    // Hubs — a correlation, so corroboration is its domain count. `tier` is the
    // engine's own honest label: coordinated = all 3 domains, multi_signal = 2.
    for (const h of hotspots?.hubs ?? []) {
      const domains = h.domains?.length ?? 0;
      if (domains < 2) continue; // single-domain cluster: the raw event says it better
      all.push({
        id: `hub:${h.hub_id}`,
        kind: "hub",
        title: `${h.tier === "coordinated" ? "Coordinated hub" : "Multi-signal hub"} — ${h.district ?? "unknown"}`,
        detail: `${h.n_points} signals · ${(h.domains ?? []).map(titleCase).join(" + ")}`,
        corroboration: domains,
        // Intensity is unbounded, so it cannot be a probability. Rank hubs of
        // equal tier against the strongest hub present rather than pretend a
        // raw intensity is a confidence.
        score: Math.min(1, h.intensity / Math.max(...(hotspots?.hubs ?? []).map((x) => x.intensity || 1), 1)),
        locate: { lat: h.lat, lon: h.lon },
      });
    }

    for (const s of events?.scams ?? []) {
      if (s.verdict === "legit") continue;
      all.push({
        id: `scam:${s.event_id}`,
        kind: "scam",
        title: `${titleCase(s.scam_type ?? "scam")} flagged — ${s.location_hint?.district ?? "unknown"}`,
        detail: `risk ${Math.round((s.risk_score ?? 0) * 100)}% · ${s.source ?? "reported"}`,
        corroboration: 1,
        score: s.risk_score ?? 0,
        at: s.timestamp,
        locate:
          s.location_hint?.lat != null && s.location_hint?.lon != null
            ? { lat: s.location_hint.lat, lon: s.location_hint.lon }
            : undefined,
      });
    }

    for (const c of events?.counterfeits ?? []) {
      if (c.verdict !== "fake") continue; // genuine/uncertain is not an alert
      all.push({
        id: `note:${c.event_id}`,
        kind: "counterfeit",
        title: `Counterfeit ₹${c.denomination} — ${c.location_hint?.district ?? "unknown"}`,
        detail: `confidence ${Math.round((c.confidence ?? 0) * 100)}%${
          c.missing_features?.length ? ` · ${c.missing_features.length} features failed` : ""
        }`,
        corroboration: 1,
        score: c.confidence ?? 0,
        at: c.timestamp,
        locate:
          c.location_hint?.lat != null && c.location_hint?.lon != null
            ? { lat: c.location_hint.lat, lon: c.location_hint.lon }
            : undefined,
      });
    }

    for (const r of events?.fraud_graph?.rings ?? []) {
      all.push({
        id: `ring:${r.ring_id}`,
        kind: "ring",
        title: `${r.label ?? "Fraud ring"} — ${r.district ?? "unknown"}`,
        detail: `${r.size} accounts · risk ${Math.round((r.risk_score ?? 0) * 100)}%`,
        corroboration: 1,
        score: r.risk_score ?? 0,
      });
    }

    return all
      .sort((a, b) => b.corroboration - a.corroboration || b.score - a.score)
      .slice(0, 3);
  }, [events, hotspots]);

  const hasAny = notices.length > 0;
  const container = useRef<HTMLDivElement>(null);
  // Ids already animated & settled — a 5s poll that re-delivers the same alerts
  // must not re-animate existing chips. Seeded lazily on first run below so the
  // React-StrictMode double-mount (dev) can't pre-mark chips as "seen" and
  // suppress the very first animation.
  const seen = useRef<Set<string> | null>(null);

  const chipIds = notices.map((n) => n.id);
  const idKey = chipIds.join("|");

  useGSAP(() => {
    const firstRun = seen.current === null;
    if (seen.current === null) seen.current = new Set();

    // On first run animate ALL chips; afterwards only ids we haven't shown yet.
    const targets = Array.from(
      container.current?.querySelectorAll<HTMLElement>(".gsap-chip[data-chip-id]") ?? [],
    ).filter((el) => {
      const id = el.dataset.chipId!;
      return firstRun || !seen.current!.has(id);
    });

    if (targets.length > 0) {
      if (prefersReducedMotion()) {
        gsap.set(targets, { opacity: 1, scale: 1, xPercent: 0 });
      } else {
        // A clear "notification slides in from the right" entrance. We use
        // xPercent (transform-based, relative to each chip's own width) +
        // scale + fade — all GPU-compositor transforms, so even though the
        // chips are `.glass` (backdrop-filter: blur(20px)) over the live map,
        // the blur is sampled ONCE and only the finished layer is moved: no
        // per-frame re-blur, so it stays smooth. A springy back.out gives the
        // chip a small overshoot so the arrival is unmistakable.
        gsap.fromTo(targets,
          { opacity: 0, xPercent: 40, scale: 0.9 },
          {
            opacity: 1, xPercent: 0, scale: 1, duration: 0.6, stagger: 0.1,
            ease: "back.out(1.7)", transformOrigin: "right center",
            force3D: true, willChange: "transform,opacity",
            clearProps: "all",
          },
        );
      }
    }
    chipIds.forEach((id) => seen.current!.add(id));
  }, { scope: container, dependencies: [idKey] });

  if (!hasAny) return null;

  return (
    <div ref={container} className="pointer-events-auto absolute right-4 top-16 z-20 flex w-[19rem] max-w-[calc(100vw-2rem)] flex-col gap-2 overflow-hidden">
      {notices.map((n, i) => {
        const Icon = ICONS[n.kind];
        // Severity is the chip's own score, not its kind: a weak signal must not
        // look critical because of the domain it came from.
        const critical = n.corroboration > 1 || n.score >= 0.9;
        return (
          <button
            key={n.id}
            data-chip-id={n.id}
            onClick={n.locate ? () => onLocate(n.locate!) : onOpenAll}
            className={`gsap-chip glass w-full border-l-2 p-3 text-left transition-[filter] hover:brightness-125 ${
              critical ? "!border-l-red-500/70" : "!border-l-amber-500/70"
            }`}
          >
            <div className="flex items-center gap-1.5">
              <Icon className={`h-3.5 w-3.5 shrink-0 ${critical ? "text-red-400" : "text-amber-400"}`} />
              <span className="truncate text-[12px] font-medium text-zinc-100">{n.title}</span>
              <span className="ml-auto shrink-0 text-[10px] text-zinc-500">
                {n.at ? clockTime(n.at) : i === 0 ? "live" : ""}
              </span>
            </div>
            <div className="mt-1 text-[10px] text-zinc-400">{n.detail}</div>
          </button>
        );
      })}

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
