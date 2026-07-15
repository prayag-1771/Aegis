"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import type {
  EventsResponse,
  FusionOutput,
  HealthResponse,
  HotspotsResponse,
  Ring,
} from "@/lib/api";
import { injectDemoRing } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import AlertChips from "@/components/AlertChips";
import AlertsDrawer from "@/components/AlertsDrawer";

import FusionChatBot from "@/components/FusionChatBot";
import Drawer from "@/components/Drawer";
import FraudConsole from "@/components/FraudConsole";
import FraudRingsDrawer from "@/components/FraudRingsDrawer";
import type { TabKey } from "@/components/types";
import ModulesDrawer from "@/components/ModulesDrawer";
import RingViewer from "@/components/RingViewer";
import ToastContainer, { type Toast } from "@/components/ToastContainer";
import TopNav from "@/components/TopNav";
import InfoPanel from "@/components/InfoPanel";

const CrimeMap = dynamic(() => import("@/components/CrimeMap"), { ssr: false });

export type RingAlert = {
  id: string;
  district: string;
  label: string;
  size: number;
  total: number | null;
  at: string;
  lat?: number;
  lon?: number;
};

const DEMO_DISTRICT_COORDS: Record<string, { lat: number; lon: number }> = {
  Jamtara: { lat: 23.795, lon: 86.803 },
  Deoghar: { lat: 24.48, lon: 86.7 },
  Alwar: { lat: 27.55, lon: 76.63 },
  Bharatpur: { lat: 27.22, lon: 77.49 },
  Nuh: { lat: 28.1, lon: 77.0 },
  "Chennai Central": { lat: 13.08, lon: 80.27 },
  "Mumbai South": { lat: 18.93, lon: 72.83 },
  "Delhi East": { lat: 28.65, lon: 77.3 },
};

