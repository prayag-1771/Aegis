"use client";

import { useState, useRef, useEffect } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import type { EventsResponse, FraudGraph, GhostRing, Ring } from "@/lib/api";
import { fetchResearch } from "@/lib/api";
import { inr } from "@/lib/format";
import { Activity, Network } from "./Icons";

const DEMO_DISTRICTS = [
  "Jamtara",
  "Deoghar",
  "Alwar",
  "Bharatpur",
  "Nuh",
  "Chennai Central",
  "Mumbai South",
  "Delhi East",
];

/** Fraud-ring workbench: inject a fresh laundering ring, watch graph detection
 *  catch it, and drill into any ring's money flow. Lifted from the old LeftPanel;
 *  failures now surface as a dismissable toast via onError instead of a stuck panel. */

/* CROSS-BANK RING — the one ring no single bank can see.
   Every other card here is a ring found inside ONE institution's data. This one
   is different in kind: it only exists once four isolated banks match embeddings
   with each other, so it belongs beside them with that difference made obvious
   rather than buried in the Research Lab.
   Numbers are read from the real Ghost Ring artifact (GET /research), never
   hardcoded, and the card hides itself if that artifact is missing. */
function CrossBankRingCard() {
  const [ring, setRing] = useState<GhostRing | null>(null);
  const [phase, setPhase] = useState(0); // 0 siloed · 1 matching · 2 fused
  const [replayKey, setReplayKey] = useState(0);

  useEffect(() => {
    fetchResearch().then((r) => setRing(r.ghost_ring)).catch(() => setRing(null));
  }, []);

  useEffect(() => {
    setPhase(0);
    const t1 = window.setTimeout(() => setPhase(1), 1200);
    const t2 = window.setTimeout(() => setPhase(2), 2600);
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
  }, [replayKey]);

  if (!ring) return null;

  const banks = Math.max(2, Math.min(ring.n_banks || 4, 4));
  const perBank = Object.values(ring.per_bank_ring_recall ?? {});
  const best = perBank.length ? Math.max(...perBank) : 0;
  const fused = ring.fused_ring_recall ?? 0;
  const multiple = best > 0 ? fused / best : 0;

  const N = 12, cx = 118, cy = 60, R = 42;
  const nodes = Array.from({ length: N }, (_, i) => {
    const a = (i / N) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), bank: Math.floor(i / (N / banks)) };
  });
  const COLORS = ["#38bdf8", "#a78bfa", "#fb7185", "#fbbf24"];

  return (
    <div className="gsap-ring-item mb-3 border border-cyan-500/30 bg-cyan-950/20 p-3" style={{ opacity: 0 }}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-cyan-300">
          <Network className="h-3.5 w-3.5" /> cross-bank ring
        </span>
        <button
          onClick={() => setReplayKey((k) => k + 1)}
          className="border border-cyan-500/30 px-1.5 py-0.5 text-[9px] text-cyan-300 transition hover:border-cyan-400 hover:text-cyan-100"
        >
          ▶ replay
        </button>
      </div>

      <svg viewBox="0 0 236 120" className="mt-1 w-full">
        {nodes.map((n, i) => {
          const next = nodes[(i + 1) % N];
          const sameBank = n.bank === next.bank;
          const shown = sameBank || phase >= 1;
          return (
            <line key={`e${i}`} x1={n.x} y1={n.y} x2={next.x} y2={next.y}
                  stroke={sameBank ? COLORS[n.bank % 4] : "#22d3ee"}
                  strokeWidth={sameBank ? 1.4 : 2}
                  strokeDasharray={sameBank ? undefined : "4 3"}
                  opacity={shown ? (sameBank ? 0.7 : phase === 2 ? 1 : 0.45) : 0}
                  style={{ transition: "opacity .55s ease" }} />
          );
        })}
        {nodes.map((n, i) => (
          <circle key={`n${i}`} cx={n.x} cy={n.y} r={phase === 2 ? 4.5 : 3.5}
                  fill={COLORS[n.bank % 4]} style={{ transition: "r .35s ease" }} />
        ))}
        {Array.from({ length: banks }, (_, b) => {
          const mid = nodes[Math.floor(b * (N / banks) + N / banks / 2) % N];
          return (
            <text key={`l${b}`} x={mid.x + (mid.x > cx ? 10 : -10)} y={mid.y + 3}
                  textAnchor={mid.x > cx ? "start" : "end"} fontSize="7"
                  fill={COLORS[b % 4]} opacity={0.9}>Bank {b}</text>
          );
        })}
      </svg>

      <p className="text-center text-[9px] leading-relaxed text-zinc-400">
        {phase === 0 && <>Each bank sees only its own fragment — no bank sees a ring.</>}
        {phase === 1 && <>Banks publish DP embeddings; the matcher links boundary accounts…</>}
        {phase === 2 && <span className="text-cyan-300">One ring across all {banks} banks — visible only when fused.</span>}
      </p>

      <div className="mt-2 space-y-1 border-t border-white/5 pt-2 text-[10px]">
        <div className="flex justify-between text-zinc-400">
          <span>Fused vs best single bank</span>
          <span className="font-semibold text-cyan-300">
            {Math.round(fused * 100)}% vs {Math.round(best * 100)}%
            {multiple >= 1.1 ? ` · ${multiple.toFixed(1)}×` : ""}
          </span>
        </div>
        <div className="flex justify-between text-zinc-500">
          <span>False-merge rate</span>
          <span className={ring.false_merge_rate === 0 ? "text-emerald-400" : "text-amber-400"}>
            {Math.round((ring.false_merge_rate ?? 0) * 100)}%
          </span>
        </div>
        {ring.dp_epsilon != null && (
          <div className="flex justify-between text-zinc-500">
            <span>Privacy</span>
            <span className="text-emerald-400">DP ε={ring.dp_epsilon} · no raw data shared</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function FraudRingsDrawer({
  events,
  onInjectRing,
  onViewRing,
  onOpenConsole,
  onError,
  injecting = false,
}: {
  events: EventsResponse | null;
  onInjectRing?: (district: string, accounts?: string[]) => Promise<FraudGraph | void> | void;
  onViewRing?: (ring: Ring) => void;
  onOpenConsole?: () => void;
  onError?: (msg: string) => void;
  injecting?: boolean;
}) {
  const rings = events?.fraud_graph?.rings ?? [];
  const [district, setDistrict] = useState(DEMO_DISTRICTS[0]);
  const [namesRaw, setNamesRaw] = useState("");
  const [caught, setCaught] = useState<{ title: string; detail: string; ring?: Ring } | null>(
    null
  );
  const [phase, setPhase] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    // Stagger in the top elements and rings
    // Fade + subtle scale (compositor transform) instead of a positional slide
    // — `.glass` over the map re-blurs on a moving transform. Scale stays smooth.
    gsap.fromTo(".gsap-ring-item",
      { opacity: 0, scale: 0.96, y: 10 },
      { opacity: 1, scale: 1, y: 0, duration: 0.4, stagger: 0.05,
        ease: "power3.out", force3D: true,
        willChange: "transform,opacity", clearProps: "all" },
    );
  }, { scope: container, dependencies: [rings.length] });

  const names = namesRaw.split(",").map((n) => n.trim()).filter(Boolean);
  const namesTooFew = names.length > 0 && names.length < 3;

  const handleInject = async () => {
    if (!onInjectRing || running) return;
    setCaught(null);
    setRunning(true);
    const t0 = performance.now();
    // staged narration while the real work happens underneath
    setPhase(
      names.length >= 3
        ? `opening accounts: ${names.slice(0, 4).join(", ")}${names.length > 4 ? "…" : ""}`
        : "opening 6 new accounts…"
    );
    const timers = [
      setTimeout(() => setPhase("money starts looping between them…"), 1000),
      setTimeout(() => setPhase("graph engine scanning the network…"), 2100),
    ];
    try {
      const graph = await onInjectRing(district, names.length >= 3 ? names : undefined);
      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      // let the story finish playing even when the engine is faster
      const elapsed = performance.now() - t0;
      if (elapsed < 3000) await new Promise((r) => setTimeout(r, 3000 - elapsed));
      if (!graph) return;
      if (names.length >= 3) {
        const hit = graph.rings.find((r) =>
          r.account_ids.some((id) => names.some((n) => id === n || id.startsWith(`${n}_`)))
        );
        setCaught({
          title: `CAUGHT in ${secs}s: ${names.slice(0, 10).join(", ")}`,
          detail: hit
            ? `${hit.label ?? "fraud ring"} in ${hit.district ?? district} · risk ${Math.round(hit.risk_score * 100)}% — click to see the money`
            : `new ring detected in ${district}`,
          ring: hit,
        });
      } else {
        setCaught({
          title: `New ring caught in ${district} — ${secs}s`,
          detail: `${graph.rings.length} rings now on the map`,
        });
      }
    } catch {
      onError?.("Inject failed — is the fraud-graph service up?");
    } finally {
      timers.forEach(clearTimeout);
      setPhase(null);
      setRunning(false);
    }
  };

  return (
    <div ref={container} className="flex flex-col gap-3 p-4">
      <div className="glass p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400 gsap-ring-item" style={{ opacity: 0 }}>
          <div className="flex items-center gap-1.5">
            <Network className="h-3.5 w-3.5 text-white" /> Fraud Rings
          </div>
          <Activity className="h-3.5 w-3.5" />
        </div>
        {onInjectRing && (
          <div className="mt-3 border border-white/15 bg-white/5 p-3 gsap-ring-item" style={{ opacity: 0 }}>
            <div className="flex items-center gap-2">
              <select
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="min-w-0 flex-1 border border-white/10 bg-zinc-950/70 px-2.5 py-2 text-[11px] text-zinc-200 outline-none transition focus:border-white/60"
              >
                {DEMO_DISTRICTS.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button
                onClick={handleInject}
                disabled={running || injecting || namesTooFew}
                className="bg-white px-3 py-2 text-[11px] font-semibold text-black transition hover:bg-zinc-200 disabled:cursor-wait disabled:opacity-50"
              >
                {running ? "Committing…" : "Inject ring"}
              </button>
            </div>
            {phase && (
              <div className="mt-2 flex items-center gap-2 bg-white/10 px-2.5 py-2">
                <span className="h-1.5 w-1.5 animate-ping rounded-full bg-white" />
                <span className="animate-pulse text-[10px] text-white">{phase}</span>
              </div>
            )}
            <input
              value={namesRaw}
              onChange={(e) => setNamesRaw(e.target.value)}
              placeholder="name the criminals (optional): ravi, pinky, quickcash"
              className="mt-2 w-full border border-white/10 bg-zinc-950/70 px-2.5 py-2 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none transition focus:border-white/60"
            />
            {namesTooFew && (
              <p className="mt-1 text-[10px] text-amber-400/90">
                a ring needs at least 3 names (comma-separated)
              </p>
            )}
            {caught && !running && (
              <button
                onClick={() => caught.ring && onViewRing?.(caught.ring)}
                disabled={!caught.ring}
                className="mt-2 w-full border border-emerald-400/25 bg-emerald-500/10 px-2.5 py-2 text-left transition enabled:hover:border-emerald-400/60"
              >
                <div className="text-[11px] font-semibold text-emerald-300">{caught.title}</div>
                <div className="mt-0.5 text-[10px] text-emerald-200/70">{caught.detail}</div>
              </button>
            )}
            <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
              Adds fresh accounts moving money in a loop, reruns graph detection, and lights up a
              new white dot.
            </p>
            {onOpenConsole && (
              <button
                onClick={onOpenConsole}
                className="mt-2 w-full border border-white/10 px-2.5 py-1.5 text-[10px] text-zinc-300 transition hover:border-white/50 hover:text-white"
              >
                ⚖ Fraud console — design the transactions yourself
              </button>
            )}
          </div>
        )}
        <div className="mt-3 space-y-2.5">
          <CrossBankRingCard />
          {rings.map((r) => (
            <button
              key={r.ring_id}
              onClick={() => onViewRing?.(r)}
              className="gsap-ring-item block w-full px-1 py-0.5 text-left transition hover:bg-white/5"
              style={{ opacity: 0 }}
              title="view the money flow"
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-zinc-300">
                  {r.ring_id} · {r.label ?? "ring"}
                </span>
                <span className="text-zinc-500">
                  {r.size} accts · {inr(r.total_amount)}
                </span>
              </div>
              <div className="mt-1 h-1 bg-white/5">
                <div
                  className="h-1 bg-gradient-to-r from-white to-zinc-400"
                  style={{ width: `${Math.round(r.risk_score * 100)}%` }}
                />
              </div>
            </button>
          ))}
          {rings.length === 0 && <div className="mt-3 text-[11px] text-zinc-600 gsap-ring-item" style={{ opacity: 0 }}>no rings yet…</div>}
        </div>
      </div>
    </div>
  );
}
