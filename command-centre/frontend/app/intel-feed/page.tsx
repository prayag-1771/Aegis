"use client";

/**
 * Intel Feed — the human review surface for news-ingested Supply Trail intelligence.
 *
 * WHY THIS PAGE EXISTS
 * Supply Trail's FIR corpus is grown from public reporting by an OFFLINE batch job
 * (fetch -> extract, run from the CLI). The step that job cannot do is decide what
 * counts as evidence. This page is that step: an officer reads each candidate and
 * chooses which ones enter the corpus.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * It never fetches news. Candidates are already staged, so no request here waits on
 * a feed and the fusion package's `inputs_hash` reproducibility is untouched.
 *
 * REVERSIBILITY
 * Every ingest writes a backup. "Undo last" walks back one step; "Reset" returns the
 * corpus to its state before the first ingest — so this is safe to drive repeatedly
 * in rehearsal, matching the existing demo-reset idiom for injected fraud rings.
 *
 * Design follows the dashboard: glass panels, zinc/violet palette, Inter (inherited
 * from the root layout), Tailwind 4.
 */

import { useCallback, useEffect, useState } from "react";

// Use the SAME base the rest of the dashboard resolves (lib/api.ts): env var
// first, then the deployed Render host in production and localhost only in dev.
// This page previously hardcoded 127.0.0.1, which on a deployed frontend means
// the VISITOR's own machine — so it worked only for whoever was running the
// stack locally. lib/api.ts documents that exact failure; do not reintroduce it.
import { API_BASE } from "@/lib/api";

type Candidate = {
  ref: string;
  district: string;
  state: string;
  lat: number;
  lon: number;
  date: string;
  source: string;
  text: string;
  places: string[];
  crime_types: string[];
  is_printing_press: boolean;
  headline: string | null;
  link: string | null;
  confidence: string | null;
  extractor: string | null;
  places_unresolved: string[];
  notes: string | null;
};

type FeedState = {
  corpus: {
    entries: number;
    presses: string[];
    press_count: number;
    ingested_count: number;
    ingested_refs: string[];
  };
  candidates: Candidate[];
  candidate_count: number;
  can_undo: boolean;
  can_reset: boolean;
  undo_steps: number;
  disclaimer: string;
};

/** One request against the shared API base. Locally that is the gateway on
 *  :4000 (which proxies /intel-feed); deployed it is the backend, which serves
 *  the same routes directly. */
async function call(path: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (res.ok) return res.json();
  const body = await res.json().catch(() => ({}));
  throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  medium: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  low: "text-zinc-400 border-zinc-500/40 bg-zinc-500/10",
};

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="glass px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accent ?? "text-zinc-100"}`}>
        {value}
      </div>
    </div>
  );
}

