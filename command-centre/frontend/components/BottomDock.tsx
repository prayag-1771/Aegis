"use client";

import { useEffect, useState } from "react";
import { runFusion, type FusionOutput, type EventsResponse } from "@/lib/api";
import { inr } from "@/lib/format";
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

export default function BottomDock({
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState("");
  const [showLinks, setShowLinks] = useState(false);

  const scamCount = events?.scams.filter((s) => s.verdict !== "legit").length ?? 0;
  const noteCount = events?.counterfeits.filter((c) => c.verdict === "fake").length ?? 0;
  const ringAccts = events?.fraud_graph?.rings.reduce((a, r) => a + r.size, 0) ?? 0;
  const total = scamCount + noteCount + ringAccts;

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
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      onError?.(`Fusion unavailable — ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glass pointer-events-auto absolute bottom-4 left-[52px] right-4 z-20 flex items-stretch gap-px overflow-hidden">
      {/* ── Left: Signal Summary Strip ── */}
      <div className="flex shrink-0 items-center gap-4 border-r border-white/5 px-5 py-3">
        <div className="text-center">
          <div className="text-xl font-light tabular-nums">{total.toLocaleString()}</div>
          <div className="text-[9px] uppercase tracking-widest text-zinc-500">signals</div>
        </div>
        <div className="flex gap-3 text-[10px] text-zinc-400">
          <span>
            <span className="font-semibold text-red-300">{scamCount}</span> scam
          </span>
          <span>
            <span className="font-semibold text-amber-300">{noteCount}</span> notes
          </span>
          <span>
            <span className="font-semibold text-violet-300">{ringAccts}</span> flagged
          </span>
        </div>
      </div>

      {/* ── Center: Intelligence Fusion ── */}
      <div className="flex min-w-0 flex-1 flex-col justify-center px-5 py-3">
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
            <p className="mt-1.5 min-h-8 text-[12px] font-light leading-relaxed text-zinc-100">
              {shown}
              {shown.length < (fusion.summary?.length ?? 0) && (
                <span className="animate-pulse text-zinc-500">▍</span>
              )}
            </p>
            {/* money trails */}
            {(fusion.money_trails ?? []).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {(fusion.money_trails ?? []).map((t) => (
                  <span
                    key={`${t.scam_event_id}-${t.account_id}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-950/40 px-2 py-0.5 text-[9px] text-red-200"
                  >
                    <span className="font-bold uppercase tracking-widest text-red-300">
                      trail
                    </span>
                    {inr(t.amount)} → {t.account_id}
                    {t.district ? ` · ${t.district}` : ""}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-1.5 flex items-center gap-3 text-[10px] text-zinc-500">
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
              {fusion.audit_trail && (
                <span className="ml-auto truncate font-mono">
                  audit {fusion.audit_trail.inputs_hash} · {fusion.audit_trail.model}
                </span>
              )}
            </div>
            {showLinks && (
              <div className="scroll-thin mt-1.5 max-h-24 space-y-1 overflow-y-auto">
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
          <p className="mt-1.5 text-[12px] font-light text-zinc-500">
            {error
              ? `fusion unavailable — ${error}`
              : "Standing by. Run fusion to correlate scam, counterfeit and fraud-ring signals into one intelligence package."}
          </p>
        )}
      </div>
    </section>
  );
}
