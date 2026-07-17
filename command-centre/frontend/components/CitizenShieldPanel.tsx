"use client";

import { useEffect, useRef, useState } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
import {
  citizenAnalyze,
  citizenCallAnalyze,
  fetchCitizenLanguages,
  type CitizenVerdict,
} from "@/lib/api";

/** Citizen Fraud Shield — multilingual + multi-channel console.
 *  Two modes: a message check (12 languages) and real-time CALL monitoring where
 *  the transcript is fed turn-by-turn and the risk climbs live, flagging an active
 *  scam mid-call — before any transfer. Reuses the existing Fraud Shield classifier
 *  (Sarvam AI only translates); nothing is faked. */

const SAMPLE_CALL = [
  "Hello, is this Mr. Sharma? I am Inspector Verma from the CBI Cyber Cell, Delhi.",
  "A courier parcel booked in your name and Aadhaar was seized at the airport — it contains illegal items and fake passports.",
  "Your bank account is now under investigation for money laundering and an FIR has been registered against you.",
  "You are under digital arrest. Do not disconnect this video call, do not leave your room, and do not contact anyone.",
  "To prove your innocence, transfer your entire balance to this RBI-verified safe account — it will be refunded after clearance.",
];

const VERDICT_STYLE: Record<string, string> = {
  scam: "border-red-500/50 bg-red-500/10 text-red-300",
  suspicious: "border-amber-500/50 bg-amber-500/10 text-amber-300",
  legit: "border-emerald-500/50 bg-emerald-500/10 text-emerald-300",
};

export default function CitizenShieldPanel({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<"message" | "call">("message");
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [translationLive, setTranslationLive] = useState(false);
  const [language, setLanguage] = useState(""); // "" = auto / detected
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchCitizenLanguages()
      .then((d) => {
        setLanguages(d.languages);
        setTranslationLive(d.translation_available);
      })
      .catch(() => {});
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
        ".gsap-cz",
        { opacity: 0, y: 12, scale: 0.98 },
        { opacity: 1, y: 0, scale: 1, duration: 0.4, stagger: 0.06, ease: "power3.out", clearProps: "all" },
      );
    },
    { scope: container },
  );

  const langSelect = (
    <select
      value={language}
      onChange={(e) => setLanguage(e.target.value)}
      className="border border-white/10 bg-zinc-950/70 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-violet-400/60"
      title="Advisory language"
    >
      <option value="">Auto (reply in detected language)</option>
      {Object.entries(languages).map(([code, name]) => (
        <option key={code} value={code}>
          {name}
        </option>
      ))}
    </select>
  );

  return (
    <div className="fixed inset-0 z-[70] bg-zinc-950/95 pointer-events-auto">
      <div ref={container} className="relative h-full overflow-y-auto p-6 scroll-thin">
        <button
          onClick={onClose}
          aria-label="Close Citizen Fraud Shield"
          className="absolute right-4 top-4 z-10 border border-white/10 bg-zinc-900/80 p-2 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="mb-5 pr-12 gsap-cz">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-zinc-100">Citizen Fraud Shield</h2>
            <span className="border border-violet-500/40 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-violet-300">
              22 languages
            </span>
            <span
              className={`px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
                translationLive ? "text-emerald-400" : "text-amber-400"
              }`}
              title={translationLive ? "Sarvam translation is live" : "No Sarvam key — English passthrough"}
            >
              {translationLive ? "● translation live" : "○ english only"}
            </span>
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
            The citizen surface. A message or live call is translated to English (Sarvam AI), run through
            the Fraud Shield classifier, and the verdict + safety advisory return in the citizen&apos;s
            language. Same model as the dashboard — only the transport and language change.
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div className="flex border border-white/10">
              {(["message", "call"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-3 py-1.5 text-[11px] font-medium transition ${
                    mode === m ? "bg-violet-500/20 text-violet-200" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {m === "message" ? "Message / WhatsApp" : "Live Call"}
                </button>
              ))}
            </div>
            {langSelect}
          </div>
        </div>

        {mode === "message" ? (
          <MessageMode language={language} />
        ) : (
          <CallMode language={language} />
        )}
      </div>
    </div>
  );
}

