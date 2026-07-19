"use client";

/**
 * ResearchPanel — the three research modules made visible.
 *
 * Ghost Ring, the adversarial arms race, and the spectral lens all ran as
 * CLI-only code with real, tested results that nobody could see. This renders
 * those results as charts, from precomputed artifacts (GET /research).
 *
 * Honesty is the design constraint, not a footnote. Two of the three carry a
 * genuine caveat — Ghost Ring's matching precision, and the spectral method's
 * weak per-community flag — and those caveats are shown next to the numbers,
 * not buried. A judge who asks "does this actually work?" should be able to
 * read the honest answer straight off the panel.
 */

import { useEffect, useRef, useState } from "react";
import { fetchResearch, type ResearchResponse, type SpectralData } from "@/lib/api";

export default function ResearchPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchResearch()
      .then(setData)
      .catch(() => setError("Could not load research results — is the backend running?"));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="gsap-panel relative h-full overflow-y-auto p-6 scroll-thin">      <div className="mb-6 pr-12">
        <h2 className="text-lg font-semibold text-zinc-100">Research Lab</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Three graph-ML experiments, shown with their real measured numbers — caveats included.
        </p>
      </div>

      {error ? (
        <div className="p-8 text-center text-sm text-zinc-500">{error}</div>
      ) : !data ? (
        <div className="p-8 text-center text-sm text-zinc-500">Loading research results…</div>
      ) : (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <GhostRingCard ring={data.ghost_ring} />
          <ArmsRaceCard arms={data.arms_race} />
          <SpectralCard spectral={data.spectral} />
        </div>
      )}
    </div>
  );
}

/* ── shared card shell ─────────────────────────────────────────────────── */

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col border border-white/10 bg-zinc-900/60 p-5">
      <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
      <p className="mt-0.5 mb-4 text-[11px] leading-relaxed text-zinc-500">{subtitle}</p>
      {children}
    </div>
  );
}

function Empty({ what }: { what: string }) {
  return (
    <div className="border border-dashed border-white/10 p-4 text-center text-[11px] text-zinc-600">
      {what} not generated yet.
      <br />
      Run the fraud-graph CLI to produce it.
    </div>
  );
}

function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}

/* ── 1. Ghost Ring ─────────────────────────────────────────────────────── */

