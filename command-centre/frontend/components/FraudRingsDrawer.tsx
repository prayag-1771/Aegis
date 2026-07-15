"use client";

import { useState, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { EventsResponse, FraudGraph, Ring } from "@/lib/api";
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
    gsap.from(".gsap-ring-item", {
      x: -30,
      opacity: 0,
      duration: 0.4,
      stagger: 0.05,
      ease: "power2.out",
    });
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
        <div className="flex items-center justify-between text-xs text-zinc-400 gsap-ring-item">
          <div className="flex items-center gap-1.5">
            <Network className="h-3.5 w-3.5 text-violet-400" /> Fraud Rings
          </div>
          <Activity className="h-3.5 w-3.5" />
        </div>
        {onInjectRing && (
          <div className="mt-3 rounded-2xl border border-violet-500/15 bg-violet-500/5 p-3 gsap-ring-item">
            <div className="flex items-center gap-2">
              <select
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-zinc-950/70 px-2.5 py-2 text-[11px] text-zinc-200 outline-none transition focus:border-violet-400/60"
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
                className="rounded-lg bg-violet-500 px-3 py-2 text-[11px] font-semibold text-white transition hover:bg-violet-400 disabled:cursor-wait disabled:opacity-50"
              >
                {running ? "Committing…" : "Inject ring"}
              </button>
            </div>
            {phase && (
              <div className="mt-2 flex items-center gap-2 rounded-lg bg-violet-500/10 px-2.5 py-2">
                <span className="h-1.5 w-1.5 animate-ping rounded-full bg-violet-400" />
                <span className="animate-pulse text-[10px] text-violet-200">{phase}</span>
              </div>
            )}
            <input
              value={namesRaw}
              onChange={(e) => setNamesRaw(e.target.value)}
              placeholder="name the criminals (optional): ravi, pinky, quickcash"
              className="mt-2 w-full rounded-lg border border-white/10 bg-zinc-950/70 px-2.5 py-2 text-[11px] text-zinc-200 placeholder:text-zinc-600 outline-none transition focus:border-violet-400/60"
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
                className="mt-2 w-full rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-2.5 py-2 text-left transition enabled:hover:border-emerald-400/60"
              >
                <div className="text-[11px] font-semibold text-emerald-300">{caught.title}</div>
                <div className="mt-0.5 text-[10px] text-emerald-200/70">{caught.detail}</div>
              </button>
            )}
            <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
              Adds fresh accounts moving money in a loop, reruns graph detection, and lights up a
              new purple dot.
            </p>
            {onOpenConsole && (
              <button
                onClick={onOpenConsole}
                className="mt-2 w-full rounded-lg border border-white/10 px-2.5 py-1.5 text-[10px] text-zinc-300 transition hover:border-violet-400/50 hover:text-violet-200"
              >
                ⚖ Fraud console — design the transactions yourself
              </button>
            )}
          </div>
        )}
        <div className="mt-3 space-y-2.5">
          {rings.map((r) => (
            <button
              key={r.ring_id}
              onClick={() => onViewRing?.(r)}
              className="gsap-ring-item block w-full rounded-lg px-1 py-0.5 text-left transition hover:bg-white/5"
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
              <div className="mt-1 h-1 rounded bg-white/5">
                <div
                  className="h-1 rounded bg-gradient-to-r from-violet-500 to-fuchsia-400"
                  style={{ width: `${Math.round(r.risk_score * 100)}%` }}
                />
              </div>
            </button>
          ))}
          {rings.length === 0 && <div className="mt-3 text-[11px] text-zinc-600 gsap-ring-item">no rings yet…</div>}
        </div>
      </div>
    </div>
  );
}
