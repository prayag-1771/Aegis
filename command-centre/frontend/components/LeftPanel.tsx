"use client";

import type { EventsResponse, HealthResponse, HotspotsResponse } from "@/lib/api";
import { clockTime, inr, pct, titleCase } from "@/lib/format";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Banknote,
  CheckCircle,
  MapPin,
  Network,
  Phone,
} from "./Icons";

/* deterministic sparkline (no hydration mismatch) */
const SPARK = [62, 58, 66, 61, 70, 64, 72, 69, 75, 71, 78, 74, 81, 77, 84, 80, 88, 85, 91, 94];

export default function LeftPanel({
  events,
  health,
  hotspots,
}: {
  events: EventsResponse | null;
  health: HealthResponse | null;
  hotspots: HotspotsResponse | null;
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
    <aside className="pointer-events-auto absolute bottom-4 left-4 top-16 z-20 flex w-[21.5rem] flex-col gap-3 overflow-y-auto pr-1 scroll-thin">
      {/* stat pills */}
      <div className="grid grid-cols-4 gap-2">
        <Pill label="Scams" value={events?.scams.length ?? 0} tone="text-red-300" />
        <Pill label="Notes" value={events?.counterfeits.length ?? 0} tone="text-amber-300" />
        <Pill label="Rings" value={rings.length} tone="text-violet-300" />
        <Pill label="Hubs" value={hotspots?.hubs.length ?? 0} tone="text-emerald-300" />
      </div>

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
      <div className="grid grid-cols-2 gap-2">
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
                {(scam.markers ?? []).slice(0, 2).map((m) => (
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
                {(note.missing_features ?? []).slice(0, 2).map((f) => (
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

      {/* fraud rings */}
      <div className="glass p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <div className="flex items-center gap-1.5">
            <Network className="h-3.5 w-3.5 text-violet-400" /> Fraud Rings
          </div>
          <Activity className="h-3.5 w-3.5" />
        </div>
        <div className="mt-3 space-y-2.5">
          {rings.slice(0, 4).map((r) => (
            <div key={r.ring_id}>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-zinc-300">
                  {r.ring_id} · {r.label ?? "ring"}
                </span>
                <span className="text-zinc-500">
                  {r.size} accts · {inr(r.total_amount)}
                </span>
              </div>
              <div className="mt-1 h-1 rounded bg-white/5">
                <div
                  className="h-1 rounded bg-gradient-to-r from-violet-500 to-fuchsia-400"
                  style={{ width: `${Math.round(r.risk_score * 100)}%` }}
                />
              </div>
            </div>
          ))}
          {rings.length === 0 && <Empty />}
        </div>
      </div>
    </aside>
  );
}

function Pill({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="glass px-2 py-2 text-center">
      <div className={`text-lg font-light leading-none ${tone}`}>{value}</div>
      <div className="mt-1 text-[9px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

function Empty() {
  return <div className="mt-3 text-[11px] text-zinc-600">no data yet…</div>;
}
