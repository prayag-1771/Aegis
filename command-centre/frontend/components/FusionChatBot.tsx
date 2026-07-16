"use client";

import { useEffect, useState } from "react";
import { runFusion, type FusionOutput, type EventsResponse } from "@/lib/api";
import { inr } from "@/lib/format";
import { Zap, X, Shield, Activity, ArrowUpRight } from "./Icons";

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

export default function FusionChatBot({
  fusion,
  events,
  onFused,
  onError,
}: {
  fusion: FusionOutput | null;
  events: EventsResponse | null;
  onFused: (f: FusionOutput) => void;
  onError?: (msg: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState("");
  const [showLinks, setShowLinks] = useState(false);

  // Typewriter reveal of the fusion summary
  useEffect(() => {
    const text = fusion?.summary ?? "";
    if (!text || !isOpen) return;
    let i = 0;
    setShown("");
    const t = setInterval(() => {
      i += 2;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(t);
    }, 14);
    return () => clearInterval(t);
  }, [fusion?.summary, isOpen]);

  async function fire() {
    setBusy(true);
    setError(null);
    try {
      const result = await runFusion();
      onFused(result);
      if (!isOpen) setIsOpen(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      onError?.(`Fusion unavailable — ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed bottom-6 right-16 z-50 pointer-events-none flex flex-col items-end">
      {/* Expanded Chat Window — pointer-events only when actually open, so the
          collapsed (scale-0/opacity-0) panel's still-present layout box can't
          eat clicks over the alerts drawer / "view all alerts" behind it. */}
      <div
        className={`mb-4 w-96 rounded-2xl border border-white/10 bg-zinc-950/90 backdrop-blur-xl shadow-2xl transition-all duration-500 origin-bottom-right ${
          isOpen ? "scale-100 opacity-100 pointer-events-auto" : "scale-50 opacity-0 pointer-events-none"
        }`}
      >
        <div className="flex items-center justify-between border-b border-white/5 bg-zinc-900/50 px-4 py-3 rounded-t-2xl">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-600 shadow-[0_0_10px_rgba(139,92,246,0.5)]">
              <Zap className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-sm font-semibold text-zinc-100">Aegis Fusion AI</span>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="rounded-full p-1.5 text-zinc-400 hover:bg-white/10 hover:text-zinc-100 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-4 scroll-thin">
          {fusion ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${
                    THREAT_TONE[fusion.threat_level] ?? "bg-white/5 text-zinc-300 border-white/10"
                  }`}
                >
                  {fusion.threat_level} THREAT
                </span>
                {fusion.audit_trail && (
                  <span className="text-[9px] text-zinc-500 font-mono ml-auto">
                    {fusion.audit_trail.model}
                  </span>
                )}
              </div>

              <div className="rounded-xl bg-white/5 p-4 border border-white/5 relative">
                <div className="absolute -left-1 top-4 w-2 h-2 rounded-full bg-violet-500 animate-ping"></div>
                <p className="text-sm font-light leading-relaxed text-zinc-100">
                  {shown}
                  {shown.length < (fusion.summary?.length ?? 0) && (
                    <span className="animate-pulse text-violet-400">▍</span>
                  )}
                </p>
              </div>

              {/* money trails */}
              {(fusion.money_trails ?? []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(fusion.money_trails ?? []).map((t) => (
                    <span
                      key={`${t.scam_event_id}-${t.account_id}`}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-950/40 px-2.5 py-1.5 text-[10px] text-red-200"
                    >
                      <Activity className="h-3 w-3 text-red-400" />
                      <span className="font-bold">TRAIL</span>
                      {inr(t.amount)} <ArrowUpRight className="h-2.5 w-2.5" /> {t.account_id}
                      {t.district ? ` · ${t.district}` : ""}
                    </span>
                  ))}
                </div>
              )}

              <div className="flex flex-col gap-2 pt-2 border-t border-white/5">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowLinks((v) => !v)}
                    className="text-[11px] text-zinc-400 transition hover:text-zinc-200"
                  >
                    {fusion.linked_signals.length} linked signals {showLinks ? "▴" : "▾"}
                  </button>
                </div>
                
                <div className="flex flex-wrap gap-1.5">
                  {fusion.correlation_basis.map((b) => (
                    <span
                      key={b}
                      className={`rounded-full px-2 py-0.5 text-[9px] ${
                        b === "shared_account"
                          ? "bg-red-500/15 text-red-300"
                          : "bg-white/5 text-zinc-400"
                      }`}
                    >
                      {BASIS_LABEL[b] ?? b.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>

                {showLinks && (
                  <div className="mt-2 space-y-1.5 bg-black/20 p-2 rounded-lg">
                    {fusion.linked_signals.map((l, i) => (
                      <div key={i} className="flex items-start gap-2 text-[10px]">
                        <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-zinc-300 font-medium">
                          {l.type.replaceAll("_", " ")}
                        </span>
                        <span className="text-zinc-400 leading-tight">
                          <span className="font-mono text-zinc-500 mr-1">{l.ref_event_id}</span>
                          {l.reason ? l.reason : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <Shield className="h-10 w-10 text-zinc-700 mb-3" />
              <p className="text-sm font-light text-zinc-400 max-w-[200px]">
                {error
                  ? `Error: ${error}`
                  : "Standing by. Run fusion to correlate signals."}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Floating Action Button — pointer-events-auto because the container is
          now pointer-events-none (so its empty area doesn't block clicks). */}
      <button
        onClick={() => (fusion ? setIsOpen(!isOpen) : fire())}
        disabled={busy}
        className="pointer-events-auto group relative flex h-14 items-center gap-3 rounded-full bg-zinc-100 pl-4 pr-5 font-semibold text-zinc-900 shadow-[0_0_20px_rgba(255,255,255,0.15)] transition-all hover:scale-105 hover:bg-white hover:shadow-[0_0_30px_rgba(255,255,255,0.3)] disabled:opacity-50"
      >
        <div className={`flex h-8 w-8 items-center justify-center rounded-full bg-zinc-900 transition-transform ${busy ? "animate-spin" : "group-hover:rotate-12"}`}>
          <Zap className="h-4 w-4 text-zinc-100" />
        </div>
        <span className="text-sm tracking-wide">
          {busy ? "Correlating…" : fusion && !isOpen ? "View Fusion" : "Run Fusion"}
        </span>
      </button>
    </div>
  );
}
