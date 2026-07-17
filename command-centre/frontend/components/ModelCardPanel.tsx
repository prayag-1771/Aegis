"use client";

import { useEffect, useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import { fetchMetrics, type MetricsResponse, type ModelCard, type MetricItem } from "@/lib/api";

/** Model Card — the measured numbers the evaluation focus scores, surfaced.
 *  Counterfeit accuracy, digital-arrest precision/recall, fraud-network detection
 *  and lead time, and the citizen-tool false-alarm rate — every value read from
 *  the model's own persisted report, with honest caveats where a criterion is not
 *  in the artifact. Nothing here is tuned for display. */

function fmt(m: MetricItem): string {
  if (m.value_text) return m.value_text;
  if (m.value == null) return "—";
  return m.value <= 1 ? `${(m.value * 100).toFixed(1)}%` : String(m.value);
}

export default function ModelCardPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchMetrics()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useGSAP(
    () => {
      gsap.fromTo(
        ".gsap-mc",
        { opacity: 0, y: 12, scale: 0.98 },
        { opacity: 1, y: 0, scale: 1, duration: 0.4, stagger: 0.06, ease: "power3.out", clearProps: "all" },
      );
    },
    { scope: container, dependencies: [data?.models.length] },
  );

  return (
    <div ref={container} className="relative h-full overflow-y-auto bg-zinc-950/95 p-6 scroll-thin">
      <button
        onClick={onClose}
        aria-label="Close Model Card"
        className="absolute right-4 top-4 z-10 border border-white/10 bg-zinc-900/80 p-2 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <div className="mb-5 pr-12 gsap-mc">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-zinc-100">Model Card · Measured Metrics</h2>
          <span className="border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-emerald-300">
            evaluation focus
          </span>
        </div>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
          {data?.disclaimer ??
            "Every figure is read from each model's persisted training/eval report — not recomputed here, not tuned for display."}
        </p>
      </div>

      {error ? (
        <div className="border border-red-500/20 bg-red-500/5 p-6 text-center text-sm text-red-300">{error}</div>
      ) : !data ? (
        <div className="p-8 text-center text-sm text-zinc-500">Loading measured metrics…</div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {data.models.map((m) => (
              <Card key={m.id} model={m} />
            ))}
          </div>

          {/* Lead-time framing */}
          <div className="gsap-mc mt-4 border border-white/10 bg-zinc-900/60 p-5">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
              Detection lead time
            </div>
            <p className="mt-1 text-[11px] text-zinc-400">{data.lead_time.summary}</p>
            <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
              {data.lead_time.points.map((p) => (
                <div key={p.stage} className="border border-white/10 bg-white/5 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-sky-300">{p.stage}</div>
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-300">{p.claim}</p>
                  <p className="mt-1 text-[9px] leading-relaxed text-zinc-600">measured: {p.measured}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[9px] leading-relaxed text-amber-500/70">{data.lead_time.caveat}</p>
          </div>
        </>
      )}
    </div>
  );
}

function Card({ model }: { model: ModelCard }) {
  return (
    <div className="gsap-mc flex flex-col border border-white/10 bg-zinc-900/60 p-5">
      <h3 className="text-sm font-semibold text-zinc-100">{model.name}</h3>
      {model.posture && (
        <div className="mt-1.5 flex items-center gap-2">
          <span
            className={`border px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${
              model.posture.label === "Predictive"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : model.posture.label === "Point-of-contact"
                ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                : "border-zinc-500/40 bg-zinc-500/10 text-zinc-400"
            }`}
            title={model.posture.detail}
          >
            {model.posture.label}
          </span>
          <span className="text-[9px] text-zinc-600">{model.posture.detail}</span>
        </div>
      )}
      <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">{model.task}</p>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {model.headline.map((h) => (
          <div key={h.label} className="border border-white/10 bg-black/20 p-2.5 text-center">
            <div className="text-xl font-light text-zinc-100">{fmt(h)}</div>
            <div className="mt-0.5 text-[9px] leading-tight text-zinc-500">{h.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {model.highlight && (
          <span className="border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
            {model.highlight.label}: <strong>{fmt(model.highlight)}</strong>
          </span>
        )}
        {model.false_alarm && (
          <span
            className="border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-zinc-300"
            title={model.false_alarm.basis}
          >
            {model.false_alarm.label}: {(model.false_alarm.value * 100).toFixed(1)}%
          </span>
        )}
      </div>

      {/* breakdown: recall-by-family bars or metric pairs */}
      {model.breakdown?.items && (
        <div className="mt-4">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            {model.breakdown.title}
          </div>
          <div className="space-y-1">
            {Object.entries(model.breakdown.items).map(([k, v]) => (
              <div key={k}>
                <div className="flex justify-between text-[9px] text-zinc-400">
                  <span>{k.replace(/_/g, " ")}</span>
                  <span>{(v * 100).toFixed(0)}%</span>
                </div>
                <div className="h-1 bg-white/5">
                  <div className={`h-1 ${v >= 0.9 ? "bg-emerald-500" : v >= 0.7 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${v * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {model.breakdown?.pairs && (
        <div className="mt-4">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            {model.breakdown.title}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {model.breakdown.pairs.map((p) => (
              <div key={p.label} className="border border-white/10 bg-black/20 p-2 text-center">
                <div className="text-sm font-light text-zinc-100">{fmt(p)}</div>
                <div className="mt-0.5 text-[8px] leading-tight text-zinc-500">{p.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto pt-3">
        <p className="text-[9px] leading-relaxed text-zinc-600">{model.dataset}</p>
        {model.caveats.map((c, i) => (
          <p key={i} className="mt-1 text-[9px] leading-relaxed text-amber-500/60">⚠ {c}</p>
        ))}
      </div>
    </div>
  );
}
