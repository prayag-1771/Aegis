"use client";

import { useEffect, useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import {
  actOnAction,
  fetchActions,
  type ActionsResponse,
  type ResponseAction,
  type ActionPriority,
  type ActionType,
} from "@/lib/api";

/** Disrupt / Respond queue — the platform's "act on it" surface.
 *  Detections and fusion produce concrete, recipient-addressed actions
 *  (freeze a mule account, block a scam number, alert I4C/MHA, hold a victim's
 *  transfer). Dispatch is SIMULATED and every card says so — this is honest
 *  decision-support with a full audit trail, not a live enforcement wire. */

const TYPE_META: Record<ActionType, { icon: string; label: string }> = {
  account_freeze: { icon: "🔒", label: "Account freeze" },
  telecom_block: { icon: "📵", label: "Telecom block" },
  mha_alert: { icon: "🚨", label: "MHA / I4C alert" },
  citizen_intercept: { icon: "🛡️", label: "Citizen intercept" },
  review_queue: { icon: "📋", label: "Review queue" },
};

const PRIORITY_STYLE: Record<ActionPriority, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-300",
  high: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  medium: "border-zinc-500/40 bg-zinc-500/10 text-zinc-300",
};

const STATUS_STYLE: Record<string, string> = {
  proposed: "border-violet-500/40 bg-violet-500/10 text-violet-300",
  dispatched: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  acknowledged: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  dismissed: "border-zinc-600/40 bg-zinc-600/10 text-zinc-500",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "Proposed",
  dispatched: "Dispatched (sim)",
  acknowledged: "Acknowledged",
  dismissed: "Dismissed",
};

