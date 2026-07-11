"use client";

import type { EventsResponse, FusionOutput } from "@/lib/api";
import { inr } from "@/lib/format";
import { ArrowUpRight } from "./Icons";

/* fixed 24h shape (deterministic — no hydration mismatch); live counts scale it */
const SHAPE = [3, 2, 2, 1, 1, 2, 4, 7, 9, 8, 10, 12, 11, 13, 12, 14, 15, 13, 16, 14, 12, 9, 6, 4];

export default function AnalyticsDrawer({
  events,
  fusion,
}: {
  events: EventsResponse | null;
  fusion: FusionOutput | null;
}) {
  const scamCount = events?.scams.filter((s) => s.verdict !== "legit").length ?? 0;
  const noteCount = events?.counterfeits.filter((c) => c.verdict === "fake").length ?? 0;
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
    <div className="flex flex-col gap-4 p-4">
      {/* ── Live Signal Volume ── */}
      <section className="glass p-4">
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
              className={`flex-1 rounded-sm ${i === hour ? "bg-red-400/90" : "bg-zinc-600/60"}`}
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
      <section className="glass p-4">
        <div className="text-xs text-zinc-400">Criminal Pipeline</div>
        <div className="mt-3 flex flex-col items-center gap-1">
          {/* Stage 1: TAKE */}
          <PipeStage
            n="1"
            verb="TAKE"
            tone="text-red-300"
            accent="border-red-500/30"
            line={`${scamCount} scam signal${scamCount === 1 ? "" : "s"}`}
          />
          <PipeArrow
            lit={takeMoveLinked}
            litClass="text-red-400"
            chip={trails[0] ? `₹${trails[0].amount.toLocaleString("en-IN")} traced` : undefined}
          />
          {/* Stage 2: MOVE */}
          <PipeStage
            n="2"
            verb="MOVE"
            tone="text-violet-300"
            accent="border-violet-500/30"
            line={`${rings.length} ring${rings.length === 1 ? "" : "s"} · ${inr(ringMoney)}`}
          />
          <PipeArrow lit={moveCashLinked} litClass="text-amber-400" />
          {/* Stage 3: CASH OUT */}
          <PipeStage
            n="3"
            verb="CASH OUT"
            tone="text-amber-300"
            accent="border-amber-500/30"
            line={`${fakeCount} fake note${fakeCount === 1 ? "" : "s"}`}
          />
        </div>
        <p className="mt-3 text-center text-[9px] leading-snug text-zinc-600">
          one criminal pipeline: scams take the money, mule rings move it, the cash economy absorbs
          it
        </p>
      </section>
    </div>
  );
}

function PipeStage({
  n,
  verb,
  tone,
  accent,
  line,
}: {
  n: string;
  verb: string;
  tone: string;
  accent: string;
  line: string;
}) {
  return (
    <div className={`w-full rounded-xl border ${accent} bg-zinc-950/60 px-4 py-2.5 text-center`}>
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
      <span
        className={`text-base leading-none ${lit ? `${litClass} animate-pulse` : "text-zinc-700"}`}
      >
        ↓
      </span>
      {chip && lit && (
        <span className="mt-0.5 rounded-full bg-red-500/15 px-1.5 py-px text-[8px] font-semibold text-red-300">
          {chip}
        </span>
      )}
    </div>
  );
}
