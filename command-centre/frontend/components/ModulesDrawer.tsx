"use client";

import { useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import type { EventsResponse, HealthResponse } from "@/lib/api";
import { clockTime, pct, titleCase } from "@/lib/format";
import CitizenShieldPanel from "./CitizenShieldPanel";
import {
  AlertTriangle,
  ArrowUpRight,
  Banknote,
  CheckCircle,
  MapPin,
  Phone,
  Zap
} from "./Icons";

const SPARK = [62, 58, 66, 61, 70, 64, 72, 69, 75, 71, 78, 74, 81, 77, 84, 80, 88, 85, 91, 94];

export default function ModulesDrawer({
  events,
  health,
  onSelectModule,
  onOpenBankPartner,
  onOpenModelCard,
}: {
  events: EventsResponse | null;
  health: HealthResponse | null;
  onSelectModule?: (type: "scam" | "counterfeit") => void;
  /** Opens the financial-institution (Bank Partner) B2B console. */
  onOpenBankPartner?: () => void;
  /** Opens the Model Card (measured metrics) panel. */
  onOpenModelCard?: () => void;
}) {
  const scam = events?.scams.at(-1) ?? null;
  const note = events?.counterfeits.at(-1) ?? null;
  const rings = events?.fraud_graph?.rings ?? [];
  const modules = Object.entries(health?.modules ?? {});
  const up = modules.filter(([, s]) => s === "up").length;
  const down = modules.length - up;
  const container = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    // Fade + subtle scale (compositor transform) instead of a positional slide
    // — `.glass` over the map re-blurs on a moving transform. Scale stays smooth.
    gsap.fromTo(".gsap-module-item",
      { opacity: 0, scale: 0.96, y: 10 },
      { opacity: 1, scale: 1, y: 0, duration: 0.4, stagger: 0.06,
        ease: "power3.out", force3D: true,
        willChange: "transform,opacity", clearProps: "all" },
    );
  }, { scope: container });

  const confidences = [
    ...(events?.scams.map((s) => s.risk_score) ?? []),
    ...(events?.counterfeits.map((c) => c.confidence) ?? []),
    ...rings.map((r) => r.risk_score),
  ];
  const avgConf = confidences.length
    ? confidences.reduce((a, b) => a + b, 0) / confidences.length
    : 0;

  const [citizenOpen, setCitizenOpen] = useState(false);

  return (
    <div ref={container} className="flex flex-col gap-3 p-4">
      {citizenOpen && <CitizenShieldPanel onClose={() => setCitizenOpen(false)} />}
      {/* module status */}
      <div className="gsap-module-item glass !rounded-none grid grid-cols-2 gap-2 p-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <CheckCircle className="h-3.5 w-3.5 text-emerald-400" /> Online
          </div>
          <div className="mt-1 text-3xl font-light">{up}</div>
        </div>
        <div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <AlertTriangle className="h-3.5 w-3.5 text-red-400" /> Offline
          </div>
          <div className="mt-1 text-3xl font-light">{down}</div>
        </div>
        <div className="col-span-2 mt-1 flex flex-wrap gap-1.5">
          {modules.map(([name, status]) => (
            <span
              key={name}
              className={`border px-2 py-0.5 text-[10px] ${
                status === "up"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-red-500/30 bg-red-500/10 text-red-300"
              }`}
            >
              {name}
            </span>
          ))}
          {modules.length === 0 && (
            <span className="text-[10px] text-zinc-500">waiting for backend…</span>
          )}
        </div>
      </div>

      {/* External Links & Features */}
      <div className="gsap-module-item glass !rounded-none p-4 space-y-3">
        <div className="text-xs font-semibold text-zinc-300 mb-2">Connected Websites</div>
        <div className="space-y-2">
          <button
            onClick={() => setCitizenOpen(true)}
            className="block w-full text-left p-2 bg-white/5 hover:bg-white/10 transition-colors border border-white/5"
          >
            <div className="flex items-center justify-between text-xs text-zinc-200">
              <span className="font-medium">Citizen Portal · Fraud Shield</span>
              <ArrowUpRight className="h-3 w-3" />
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Check scams in 22 languages · live-call detection.</div>
          </button>
          <a href="#" target="_blank" className="block p-2 bg-white/5 hover:bg-white/10 transition-colors border border-white/5">
            <div className="flex items-center justify-between text-xs text-zinc-200">
              <span className="font-medium">Investigator Dashboard</span>
              <ArrowUpRight className="h-3 w-3" />
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">Deep-dive graph analytics.</div>
          </a>
          <button
            onClick={onOpenBankPartner}
            className="block w-full text-left p-2 bg-white/5 hover:bg-white/10 transition-colors border border-white/5"
          >
            <div className="flex items-center justify-between text-xs text-zinc-200">
              <span className="font-medium">Bank Partner · AML</span>
              <ArrowUpRight className="h-3 w-3" />
            </div>
            <div className="text-[10px] text-zinc-400 mt-1">B2B account screening + note verify (API-key).</div>
          </button>
        </div>
        
        <div className="text-xs font-semibold text-zinc-300 mt-4 mb-2">Key Features</div>
        <ul className="text-[10px] text-zinc-400 space-y-1.5 list-disc pl-3">
          <li>Live scam call audio analysis using Fraud Shield</li>
          <li>Real-time currency note scanning with Counterfeit Vision</li>
          <li>Graph ML for tracing fraud rings</li>
          <li>Gen AI driven intelligence fusion</li>
        </ul>

        <button
          onClick={onOpenModelCard}
          className="mt-3 w-full flex items-center justify-between border border-emerald-500/25 bg-emerald-500/5 px-2.5 py-2 text-[11px] text-emerald-200 transition hover:border-emerald-400/50 hover:bg-emerald-500/10"
        >
          <span className="font-medium">📊 Model Card — measured metrics</span>
          <span className="text-[9px] uppercase tracking-widest text-emerald-400/70">P/R · FPR · AUC</span>
        </button>
      </div>

      {/* latest scam card */}
      <button onClick={() => onSelectModule?.("scam")} className="gsap-module-item glass !rounded-none glass-hover p-3 text-left relative group border !border-white/8 hover:!border-red-500/30 cursor-pointer">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-300">
            <Phone className="h-3.5 w-3.5 text-red-400" /> Scam Call
          </div>
          <span className="text-[10px] text-zinc-500">{clockTime(scam?.timestamp)}</span>
        </div>
        {scam ? (
          <>
            <div className="mt-2 flex items-center gap-2">
              <span className="bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-300">
                {scam.verdict}
              </span>
              <span className="text-lg font-light">{pct(scam.risk_score)}</span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-400">
              {titleCase(scam.scam_type ?? "unknown")}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(scam.markers ?? []).slice(0, 3).map((m) => (
                <span key={m} className="bg-white/5 px-1.5 py-0.5 text-[9px] text-zinc-400">
                  {m.replaceAll("_", " ")}
                </span>
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between">
              <div className="flex items-center gap-1 text-[10px] text-zinc-500">
                <MapPin className="h-3 w-3" /> {scam.location_hint?.district ?? "unknown"}
              </div>
              <div className="flex items-center gap-1 text-[10px] text-violet-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <Zap className="h-3 w-3" /> AI Summary
              </div>
            </div>
          </>
        ) : (
          <Empty />
        )}
      </button>

      {/* latest note card */}
      <button onClick={() => onSelectModule?.("counterfeit")} className="gsap-module-item glass !rounded-none glass-hover p-3 text-left relative group border !border-white/8 hover:!border-amber-500/30 cursor-pointer">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-300">
            <Banknote className="h-3.5 w-3.5 text-amber-400" /> Note Scan
          </div>
          <span className="text-[10px] text-zinc-500">{clockTime(note?.timestamp)}</span>
        </div>
        {note ? (
          <>
            <div className="mt-2 flex items-center gap-2">
              <span className="bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                {note.verdict}
              </span>
              <span className="text-lg font-light">{pct(note.confidence)}</span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-400">₹{note.denomination} note</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(note.missing_features ?? []).slice(0, 3).map((f) => (
                <span key={f} className="bg-white/5 px-1.5 py-0.5 text-[9px] text-zinc-400">
                  no {f.replaceAll("_", " ")}
                </span>
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between">
              <div className="flex items-center gap-1 text-[10px] text-zinc-500">
                <MapPin className="h-3 w-3" /> {note.location_hint?.district ?? "unknown"}
              </div>
              <div className="flex items-center gap-1 text-[10px] text-violet-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <Zap className="h-3 w-3" /> AI Summary
              </div>
            </div>
          </>
        ) : (
          <Empty />
        )}
      </button>
    </div>
  );
}

function Empty() {
  return <div className="mt-3 text-[11px] text-zinc-600">no data yet…</div>;
}