function GhostRingCard({ ring }: { ring: ResearchResponse["ghost_ring"] }) {
  return (
    <Card
      title="Ghost Ring"
      subtitle="Isolated banks reveal a shared ring by exchanging only embeddings. Does fusing beat any bank alone?"
    >
      {!ring ? (
        <Empty what="Ghost Ring result" />
      ) : (
        <>
          {(() => {
            const perBank = Object.entries(ring.per_bank_ring_recall).sort();
            const max = Math.max(ring.fused_ring_recall, ...perBank.map(([, v]) => v), 0.01);
            const bar = (label: string, v: number, highlight = false) => (
              <div key={label} className="mb-1.5">
                <div className="mb-0.5 flex justify-between text-[10px]">
                  <span className={highlight ? "font-semibold text-violet-300" : "text-zinc-400"}>
                    {label}
                  </span>
                  <span className={highlight ? "font-semibold text-violet-300" : "text-zinc-500"}>
                    {pct(v)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden bg-white/5">
                  <div
                    className={`h-full ${highlight ? "bg-violet-500" : "bg-zinc-600"}`}
                    style={{ width: `${(v / max) * 100}%` }}
                  />
                </div>
              </div>
            );
            return (
              <>
                {perBank.map(([k, v]) => bar(`Bank ${k} alone`, v))}
                {bar("Fused (all banks)", ring.fused_ring_recall, true)}
              </>
            );
          })()}

          {(() => {
            const bestBank = Math.max(...Object.values(ring.per_bank_ring_recall));
            const fusionWins = ring.fused_ring_recall > bestBank;
            return (
              <>
                <div className="mt-3 bg-white/5 p-2.5 text-[10px]">
                  <div className="flex justify-between text-zinc-400">
                    <span>Fused vs best single bank</span>
                    <span className={fusionWins ? "font-semibold text-emerald-400" : "font-semibold text-red-400"}>
                      {pct(ring.fused_ring_recall)} vs {pct(bestBank)}
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between text-zinc-500">
                    <span>Recall gap (fused − avg bank)</span>
                    <span>
                      {ring.recall_gap >= 0 ? "+" : ""}
                      {pct(ring.recall_gap)}
                    </span>
                  </div>
                  {ring.best_min_score != null && (
                    <div className="mt-1 flex justify-between text-zinc-500">
                      <span>Match threshold used</span>
                      <span>{ring.best_min_score.toFixed(2)}</span>
                    </div>
                  )}
                </div>

                {/* The verdict the whole method turns on — shown, not hidden.
                    The honest headline moved: matching precision is solved on
                    this data (0% false merges), so the card must not reassure
                    while fusion loses to a single bank's own view. */}
                <div
                  className={`mt-2 border p-2.5 text-[10px] leading-relaxed ${
                    fusionWins
                      ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-200/70"
                      : "border-red-500/25 bg-red-500/5 text-red-200/80"
                  }`}
                >
                  {fusionWins ? (
                    <>
                      <span className="font-semibold">Fusion beats every single bank on this run.</span>{" "}
                      Read together with the false-merge rate ({pct(ring.false_merge_rate)}) — either
                      number alone misleads.
                    </>
                  ) : (
                    <>
                      <span className="font-semibold">
                        Fusion did not beat the best single bank ({pct(ring.fused_ring_recall)} vs{" "}
                        {pct(bestBank)}) — reported as a genuine negative.
                      </span>{" "}
                      The privacy mechanism itself held: no raw data left any bank and{" "}
                      {pct(1 - ring.false_merge_rate)} of matched links were real cross-bank edges.
                      The loss is in the fusion/detection step — turning this positive is research,
                      not tuning.
                    </>
                  )}
                </div>
              </>
            );
          })()}
        </>
      )}
    </Card>
  );
}

/* ── 2. Arms Race ──────────────────────────────────────────────────────── */

function ArmsRaceCard({ arms }: { arms: ResearchResponse["arms_race"] }) {
  return (
    <Card
      title="Criminal Trains the Cop"
      subtitle="Criminal strategies evolve to evade the detector; the detector retrains. The card reports whatever the run actually shows — a healthy loop is a see-saw."
    >
      {!arms || arms.generation.length < 2 ? (
        <Empty what="Arms-race history" />
      ) : (
        <>
          <LineChart
            gens={arms.generation}
            series={[
              { label: "Best escape rate", values: arms.escape_rate, color: "#ef4444" },
              ...(arms.mean_escape_rate
                ? [{ label: "Mean escape (population)", values: arms.mean_escape_rate, color: "#f59e0b" }]
                : []),
              { label: "Detector recall", values: arms.detector_recall, color: "#22c55e" },
            ]}
            retrained={arms.retrained_generations}
          />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
            <span className="flex items-center gap-1.5 text-zinc-400">
              <span className="h-2 w-2 rounded-full bg-red-500" /> best escape
            </span>
            {arms.mean_escape_rate && (
              <span className="flex items-center gap-1.5 text-zinc-400">
                <span className="h-2 w-2 rounded-full bg-amber-500" /> mean escape
              </span>
            )}
            <span className="flex items-center gap-1.5 text-zinc-400">
              <span className="h-2 w-2 rounded-full bg-green-500" /> detector recall
            </span>
            <span className="flex items-center gap-1.5 text-zinc-500">
              <span className="h-3 w-px bg-violet-400" /> retrain
            </span>
          </div>

          {/* Verdict computed from the series — the caption must never claim
              a see-saw the chart does not show. */}
          {(() => {
            // Judge calibration on the honest series: population mean when
            // available (best-of-50 saturates by construction).
            const escape = arms.mean_escape_rate ?? arms.escape_rate;
            const recall = arms.detector_recall;
            const finalRecall = recall[recall.length - 1] ?? 0;
            const saturated =
              escape.filter((v) => v >= 0.95).length >= Math.ceil(escape.length * 0.8);
            const collapsed = finalRecall < 0.3;
            if (saturated && collapsed) {
              return (
                <div className="mt-2 border border-amber-500/25 bg-amber-500/5 p-2.5 text-[10px] leading-relaxed text-amber-200/80">
                  <span className="font-semibold">Mis-calibrated run — no arms race yet.</span>{" "}
                  The criminal escapes ~100% from the start and the detector ends at{" "}
                  {pct(finalRecall)} recall, with {arms.retrained_generations.length} retrain(s) in{" "}
                  {arms.generation.length} generations. The loop needs a tighter evasion budget and
                  more frequent retraining before this chart shows a genuine see-saw.
                </div>
              );
            }
            return (
              <div className="mt-2 border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-[10px] leading-relaxed text-emerald-200/70">
                Final generation: escape {pct(escape[escape.length - 1] ?? 0)}, detector recall{" "}
                {pct(finalRecall)}, after {arms.retrained_generations.length} retrain(s).
              </div>
            );
          })()}

          <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
            The criminal can only invent tricks the simulator can express — the arms race is real
            but bounded by what the generator models.
          </p>
        </>
      )}
    </Card>
  );
}

function LineChart({
  gens,
  series,
  retrained,
}: {
  gens: number[];
  series: { label: string; values: number[]; color: string }[];
  retrained: number[];
}) {
  const W = 300;
  const H = 150;
  const P = 6;
  const g0 = gens[0];
  const g1 = gens[gens.length - 1];
  const x = (g: number) => P + ((g - g0) / Math.max(g1 - g0, 1)) * (W - 2 * P);
  const y = (v: number) => H - P - v * (H - 2 * P); // values in [0,1]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
      {[0.25, 0.5, 0.75].map((g) => (
        <line key={g} x1={P} x2={W - P} y1={y(g)} y2={y(g)} stroke="rgba(255,255,255,0.05)" />
      ))}
      {retrained.map((g) => (
        <line key={g} x1={x(g)} x2={x(g)} y1={P} y2={H - P} stroke="rgba(139,92,246,0.35)" strokeDasharray="2 3" />
      ))}
      {series.map((s) => (
        <polyline
          key={s.label}
          points={gens.map((g, i) => `${x(g)},${y(s.values[i] ?? 0)}`).join(" ")}
          fill="none"
          stroke={s.color}
          strokeWidth={1.8}
        />
      ))}
    </svg>
  );
}

