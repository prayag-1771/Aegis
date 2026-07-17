"use client";

import { useEffect, useState } from "react";
import { fetchCaseFile, type CaseFileResponse } from "@/lib/api";
import { X } from "./Icons";

/** AI Case Officer output: a police-ready brief for one district.
 *  The brief is LLM-written over a deterministic dossier (template fallback
 *  keeps it working with zero API keys) — engine is always shown. */
export default function CaseFileModal({
  district,
  onClose,
}: {
  district: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<CaseFileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    fetchCaseFile(district)
      .then((d) => !gone && setData(d))
      .catch((e) => !gone && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      gone = true;
    };
  }, [district]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-zinc-950/70 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="glass !rounded-none max-h-[88vh] w-[560px] max-w-[94vw] overflow-y-auto p-5 scroll-thin animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              Case file — {district}
            </h2>
            <p className="mt-0.5 text-[10px] text-zinc-500">
              {data ? `written by ${data.engine}` : "gathering evidence…"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <p className="mt-4 text-xs text-red-300">Case officer unavailable — {error}</p>
        )}

        {!data && !error && (
          <div className="mt-4 space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-10" />
            ))}
          </div>
        )}

        {data && (
          <div className="mt-4 space-y-4 text-left">
            {/* evidence counts strip */}
            <div className="flex gap-2 text-[10px] text-zinc-400">
              <span className="bg-white/5 px-2 py-0.5">{data.dossier.counts.scams} scams</span>
              <span className="bg-white/5 px-2 py-0.5">{data.dossier.counts.fake_notes} fake notes</span>
              <span className="bg-white/5 px-2 py-0.5">{data.dossier.counts.rings} rings</span>
            </div>

            <section>
              <h3 className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">Summary</h3>
              <p className="mt-1 text-xs leading-relaxed text-zinc-100">{data.case_file.summary}</p>
            </section>

            {data.case_file.timeline.length > 0 && (
              <section>
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">Timeline</h3>
                <ul className="mt-1 space-y-1">
                  {data.case_file.timeline.map((t, i) => (
                    <li key={i} className="text-[11px] leading-relaxed text-zinc-300 font-mono">{t}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="border border-amber-500/25 bg-amber-500/5 p-3">
              <h3 className="text-[10px] font-semibold uppercase tracking-widest text-amber-400">Hypothesis</h3>
              <p className="mt-1 text-[11px] leading-relaxed text-zinc-200">{data.case_file.hypothesis}</p>
            </section>

            <section>
              <h3 className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">Recommended actions</h3>
              <ol className="mt-1 list-decimal space-y-1 pl-4">
                {data.case_file.recommended_actions.map((a, i) => (
                  <li key={i} className="text-[11px] leading-relaxed text-zinc-200">{a}</li>
                ))}
              </ol>
            </section>

            <p className="text-[9px] leading-relaxed text-zinc-600">{data.disclaimer}</p>
          </div>
        )}
      </div>
    </div>
  );
}