export default function IntelFeedPage() {
  const [state, setState] = useState<FeedState | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await call("/intel-feed"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = (ref: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });

  const act = async (path: string, body?: unknown, note?: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const result = await call(path, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      setSelected(new Set());
      await load();
      setFlash(note ?? `Done — corpus now holds ${result?.corpus?.entries ?? "?"} entries.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "action failed");
    } finally {
      setBusy(false);
    }
  };

  const candidates = state?.candidates ?? [];

  return (
    <main className="min-h-screen px-6 py-8 lg:px-10">
      <div className="mx-auto max-w-6xl">
        {/* header */}
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <a
              href="/"
              className="mb-2 inline-flex items-center gap-1.5 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
            >
              ← Command Centre
            </a>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
                Intel Feed
              </h1>
              <span className="rounded border border-zinc-600/50 bg-zinc-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                background intelligence
              </span>
            </div>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-zinc-400">
              Public reporting on counterfeit-currency seizures — a{" "}
              <span className="text-zinc-300">prior, not a finding</span>. The signal
              driving a Supply Trail comes from notes actually scanned by Counterfeit
              Vision; these records only corroborate corridors and supply candidate
              origins. Choose which ones enter the corpus.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => act("/intel-feed/undo", undefined, "Reversed the last ingest.")}
              disabled={busy || !state?.can_undo}
              className="glass glass-hover px-3 py-2 text-xs font-medium text-zinc-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Undo last{state?.undo_steps ? ` (${state.undo_steps})` : ""}
            </button>
            <button
              onClick={() => act("/intel-feed/reset", undefined, "Corpus restored to its original state.")}
              disabled={busy || !state?.can_reset}
              className="glass glass-hover px-3 py-2 text-xs font-medium text-zinc-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Reset to original
            </button>
          </div>
        </header>

        {/* corpus stats */}
        <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Corpus entries" value={state?.corpus.entries ?? "—"} />
          <Stat
            label="Printing presses"
            value={state?.corpus.press_count ?? "—"}
            accent="text-violet-300"
          />
          <Stat
            label="From news"
            value={state?.corpus.ingested_count ?? "—"}
            accent="text-emerald-300"
          />
          <Stat label="Awaiting review" value={state?.candidate_count ?? "—"} accent="text-amber-300" />
        </section>

        {/* Why presses matter, and the ceiling that comes with the source.
            The caveat renders unconditionally — it is the most important copy on
            this page and must not disappear when the backend is unreachable. */}
        <div className="glass mb-6 space-y-2 px-4 py-3 text-xs leading-relaxed">
          {state && (
            <p className="text-zinc-400">
              <span className="text-violet-300">Route origins:</span>{" "}
              {state.corpus.presses.length ? state.corpus.presses.join(" · ") : "none"} — only
              entries tagged <code className="text-zinc-300">printing_press</code> can originate a
              route, so each one added is a new answerable question.
            </p>
          )}
          <p className="text-zinc-500">
            <span className="text-zinc-400">Known ceiling:</span> news is downstream of
            enforcement, so a press that was never raided and reported cannot appear here.
            Supply Trail connects new seizures to{" "}
            <span className="text-zinc-400">known</span> sources — it does not discover unknown
            ones. Reporting is also lagged and publication-biased, so treat corroboration
            density as an investigative lead, not a map of where crime concentrates.
          </p>
        </div>

        {/* messages */}
        {error && (
          <div className="glass mb-4 border-red-500/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}
        {flash && (
          <div className="glass mb-4 border-emerald-500/40 px-4 py-3 text-sm text-emerald-300">
            {flash}
          </div>
        )}

        {/* candidates */}
        <section className="space-y-3">
          {!state && !error && (
            <div className="glass px-4 py-8 text-center text-sm text-zinc-500">Loading…</div>
          )}

          {state && candidates.length === 0 && (
            <div className="glass px-4 py-10 text-center">
              <p className="text-sm text-zinc-300">No candidates awaiting review.</p>
              <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-zinc-500">
                Stage more by running the offline ingester:
                <code className="mt-2 block text-zinc-400">
                  python -m aegis_supply_trail.ingest.cli fetch
                </code>
                <code className="block text-zinc-400">
                  python -m aegis_supply_trail.ingest.cli extract
                </code>
              </p>
            </div>
          )}

          {candidates.map((c) => {
            const isSelected = selected.has(c.ref);
            return (
              <article
                key={c.ref}
                onClick={() => toggle(c.ref)}
                className={`glass glass-hover cursor-pointer px-4 py-4 transition-colors ${
                  isSelected ? "border-violet-400/50" : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggle(c.ref)}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1 h-4 w-4 shrink-0 accent-violet-500"
                    aria-label={`Select ${c.district} record`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-zinc-100">{c.district}</span>
                      <span className="text-xs text-zinc-500">{c.state}</span>
                      <span className="text-xs tabular-nums text-zinc-500">{c.date}</span>
                      {c.confidence && (
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                            CONFIDENCE_STYLE[c.confidence] ?? CONFIDENCE_STYLE.low
                          }`}
                        >
                          {c.confidence}
                        </span>
                      )}
                      {c.is_printing_press && (
                        <span className="rounded border border-violet-500/40 bg-violet-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-violet-300">
                          printing press → route origin
                        </span>
                      )}
                    </div>

                    {c.headline && (
                      <p className="mt-2 text-sm leading-snug text-zinc-300">{c.headline}</p>
                    )}
                    <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">{c.text}</p>

                    <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-600">
                      <span>{c.source}</span>
                      <span className="tabular-nums">
                        {c.lat.toFixed(3)}, {c.lon.toFixed(3)}
                      </span>
                      <span>{c.crime_types.join(", ")}</span>
                      {c.extractor && <span>via {c.extractor}</span>}
                      {c.link && (
                        <a
                          href={c.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-zinc-500 underline decoration-zinc-700 underline-offset-2 transition-colors hover:text-zinc-300"
                        >
                          source article ↗
                        </a>
                      )}
                    </div>

                    {c.places_unresolved.length > 0 && (
                      <p className="mt-2 text-[11px] text-amber-500/80">
                        Unplaced: {c.places_unresolved.join(", ")}
                      </p>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </section>

        {/* ingest action */}
        {candidates.length > 0 && (
          <div className="glass sticky bottom-4 mt-5 flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <span className="text-xs text-zinc-400">
              {selected.size} of {candidates.length} selected
            </span>
            <button
              onClick={() =>
                act(
                  "/intel-feed/ingest",
                  { refs: [...selected] },
                  `Ingested ${selected.size} record(s). Supply Trail updates immediately — no restart.`,
                )
              }
              disabled={busy || selected.size === 0}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Working…" : `Ingest ${selected.size || ""} into corpus`}
            </button>
          </div>
        )}

        {state && (
          <p className="mt-6 text-[11px] leading-relaxed text-zinc-600">{state.disclaimer}</p>
        )}
      </div>
    </main>
  );
}