export default function DisruptPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<ActionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      setData(await fetchActions());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    load();
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
        ".gsap-action",
        { opacity: 0, y: 12, scale: 0.98 },
        {
          opacity: 1, y: 0, scale: 1, duration: 0.4, stagger: 0.05,
          ease: "power3.out", force3D: true, clearProps: "all",
        },
      );
    },
    { scope: container, dependencies: [data?.actions.length] },
  );

  const act = async (id: string, op: "dispatch" | "acknowledge" | "dismiss") => {
    setBusy(`${id}:${op}`);
    try {
      const updated = await actOnAction(id, op);
      setData((prev) =>
        prev
          ? { ...prev, actions: prev.actions.map((a) => (a.action_id === id ? updated : a)) }
          : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const actions = data?.actions ?? [];
  const open = actions.filter((a) => a.status === "proposed").length;
  const critical = actions.filter((a) => a.priority === "critical" && a.status === "proposed").length;

  return (
    <div ref={container} className="relative h-full overflow-y-auto bg-zinc-950/95 p-6 scroll-thin">
      <button
        onClick={onClose}
        aria-label="Close Disrupt queue"
        className="absolute right-4 top-4 z-10 border border-white/10 bg-zinc-900/80 p-2 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <div className="mb-5 pr-12">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-zinc-100">Disrupt &amp; Respond</h2>
          <span className="border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-red-300">
            {open} open · {critical} critical
          </span>
        </div>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
          Every detection here has been turned into a concrete, recipient-addressed action — freeze a mule
          account, block a scam number, alert I4C/MHA, or hold a victim&apos;s transfer. Dispatch is{" "}
          <span className="text-amber-400/90">simulated for demonstration</span> (no live bank/telecom/MHA
          integration is connected); each action carries its evidence chain and an append-only audit log.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={load}
            className="border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] text-zinc-300 transition hover:border-violet-400/50 hover:text-violet-200"
          >
            ↻ Re-derive from current state
          </button>
          <span className="text-[10px] text-zinc-600">
            Actions also auto-generate the moment Fusion runs.
          </span>
        </div>
      </div>

      {error ? (
        <div className="border border-red-500/20 bg-red-500/5 p-6 text-center text-sm text-red-300">
          {error}
        </div>
      ) : actions.length === 0 ? (
        <div className="border border-dashed border-white/10 p-10 text-center text-sm text-zinc-600">
          No actions yet. Run Fusion or analyse a scam/note to populate the disrupt queue.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {actions.map((a) => (
            <ActionCard key={a.action_id} action={a} busy={busy} onAct={act} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActionCard({
  action,
  busy,
  onAct,
}: {
  action: ResponseAction;
  busy: string | null;
  onAct: (id: string, op: "dispatch" | "acknowledge" | "dismiss") => void;
}) {
  const [showAudit, setShowAudit] = useState(false);
  const meta = TYPE_META[action.action_type];
  const isProposed = action.status === "proposed";
  const isBusy = (op: string) => busy === `${action.action_id}:${op}`;

  return (
    <div className="gsap-action flex flex-col border border-white/10 bg-zinc-900/60 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base leading-none">{meta.icon}</span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            {meta.label}
          </span>
        </div>
        <span className={`border px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${PRIORITY_STYLE[action.priority]}`}>
          {action.priority}
        </span>
      </div>

      <h3 className="mt-2 text-sm font-medium leading-snug text-zinc-100">{action.title}</h3>

      <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-500">
        <span>→ {action.recipient}</span>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-zinc-400">{action.trigger.rationale}</p>

      {/* target chips */}
      <div className="mt-2 flex flex-wrap gap-1">
        {action.target.account_id && <Chip>acct {action.target.account_id}</Chip>}
        {action.target.phone_number && <Chip>{action.target.phone_number}</Chip>}
        {action.target.ring_id && <Chip>{action.target.ring_id}</Chip>}
        {typeof action.target.amount === "number" && <Chip>₹{action.target.amount.toLocaleString("en-IN")}</Chip>}
        {action.target.district && <Chip>{action.target.district}</Chip>}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2">
        <span className={`border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${STATUS_STYLE[action.status]}`}>
          {STATUS_LABEL[action.status]}
        </span>
        {action.sla_minutes != null && (
          <span className="text-[9px] text-zinc-600" title="Target time-to-action against the fraud clock">
            SLA ≤ {action.sla_minutes >= 60 ? `${Math.round(action.sla_minutes / 60)}h` : `${action.sla_minutes}m`}
          </span>
        )}
      </div>

      {/* controls */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {isProposed ? (
          <>
            <button
              onClick={() => onAct(action.action_id, "dispatch")}
              disabled={!!busy}
              className="border border-violet-500/40 bg-violet-500/15 px-2.5 py-1 text-[10px] font-medium text-violet-200 transition hover:bg-violet-500/25 disabled:opacity-50"
            >
              {isBusy("dispatch") ? "Dispatching…" : "Dispatch (simulate)"}
            </button>
            <button
              onClick={() => onAct(action.action_id, "dismiss")}
              disabled={!!busy}
              className="border border-white/10 px-2.5 py-1 text-[10px] text-zinc-400 transition hover:border-white/25 hover:text-zinc-200 disabled:opacity-50"
            >
              Dismiss
            </button>
          </>
        ) : action.status === "dispatched" ? (
          <button
            onClick={() => onAct(action.action_id, "acknowledge")}
            disabled={!!busy}
            className="border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 text-[10px] text-sky-300 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            {isBusy("acknowledge") ? "…" : "Mark acknowledged"}
          </button>
        ) : null}
        {action.audit && action.audit.length > 0 && (
          <button
            onClick={() => setShowAudit((s) => !s)}
            className="ml-auto px-1.5 py-1 text-[10px] text-zinc-600 transition hover:text-zinc-300"
          >
            {showAudit ? "hide audit" : `audit (${action.audit.length})`}
          </button>
        )}
      </div>

      {showAudit && action.audit && (
        <div className="mt-2 space-y-1 border-t border-white/5 pt-2">
          {action.audit.map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-[9px] text-zinc-500">
              <span className="font-mono text-zinc-600">{e.at.slice(11, 19)}</span>
              <span className="text-zinc-400">{e.event}</span>
              <span className="text-zinc-600">· {e.actor}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="bg-white/5 px-1.5 py-0.5 text-[9px] text-zinc-400 font-mono">{children}</span>
  );
}
