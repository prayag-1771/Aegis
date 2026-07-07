"use client";

import { useEffect, useState } from "react";
import { runFusion, type FusionOutput } from "@/lib/api";
import { Zap } from "./Icons";

const THREAT_TONE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-300 border-red-500/40",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  elevated: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  low: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
};

/** The fusion-moment reveal — calls the existing Gen AI layer via POST /api/fuse. */
export default function FusionPanel({
  fusion,
  onFused,
}: {
  fusion: FusionOutput | null;
  onFused: (f: FusionOutput) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState("");

  // typewriter reveal of the fusion summary
  useEffect(() => {
    const text = fusion?.summary ?? "";
    if (!text) return;
    let i = 0;
    setShown("");
    const t = setInterval(() => {
      i += 2;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(t);
    }, 14);
    return () => clearInterval(t);
  }, [fusion?.summary]);

  async function fire() {
    setBusy(true);
    setError(null);
    try {
      onFused(await runFusion());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glass pointer-events-auto absolute bottom-4 left-[23rem] right-[26.5rem] z-20 hidden p-4 lg:block">
      <div className="flex items-center gap-3">
        <div className="text-xs text-zinc-400">Intelligence Fusion</div>
        {fusion && (
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
              THREAT_TONE[fusion.threat_level] ?? "bg-white/5 text-zinc-300 border-white/10"
            }`}
          >
            {fusion.threat_level}
          </span>
        )}
        <button
          onClick={fire}
          disabled={busy}
          className="ml-auto flex items-center gap-1.5 rounded-full bg-zinc-100 px-4 py-1.5 text-xs font-semibold text-zinc-900 shadow transition hover:bg-white disabled:opacity-50"
        >
          <Zap className="h-3.5 w-3.5" />
          {busy ? "Correlating…" : "Run Fusion"}
        </button>
      </div>

      {fusion ? (
        <>
          <p className="mt-2 min-h-10 text-[13px] font-light leading-relaxed text-zinc-100">
            {shown}
            {shown.length < (fusion.summary?.length ?? 0) && (
              <span className="animate-pulse text-zinc-500">▍</span>
            )}
          </p>
          <div className="mt-2 flex items-center gap-4 text-[10px] text-zinc-500">
            <span>{fusion.linked_signals.length} linked signals</span>
            <span className="truncate">
              next: {fusion.recommended_actions[0] ?? "—"}
            </span>
            {fusion.audit_trail && (
              <span className="ml-auto font-mono">
                audit {fusion.audit_trail.inputs_hash} · {fusion.audit_trail.model}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="mt-2 text-[13px] font-light text-zinc-500">
          {error
            ? `fusion unavailable — ${error}`
            : "Standing by. Run fusion to correlate scam, counterfeit and fraud-ring signals into one intelligence package."}
        </p>
      )}
    </section>
  );
}
