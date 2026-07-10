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

const BASIS_LABEL: Record<string, string> = {
  shared_account: "money trail",
  shared_district: "same district",
  geospatial_overlap: "geo overlap",
  temporal_proximity: "time window",
  shared_phone: "same phone",
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
  const [showLinks, setShowLinks] = useState(false);

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
          {/* the money trail — hard cross-domain evidence, gets top billing */}
          {(fusion.money_trails ?? []).map((t) => (
            <div
              key={`${t.scam_event_id}-${t.account_id}`}
              className="mt-2 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-950/40 px-2.5 py-1.5"
            >
              <span className="rounded-full bg-red-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest text-red-300">
                money trail
              </span>
              <span className="text-[11px] text-red-100/90">
                ₹{t.amount.toLocaleString("en-IN")} → account{" "}
                <span className="font-mono">{t.account_id}</span> of {t.ring_id}
                {t.district ? ` · ${t.district}` : ""}
              </span>
            </div>
          ))}

          <div className="mt-2 flex items-center gap-3 text-[10px] text-zinc-500">
            <button
              onClick={() => setShowLinks((v) => !v)}
              className="transition hover:text-zinc-300"
            >
              {fusion.linked_signals.length} linked signals {showLinks ? "▴" : "▾"}
            </button>
            {fusion.correlation_basis.map((b) => (
              <span
                key={b}
                className={`rounded-full px-1.5 py-0.5 text-[9px] ${
                  b === "shared_account"
                    ? "bg-red-500/15 text-red-300"
                    : "bg-white/5 text-zinc-400"
                }`}
              >
                {BASIS_LABEL[b] ?? b.replaceAll("_", " ")}
              </span>
            ))}
            <span className="truncate">next: {fusion.recommended_actions[0] ?? "—"}</span>
            {fusion.audit_trail && (
              <span className="ml-auto font-mono">
                audit {fusion.audit_trail.inputs_hash} · {fusion.audit_trail.model}
              </span>
            )}
          </div>
          {showLinks && (
            <div className="scroll-thin mt-2 max-h-24 space-y-1 overflow-y-auto">
              {fusion.linked_signals.map((l, i) => (
                <div key={i} className="flex items-start gap-2 text-[10px]">
                  <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-zinc-400">
                    {l.type.replaceAll("_", " ")}
                  </span>
                  <span className="text-zinc-400">
                    <span className="font-mono text-zinc-500">{l.ref_event_id}</span>
                    {l.reason ? ` — ${l.reason}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
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