/* ── 3. Spectral ───────────────────────────────────────────────────────── */

function SpectralCard({ spectral }: { spectral: ResearchResponse["spectral"] }) {
  if (!spectral) {
    return (
      <Card title="Frequency of Fraud" subtitle="A spectral lens over communities — and you can hear it.">
        <Empty what="Spectral data" />
      </Card>
    );
  }

  const shiftHolds = spectral.shift.shift_magnitude > 0;
  // Rank of the ring community by Rayleigh across ALL communities: rank 1 means
  // a "rank by Rayleigh, investigate top-k" detector finds the ring first —
  // the strongest claim this data supports today.
  const ringRank =
    1 +
    spectral.communities.filter((c) => c.rayleigh > spectral.shift.ring_rayleigh).length;
  const nCommunities = spectral.communities.length;

  return (
    <Card
      title="Frequency of Fraud"
      subtitle="A ring shifts a community's energy toward high frequency. Compare a ring community with a matched clean one — and hear the difference."
    >
      <SpectralPlot spectral={spectral} />

      <div className="mt-3 rounded-lg bg-white/5 p-2.5 text-[10px]">
        <div className="flex justify-between text-zinc-400">
          <span>Clean community (Rayleigh)</span>
          <span className="text-sky-300">{spectral.shift.clean_rayleigh.toFixed(3)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Ring community (Rayleigh)</span>
          <span className="text-rose-300">{spectral.shift.ring_rayleigh.toFixed(3)}</span>
        </div>
        <div className="mt-1 flex justify-between border-t border-white/5 pt-1 text-zinc-400">
          <span>Shift (ring − clean)</span>
          <span className={shiftHolds ? "font-semibold text-emerald-400" : "text-red-400"}>
            {spectral.shift.shift_magnitude >= 0 ? "+" : ""}
            {spectral.shift.shift_magnitude.toFixed(3)}
          </span>
        </div>
        <div className="mt-1 flex justify-between border-t border-white/5 pt-1 text-zinc-400">
          <span>Rank by Rayleigh (all communities)</span>
          <span className={ringRank === 1 ? "font-semibold text-emerald-400" : "text-zinc-300"}>
            #{ringRank} of {nCommunities}
          </span>
        </div>
      </div>

      <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
        {shiftHolds
          ? `The validated result is the MATCHED-PAIR shift: a ring community sits higher-frequency than a clean one of comparable size. The #${ringRank} rank is a triage hint on this artifact — the module's own validation warns that absolute cross-community comparison varies with size and density, so ranking is not claimed as a detector. The real detection gain is BWGNN wavelet features fed to the classifier.`
          : "The shift did not hold on this run."}
      </p>
    </Card>
  );
}

function SpectralPlot({ spectral }: { spectral: SpectralData }) {
  // Pick the clean vs ring community by their Rayleigh (matches the shift block).
  const byR = [...spectral.communities].sort((a, b) => a.rayleigh - b.rayleigh);
  const clean = byR.find((c) => Math.abs(c.rayleigh - spectral.shift.clean_rayleigh) < 1e-3) ?? byR[0];
  const ring = byR.find((c) => Math.abs(c.rayleigh - spectral.shift.ring_rayleigh) < 1e-3) ?? byR[byR.length - 1];

  return (
    <div className="space-y-2">
      <SedBars label="Clean community" community={clean} color="#38bdf8" />
      <SedBars label="Ring community" community={ring} color="#fb7185" />
      <AudioButtons clean={clean} ring={ring} />
    </div>
  );
}

function SedBars({
  label,
  community,
  color,
}: {
  label: string;
  community: SpectralData["communities"][number];
  color: string;
}) {
  // Spectral energy distribution, binned to a fixed width. Left = low freq
  // (smooth/normal), right = high freq (irregular). A ring pushes weight right.
  const bins = 32;
  const sed = community.sed ?? [];
  const binned = new Array(bins).fill(0);
  sed.forEach((e, i) => {
    const b = Math.min(bins - 1, Math.floor((i / Math.max(sed.length, 1)) * bins));
    binned[b] += e;
  });
  const max = Math.max(...binned, 1e-9);

  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[10px]">
        <span className="text-zinc-400">{label}</span>
        <span className="text-zinc-600">n={community.size}</span>
      </div>
      <div className="flex h-10 items-end gap-px">
        {binned.map((v, i) => (
          <div
            key={i}
            className="flex-1"
            style={{ height: `${Math.max((v / max) * 100, 2)}%`, backgroundColor: color, opacity: 0.85 }}
          />
        ))}
      </div>
      <div className="mt-0.5 flex justify-between text-[8px] text-zinc-700">
        <span>low freq</span>
        <span>high freq →</span>
      </div>
    </div>
  );
}