export default function Page() {
  const { data: events, refresh: refreshEvents } = usePolling<EventsResponse>("/api/events", 5000);
  const { data: health } = usePolling<HealthResponse>("/api/health", 10000);
  const { data: hotspots, refresh: refreshHotspots } = usePolling<HotspotsResponse>(
    "/api/hotspots",
    8000
  );

  const [activeTab, setActiveTab] = useState<TabKey>("map");
  const [fusion, setFusion] = useState<FusionOutput | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [injecting, setInjecting] = useState(false);
  const [ringAlerts, setRingAlerts] = useState<RingAlert[]>([]);
  const [viewRing, setViewRing] = useState<Ring | null>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [cityAlerts, setCityAlerts] = useState<{district: string; alerts: any[]} | null>(null);
  const [selectedModule, setSelectedModule] = useState<"scam" | "counterfeit" | null>(null);

  const pushToast = useCallback((msg: string, type: Toast["type"] = "error") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, msg, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);
  const dismissToast = useCallback(
    (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    []
  );

  const locate = useCallback((p: { lat: number; lon: number }) => {
    setFocus(p);
    setActiveTab("map");
  }, []);

  const handleConsoleCommitted = useCallback(
    (district: string) => {
      const coords = DEMO_DISTRICT_COORDS[district];
      if (coords) setFocus(coords);
      refreshEvents();
      refreshHotspots();
    },
    [refreshEvents, refreshHotspots]
  );

  const lastFusion = fusion ?? events?.last_fusion ?? null;

  const viewerData = useMemo(() => {
    if (!viewRing) return null;
    const g = events?.fraud_graph;
    const member = new Set(viewRing.account_ids);
    const nodes = viewRing.account_ids.map((id) => {
      const acc = g?.accounts?.find((a) => a.account_id === id);
      return { id, score: acc?.illicit_probability, features: acc?.features ?? null };
    });
    const intra = (g?.edges ?? []).filter((e) => member.has(e.source) && member.has(e.target));
    const trail =
      (lastFusion?.money_trails ?? []).find((t) => t.ring_id === viewRing.ring_id) ?? null;
    const inflow = (g?.edges ?? [])
      .filter((e) => !member.has(e.source) && member.has(e.target))
      .sort((a, b) => {
        const hit = (e: { target: string; amount: number }) =>
          trail && e.target === trail.account_id && Math.abs(e.amount - trail.amount) < 1 ? 1 : 0;
        return hit(b) - hit(a) || b.amount - a.amount;
      })
      .slice(0, 10);
    const satellites = [...new Set(inflow.map((e) => e.source))].map((id) => ({
      id,
      satellite: true,
    }));
    return { nodes: [...nodes, ...satellites], edges: [...intra, ...inflow], trail };
  }, [viewRing, events, lastFusion]);

  const alertCount =
    (events?.scams.filter((s) => s.verdict !== "legit").length ?? 0) +
    (events?.counterfeits.filter((c) => c.verdict === "fake").length ?? 0) +
    (hotspots?.n_cross_domain ?? 0) +
    ringAlerts.length;

  const handleFused = useCallback(
    (f: FusionOutput) => {
      setFusion(f);
      const p = f.map_hotspots?.[0];
      if (p) setFocus({ lat: p.lat, lon: p.lon });
      refreshHotspots();
    },
    [refreshHotspots]
  );

  const handleInjectRing = useCallback(
    async (district: string, accounts?: string[]) => {
      setInjecting(true);
      try {
        const before = new Set(
          (events?.fraud_graph?.rings ?? []).map((r) => [...r.account_ids].sort().join("|"))
        );
        const graph = await injectDemoRing(district, accounts);
        const fresh = graph.rings.find(
          (r) => !before.has([...r.account_ids].sort().join("|"))
        );
        if (fresh) {
          const coords = DEMO_DISTRICT_COORDS[fresh.district ?? district];
          setRingAlerts((prev) =>
            [
              {
                id: `${Date.now()}`,
                district: fresh.district ?? district,
                label: fresh.label ?? "fraud ring",
                size: fresh.size,
                total: fresh.total_amount ?? null,
                at: new Date().toISOString(),
                ...coords,
              },
              ...prev,
            ].slice(0, 3)
          );
        }
        const coords = DEMO_DISTRICT_COORDS[district];
        if (coords) setFocus(coords);
        await Promise.all([refreshEvents(), refreshHotspots()]);
        return graph;
      } finally {
        setInjecting(false);
      }
    },
    [events, refreshEvents, refreshHotspots]
  );

  const handleSearch = (query: string) => {
    const districtKey = Object.keys(DEMO_DISTRICT_COORDS).find(k => k.toLowerCase().includes(query.toLowerCase()));
    if (districtKey) {
      locate(DEMO_DISTRICT_COORDS[districtKey]);
      
      const relatedScams = events?.scams.filter(s => s.location.toLowerCase().includes(districtKey.toLowerCase()) || districtKey.toLowerCase().includes(s.location.toLowerCase())) || [];
      const relatedFakes = events?.counterfeits.filter(c => c.location.toLowerCase().includes(districtKey.toLowerCase()) || districtKey.toLowerCase().includes(c.location.toLowerCase())) || [];
      
      setCityAlerts({
        district: districtKey,
        alerts: [...relatedScams, ...relatedFakes]
      });
      // auto-dismiss city alerts panel after 10 seconds
      setTimeout(() => setCityAlerts(null), 10000);
    } else {
      pushToast(`Location not found: ${query}`, "error");
    }
  };

  const drawerOpen = activeTab !== "map";

  return (
    <main className="relative h-dvh w-screen select-none overflow-hidden bg-zinc-950">
      <CrimeMap points={hotspots?.points ?? []} hubs={hotspots?.hubs ?? []} focus={focus} />

      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-24 bg-gradient-to-b from-zinc-950/80 to-transparent" />

      <TopNav
        health={health}
        alertCount={alertCount}
        activeTab={activeTab}
        onTabChange={(t) => setActiveTab((cur) => (cur === t && t !== "map" ? "map" : t))}
        onBell={() => setActiveTab("alerts")}
        onSearch={handleSearch}
      />

      {/* Top right localized alerts panel */}
      {cityAlerts && (
        <div className="absolute top-16 right-5 z-40 w-80 rounded-2xl bg-zinc-900/90 backdrop-blur-md border border-zinc-800 shadow-2xl overflow-hidden pointer-events-auto">
          <div className="bg-zinc-800/50 px-4 py-2 border-b border-zinc-800 flex justify-between items-center">
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
              {cityAlerts.district} Alerts
            </h3>
            <button onClick={() => setCityAlerts(null)} className="text-zinc-400 hover:text-zinc-100">&times;</button>
          </div>
          <div className="max-h-64 overflow-y-auto p-2">
            {cityAlerts.alerts.length === 0 ? (
              <p className="text-xs text-zinc-500 text-center py-4">No active alerts for this region.</p>
            ) : (
              cityAlerts.alerts.map((a, i) => (
                <div key={i} className="mb-2 p-2 bg-zinc-800/30 rounded-lg border border-zinc-800/50">
                  <div className="text-xs font-medium text-zinc-200">{a.verdict ? (a.verdict === 'fake' ? 'Counterfeit Note' : 'Scam Call') : 'Alert'}</div>
                  <div className="text-[10px] text-zinc-500 mt-1">{a.summary || "Suspicious activity detected."}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* hero title + module pills */}
      {activeTab === "map" && (
        <div className="pointer-events-none absolute left-5 top-20 z-10 hidden lg:block">
          <h1 className="text-4xl font-extralight tracking-wide text-zinc-100 drop-shadow">
            Public Safety Intelligence
          </h1>
          <div className="mt-2 flex gap-2 text-[10px] uppercase tracking-widest text-zinc-500">
            <span className="glass pointer-events-auto px-2.5 py-1">Scam · Fraud Shield</span>
            <span className="glass pointer-events-auto px-2.5 py-1">Counterfeit · Vision</span>
            <span className="glass pointer-events-auto px-2.5 py-1">Rings · Graph ML</span>
          </div>
        </div>
      )}

      {activeTab === "map" && (
        <AlertChips
          events={events}
          hotspots={hotspots}
          onLocate={locate}
          onOpenAll={() => setActiveTab("alerts")}
        />
      )}

      {/* slide-out drawers, one per tab */}
      {drawerOpen && activeTab !== "fraud-rings" && (
        <Drawer onClose={() => setActiveTab("map")}>
          {activeTab === "modules" && (
            <ModulesDrawer 
              events={events} 
              health={health} 
              onSelectModule={setSelectedModule} 
            />
          )}
          {activeTab === "alerts" && (
            <AlertsDrawer
              events={events}
              hotspots={hotspots}
              fusion={lastFusion}
              ringAlerts={ringAlerts}
              onLocate={locate}
            />
          )}
          {activeTab === "analytics" && <AnalyticsDrawer events={events} fusion={lastFusion} />}
        </Drawer>
      )}

      {/* Full screen blur overlay for Fraud Rings */}
      {activeTab === "fraud-rings" && (
        <div className="absolute inset-0 z-30 bg-zinc-950/80 backdrop-blur-md flex items-center justify-center p-8 pointer-events-auto">
          <div className="w-full max-w-4xl max-h-full overflow-y-auto bg-zinc-900/90 border border-white/10 rounded-2xl shadow-2xl relative">
            <button 
              onClick={() => setActiveTab("map")}
              className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-100 p-2 rounded-full hover:bg-white/10 transition z-10"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            <FraudRingsDrawer
              events={events}
              onInjectRing={handleInjectRing}
              onViewRing={setViewRing}
              onOpenConsole={() => setConsoleOpen(true)}
              onError={(msg) => pushToast(msg, "error")}
              injecting={injecting}
            />
          </div>
        </div>
      )}

      {/* InfoPanel for selected module in ModulesDrawer */}
      {selectedModule && (
        <InfoPanel
          moduleType={selectedModule}
          events={events}
          onClose={() => setSelectedModule(null)}
        />
      )}

      <FusionChatBot
        fusion={lastFusion}
        events={events}
        onFused={handleFused}
        onError={(msg) => pushToast(msg, "error")}
      />

      {consoleOpen && (
        <FraudConsole onClose={() => setConsoleOpen(false)} onCommitted={handleConsoleCommitted} />
      )}
      {viewRing && viewerData && (
        <RingViewer
          title={`${viewRing.ring_id} · ${viewRing.label ?? "fraud ring"}`}
          subtitle={`${viewRing.district ?? "unknown district"} · ${viewRing.size} accounts · risk ${Math.round(viewRing.risk_score * 100)}%${viewRing.total_amount != null ? ` · ₹${Math.round(viewRing.total_amount / 100000)}L` : ""}`}
          badge="SIMULATED CITY"
          label={viewRing.label}
          nodes={viewerData.nodes}
          edges={viewerData.edges}
          trail={viewerData.trail}
          onClose={() => setViewRing(null)}
        />
      )}

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </main>
  );
}
