"use client";

import { X, Shield, Phone, Banknote, MapPin, Zap } from "./Icons";
import { titleCase, pct, clockTime } from "@/lib/format";
import type { EventsResponse } from "@/lib/api";

export default function InfoPanel({
  moduleType,
  events,
  onClose,
  inline = false,
}: {
  moduleType: "scam" | "counterfeit" | null;
  events: EventsResponse | null;
  onClose: () => void;
  inline?: boolean;
}) {
  if (!moduleType) return null;

  const dataList = moduleType === "scam" ? events?.scams || [] : events?.counterfeits || [];
  const latestData = dataList.at(-1);

  const content = (
    <div className={inline ? "h-full flex flex-col" : "h-full w-full bg-zinc-950/95 backdrop-blur-2xl border-l border-white/10 shadow-[-20px_0_40px_rgba(0,0,0,0.5)] flex flex-col pointer-events-auto"}>
        <div className="flex items-center justify-between p-5 border-b border-white/10">
          <div className="flex items-center gap-2">
            <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${moduleType === 'scam' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
              {moduleType === "scam" ? <Phone className="h-4 w-4" /> : <Banknote className="h-4 w-4" />}
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">
                {moduleType === "scam" ? "Scam Analysis" : "Counterfeit Analysis"}
              </h2>
              <span className="text-[10px] text-zinc-500">{dataList.length} recent reports</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-white/10 text-zinc-400 transition">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 scroll-thin space-y-6">
          {dataList.length > 0 && latestData ? (
            <>
              {/* Overall Gen AI Summary */}
              <div>
                <div className="flex items-center gap-2 text-xs font-medium text-zinc-300 mb-3">
                  <Zap className="h-4 w-4 text-violet-400" />
                  Consolidated AI Summary
                </div>
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-xs font-light leading-relaxed text-zinc-300">
                  {moduleType === "scam" ? (
                    <p>
                      The Fraud Shield NLP engine has flagged <strong>{dataList.length}</strong> recent calls.
                      A common pattern is emerging around <strong>{titleCase((latestData as any).scam_type ?? "unknown")}</strong> scams. 
                      Callers are using high-pressure tactics, urgency markers, and requesting sensitive credentials. 
                      Recommended action: block associated phone nodes in affected regions.
                    </p>
                  ) : (
                    <p>
                      Counterfeit Vision processed <strong>{dataList.length}</strong> scanned currency images recently. 
                      Many notes lack crucial security features such as <strong>{((latestData as any).missing_features ?? []).join(", ")}</strong>. 
                      There is high structural similarity to known forged batches circulating in the region. 
                      Seizure and tracing of origin node recommended.
                    </p>
                  )}
                </div>
              </div>

              {/* List of Data Points */}
              <div className="space-y-4">
                <div className="text-xs font-medium text-zinc-300 mb-2">Recent Reports</div>
                {dataList.slice().reverse().map((data: any, idx: number) => (
                  <div key={idx} className="glass p-4 rounded-xl relative overflow-hidden group">
                    <div className={`absolute inset-0 opacity-10 bg-gradient-to-br ${moduleType === 'scam' ? 'from-red-500 to-transparent' : 'from-amber-500 to-transparent'}`}></div>
                    
                    <div className="relative z-10 flex flex-col gap-3">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className={`text-sm font-semibold uppercase ${moduleType === 'scam' ? 'text-red-400' : 'text-amber-400'}`}>
                            {data.verdict}
                          </div>
                          <div className="text-[10px] text-zinc-400 mt-0.5">{clockTime(data.timestamp)}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Confidence</div>
                          <div className="text-sm font-medium text-zinc-200">
                            {pct('risk_score' in data ? data.risk_score : data.confidence)}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 pt-2 border-t border-white/10">
                        <div className="flex items-center gap-1 text-[11px] text-zinc-300">
                          <MapPin className="h-3 w-3 text-zinc-500" />
                          {data.location_hint?.district ?? "unknown location"}
                        </div>
                        {moduleType === "scam" && data.scam_type && (
                          <div className="text-[11px] text-zinc-400 bg-black/20 px-2 py-0.5 rounded-full">
                            {titleCase(data.scam_type)}
                          </div>
                        )}
                        {moduleType === "counterfeit" && data.missing_features && (
                          <div className="text-[10px] text-zinc-400 truncate max-w-[120px]">
                            Missing: {data.missing_features.join(", ")}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
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

  if (inline) return content;

  return (
    <div className="absolute right-0 top-16 bottom-0 w-[500px] z-30 transform transition-transform duration-300">
      {content}
    </div>
  );
}
