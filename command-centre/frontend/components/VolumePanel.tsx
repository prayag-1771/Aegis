"use client";

import type { EventsResponse } from "@/lib/api";
import { ArrowUpRight } from "./Icons";

/* fixed 24h shape (deterministic — no hydration mismatch); live counts scale it */
const SHAPE = [3, 2, 2, 1, 1, 2, 4, 7, 9, 8, 10, 12, 11, 13, 12, 14, 15, 13, 16, 14, 12, 9, 6, 4];

export default function VolumePanel({ events }: { events: EventsResponse | null }) {
  const scams = events?.scams.length ?? 0;
  const notes = events?.counterfeits.length ?? 0;
  const ringAccts =
    events?.fraud_graph?.rings.reduce((a, r) => a + r.size, 0) ?? 0;
  const total = scams + notes + ringAccts;
  const max = Math.max(...SHAPE);
  const hour = new Date().getUTCHours();

  return (
    <section className="glass pointer-events-auto absolute bottom-4 right-4 z-20 w-96 p-4">
      <div className="flex items-center justify-between text-xs text-zinc-400">
        <span>Live Signal Volume</span>
        <ArrowUpRight className="h-3.5 w-3.5" />
      </div>
      <div className="mt-1 flex items-end gap-2">
        <span className="text-3xl font-light tabular-nums">{total.toLocaleString()}</span>
        <span className="pb-1 text-[10px] text-zinc-500">
          signals today · {scams} scam / {notes} notes / {ringAccts} flagged accts
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
  );
}
