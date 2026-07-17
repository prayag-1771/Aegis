"use client";

import { useEffect, useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import type {
  CampaignsResponse,
  EventsResponse,
  FusionOutput,
  HotspotsResponse,
  PlateFamiliesResponse,
} from "@/lib/api";
import { fetchCampaigns, fetchPlateFamilies } from "@/lib/api";
import { clockTime, inr, titleCase } from "@/lib/format";
import { AlertTriangle, Banknote, MapPin, Network, Phone, ArrowUpRight } from "./Icons";
import CaseFileModal from "./CaseFileModal";

const TIER_BADGE: Record<string, string> = {
  high: "bg-red-500/15 text-red-300 border-red-500/40",
  probable: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  possible: "bg-amber-500/15 text-amber-300 border-amber-500/40",
};

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

/* fixed 24h shape (deterministic — no hydration mismatch); live counts scale it */
const SHAPE = [3, 2, 2, 1, 1, 2, 4, 7, 9, 8, 10, 12, 11, 13, 12, 14, 15, 13, 16, 14, 12, 9, 6, 4];

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
  const container = useRef<HTMLDivElement>(null);
  // Intelligence layer: fetched once when the drawer opens (cheap endpoints).
  const [families, setFamilies] = useState<PlateFamiliesResponse | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignsResponse | null>(null);
  const [caseDistrict, setCaseDistrict] = useState<string | null>(null);
  useEffect(() => {
    fetchPlateFamilies().then(setFamilies).catch(() => {});
    fetchCampaigns().then(setCampaigns).catch(() => {});
  }, []);

  useGSAP(() => {
    // Fade + subtle scale (compositor transform) instead of a positional x
    // slide — these are `.glass` (backdrop-filter) over the map, where a moving
    // slide re-blurs every frame and stutters. Scale samples the blur once.
    gsap.fromTo(".gsap-alert-item",
      { opacity: 0, scale: 0.96, y: 10 },
      { opacity: 1, scale: 1, y: 0, duration: 0.4, stagger: 0.05,
        ease: "power3.out", force3D: true,
        willChange: "transform,opacity", clearProps: "all" },
    );
  }, { scope: container });

  const crossHubs = (hotspots?.hubs ?? []).filter((h) => h.cross_domain);
  const scams = (events?.scams ?? []).filter((s) => s.verdict !== "legit").reverse();
  const notes = (events?.counterfeits ?? []).filter((c) => c.verdict === "fake").reverse();

  // Analytics logic
  const scamCount = scams.length;
  const noteCount = notes.length;
  const ringAccts = events?.fraud_graph?.rings.reduce((a, r) => a + r.size, 0) ?? 0;
  const total = scamCount + noteCount + ringAccts;
  const max = Math.max(...SHAPE);
  const hour = new Date().getUTCHours();

  const rings = events?.fraud_graph?.rings ?? [];
  const ringMoney = rings.reduce((a, r) => a + (r.total_amount ?? 0), 0);
  const fakeCount = noteCount;

  const trails = fusion?.money_trails ?? [];
  const types = new Set((fusion?.linked_signals ?? []).map((l) => l.type));
  const takeMoveLinked = trails.length > 0 || (types.has("scam") && types.has("fraud_ring"));
  const moveCashLinked = types.has("counterfeit");

  return (
    <div ref={container} className="flex flex-col gap-4 p-4">
      {/* ── Live Signal Volume ── */}
      <section className="gsap-alert-item glass p-4 !rounded-none">
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span>Live Signal Volume</span>
          <ArrowUpRight className="h-3.5 w-3.5" />
        </div>
        <div className="mt-1 flex items-end gap-2">
          <span className="text-3xl font-light tabular-nums">{total.toLocaleString()}</span>
          <span className="pb-1 text-[10px] text-zinc-500">
            signals today · {scamCount} scam / {noteCount} notes / {ringAccts} flagged accts
          </span>
        </div>
        <div className="mt-3 flex h-16 items-end gap-1">
          {SHAPE.map((v, i) => (
            <div
              key={i}
              className={`flex-1 ${i === hour ? "bg-red-400/90" : "bg-zinc-600/60"}`}
              style={{ height: `${(v / max) * 100}%` }}
              title={`${String(i).padStart(2, "0")}:00`}
            />
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[9px] text-zinc-600">
          <span>00</span>
          <span>06</span>
          <span>12</span>
          <span>18</span>
          <span>24</span>
        </div>
      </section>

      {/* ── Pipeline Visualization (Vertical) ── */}
      <section className="gsap-alert-item glass p-4 !rounded-none">
        <div className="text-xs text-zinc-400">Criminal Pipeline</div>
        <div className="mt-3 flex flex-col items-center gap-1">
          <PipeStage n="1" verb="TAKE" tone="text-red-300" accent="border-red-500/30" line={`${scamCount} scam signal${scamCount === 1 ? "" : "s"}`} />
          <PipeArrow lit={takeMoveLinked} litClass="text-red-400" chip={trails[0] ? `₹${trails[0].amount.toLocaleString("en-IN")} traced` : undefined} />
          <PipeStage n="2" verb="MOVE" tone="text-violet-300" accent="border-violet-500/30" line={`${rings.length} ring${rings.length === 1 ? "" : "s"} · ${inr(ringMoney)}`} />
          <PipeArrow lit={moveCashLinked} litClass="text-amber-400" />
          <PipeStage n="3" verb="CASH OUT" tone="text-amber-300" accent="border-amber-500/30" line={`${fakeCount} fake note${fakeCount === 1 ? "" : "s"}`} />
        </div>
      </section>

      <div className="gsap-alert-item border-t border-white/5 my-2"></div>

      {/* intelligence: scam campaigns — one gang, one script, many districts */}
      {(campaigns?.campaigns ?? []).map((c) => (
        <div key={c.campaign_id} className="gsap-alert-item border border-fuchsia-500/30 bg-fuchsia-950/30 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-fuchsia-300">
              Campaign detected · {titleCase(c.scam_type)}
            </span>
            <span className={`border px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${TIER_BADGE[c.tier]}`}>
              {c.tier}
            </span>
          </div>
          <p className="mt-1 text-[10px] leading-relaxed text-zinc-300">
            Same script behind <strong>{c.n_events} reports</strong>: {c.district_spread.join(" → ")}
            {c.phone_numbers.length > 0 && <> · {c.phone_numbers.length} number(s)</>}
          </p>
          <p className="mt-1 text-[9px] text-zinc-500 line-clamp-2">“{c.sample_text}…”</p>
          <p className="mt-1 text-[9px] text-zinc-600">{c.note}</p>
        </div>
      ))}

      {/* intelligence: plate families — shared printing defects = common source */}
      {(families?.families ?? []).map((f) => (
        <div key={f.family_id} className="gsap-alert-item border border-teal-500/30 bg-teal-950/30 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-teal-300">
              Plate family · ₹{f.denomination} × {f.n_notes} notes
            </span>
            <span className={`border px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${TIER_BADGE[f.tier]}`}>
              {f.tier}
            </span>
          </div>
          <p className="mt-1 text-[10px] leading-relaxed text-zinc-300">
            Same failed features (<strong>{f.shared_defects.join(", ") || "partial overlap"}</strong>) across{" "}
            {f.districts.join(", ")} · {Math.round(f.span_km)} km apart
          </p>
          <p className="mt-1 text-[9px] text-zinc-600">{f.note}</p>
        </div>
      ))}

      {/* fusion verdict */}
      {fusion && (
        <div className="gsap-alert-item border border-red-500/30 bg-red-950/40 p-3">
          <div className="flex items-center justify-between">
            <span
              className={`border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
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
                className="bg-red-500/10 px-1.5 py-0.5 text-[9px] text-red-300"
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
          className="gsap-alert-item w-full border border-violet-500/30 bg-violet-950/40 p-3 text-left transition hover:border-violet-400/60"
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
          className="gsap-alert-item w-full border border-amber-500/25 bg-amber-950/30 p-3 text-left transition hover:border-amber-400/50"
        >
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-200">
            <MapPin className="h-3.5 w-3.5" />
            {h.tier === "coordinated" ? "Coordinated hub" : "Multi-signal hub"} — {h.district ?? "unknown"}
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-400">
            <span>{h.n_points} signals · {h.domains.map(titleCase).join(" + ")}</span>
            {h.district && (
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  setCaseDistrict(h.district);
                }}
                className="border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-300 transition hover:bg-amber-500/20"
              >
                📋 case file
              </span>
            )}
          </div>
        </button>
      ))}

      {caseDistrict && (
        <CaseFileModal district={caseDistrict} onClose={() => setCaseDistrict(null)} />
      )}

      {/* ALL scam detections */}
      {scams.length > 0 && (
        <div className="space-y-1.5">
          <div className="gsap-alert-item text-[10px] font-bold uppercase tracking-widest text-zinc-500">
            Scam detections ({scams.length})
          </div>
          {scams.map((s) => (
            <div key={s.event_id} className="gsap-alert-item">
              <Row
                icon={<Phone className="h-3.5 w-3.5 text-red-400" />}
                text={`${titleCase(s.scam_type ?? "scam")} flagged — ${s.location_hint?.district ?? "?"}`}
                time={clockTime(s.timestamp)}
                onClick={
                  s.location_hint?.lat != null
                    ? () => onLocate({ lat: s.location_hint!.lat!, lon: s.location_hint!.lon! })
                    : undefined
                }
              />
            </div>
          ))}
        </div>
      )}

      {/* ALL counterfeit detections */}
      {notes.length > 0 && (
        <div className="space-y-1.5">
          <div className="gsap-alert-item text-[10px] font-bold uppercase tracking-widest text-zinc-500">
            Counterfeit detections ({notes.length})
          </div>
          {notes.map((c) => (
            <div key={c.event_id} className="gsap-alert-item">
              <Row
                icon={<Banknote className="h-3.5 w-3.5 text-amber-400" />}
                text={`Fake ₹${c.denomination} seized — ${c.location_hint?.district ?? "?"}`}
                time={clockTime(c.timestamp)}
                onClick={
                  c.location_hint?.lat != null
                    ? () => onLocate({ lat: c.location_hint!.lat!, lon: c.location_hint!.lon! })
                    : undefined
                }
              />
            </div>
          ))}
        </div>
      )}

      {/* empty state */}
      {scams.length === 0 && notes.length === 0 && !fusion && ringAlerts.length === 0 && crossHubs.length === 0 && (
        <div className="gsap-alert-item flex items-center gap-2 text-[11px] text-zinc-600">
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
      className="flex w-full items-center gap-2 px-2 py-1.5 text-left transition enabled:hover:bg-white/5"
    >
      {icon}
      <span className="flex-1 truncate text-[11px] text-zinc-300">{text}</span>
      <span className="text-[10px] text-zinc-600">{time}</span>
    </button>
  );
}

function PipeStage({ n, verb, tone, accent, line }: { n: string; verb: string; tone: string; accent: string; line: string; }) {
  return (
    <div className={`w-full border ${accent} bg-zinc-950/60 px-4 py-2.5 text-center`}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${tone}`}>
        {n} · {verb}
      </div>
      <div className="mt-0.5 text-[10px] text-zinc-400">{line}</div>
    </div>
  );
}

function PipeArrow({ lit, litClass, chip }: { lit: boolean; litClass: string; chip?: string }) {
  return (
    <div className="flex flex-col items-center py-0.5">
      <span className={`text-base leading-none ${lit ? `${litClass} animate-pulse` : "text-zinc-700"}`}>
        ↓
      </span>
      {chip && lit && (
        <span className="mt-0.5 bg-red-500/15 px-1.5 py-px text-[8px] font-semibold text-red-300">
          {chip}
        </span>
      )}
    </div>
  );
}
