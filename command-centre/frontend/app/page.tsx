"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type {
  EventsResponse,
  FusionOutput,
  HealthResponse,
  HotspotsResponse,
} from "@/lib/api";
import { injectDemoRing } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import FusionPanel from "@/components/FusionPanel";
import LeftPanel from "@/components/LeftPanel";
import TopNav from "@/components/TopNav";
import VolumePanel from "@/components/VolumePanel";
import WarningPanel from "@/components/WarningPanel";

const CrimeMap = dynamic(() => import("@/components/CrimeMap"), { ssr: false });

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

  const [fusion, setFusion] = useState<FusionOutput | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number } | null>(null);
  const [injecting, setInjecting] = useState(false);

  const lastFusion = fusion ?? events?.last_fusion ?? null;
  const alertCount =
    (events?.scams.filter((s) => s.verdict !== "legit").length ?? 0) +
    (events?.counterfeits.filter((c) => c.verdict === "fake").length ?? 0) +
    (hotspots?.n_cross_domain ?? 0);

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
        const graph = await injectDemoRing(district, accounts);
        const coords = DEMO_DISTRICT_COORDS[district];
        if (coords) setFocus(coords);
        await Promise.all([refreshEvents(), refreshHotspots()]);
        return graph;
      } finally {
        setInjecting(false);
      }
    },
    [refreshEvents, refreshHotspots]
  );

  return (
    <main className="relative h-dvh w-screen select-none overflow-hidden bg-zinc-950">
      <CrimeMap points={hotspots?.points ?? []} hubs={hotspots?.hubs ?? []} focus={focus} />

      {/* readability gradients over the map */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[40rem] bg-gradient-to-r from-zinc-950/85 via-zinc-950/35 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-24 bg-gradient-to-b from-zinc-950/80 to-transparent" />

      <TopNav health={health} alertCount={alertCount} />

      {/* hero title, like the reference */}
      <div className="pointer-events-none absolute left-[23rem] top-16 z-10 hidden lg:block">
        <h1 className="text-4xl font-extralight tracking-wide text-zinc-100 drop-shadow">
          Public Safety Intelligence
        </h1>
        <div className="mt-2 flex gap-2 text-[10px] uppercase tracking-widest text-zinc-500">
          <span className="glass pointer-events-auto px-2.5 py-1">Scam · Fraud Shield</span>
          <span className="glass pointer-events-auto px-2.5 py-1">Counterfeit · Vision</span>
          <span className="glass pointer-events-auto px-2.5 py-1">Rings · Graph ML</span>
        </div>
      </div>

      <LeftPanel
        events={events}
        health={health}
        hotspots={hotspots}
        onInjectRing={handleInjectRing}
        injecting={injecting}
      />
      <WarningPanel events={events} hotspots={hotspots} fusion={lastFusion} onLocate={setFocus} />
      <FusionPanel fusion={lastFusion} onFused={handleFused} />
      <VolumePanel events={events} />
    </main>
  );
}