function Advisory({ result }: { result: CitizenVerdict }) {
  return (
    <div className="mt-4 border-t border-white/5 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`border px-2 py-0.5 text-[11px] font-bold uppercase tracking-widest ${VERDICT_STYLE[result.verdict]}`}>
          {result.verdict}
        </span>
        <span className="text-2xl font-light text-zinc-100">{Math.round(result.risk_score * 100)}%</span>
        {result.scam_type && (
          <span className="bg-white/5 px-2 py-0.5 text-[10px] text-zinc-400">{result.scam_type.replace(/_/g, " ")}</span>
        )}
        <span className="ml-auto text-[9px] text-zinc-600">
          {result.language_name} · {result.translated ? "translated" : "english"}
        </span>
      </div>

      <div className="mt-3 border border-violet-500/25 bg-violet-500/5 p-3">
        <div className="text-[9px] font-semibold uppercase tracking-widest text-violet-300">Advisory to citizen</div>
        <p className="mt-1 text-[13px] leading-relaxed text-zinc-100">{result.advisory}</p>
        {result.translated && result.advisory_en !== result.advisory && (
          <p className="mt-2 border-t border-white/5 pt-2 text-[10px] leading-relaxed text-zinc-500">
            EN: {result.advisory_en}
          </p>
        )}
      </div>

      {result.markers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {result.markers.map((m) => (
            <span key={m} className="bg-red-500/10 px-1.5 py-0.5 text-[9px] text-red-300">
              {m.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageMode({ language }: { language: string }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<CitizenVerdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await citizenAnalyze(text, language || undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gsap-cz border border-white/10 bg-zinc-900/60 p-5 max-w-3xl">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
        Check a suspicious message
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="Paste a suspicious SMS / WhatsApp / call transcript in any language…"
        className="mt-2 w-full border border-white/10 bg-zinc-950/70 px-3 py-2 text-[12px] text-zinc-200 outline-none transition focus:border-violet-400/60"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={run}
          disabled={busy || !text.trim()}
          className="border border-violet-500/40 bg-violet-500/15 px-3 py-1.5 text-[11px] font-semibold text-violet-200 transition hover:bg-violet-500/25 disabled:opacity-50"
        >
          {busy ? "Checking…" : "Check message"}
        </button>
        <button
          onClick={() => setText("मैं सीबीआई से बोल रहा हूं। आपका खाता मनी लॉन्ड्रिंग में शामिल है। तुरंत सुरक्षित खाते में पैसे ट्रांसफर करें।")}
          className="px-2 py-1.5 text-[10px] text-zinc-500 transition hover:text-zinc-300"
        >
          try a Hindi example
        </button>
      </div>
      {error && <p className="mt-3 text-[11px] text-red-300">{error}</p>}
      {result && <Advisory result={result} />}
    </div>
  );
}

function CallMode({ language }: { language: string }) {
  const [turns, setTurns] = useState<string[]>([]);
  const [result, setResult] = useState<CitizenVerdict | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const analyzeSoFar = async (accum: string[]) => {
    try {
      setResult(await citizenCallAnalyze(accum, language || undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const play = () => {
    setTurns([]);
    setResult(null);
    setError(null);
    setPlaying(true);
    let i = 0;
    const step = () => {
      const accum = SAMPLE_CALL.slice(0, i + 1);
      setTurns(accum);
      analyzeSoFar(accum);
      i += 1;
      if (i < SAMPLE_CALL.length) {
        timer.current = setTimeout(step, 1800);
      } else {
        setPlaying(false);
      }
    };
    step();
  };

  const risk = result ? Math.round(result.risk_score * 100) : 0;
  const gaugeColor =
    result?.verdict === "scam" ? "bg-red-500" : result?.verdict === "suspicious" ? "bg-amber-500" : "bg-emerald-500";

  return (
    <div className="gsap-cz grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* transcript */}
      <div className="border border-white/10 bg-zinc-900/60 p-5">
        <div className="flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            Live call transcript
          </div>
          <button
            onClick={play}
            disabled={playing}
            className="border border-violet-500/40 bg-violet-500/15 px-3 py-1.5 text-[11px] font-semibold text-violet-200 transition hover:bg-violet-500/25 disabled:opacity-50"
          >
            {playing ? "● Live…" : "▶ Play digital-arrest call"}
          </button>
        </div>
        <div className="mt-3 space-y-2 min-h-[220px]">
          {turns.length === 0 ? (
            <p className="text-[11px] text-zinc-600">
              Press play to stream a scam call turn-by-turn. The risk updates after every line —
              watch it flag the scam <em>before</em> the money is asked for.
            </p>
          ) : (
            turns.map((t, i) => (
              <div key={i} className="flex gap-2 text-[12px] leading-relaxed">
                <span className="shrink-0 font-mono text-[9px] text-zinc-600 mt-1">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-zinc-200">📞 {t}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* live verdict */}
      <div className="border border-white/10 bg-zinc-900/60 p-5">
        <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
          Real-time risk
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-4xl font-light text-zinc-100">{risk}%</span>
          {result && (
            <span className={`border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${VERDICT_STYLE[result.verdict]}`}>
              {result.verdict}
            </span>
          )}
        </div>
        <div className="mt-2 h-2 w-full bg-white/5">
          <div className={`h-2 transition-all duration-500 ${gaugeColor}`} style={{ width: `${risk}%` }} />
        </div>

        {result?.intercept && (
          <div className="mt-4 border border-red-500/50 bg-red-500/15 p-3 animate-pulse">
            <div className="text-[11px] font-bold uppercase tracking-widest text-red-300">
              ⚠ Intercept — active scam in progress
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-red-100/90">
              Warn the citizen and hold any transfer NOW — before money moves. (Feeds the Disrupt
              queue&apos;s citizen-intercept action.)
            </p>
          </div>
        )}

        {result && <Advisory result={result} />}
        {error && <p className="mt-3 text-[11px] text-red-300">{error}</p>}
      </div>
    </div>
  );
}