/* Sonification — the bonus flourish, never the headline. Maps eigenvalue →
   pitch (200Hz–4kHz) and spectral energy → amplitude, synthesised in-browser
   via Web Audio so it needs no served audio files. If it fails or is muted,
   the bars above already made the whole point. */
function AudioButtons({
  clean,
  ring,
}: {
  clean: SpectralData["communities"][number];
  ring: SpectralData["communities"][number];
}) {
  const ctxRef = useRef<AudioContext | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  const play = (which: "clean" | "ring", c: SpectralData["communities"][number]) => {
    try {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = ctxRef.current ?? new AC();
      ctxRef.current = ctx;
      const evals = c.eigenvalues ?? [];
      const sed = c.sed ?? [];
      const dur = 1.6;
      const now = ctx.currentTime;
      const master = ctx.createGain();
      master.gain.value = 0.0001;
      master.connect(ctx.destination);
      master.gain.exponentialRampToValueAtTime(0.4, now + 0.05);
      master.gain.exponentialRampToValueAtTime(0.0001, now + dur);

      const n = Math.min(evals.length, sed.length, 40);
      const eMax = Math.max(...sed.slice(0, n), 1e-9);
      for (let i = 0; i < n; i++) {
        const amp = sed[i] / eMax;
        if (amp < 0.02) continue;
        // eigenvalue in [0,2] → 200Hz–4kHz, log-spaced
        const freq = 200 * Math.pow(20, evals[i] / 2);
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.frequency.value = freq;
        osc.type = "sine";
        g.gain.value = amp * 0.5;
        osc.connect(g);
        g.connect(master);
        osc.start(now);
        osc.stop(now + dur);
      }
      setPlaying(which);
      window.setTimeout(() => setPlaying((p) => (p === which ? null : p)), dur * 1000);
    } catch {
      /* audio unavailable — the bars carry the point */
    }
  };

  return (
    <div className="flex gap-2 pt-1">
      <button
        onClick={() => play("clean", clean)}
        className={`flex-1 border px-2 py-1.5 text-[10px] font-medium transition ${
          playing === "clean"
            ? "border-sky-400/50 bg-sky-500/20 text-sky-200"
            : "border-white/10 bg-white/5 text-zinc-300 hover:border-sky-400/40"
        }`}
      >
        🔊 Hear clean
      </button>
      <button
        onClick={() => play("ring", ring)}
        className={`flex-1 border px-2 py-1.5 text-[10px] font-medium transition ${
          playing === "ring"
            ? "border-rose-400/50 bg-rose-500/20 text-rose-200"
            : "border-white/10 bg-white/5 text-zinc-300 hover:border-rose-400/40"
        }`}
      >
        🔊 Hear ring
      </button>
    </div>
  );
}
