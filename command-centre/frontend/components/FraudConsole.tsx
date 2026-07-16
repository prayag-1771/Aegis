"use client";

import { useState } from "react";
import { scoreCustom, type ConsoleResult, type ConsoleTx } from "@/lib/api";
import { X } from "./Icons";

const DISTRICTS = [
  "Jamtara",
  "Deoghar",
  "Alwar",
  "Bharatpur",
  "Nuh",
  "Chennai Central",
  "Mumbai South",
  "Delhi East",
];

type Row = { source: string; target: string; amount: string };

const EMPTY_ROW: Row = { source: "", target: "", amount: "" };

/* two starting points a presenter can fill in one click, then edit freely */
const PRESET_LAUNDER: Row[] = [
  { source: "ravi", target: "pinky", amount: "250000" },
  { source: "pinky", target: "quickcash", amount: "245000" },
  { source: "quickcash", target: "ravi", amount: "240000" },
  { source: "ravi", target: "pinky", amount: "238000" },
  { source: "pinky", target: "quickcash", amount: "233000" },
  { source: "quickcash", target: "ravi", amount: "229000" },
];
const PRESET_NORMAL: Row[] = [
  { source: "meena", target: "landlord", amount: "12500" },
  { source: "meena", target: "grocer", amount: "1840" },
  { source: "employer", target: "meena", amount: "45000" },
];

