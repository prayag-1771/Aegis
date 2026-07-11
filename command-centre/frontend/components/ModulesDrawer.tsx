"use client";

import type { EventsResponse, HealthResponse } from "@/lib/api";
import { clockTime, pct, titleCase } from "@/lib/format";
import {
  AlertTriangle,
  ArrowUpRight,
  Banknote,
  CheckCircle,
  MapPin,
  Phone,
} from "./Icons";

/* deterministic sparkline (no hydration mismatch) */
const SPARK = [62, 58, 66, 61, 70, 64, 72, 69, 75, 71, 78, 74, 81, 77, 84, 80, 88, 85, 91, 94];

/** Detection-module detail: live health of each engine + the latest scam and
 *  counterfeit verdicts. Lifted from the old LeftPanel so all bindings survive. */
export default function ModulesDrawer({
  events,
  health,
}: {
  events: EventsResponse | null;
  health: HealthResponse | null;
}) {
  const scam = events?.scams.at(-1) ?? null;
  const note = events?.counterfeits.at(-1) ?? null;
  const rings = events?.fraud_graph?.rings ?? [];
  const modules = Object.entries(health?.modules ?? {});
  const up = modules.filter(([, s]) => s === "up").length;
  const down = modules.length - up;

  const confidences = [
    ...(events?.scams.map((s) => s.risk_score) ?? []),
    ...(events?.counterfeits.map((c) => c.confidence) ?? []),
    ...rings.map((r) => r.risk_score),
  ];
  const avgConf = confidences.length
    ? confidences.reduce((a, b) => a + b, 0) / confidences.length
    : 0;

  return (
    <div className="flex flex-col gap-3 p-4">
      {/* module status */}
      <div className="glass grid grid-cols-2 gap-2 p-4">
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
              className={`rounded-full border px-2 py-0.5 text-[10px] ${
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

      {/* signal confidence */}
      <div className="glass p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span>Signal Confidence</span>
          <ArrowUpRight className="h-3.5 w-3.5" />
        </div>
        <div className="mt-1 flex items-end gap-2">
          <span className="text-3xl font-light">{(avgConf * 100).toFixed(1)}</span>
          <span className="pb-1 text-sm text-zinc-500">%</span>
          <span className="pb-1 text-[10px] text-zinc-500">target ≥ 90</span>
        </div>
        <svg viewBox="0 0 200 44" className="mt-2 h-11 w-full">
          <polyline
            points={SPARK.map((v, i) => `${(i / (SPARK.length - 1)) * 200},${44 - (v / 100) * 40}`).join(" ")}
            fill="none"
            stroke="#e4e4e7"
            strokeWidth="1.5"
          />
          <line x1="0" y1={44 - 0.9 * 40} x2="200" y2={44 - 0.9 * 40} stroke="#71717a" strokeWidth="0.75" strokeDasharray="3 3" />
        </svg>
      </div>

      {/* latest scam + note cards */}
      <div className="glass p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-300">
            <Phone className="h-3.5 w-3.5 text-red-400" /> Scam Call
          </div>
          <span className="text-[10px] text-zinc-500">{clockTime(scam?.timestamp)}</span>
        </div>
        {scam ? (
          <>
            <div className="mt-2 flex items-center gap-2">
              <span className="rounded-md bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-300">
                {scam.verdict}
              </span>
              <span className="text-lg font-light">{pct(scam.risk_score)}</span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-400">
              {titleCase(scam.scam_type ?? "unknown")}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(scam.markers ?? []).slice(0, 3).map((m) => (
                <span key={m} className="rounded-full bg-white/5 px-1.5 py-0.5 text-[9px] text-zinc-400">
                  {m.replaceAll("_", " ")}
                </span>
              ))}
            </div>
            <div className="mt-2 flex items-center gap-1 text-[10px] text-zinc-500">
              <MapPin className="h-3 w-3" /> {scam.location_hint?.district ?? "unknown"}
            </div>
          </>
        ) : (
          <Empty />
        )}
      </div>

      <div className="glass p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-300">
            <Banknote className="h-3.5 w-3.5 text-amber-400" /> Note Scan
          </div>
          <span className="text-[10px] text-zinc-500">{clockTime(note?.timestamp)}</span>
        </div>
        {note ? (
          <>
            <div className="mt-2 flex items-center gap-2">
              <span className="rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                {note.verdict}
              </span>
              <span className="text-lg font-light">{pct(note.confidence)}</span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-400">₹{note.denomination} note</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(note.missing_features ?? []).slice(0, 3).map((f) => (
                <span key={f} className="rounded-full bg-white/5 px-1.5 py-0.5 text-[9px] text-zinc-400">
                  no {f.replaceAll("_", " ")}
                </span>
              ))}
            </div>
            <div className="mt-2 flex items-center gap-1 text-[10px] text-zinc-500">
              <MapPin className="h-3 w-3" /> {note.location_hint?.district ?? "unknown"}
            </div>
          </>
        ) : (
          <Empty />
        )}
      </div>
    </div>
  );
}

function Empty() {
  return <div className="mt-3 text-[11px] text-zinc-600">no data yet…</div>;
}
