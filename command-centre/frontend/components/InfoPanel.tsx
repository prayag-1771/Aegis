"use client";

import { X, Shield, Phone, Banknote, MapPin, Zap } from "./Icons";
import { titleCase, pct, clockTime } from "@/lib/format";
import type { EventsResponse } from "@/lib/api";

export default function InfoPanel({
  moduleType,
  events,
  onClose,
}: {
  moduleType: "scam" | "counterfeit" | null;
  events: EventsResponse | null;
  onClose: () => void;
}) {
  if (!moduleType) return null;

  const data = moduleType === "scam" ? events?.scams.at(-1) : events?.counterfeits.at(-1);

  return (
    <div className="absolute right-0 top-16 bottom-0 w-[400px] z-30 transform transition-transform duration-300">
      <div className="h-full w-full bg-zinc-950/95 backdrop-blur-2xl border-l border-white/10 shadow-[-20px_0_40px_rgba(0,0,0,0.5)] flex flex-col pointer-events-auto">
        <div className="flex items-center justify-between p-5 border-b border-white/10">
          <div className="flex items-center gap-2">
            <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${moduleType === 'scam' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
              {moduleType === "scam" ? <Phone className="h-4 w-4" /> : <Banknote className="h-4 w-4" />}
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">
                {moduleType === "scam" ? "Scam Analysis" : "Counterfeit Analysis"}
              </h2>
              <span className="text-[10px] text-zinc-500">{data ? clockTime(data.timestamp) : "No data"}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-white/10 text-zinc-400 transition">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 scroll-thin space-y-6">
          {data ? (
            <>
              {/* Verdict Section */}
              <div className="glass p-4 rounded-xl relative overflow-hidden group">
                <div className={`absolute inset-0 opacity-10 bg-gradient-to-br ${moduleType === 'scam' ? 'from-red-500 to-transparent' : 'from-amber-500 to-transparent'}`}></div>
                <div className="flex justify-between items-start mb-2 relative z-10">
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">AI Verdict</div>
                    <div className={`text-xl font-semibold uppercase ${moduleType === 'scam' ? 'text-red-400' : 'text-amber-400'}`}>
                      {data.verdict}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Confidence</div>
                    <div className="text-xl font-light text-zinc-100">
                      {pct('risk_score' in data ? data.risk_score : data.confidence)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Gen AI Summary */}
              <div>
                <div className="flex items-center gap-2 text-xs font-medium text-zinc-300 mb-3">
                  <Zap className="h-4 w-4 text-violet-400" />
                  Generative AI Summary
                </div>
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-xs font-light leading-relaxed text-zinc-300">
                  {moduleType === "scam" ? (
                    <p>
                      The Fraud Shield NLP engine analyzed the live audio transcript. The caller exhibits strong indicators of a <strong>{titleCase((data as any).scam_type ?? "unknown")}</strong> scam. The speech pattern involves high-pressure tactics, urgency markers, and requests for sensitive credentials. Recommended action: immediate block and flag associated phone nodes.
                    </p>
                  ) : (
                    <p>
                      Counterfeit Vision processed the scanned currency image. The note lacks crucial security features including: <strong>{((data as any).missing_features ?? []).join(", ")}</strong>. High structural similarity to known forged batches circulating in the region. Seizure and tracing of origin node recommended.
                    </p>
                  )}
                </div>
              </div>

              {/* Data Points */}
              <div className="space-y-3">
                <div className="text-xs font-medium text-zinc-300">Key Indicators</div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-black/20 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1 flex items-center gap-1">
                      <MapPin className="h-3 w-3" /> Location
                    </div>
                    <div className="text-xs text-zinc-200 truncate" title={data.location_hint?.district ?? "unknown"}>
                      {data.location_hint?.district ?? "unknown"}
                    </div>
                  </div>
                  <div className="bg-black/20 rounded-lg p-3">
                    <div className="text-[10px] text-zinc-500 mb-1 flex items-center gap-1">
                      <Shield className="h-3 w-3" /> Model
                    </div>
                    <div className="text-xs text-zinc-200">
                      {moduleType === "scam" ? "FraudShield v4" : "VisionNet v2"}
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center py-20">
              <Shield className="h-10 w-10 text-zinc-700 mb-4" />
              <p className="text-sm text-zinc-500">No detection data available to analyze.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