export default function FraudConsole({
  onClose,
  onCommitted,
}: {
  onClose: () => void;
  onCommitted?: (district: string) => void;
}) {
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY_ROW }, { ...EMPTY_ROW }, { ...EMPTY_ROW }]);
  const [district, setDistrict] = useState(DISTRICTS[0]);
  const [speed, setSpeed] = useState<"minutes" | "days">("minutes");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ConsoleResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const parsed: ConsoleTx[] = rows
    .filter((r) => r.source.trim() && r.target.trim() && Number(r.amount) > 0)
    .map((r) => ({
      source: r.source.trim(),
      target: r.target.trim(),
      amount: Number(r.amount),
    }));

  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const loopBack = () => {
    const valid = rows.filter((r) => r.source.trim() && r.target.trim());
    if (valid.length === 0) return;
    const last = valid[valid.length - 1];
    const first = valid[0];
    setRows((rs) => [
      ...rs.filter((r) => r.source.trim() || r.target.trim() || r.amount.trim()),
      { source: last.target, target: first.source, amount: last.amount || "" },
    ]);
  };

  const run = async () => {
    if (parsed.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await scoreCustom({ district, speed, transactions: parsed });
      setResult(res);
      if (res.committed) onCommitted?.(district);
    } catch (e) {
      setError(e instanceof Error ? e.message : "scoring failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-zinc-950/70 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="glass max-h-[88vh] w-[620px] max-w-[94vw] overflow-y-auto p-5 scroll-thin animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Fraud Console</h2>
            <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-400">
              You design the money movement — the engine has never seen these accounts.
              Build laundering or a normal day; see what it flags (and what it doesn&apos;t).
            </p>
          </div>
          <button onClick={onClose} className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* presets */}
        <div className="mt-3 flex gap-2 text-[10px]">
          <button
            onClick={() => {
              setRows(PRESET_LAUNDER.map((r) => ({ ...r })));
              setSpeed("minutes");
              setResult(null);
            }}
            className="rounded-full border border-red-500/25 bg-red-500/10 px-2.5 py-1 text-red-300 transition-colors hover:border-red-400/50 hover:bg-red-500/15"
          >
            example: laundering loop
          </button>
          <button
            onClick={() => {
              setRows(PRESET_NORMAL.map((r) => ({ ...r })));
              setSpeed("days");
              setResult(null);
            }}
            className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-emerald-300 transition-colors hover:border-emerald-400/50 hover:bg-emerald-500/15"
          >
            example: normal day
          </button>
        </div>

        {/* transaction rows */}
        <div className="mt-3 space-y-1.5">
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <input
                value={r.source}
                onChange={(e) => setRow(i, { source: e.target.value })}
                placeholder="from"
                className="w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/70 px-2.5 py-1.5 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none transition-colors focus:border-violet-400/60"
              />
              <span className="text-[11px] text-zinc-600">→</span>
              <input
                value={r.target}
                onChange={(e) => setRow(i, { target: e.target.value })}
                placeholder="to"
                className="w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/70 px-2.5 py-1.5 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none transition-colors focus:border-violet-400/60"
              />
              <input
                value={r.amount}
                onChange={(e) => setRow(i, { amount: e.target.value.replace(/[^\d]/g, "") })}
                placeholder="₹ amount"
                inputMode="numeric"
                className="w-24 rounded-lg border border-white/10 bg-zinc-950/70 px-2.5 py-1.5 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-violet-400/60"
              />
              <button
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                className="px-1 text-zinc-600 transition hover:text-red-400"
                title="remove"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
          <button
            onClick={() => setRows((rs) => [...rs, { ...EMPTY_ROW }])}
            className="rounded-lg border border-white/10 px-2.5 py-1.5 text-zinc-300 transition hover:border-white/25"
          >
            + transaction
          </button>
          <button
            onClick={loopBack}
            className="rounded-lg border border-white/10 px-2.5 py-1.5 text-zinc-300 transition hover:border-white/25"
            title="add a transfer closing the loop back to the first account"
          >
            ↺ loop it back
          </button>
          <span className="ml-auto" />
          <select
            value={district}
            onChange={(e) => setDistrict(e.target.value)}
            className="rounded-lg border border-white/10 bg-zinc-950/70 px-2 py-1.5 text-zinc-200 outline-none"
          >
            {DISTRICTS.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <select
            value={speed}
            onChange={(e) => setSpeed(e.target.value as "minutes" | "days")}
            className="rounded-lg border border-white/10 bg-zinc-950/70 px-2 py-1.5 text-zinc-200 outline-none"
            title="tempo of the transfers — laundering moves in minutes, life moves in days"
          >
            <option value="minutes">minutes apart</option>
            <option value="days">days apart</option>
          </select>
          <button
            onClick={run}
            disabled={busy || parsed.length === 0}
            className="btn-primary rounded-lg px-3 py-1.5 text-[11px] font-semibold text-white disabled:cursor-wait disabled:opacity-50 disabled:shadow-none"
          >
            {busy ? "Scoring…" : "Run detection"}
          </button>
        </div>

        {error && (
          <div className="mt-3 animate-slide-up rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[11px] text-red-300">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-3 animate-slide-up">
            {result.ring ? (
              <div className="rounded-xl border border-red-500/30 bg-red-950/40 p-3">
                <div className="text-[11px] font-bold uppercase tracking-widest text-red-300">
                  ⚠ Fraud ring detected
                </div>
                <div className="mt-1 text-[11px] text-red-100/90">
                  {result.ring.label ?? "fraud ring"} · {result.ring.size} accounts · risk{" "}
                  {Math.round(result.ring.risk_score * 100)}%
                  {result.committed ? ` — now live on the map in ${district}` : ""}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-emerald-500/25 bg-emerald-950/40 p-3">
                <div className="text-[11px] font-bold uppercase tracking-widest text-emerald-300">
                  ✓ No fraud pattern
                </div>
                <div className="mt-1 text-[11px] text-emerald-100/80">
                  This looks like ordinary behaviour — nothing was flagged. (Try the laundering
                  preset to see the difference.)
                </div>
              </div>
            )}

            <div className="mt-2 space-y-1.5">
              {result.accounts.map((a) => (
                <div key={a.account_id}>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-zinc-300">{a.account_id}</span>
                    <span className={a.in_ring ? "text-red-300" : "text-zinc-500"}>
                      {(a.illicit_probability * 100).toFixed(1)}% illicit
                      {a.in_ring ? " · in ring" : ""}
                    </span>
                  </div>
                  <div className="mt-0.5 h-1 rounded bg-white/5">
                    <div
                      className={`h-1 rounded ${
                        a.illicit_probability >= 0.5
                          ? "bg-gradient-to-r from-red-500 to-rose-400"
                          : "bg-gradient-to-r from-emerald-600 to-emerald-400"
                      }`}
                      style={{ width: `${Math.max(Math.round(a.illicit_probability * 100), 2)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
