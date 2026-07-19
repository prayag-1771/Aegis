"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { fetchRingSpectral, type RingSpectral as RingSpectralType } from "@/lib/api";
import gsap from "gsap";
import { inr } from "@/lib/format";
import { X, Play, Zap } from "./Icons";

export type ViewNode = {
  id: string;
  score?: number;
  /** true = victim/outside account paying into the ring (drawn as a small grey orbit node) */
  satellite?: boolean;
  features?: {
    throughput_ratio?: number | null;
    burst_ratio?: number | null;
    round_amount_ratio?: number | null;
    tx_count?: number | null;
    in_degree?: number;
    out_degree?: number;
  } | null;
};

export type ViewEdge = { source: string; target: string; amount?: number | null };

const W = 520;
const H = 340;
const CX = W / 2;
const CY = H / 2;
const R = 118;

/** Position nodes so the ring's topology is visible at a glance:
 *  hub -> star (collector centred), chain -> left-to-right line, else circle.
 *  Satellite (victim) nodes orbit outside, near the member they pay into. */
function layout(allNodes: ViewNode[], edges: ViewEdge[], label?: string | null) {
  const pos = new Map<string, { x: number; y: number }>();
  const nodes = allNodes.filter((n) => !n.satellite);
  const ids = nodes.map((n) => n.id);
  const deg = new Map<string, number>(ids.map((id) => [id, 0]));
  const inDeg = new Map<string, number>(ids.map((id) => [id, 0]));
  const next = new Map<string, string[]>();
  for (const e of edges) {
    deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
    deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    inDeg.set(e.target, (inDeg.get(e.target) ?? 0) + 1);
    next.set(e.source, [...(next.get(e.source) ?? []), e.target]);
  }

  const circle = (list: string[], cx = CX, cy = CY, r = R) =>
    list.forEach((id, i) => {
      const a = (2 * Math.PI * i) / list.length - Math.PI / 2;
      pos.set(id, { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
    });

  if (label?.includes("hub") && ids.length > 2) {
    const hub = [...ids].sort((a, b) => (deg.get(b) ?? 0) - (deg.get(a) ?? 0))[0];
    pos.set(hub, { x: CX, y: CY });
    circle(ids.filter((id) => id !== hub));
  } else if (label?.includes("chain") && ids.length > 1) {
    // follow the money left to right from the account nothing pays into
    const start = ids.find((id) => (inDeg.get(id) ?? 0) === 0) ?? ids[0];
    const order: string[] = [];
    const seen = new Set<string>();
    let cur: string | undefined = start;
    while (cur && !seen.has(cur)) {
      order.push(cur);
      seen.add(cur);
      cur = (next.get(cur) ?? []).find((t) => !seen.has(t));
    }
    ids.filter((id) => !seen.has(id)).forEach((id) => order.push(id));
    const step = (W - 120) / Math.max(order.length - 1, 1);
    order.forEach((id, i) =>
      pos.set(id, { x: 60 + i * step, y: CY + (i % 2 === 0 ? -18 : 18) })
    );
  } else {
    circle(ids);
  }

  // victims orbit outside, angled toward the member account they pay into
  const satellites = allNodes.filter((n) => n.satellite);
  satellites.forEach((sat, i) => {
    const targetEdge = edges.find((e) => e.source === sat.id && pos.has(e.target));
    const t = targetEdge ? pos.get(targetEdge.target)! : { x: CX, y: CY };
    let angle = Math.atan2(t.y - CY, t.x - CX);
    if (!Number.isFinite(angle) || (t.x === CX && t.y === CY)) {
      angle = (2 * Math.PI * i) / Math.max(satellites.length, 1) - Math.PI / 2;
    }
    // fan siblings out so victims of the same collector don't stack
    angle += (i % 3 - 1) * 0.35;
    const r = R + 44;
    pos.set(sat.id, {
      x: Math.min(Math.max(CX + r * Math.cos(angle), 26), W - 26),
      y: Math.min(Math.max(CY + r * Math.sin(angle), 22), H - 30),
    });
  });
  return pos;
}

function short(id: string) {
  return id.length > 12 ? `${id.slice(0, 10)}…` : id;
}

export default function RingViewer({
  title,
  subtitle,
  badge,
  label,
  ringId,
  nodes,
  edges,
  trail,
  onClose,
  inline = false,
}: {
  title: string;
  subtitle?: string;
  badge?: string;
  label?: string | null;
  /** When set, fetches the spectral second opinion for this ring. */
  ringId?: string;
  nodes: ViewNode[];
  edges: ViewEdge[];
  trail?: { account_id: string; amount: number } | null;
  onClose: () => void;
  inline?: boolean;
}) {
  const [picked, setPicked] = useState<ViewNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Spectral second opinion — an independent lens corroborating the
  // classifier. Silently absent on any failure: the viewer must not degrade
  // because a research endpoint is down.
  const [spectral, setSpectral] = useState<RingSpectralType | null>(null);
  useEffect(() => {
    setSpectral(null);
    if (!ringId) return;
    let stale = false;
    fetchRingSpectral(ringId)
      .then((s) => {
        if (!stale) setSpectral(s);
      })
      .catch(() => {});
    return () => {
      stale = true;
    };
  }, [ringId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // merge parallel transfers between the same pair so the drawing stays clean
  const merged = useMemo(() => {
    const m = new Map<string, ViewEdge & { n: number }>();
    for (const e of edges) {
      const k = `${e.source}->${e.target}`;
      const cur = m.get(k);
      if (cur) {
        cur.amount = (cur.amount ?? 0) + (e.amount ?? 0);
        cur.n += 1;
      } else {
        m.set(k, { ...e, amount: e.amount ?? 0, n: 1 });
      }
    }
    return [...m.values()];
  }, [edges]);

  const pos = useMemo(() => layout(nodes, merged, label), [nodes, merged, label]);
  const maxAmt = Math.max(...merged.map((e) => e.amount ?? 0), 1);

  const startSimulation = () => {
    setPicked(null);
    if (!containerRef.current) return;

    // Build an ordered walk through the ring following the money trail
    const visited = new Set<string>();
    const orderedNodeIds: string[] = [];
    const orderedEdgeIndices: number[] = [];

    // Find a starting node (one with no incoming edges from ring members, or just the first node)
    const ringNodes = nodes.filter((n) => !n.satellite);
    const incomingSources = new Set(merged.map((e) => e.target));
    const startNode = ringNodes.find((n) => !incomingSources.has(n.id)) ?? ringNodes[0];

    // BFS/DFS walk following edge order
    if (startNode) {
      const queue = [startNode.id];
      while (queue.length > 0) {
        const current = queue.shift()!;
        if (visited.has(current)) continue;
        visited.add(current);
        orderedNodeIds.push(current);

        // Find all edges from this node and queue their targets
        merged.forEach((e, idx) => {
          if (e.source === current && !visited.has(e.target)) {
            orderedEdgeIndices.push(idx);
            queue.push(e.target);
          }
        });
      }
    }

    // Add any remaining nodes/edges not reached by the walk
    nodes.forEach((n) => {
      if (!visited.has(n.id)) {
        orderedNodeIds.push(n.id);
      }
    });
    merged.forEach((_, idx) => {
      if (!orderedEdgeIndices.includes(idx)) {
        orderedEdgeIndices.push(idx);
      }
    });

    gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

      // Hide everything first
      gsap.set(".gsap-node", { opacity: 0, scale: 0, transformOrigin: "50% 50%" });
      gsap.set(".gsap-edge", { opacity: 0 });
      gsap.set(".gsap-anim-flow", { opacity: 0 });

      // Step through: account pops in → its arrows draw → next account → its arrows → …
      orderedNodeIds.forEach((nodeId) => {
        const nodeEl = `.gsap-node-${nodeId.replace(/[^a-zA-Z0-9]/g, "_")}`;

        // Pop the account node in
        tl.to(nodeEl, {
          opacity: 1,
          scale: 1,
          duration: 0.4,
          ease: "back.out(1.7)",
        });

        // Then draw all outgoing edges from this account one by one
        const nodeEdgeIndices = orderedEdgeIndices.filter(
          (idx) => merged[idx].source === nodeId
        );
        nodeEdgeIndices.forEach((edgeIdx) => {
          const edgeEl = `.gsap-edge-${edgeIdx}`;
          tl.to(edgeEl, {
            opacity: 1,
            duration: 0.35,
            ease: "power1.inOut",
          });
        });
      });

      // Finally, activate all the flowing dash animations
      tl.to(".gsap-anim-flow", {
        opacity: 1,
        duration: 0.5,
        stagger: 0.04,
        ease: "power1.inOut",
      }, "+=0.2");

    }, containerRef);
  };

  const renderContent = () => (
    <div
      ref={containerRef}
      className={inline ? "relative" : "glass w-[860px] max-w-[94vw] p-5 relative"}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
            {badge && (
              <span
                className={`px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${
                  badge.startsWith("REAL")
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-violet-500/15 text-violet-300"
                }`}
              >
                {badge}
              </span>
            )}
          </div>
          {subtitle && <p className="mt-0.5 text-[11px] text-zinc-400">{subtitle}</p>}
          {/* Corroboration-only, like the verify layer: shown when the
              independent lens agrees, silent when neutral — a neutral reading
              is documented as uninformative, never counter-evidence. */}
          {spectral?.agrees && (
            <p className="mt-1 text-[10px] text-zinc-400" title={spectral.note}>
              <span className="font-semibold text-emerald-300">🎵 Spectral second opinion:</span>{" "}
              Rayleigh {spectral.ring_rayleigh.toFixed(3)} vs matched clean{" "}
              {spectral.matched_clean_rayleigh.toFixed(3)} (+{spectral.shift.toFixed(3)}) ·
              independent lens agrees
            </p>
          )}
          {trail && (
            <p className="mt-1 text-[10px] font-semibold text-red-300">
              ⚠ ₹{trail.amount.toLocaleString("en-IN")} victim payment traced into{" "}
              <span className="font-mono">{trail.account_id}</span> — red arrow below
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={startSimulation}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 transition text-[11px] font-medium"
          >
            <Play className="h-3 w-3" /> Simulate
          </button>
          <button onClick={onClose} className="text-zinc-500 transition hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-3 flex gap-4">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="min-w-0 flex-1 border border-white/5 bg-zinc-950/60 transition-all duration-500"
        >
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 z" fill="#a78bfa" opacity="0.85" />
            </marker>
            <marker id="arrowRed" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 z" fill="#f87171" />
            </marker>
          </defs>
          {merged.map((e, i) => {
            const a = pos.get(e.source);
            const b = pos.get(e.target);
            if (!a || !b) return null;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const len = Math.hypot(dx, dy) || 1;
            const trim = 16;
            const x2 = b.x - (dx / len) * trim;
            const y2 = b.y - (dy / len) * trim;
            const x1 = a.x + (dx / len) * trim;
            const y1 = a.y + (dy / len) * trim;
            const wgt = 1 + 2.5 * ((e.amount ?? 0) / maxAmt);
            const traced =
              trail != null &&
              e.target === trail.account_id &&
              e.amount != null &&
              Math.abs(e.amount - trail.amount) <= Math.max(0.01 * trail.amount, 1);
            return (
              <g key={i} className={`gsap-edge gsap-edge-${i}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={traced ? "#f87171" : "#a78bfa"} strokeOpacity={traced ? 0.95 : 0.4} strokeWidth={traced ? 2.5 : wgt} markerEnd={traced ? "url(#arrowRed)" : "url(#arrow)"} />
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={traced ? "#f87171" : "#d8b4fe"} strokeOpacity={traced ? 1 : 0.8} strokeWidth={wgt * 0.8} strokeDasharray="4 8" className="gsap-anim-flow">
                  <animate attributeName="stroke-dashoffset" values="12;0" dur={`${2 / wgt}s`} repeatCount="indefinite" />
                </line>
                <title>
                  {traced ? "TRACED VICTIM PAYMENT · " : ""}
                  {e.source} → {e.target}
                  {e.amount ? ` · ${inr(e.amount)}` : ""}
                  {e.n > 1 ? ` (${e.n} transfers)` : ""}
                </title>
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = pos.get(n.id);
            if (!p) return null;
            if (n.satellite) {
              return (
                <g key={n.id} className={`gsap-node gsap-node-${n.id.replace(/[^a-zA-Z0-9]/g, "_")}`}>
                  <circle cx={p.x} cy={p.y} r={6} fill="#27272a" stroke="#52525b" strokeWidth={1} />
                  <text x={p.x} y={p.y + 16} textAnchor="middle" fontSize="7.5" fill="#71717a">{short(n.id)}</text>
                  <title>{n.id} — outside account paying into the ring (victim)</title>
                </g>
              );
            }
            const hot = (n.score ?? 0) >= 0.9;
            return (
              <g key={n.id} onClick={() => setPicked(n)} className={`cursor-pointer gsap-node gsap-node-${n.id.replace(/[^a-zA-Z0-9]/g, "_")}`}>
                <circle cx={p.x} cy={p.y} r={12} fill={hot ? "#7c3aed" : "#3f3f46"} stroke={picked?.id === n.id ? "#f0abfc" : hot ? "#c4b5fd" : "#71717a"} strokeWidth={picked?.id === n.id ? 2.5 : 1.2} />
                <text x={p.x} y={p.y + 26} textAnchor="middle" fontSize="9" fill="#d4d4d8">{short(n.id)}</text>
                {n.score != null && (
                  <text x={p.x} y={p.y + 3.5} textAnchor="middle" fontSize="8" fontWeight="bold" fill="#fafafa">{Math.round(n.score * 100)}</text>
                )}
                <title>{n.id}</title>
              </g>
            );
          })}
        </svg>

        <div className="w-64 shrink-0 border border-white/5 bg-zinc-950/60 p-3 flex flex-col h-full overflow-y-auto scroll-thin">
          <div className="mb-4 pb-4 border-b border-white/5">
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-violet-400 mb-2">
              <Zap className="h-3.5 w-3.5" /> AI Summary
            </div>
            <div className="text-[11px] text-zinc-300 leading-relaxed font-light">
              {label?.includes("hub") ? (
                <p>Graph ML detects a <strong>Hub-and-Spoke</strong> topology. Central account acts as a collector, aggregating funds from victims before layering via mules.</p>
              ) : label?.includes("chain") ? (
                <p>Graph ML detects a <strong>Chain</strong> topology. Funds are transferred sequentially across multiple accounts to obfuscate the money trail.</p>
              ) : (
                <p>Graph ML detects an <strong>Organized Ring</strong>. Multiple accounts exhibit high-velocity transfers with synchronized timing and identical amounts.</p>
              )}
            </div>
          </div>

          {picked ? (
            <>
              <div className="text-[11px] font-semibold text-zinc-100">{picked.id}</div>
              {picked.score != null && (
                <div className="mt-1 text-[10px] text-violet-300">
                  illicit probability {Math.round(picked.score * 100)}%
                </div>
              )}
              <div className="mt-3 space-y-2">
                <Evidence when={picked.features?.throughput_ratio != null} strong={(picked.features?.throughput_ratio ?? 0) > 0.8} text={`money out ≈ money in (${Math.round((picked.features?.throughput_ratio ?? 0) * 100)}%) — nothing sticks, classic mule`} weak="keeps money like a normal account" />
                <Evidence when={picked.features?.burst_ratio != null} strong={(picked.features?.burst_ratio ?? 0) > 0.5} text={`${Math.round((picked.features?.burst_ratio ?? 0) * 100)}% of transfers within 60 min of the last — machine-speed movement`} weak="human-paced transactions" />
                <Evidence when={picked.features?.round_amount_ratio != null} strong={(picked.features?.round_amount_ratio ?? 0) > 0.5} text={`${Math.round((picked.features?.round_amount_ratio ?? 0) * 100)}% suspiciously round amounts (₹49,999-style)`} weak="organic, non-round amounts" />
                {picked.features?.tx_count != null && (
                  <div className="text-[10px] text-zinc-400">
                    {picked.features.tx_count} transactions · {picked.features.in_degree ?? "?"} in / {picked.features.out_degree ?? "?"} out
                  </div>
                )}
                {!picked.features && (
                  <div className="text-[10px] text-zinc-500">no per-account evidence in this dataset (anonymised)</div>
                )}
              </div>
            </>
          ) : (
            <div className="text-[11px] leading-relaxed text-zinc-500">
              Click an account to see <span className="text-zinc-300">why it was flagged</span> — the evidence the model used, in plain words.
              <div className="mt-3 text-[10px] text-zinc-600">Node number = illicit probability. Arrow thickness = money volume.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  if (inline) return renderContent();

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-zinc-950/70 backdrop-blur-sm"
      onClick={onClose}
    >
      {renderContent()}
    </div>
  );
}

function Evidence({
  when,
  strong,
  text,
  weak,
}: {
  when: boolean;
  strong: boolean;
  text: string;
  weak: string;
}) {
  if (!when) return null;
  return (
    <div
      className={`px-2 py-1.5 text-[10px] leading-relaxed ${
        strong ? "bg-red-500/10 text-red-200" : "bg-white/5 text-zinc-400"
      }`}
    >
      {strong ? "⚠ " : "· "}
      {strong ? text : weak}
    </div>
  );
}
