"use client";

import { useEffect, useRef } from "react";
import { gsap, useGSAP } from "@/lib/gsap";
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
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useGSAP(() => {
    if (!moduleType) return;
    
    // Animate the main panel sliding in
    // Fade + subtle scale (compositor transform) instead of a positional slide
    // — panel/rows are `.glass` over the map, which re-blurs on a moving slide.
    if (!inline) {
      gsap.fromTo(container.current,
        { opacity: 0, scale: 0.98 },
        { opacity: 1, scale: 1, duration: 0.35, ease: "power3.out",
          transformOrigin: "right center", force3D: true,
          willChange: "transform,opacity", clearProps: "all" },
      );
    }

    gsap.fromTo(".gsap-panel-item",
      { opacity: 0, scale: 0.96, y: 10 },
      { opacity: 1, scale: 1, y: 0, duration: 0.4, stagger: 0.05, delay: 0.08,
        ease: "power3.out", force3D: true,
        willChange: "transform,opacity", clearProps: "all" },
    );
  }, { scope: container, dependencies: [moduleType] });

  if (!moduleType) return null;

  const dataList = moduleType === "scam" ? events?.scams || [] : events?.counterfeits || [];
  const latestData = dataList.at(-1);

  const renderContent = () => (
    <div className={inline ? "h-full flex flex-col" : "h-full w-full bg-zinc-950/95 backdrop-blur-2xl border-l border-white/10 shadow-[-20px_0_40px_rgba(0,0,0,0.5)] flex flex-col pointer-events-auto"}>
      <div className="flex items-center justify-between p-5 border-b border-white/10 gsap-panel-item">
        <div className="flex items-center gap-2">
          <div className={`flex h-8 w-8 items-center justify-center ${moduleType === "scam" ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"}`}>
            {moduleType === "scam" ? <Phone className="h-4 w-4" /> : <Banknote className="h-4 w-4" />}
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              {moduleType === "scam" ? "Scam Analysis" : "Counterfeit Analysis"}
            </h2>
            <span className="text-[10px] text-zinc-500">{dataList.length} recent reports</span>
          </div>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-white/10 text-zinc-400 transition">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 scroll-thin space-y-6">
        {dataList.length > 0 && latestData ? (
          <>
            <div className="gsap-panel-item">
              <div className="flex items-center gap-2 text-xs font-medium text-zinc-300 mb-3">
                <Zap className="h-4 w-4 text-violet-400" />
                Consolidated AI Summary
              </div>
              <div className="bg-white/5 border border-white/10 p-4 text-xs font-light leading-relaxed text-zinc-300">
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

            <div className="space-y-4">
              <div className="text-xs font-medium text-zinc-300 mb-2 gsap-panel-item">Recent Reports</div>
              {dataList.slice().reverse().map((data: any, idx: number) => (
                <div key={idx} className="gsap-panel-item glass !rounded-none glass-hover p-4 relative overflow-hidden group">
                  <div className={`absolute inset-0 opacity-10 bg-gradient-to-br ${moduleType === "scam" ? "from-red-500 to-transparent" : "from-amber-500 to-transparent"}`} />
                  <div className="relative z-10 flex flex-col gap-3">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className={`text-sm font-semibold uppercase ${moduleType === "scam" ? "text-red-400" : "text-amber-400"}`}>
                          {data.verdict}
                        </div>
                        <div className="text-[10px] text-zinc-400 mt-0.5">{clockTime(data.timestamp)}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Confidence</div>
                        <div className="text-sm font-medium text-zinc-200">
                          {pct("risk_score" in data ? data.risk_score : data.confidence)}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 pt-2 border-t border-white/10">
                      <div className="flex items-center gap-1 text-[11px] text-zinc-300">
                        <MapPin className="h-3 w-3 text-zinc-500" />
                        {data.location_hint?.district ?? "unknown location"}
                      </div>
                      {moduleType === "scam" && data.scam_type && (
                        <div className="text-[11px] text-zinc-400 bg-black/20 px-2 py-0.5">
                          {titleCase(data.scam_type)}
                        </div>
                      )}
                      {moduleType === "counterfeit" && data.missing_features && (
                        <div className="text-[10px] text-zinc-400 truncate max-w-[120px]">
                          Missing: {data.missing_features.join(", ")}
                        </div>
                      )}
                    </div>
                    <div className="pt-1">
                      <p className="text-[11px] text-zinc-400/90 leading-snug line-clamp-2">
                        <span className="text-violet-400/90 font-medium mr-1">AI Analysis:</span>
                        {data.explanation ?? (moduleType === "scam" 
                          ? "Voice analysis flagged high-pressure tactics and suspicious credential requests."
                          : "Visual inspection revealed critical missing security features and anomalous structural patterns.")}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center py-20 gsap-panel-item">
            <Shield className="h-10 w-10 text-zinc-700 mb-4" />
            <p className="text-sm text-zinc-500">No detection data available to analyze.</p>
          </div>
        )}
      </div>
    </div>
  );

  if (inline) return <div ref={container} className="h-full w-full">{renderContent()}</div>;

  return (
    <div ref={container} className="absolute right-0 top-16 bottom-0 w-[500px] z-30">
      {renderContent()}
    </div>
  );
}
