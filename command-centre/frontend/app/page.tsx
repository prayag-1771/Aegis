"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type EventsPayload,
  type FusionOutput,
  type HealthPayload,
  type HotspotsPayload,
} from "@/lib/api";

// Leaflet touches `window` — must skip SSR.
const CrimeMap = dynamic(() => import("./components/CrimeMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-slate-500">loading map…</div>
  ),
});

const THREAT_STYLE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/40",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/40",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40",
};

function Pill({ label, state }: { label: string; state: string }) {
  const up = state === "up";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
        up ? "border-emerald-500/40 text-emerald-400" : "border-slate-600 text-slate-500"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${up ? "bg-emerald-400" : "bg-slate-600"}`} />
      {label}
    </span>
  );
}

function Card({
  title,
  accent,
  children,
}: {
  title: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <h2 className={`mb-3 text-xs font-semibold uppercase tracking-widest ${accent}`}>{title}</h2>
      {children}
    </section>
  );
}

export default function Dashboard() {
  const [events, setEvents] = useState<EventsPayload | null>(null);
  const [hotspots, setHotspots] = useState<HotspotsPayload | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [fusion, setFusion] = useState<FusionOutput | null>(null);
  const [fusing, setFusing] = useState(false);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [ev, hs] = await Promise.all([api.events(), api.hotspots()]);
      setEvents(ev);
      setHotspots(hs);
      if (ev.last_fusion) setFusion(ev.last_fusion);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t1 = setInterval(refresh, 5000);
    const t2 = setInterval(() => api.health().then(setHealth).catch(() => setHealth(null)), 10000);
    api.health().then(setHealth).catch(() => setHealth(null));
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [refresh]);

  const runFusion = async () => {
    setFusing(true);
    try {
      setFusion(await api.fuse());
    } catch {
      /* backend down — banner already shows */
    } finally {
      setFusing(false);
    }
  };

  const scam = events?.scams.at(-1);
  const note = events?.counterfeits.at(-1);
  const rings = events?.fraud_graph?.rings ?? [];

  return (
    <main className="min-h-screen bg-[#0b1117] px-5 py-4 font-sans text-slate-200">
      {/* header */}
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-bold tracking-[0.3em] text-slate-100">AEGIS</h1>
          <span className="text-xs uppercase tracking-widest text-slate-500">
            digital public safety command centre
          </span>
        </div>
        <div className="flex items-center gap-2">
          {health ? (
            Object.entries(health.modules).map(([m, s]) => <Pill key={m} label={m} state={s} />)
          ) : (
            <Pill label="command-centre" state="down" />
          )}
        </div>
      </header>

      {offline && (
        <div className="mb-4 rounded border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          Backend unreachable — start it with:{" "}
          <code className="text-red-200">uvicorn aegis_command.api:app --port 8000</code>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* left column — the three signals */}
        <div className="flex flex-col gap-4">
          <Card title="Fraud Shield · scam calls" accent="text-amber-400">
            {scam ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-500">{scam.event_id}</span>
                  <span
                    className={`rounded border px-2 py-0.5 text-xs font-semibold uppercase ${
                      scam.verdict === "scam"
                        ? "border-red-500/40 bg-red-500/10 text-red-400"
                        : "border-emerald-500/40 text-emerald-400"
                    }`}
                  >
                    {scam.verdict} · {(scam.risk_score * 100).toFixed(0)}%
                  </span>
                </div>
                {scam.raw_text && (
                  <p className="line-clamp-3 rounded bg-slate-950/60 p-2 text-xs italic text-slate-400">
                    “{scam.raw_text}”
                  </p>
                )}
                <div className="flex flex-wrap gap-1">
                  {(scam.markers ?? []).map((m) => (
                    <span
                      key={m}
                      className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-300"
                    >
                      {m.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-slate-500">
                  {scam.scam_type?.replaceAll("_", " ")} · {scam.location_hint?.district ?? "unknown"}
                </p>
              </div>
            ) : (
              <p className="text-sm text-slate-500">no detections yet</p>
            )}
          </Card>

          <Card title="Counterfeit Vision · currency" accent="text-cyan-400">
            {note ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-500">{note.event_id}</span>
                  <span
                    className={`rounded border px-2 py-0.5 text-xs font-semibold uppercase ${
                      note.verdict === "fake"
                        ? "border-red-500/40 bg-red-500/10 text-red-400"
                        : "border-emerald-500/40 text-emerald-400"
                    }`}
                  >
                    ₹{note.denomination} {note.verdict} · {(note.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {(note.missing_features?.length ?? 0) > 0 && (
                  <p className="text-xs text-slate-400">
                    missing:{" "}
                    <span className="text-cyan-300">
                      {note.missing_features!.map((f) => f.replaceAll("_", " ")).join(", ")}
                    </span>
                  </p>
                )}
                <p className="text-xs text-slate-500">
                  seized in {note.location_hint?.district ?? "unknown"}
                </p>
              </div>
            ) : (
              <p className="text-sm text-slate-500">no scans yet</p>
            )}
          </Card>

          <Card title="Fraud Graph · rings" accent="text-violet-400">
            {rings.length ? (
              <ul className="space-y-1.5 text-sm">
                {rings.slice(0, 6).map((r) => (
                  <li
                    key={r.ring_id}
                    className="flex items-center justify-between rounded bg-slate-950/60 px-2 py-1.5"
                  >
                    <span className="font-mono text-xs text-slate-400">{r.ring_id}</span>
                    <span className="text-xs text-slate-500">
                      {r.label} · {r.district ?? "?"}
                    </span>
                    <span className="text-xs font-semibold text-violet-300">
                      {r.size} acc · {(r.risk_score * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
                {rings.length > 6 && (
                  <li className="text-center text-xs text-slate-600">+{rings.length - 6} more</li>
                )}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">no rings detected</p>
            )}
          </Card>
        </div>

        {/* right 2/3 — map + fusion */}
        <div className="flex flex-col gap-4 xl:col-span-2">
          <section className="h-[380px] overflow-hidden rounded-lg border border-slate-800">
            <CrimeMap points={hotspots?.points ?? []} hubs={hotspots?.hubs ?? []} />
          </section>

          <Card title="Gen AI Fusion · correlated intelligence" accent="text-red-400">
            <div className="mb-3 flex items-center justify-between">
              <button
                onClick={runFusion}
                disabled={fusing}
                className="rounded bg-red-500/90 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-red-500 disabled:opacity-50"
              >
                {fusing ? "correlating…" : "▶ RUN FUSION"}
              </button>
              {fusion && (
                <span
                  className={`rounded border px-3 py-1 text-xs font-bold uppercase tracking-widest ${THREAT_STYLE[fusion.threat_level]}`}
                >
                  threat: {fusion.threat_level}
                </span>
              )}
            </div>

            {fusion ? (
              <div className="space-y-3 text-sm">
                <p className="rounded border-l-2 border-red-500/60 bg-slate-950/60 p-3 leading-relaxed text-slate-200">
                  {fusion.summary}
                </p>
                {(fusion.recommended_actions?.length ?? 0) > 0 && (
                  <ul className="grid gap-1 text-xs text-slate-300 md:grid-cols-2">
                    {fusion.recommended_actions!.map((a) => (
                      <li key={a} className="rounded bg-slate-950/60 px-2 py-1.5">
                        → {a}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-600">
                  <span>{fusion.linked_signals.length} linked signals</span>
                  {fusion.correlation_basis?.map((b) => (
                    <span key={b} className="rounded bg-slate-800 px-1.5 py-0.5">
                      {b.replaceAll("_", " ")}
                    </span>
                  ))}
                  {fusion.audit_trail && (
                    <span className="ml-auto font-mono">
                      audit {fusion.audit_trail.inputs_hash} · {fusion.audit_trail.model}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                Press RUN FUSION to correlate all current signals into one intelligence package.
              </p>
            )}
          </Card>
        </div>
      </div>
    </main>
  );
}
