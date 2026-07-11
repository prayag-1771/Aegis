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
import AnalyticsDrawer from "@/components/AnalyticsDrawer";
import BottomDock from "@/components/BottomDock";
import Drawer from "@/components/Drawer";
import FraudConsole from "@/components/FraudConsole";
import FraudRingsDrawer from "@/components/FraudRingsDrawer";
import IconRail, { type TabKey } from "@/components/IconRail";
import ModulesDrawer from "@/components/ModulesDrawer";
import RingViewer from "@/components/RingViewer";
import ToastContainer, { type Toast } from "@/components/ToastContainer";
import TopNav from "@/components/TopNav";

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

  const pushToast = useCallback((msg: string, type: Toast["type"] = "error") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, msg, type }]);
    // auto-dismiss after a few seconds; still manually dismissable
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);
  const dismissToast = useCallback(
    (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    []
  );

  // clicking a marker / alert flies the map there and returns to the map view
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
    // victim payments INTO the ring — traced edge first, then biggest, capped
    // so the drawing stays readable
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

  const drawerOpen = activeTab !== "map";

  return (
    <main className="relative h-dvh w-screen select-none overflow-hidden bg-zinc-950">
      <CrimeMap points={hotspots?.points ?? []} hubs={hotspots?.hubs ?? []} focus={focus} />

      {/* readability gradient over the top of the map */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-24 bg-gradient-to-b from-zinc-950/80 to-transparent" />

      <TopNav
        health={health}
        alertCount={alertCount}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onBell={() => setActiveTab("alerts")}
      />

      <IconRail
        activeTab={activeTab}
        onTabChange={(t) => setActiveTab((cur) => (cur === t && t !== "map" ? "map" : t))}
        drawerOpen={drawerOpen}
        onSettings={() => pushToast("Settings — coming soon", "success")}
      />

      {/* hero title + module pills — only on the map view, clear of the rail */}
      {activeTab === "map" && (
        <div className="pointer-events-none absolute left-20 top-20 z-10 hidden lg:block">
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

      {/* top-priority live alert chips (map view only) */}
      {activeTab === "map" && (
        <AlertChips
          events={events}
          hotspots={hotspots}
          onLocate={locate}
          onOpenAll={() => setActiveTab("alerts")}
        />
      )}

      {/* slide-out drawers, one per tab */}
      {drawerOpen && (
        <Drawer onClose={() => setActiveTab("map")}>
          {activeTab === "modules" && <ModulesDrawer events={events} health={health} />}
          {activeTab === "fraud-rings" && (
            <FraudRingsDrawer
              events={events}
              onInjectRing={handleInjectRing}
              onViewRing={setViewRing}
              onOpenConsole={() => setConsoleOpen(true)}
              onError={(msg) => pushToast(msg, "error")}
              injecting={injecting}
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

      {/* merged bottom dock — signal counts + intelligence fusion */}
      <BottomDock
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
