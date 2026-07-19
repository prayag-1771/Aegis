"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useRef, useState, useEffect } from "react";
import type {
  EventsResponse,
  FusionOutput,
  HealthResponse,
  HotspotsResponse,
  Ring,
  EntryRoutesResponse,
  SupplyTrail,
  SupplyTrailResponse,
  DashboardSummariesResponse,
} from "@/lib/api";
import { fetchEntryRoutes, fetchSupplyTrail, injectDemoRing, fetchDashboardSummaries } from "@/lib/api";
import { gsap, playPanelExit, prefersReducedMotion, useGSAP, usePanelEntrance } from "@/lib/gsap";
import { usePolling } from "@/lib/usePolling";
import AlertChips from "@/components/AlertChips";
import RecenterFX from "@/components/RecenterFX";

import { AlertsSkeleton, DisruptSkeleton, MetricsSkeleton, ResearchSkeleton } from "@/components/Skeletons";

const MapSkeleton = () => (
  <div className="absolute inset-0 z-0 bg-zinc-950 flex flex-col items-center justify-center pointer-events-none">
    <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-zinc-700 via-zinc-950 to-zinc-950"></div>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src="/logo-owl-shield.png" alt="Aegis" className="h-12 w-12 rounded-lg opacity-20 animate-pulse relative z-10 mb-4" />
    <div className="h-3 w-24 bg-zinc-800 rounded animate-pulse relative z-10"></div>
  </div>
);

const LeftCardSkeleton = () => (
  <>
    {/* Left Side */}
    <div className="fixed left-6 top-20 bottom-6 z-[9999] w-72 bg-zinc-900/80 backdrop-blur-md border border-white/10 p-5 flex flex-col animate-pulse pointer-events-none rounded-2xl shadow-2xl">
      <div className="flex justify-between items-center mb-6">
        <div className="h-4 w-1/3 bg-white/10 rounded"></div>
        <div className="h-4 w-6 bg-white/10 rounded"></div>
      </div>
      
      <div className="h-24 w-full bg-white/5 rounded-xl border border-white/5 mb-3"></div>
      <div className="h-24 w-full bg-white/5 rounded-xl border border-white/5 mb-3"></div>
      <div className="h-24 w-full bg-white/5 rounded-xl border border-white/5 mb-3"></div>
      
      <div className="mt-4 mb-2 h-4 w-1/4 bg-white/10 rounded"></div>
      <div className="h-32 w-full bg-white/5 rounded-xl border border-white/5"></div>
    </div>

    {/* Right Side Synchronized Overlay */}
    <div className="fixed left-[380px] top-20 bottom-6 right-10 z-[9999] bg-zinc-900/95 backdrop-blur-md border border-white/10 p-6 flex flex-col animate-pulse pointer-events-none rounded shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="h-10 w-10 bg-white/10 rounded"></div>
        <div className="space-y-2">
          <div className="h-4 w-48 bg-white/10 rounded"></div>
          <div className="h-3 w-32 bg-white/5 rounded"></div>
        </div>
      </div>
      <div className="h-32 w-full bg-white/5 border border-white/10 rounded-lg mb-6"></div>
      <div className="flex-1 bg-white/5 border border-white/10 rounded-lg p-5 flex flex-col gap-4">
        <div className="h-4 w-1/4 bg-white/10 rounded mb-2"></div>
        <div className="h-3 w-full bg-white/5 rounded"></div>
        <div className="h-3 w-5/6 bg-white/5 rounded"></div>
        <div className="h-3 w-4/5 bg-white/5 rounded"></div>
      </div>
    </div>
  </>
);

const AlertsDrawer = dynamic(() => import("@/components/AlertsDrawer"), { ssr: false, loading: AlertsSkeleton });
import FusionChatBot from "@/components/FusionChatBot";
import Drawer from "@/components/Drawer";
import FraudConsole from "@/components/FraudConsole";
import type { TabKey } from "@/components/types";
import RingViewer from "@/components/RingViewer";
import BankPartnerPanel from "@/components/BankPartnerPanel";

const FraudRingsDrawer = dynamic(() => import("@/components/FraudRingsDrawer"), { ssr: false, loading: LeftCardSkeleton });
const ModulesDrawer = dynamic(() => import("@/components/ModulesDrawer"), { ssr: false, loading: LeftCardSkeleton });
const ResearchPanel = dynamic(() => import("@/components/ResearchPanel"), { ssr: false, loading: ResearchSkeleton });
const DisruptPanel = dynamic(() => import("@/components/DisruptPanel"), { ssr: false, loading: DisruptSkeleton });
const ModelCardPanel = dynamic(() => import("@/components/ModelCardPanel"), { ssr: false, loading: MetricsSkeleton });
import ToastContainer, { type Toast } from "@/components/ToastContainer";
import TopNav from "@/components/TopNav";
import InfoPanel from "@/components/InfoPanel";
import SupplyTrailPanel from "@/components/SupplyTrailPanel";

const CrimeMap = dynamic(() => import("@/components/CrimeMap"), { ssr: false, loading: MapSkeleton });

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
  Jamtara: { lat: 23.963, lon: 86.804 },
  Deoghar: { lat: 24.48, lon: 86.7 },
  Alwar: { lat: 27.55, lon: 76.63 },
  Bharatpur: { lat: 27.22, lon: 77.49 },
  Nuh: { lat: 28.1, lon: 77.0 },
  "Chennai Central": { lat: 13.08, lon: 80.27 },
  "Mumbai South": { lat: 18.93, lon: 72.83 },
  "Delhi East": { lat: 28.65, lon: 77.3 },
};

/** Geocode any place name to coordinates via the free, keyless OpenStreetMap
 *  Nominatim API — so search works for EVERY city, not just the demo districts.
 *  Biases results toward India first; falls back to a global lookup. */
async function geocodePlace(
  query: string,
): Promise<{ lat: number; lon: number; label: string } | null> {
  const hit = async (url: string) => {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) return null;
    const rows = (await r.json()) as Array<{ lat: string; lon: string; display_name: string }>;
    if (!rows.length) return null;
    const top = rows[0];
    return {
      lat: parseFloat(top.lat),
      lon: parseFloat(top.lon),
      label: top.display_name.split(",")[0] || query,
    };
  };
  const base = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=";
  // India-biased first (countrycodes=in), then unrestricted global fallback.
  return (
    (await hit(`${base}${encodeURIComponent(query)}&countrycodes=in`)) ??
    (await hit(`${base}${encodeURIComponent(query)}`))
  );
}

export default function Page() {
  const { data: events, refresh: refreshEvents } = usePolling<EventsResponse>("/events", 5000);
  const { data: health } = usePolling<HealthResponse>("/health", 10000);
  const { data: hotspots, refresh: refreshHotspots } = usePolling<HotspotsResponse>(
    "/hotspots",
    8000
  );

  const [activeTab, setActiveTab] = useState<TabKey>("map");
  const [fusion, setFusion] = useState<FusionOutput | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number } | null>(null);
  // Bumped by the owl-logo reset — drives both the map fly-to-India and the sonar FX.
  const [recenterSignal, setRecenterSignal] = useState(0);
  const [injecting, setInjecting] = useState(false);
  const [ringAlerts, setRingAlerts] = useState<RingAlert[]>([]);
  const [viewRing, setViewRing] = useState<Ring | null>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);

  const [aiSummaries, setAiSummaries] = useState<DashboardSummariesResponse | null>(null);

  // Fetch AI summaries whenever underlying threat counts meaningfully change.
  // Stale-while-revalidate: the previous summary stays visible during the
  // refetch (first load shows the skeleton), and the cleanup flag stops a slow
  // older response from overwriting a newer one.
  useEffect(() => {
    if (!events && !hotspots) return;
    let stale = false;
    fetchDashboardSummaries()
      .then((res) => {
        if (!stale) setAiSummaries(res);
      })
      .catch((err) => {
        console.error("Failed to fetch dashboard summaries:", err);
        if (stale) return;
        // Offline floor: the panel must never stick on a skeleton. Derive a
        // deterministic overview from the same event stream the tiles use, so
        // the text keeps tracking the data even with the summariser down.
        const scams = events?.scams?.filter((s) => s.verdict !== "legit").length ?? 0;
        const fakes = events?.counterfeits?.filter((c) => c.verdict === "fake").length ?? 0;
        const rings = events?.fraud_graph?.rings?.length ?? 0;
        setAiSummaries({
          modules_overview: `Fraud Shield has flagged ${scams} scam signal${scams === 1 ? "" : "s"} and Counterfeit Vision has confirmed ${fakes} fake note${fakes === 1 ? "" : "s"}. AI synthesis is unreachable right now — this overview is computed directly from the live event stream.`,
          rings_summary: `The graph engine is tracking ${rings} fraud ring${rings === 1 ? "" : "s"} in the current snapshot. AI synthesis is unreachable right now — figures update as detections stream in.`,
          engine: "offline-fallback",
        });
      });
    return () => {
      stale = true;
    };
  }, [events?.scams?.length, events?.counterfeits?.length, events?.fraud_graph?.rings?.length]);

  const [toasts, setToasts] = useState<Toast[]>([]);
  const [cityAlerts, setCityAlerts] = useState<{district: string; alerts: any[]} | null>(null);
  // Provenance for the searched city: where its fake notes most likely entered.
  // `origin` is null when the evidence cannot support naming one — the panel
  // says so rather than showing the engine's placeholder as a real answer.
  // Highest-plausibility entry route for the searched city, highlighted on the
  // map. Answers "how did notes get here?" — works from a single seizure.
  const [entryRoutes, setEntryRoutes] = useState<EntryRoutesResponse | null>(null);
  /** Where the search card sits. null = centred; set once dragged, so it can be
   *  moved off whatever it is covering on the map. */
  const [cardPos, setCardPos] = useState<{ x: number; y: number } | null>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const cardScope = useRef<HTMLDivElement>(null);
  const [cityOrigin, setCityOrigin] = useState<{
    loading: boolean;
    /** True when this city's own seizures could not trace a direction and the
     *  shown trail is the wider regional one. Must be surfaced, not hidden. */
    regional?: boolean;
    seizuresUsed?: number;
    origin: { name: string; confidence: number; band: string; mode: string; reasoning: string } | null;
    note: string | null;
  } | null>(null);
  const [selectedModule, setSelectedModule] = useState<"scam" | "counterfeit" | null>(null);
  const [bankPartnerOpen, setBankPartnerOpen] = useState(false);

  // Supply Trail state
  const [supplyTrailOpen, setSupplyTrailOpen] = useState(false);
  const [supplyTrailLoading, setSupplyTrailLoading] = useState(false);
  const [supplyTrailData, setSupplyTrailData] = useState<SupplyTrailResponse | null>(null);
  const [activeTrail, setActiveTrail] = useState<SupplyTrail | null>(null);
  /** Who asked for the trail. From "search" the corridor is context and must
   *  not steal the viewport; from "panel" it IS the subject and should frame
   *  itself. Known the moment the trail is set — unlike entryRoutes, which
   *  lands ~2.5s later and so cannot gate a decision made immediately. */
  const [trailSource, setTrailSource] = useState<"search" | "panel" | null>(null);

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

  // Fetch and open the supply trail panel
  const handleOpenSupplyTrail = useCallback(async () => {
    setSupplyTrailOpen(true);
    setSupplyTrailLoading(true);
    try {
      const data = await fetchSupplyTrail();
      setSupplyTrailData(data);
      setActiveTrail(data.all_trails.find((t: any) => t.mode === "rail") || data.best_trail);
      setTrailSource("panel"); // the trail is the subject here — let it frame itself
    } catch (e) {
      pushToast("Supply Trail fetch failed — is the backend running?", "error");
      setSupplyTrailOpen(false);
    } finally {
      setSupplyTrailLoading(false);
    }
  }, [pushToast]);

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

  /** Drag the card by its header. Pointer events cover mouse and touch alike,
   *  and setPointerCapture keeps the drag alive if the cursor outruns the
   *  element or crosses the map canvas. */
  const onCardPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest("button")) return; // let the X through
    const card = e.currentTarget.closest("[data-search-card]") as HTMLElement | null;
    if (!card) return;
    const box = card.getBoundingClientRect();
    dragRef.current = { dx: e.clientX - box.left, dy: e.clientY - box.top };
    setCardPos({ x: box.left, y: box.top }); // pin where it already is, then move
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

  const onCardPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d) return;
    // Keep a grabbable strip on screen — a card dragged fully off is unreachable.
    const x = Math.min(Math.max(e.clientX - d.dx, 8), window.innerWidth - 60);
    const y = Math.min(Math.max(e.clientY - d.dy, 8), window.innerHeight - 40);
    setCardPos({ x, y });
  }, []);

  const onCardPointerUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  /* ── Search card open/close ──
     The card is now anchored to the bottom-left, so it animates in-place
     using opacity and scale without needing x/y translations. */
  useGSAP(
    () => {
      const el = cardScope.current;
      if (!el) return;
      if (prefersReducedMotion()) {
        gsap.set(el, { clearProps: "all" });
        return;
      }
      gsap.fromTo(
        el,
        { opacity: 0, scale: 0.96, transformOrigin: "bottom left" },
        { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.2)", force3D: true, clearProps: "all" },
      );
    },
    // District only: dragging re-renders constantly and must not replay this.
    { dependencies: [cityAlerts?.district] },
  );

  /** Tween the card out, then run `done`. React drops it the instant cityAlerts
   *  goes null, so the exit has to gate that rather than follow it. */
  const dismissCard = useCallback(
    (done: () => void) => {
      const el = cardScope.current;
      if (!el || prefersReducedMotion()) {
        done();
        return;
      }
      gsap.fromTo(
        el,
        { opacity: 1, scale: 1, transformOrigin: "bottom left" },
        {
          opacity: 0,
          scale: 0.96,
          duration: 0.25,
          ease: "power2.in",
          force3D: true,
          overwrite: true,
          onComplete: done,
        },
      );
    },
    [cardPos],
  );

  /** The card's own X — dismisses the popup only. The map highlights belong to
   *  the search, not to this panel, and clear from the top nav. */
  const closeCard = useCallback(
    () =>
      dismissCard(() => {
        setCityAlerts(null);
        setCityOrigin(null);
      }),
    [dismissCard],
  );

  /** Search dismissed from the top nav — take everything it drew back off the
   *  map. Without this the routes and the panel outlive the search that
   *  produced them. The card animates out; the map layers go with it. */
  const clearSearch = useCallback(() => {
    dismissCard(() => {
      setEntryRoutes(null);
      setActiveTrail(null);
      setTrailSource(null);
      setCityOrigin(null);
      setCityAlerts(null);
      setCardPos(null);
    });
  }, [dismissCard]);

  // Owl-logo hard reset: clear every search/overlay/panel, return to the Live Map,
  // and fly the camera out to the India overview with the cyber sonar sweep.
  const handleRecenter = useCallback(() => {
    setActiveTab("map");
    clearSearch();
    setFocus(null);
    setSupplyTrailOpen(false);
    setActiveTrail(null);
    setViewRing(null);
    setSelectedModule(null);
    setBankPartnerOpen(false);
    setConsoleOpen(false);
    setRecenterSignal((n) => n + 1);
  }, [clearSearch]);

  const handleSearch = async (query: string) => {
    const q = query.trim();
    if (!q) return;

    // 1) A known demo district → fly there AND surface its related alerts.
    const districtKey = Object.keys(DEMO_DISTRICT_COORDS).find((k) =>
      k.toLowerCase().includes(q.toLowerCase()),
    );
    if (districtKey) {
      locate(DEMO_DISTRICT_COORDS[districtKey]);
      const dk = districtKey.toLowerCase();
      const inDistrict = (d?: string) =>
        !!d && (d.toLowerCase().includes(dk) || dk.includes(d.toLowerCase()));
      const relatedScams = events?.scams.filter((s) => inDistrict(s.location_hint?.district)) || [];
      const relatedFakes = events?.counterfeits.filter((c) => inDistrict(c.location_hint?.district)) || [];
      // Fraud rings carry a district too — include them so a ring-only district
      // (e.g. Bharatpur) still surfaces its alerts instead of "no alerts".
      const relatedRings =
        (events?.fraud_graph?.rings ?? [])
          .filter((r) => inDistrict(r.district))
          .map((r) => ({
            kind: "ring",
            summary: `${r.label ?? "Fraud ring"} — ${r.size} accounts, risk ${Math.round(
              (r.risk_score ?? 0) * 100,
            )}%`,
          })) || [];
      setCityAlerts({
        district: districtKey,
        alerts: [...relatedScams, ...relatedFakes, ...relatedRings],
      });

      // Where did THIS city's notes physically enter from? Unlike the corridor
      // trail below, this works from a single seizure, so it is the question
      // that actually gets answered for most districts. Highlights the channel
      // on the map from the source press to here.
      if (relatedFakes.length > 0) {
        fetchEntryRoutes(districtKey)
          .then((r) => setEntryRoutes(r))
          .catch(() => setEntryRoutes(null)); // 404 = no seizures here; stay silent
      } else {
        setEntryRoutes(null);
      }

      // Ask Supply Trail where THIS city's fake notes came from. Only meaningful
      // where notes were actually seized, so skip the call otherwise.
      if (relatedFakes.length > 0) {
        setCityOrigin({ loading: true, origin: null, note: null });
        // Ask this district first. If its own seizures cannot trace a direction,
        // fall back to the regional trail — which IS traced, from the full
        // seizure cluster — and label it as regional. Never loosen the engine
        // to manufacture a city-specific line that the evidence cannot support.
        fetchSupplyTrail(undefined, districtKey)
          .then(async (res) => {
            const districtTrail = res.best_trail;
            const dO = districtTrail?.inferred_origin;
            const districtTraced = dO && !dO.reasoning.includes("NOT INFERRED");
            if (districtTraced) return { res, regional: false };
            const wide = await fetchSupplyTrail();
            return { res: wide, regional: true };
          })
          .then(({ res, regional }) => {
            const t = res.best_trail;
            const o = t?.inferred_origin;
            // The engine emits a terminus placeholder when it cannot trace a
            // direction, and marks it NOT INFERRED. Never render that as a
            // finding — a named city implies evidence that does not exist.
            const traced = o && !o.reasoning.includes("NOT INFERRED");
            setCityOrigin({
              loading: false,
              regional: traced ? regional : false,
              seizuresUsed: res.seizures_used,
              origin: traced
                ? {
                    name: o.name,
                    confidence: t!.confidence,
                    band: t!.confidence_band,
                    mode: t!.mode,
                    reasoning: o.reasoning,
                  }
                : null,
              note: traced
                ? null
                : `${relatedFakes.length} seizure(s) here — too few to trace a direction, and no regional trail either.`,
            });
            // Draw the corridor only when a direction was actually traced. The
            // marching dashes read as "notes move this way", so animating an
            // untraced trail would assert movement the evidence never showed.
            setActiveTrail(traced ? t : null);
            setTrailSource("search");
          })
          .catch(() => setCityOrigin(null));
      } else {
        setCityOrigin(null);
      }

      // Nothing auto-hides. The card carries findings an officer reads at their
      // own pace — a timer that yanks it away mid-sentence is a bug, not a
      // feature. It closes on the X, or with the rest of the search.
      setCardPos(null); // fresh search re-centres the card
      return;
    }

    // 2) Any other place → geocode it (free, keyless OSM Nominatim) so search
    //    works for EVERY city, not just the demo districts. Bias to India but
    //    fall back to a global lookup so nothing is unreachable.
    try {
      const coords = await geocodePlace(q);
      if (coords) {
        locate(coords);
        // A city we have no seizures for: clear any previous highlight rather
        // than leaving a stale route drawn over an unrelated place.
        setEntryRoutes(null);
        setActiveTrail(null);
        setTrailSource(null);
        setCityOrigin(null);
        setCityAlerts({ district: coords.label, alerts: [] });
        setCardPos(null);
      } else {
        pushToast(`Location not found: ${q}`, "error");
      }
    } catch {
      pushToast(`Search failed — could not reach the geocoder.`, "error");
    }
  };

  /** ONLY the alerts tab uses the slide-out drawer. This must not be
   *  `activeTab !== "map"`: every other non-map tab (disrupt/metrics/research)
   *  renders its own z-40 full-screen overlay, so a truthy `drawerOpen` mounted
   *  a second, EMPTY drawer behind them — and, worse, kept it mounted across
   *  tab switches. `changeTab` tweens the drawer to opacity:0 on the way out of
   *  alerts; with the node never unmounting, that inline opacity survived, and
   *  the entrance tween (empty deps) never re-ran on the way back — so
   *  returning to Alerts & Analytics showed an invisible drawer. */
  const drawerOpen = activeTab === "alerts";

  // Card entrances for the two full-screen overlays. Keyed on the sub-view too,
  // so picking a module or opening a ring reveals the right-hand card instead
  // of swapping its contents instantly.
  const modulesScope = useRef<HTMLDivElement>(null);
  const ringsScope = useRef<HTMLDivElement>(null);
  const drawerScope = useRef<HTMLDivElement>(null);
  const researchScope = useRef<HTMLDivElement>(null);
  const disruptScope = useRef<HTMLDivElement>(null);
  const metricsScope = useRef<HTMLDivElement>(null);

  usePanelEntrance(modulesScope, ".gsap-panel", [activeTab, selectedModule]);
  usePanelEntrance(ringsScope, ".gsap-panel", [activeTab, viewRing?.ring_id]);
  usePanelEntrance(researchScope, ".gsap-panel", [activeTab]);
  usePanelEntrance(disruptScope, ".gsap-panel", [activeTab]);
  usePanelEntrance(metricsScope, ".gsap-panel", [activeTab]);

  // Overlays are conditionally rendered, so their cards vanish the moment
  // activeTab flips. Tween them out first, flip after.
  const closeModules = () =>
    playPanelExit(modulesScope, () => {
      setActiveTab("map");
      setSelectedModule(null);
    });
  const closeRings = () =>
    playPanelExit(ringsScope, () => {
      setActiveTab("map");
      setViewRing(null);
    });
  const closeResearch = () => playPanelExit(researchScope, () => setActiveTab("map"));
  const closeDisrupt = () => playPanelExit(disruptScope, () => setActiveTab("map"));
  const closeMetrics = () => playPanelExit(metricsScope, () => setActiveTab("map"));



  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Blur whatever is focused so the browser doesn't apply :focus-visible to the tab button
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }

        // Do not close background tabs if a modal overlay is handling the escape key
        if (bankPartnerOpen || consoleOpen) return;

        if (activeTab === "modules") {
          if (selectedModule) setSelectedModule(null);
          else closeModules();
          return;
        }

        if (activeTab === "fraud-rings") {
          if (viewRing) setViewRing(null);
          else closeRings();
          return;
        }

        if (activeTab === "research") {
          closeResearch();
          return;
        }
        
        if (activeTab === "disrupt") {
          closeDisrupt();
          return;
        }
        
        if (activeTab === "metrics") {
          closeMetrics();
          return;
        }

        if (activeTab === "map" && supplyTrailOpen) {
          setSupplyTrailOpen(false);
          setActiveTrail(null);
          setTrailSource(null);
          return;
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeTab, selectedModule, viewRing, bankPartnerOpen, consoleOpen, supplyTrailOpen]);

  /** Tab switching is a close path for the alerts drawer — it sits below the
   *  nav, unlike the z-50 overlays whose X button is the only way out. Tween it
   *  away before the tab flips, or leaving it is a hard cut. */
  const changeTab = (t: typeof activeTab) => {
    const next = activeTab === t && t !== "map" ? "map" : t;
    if (next === activeTab) return;

    if (activeTab === "alerts" && drawerScope.current) {
      playPanelExit(drawerScope, () => setActiveTab(next));
      return;
    }
    setActiveTab(next);
  };

  return (
    <main className="relative h-dvh w-screen select-none overflow-hidden bg-zinc-950">
      <CrimeMap
        points={hotspots?.points ?? []}
        hubs={hotspots?.hubs ?? []}
        focus={focus}
        // Both are shown together: the orange corridor is the wider context
        // (how notes move through the region), the violet entry route is the
        // specific claim (how they reached THIS city). Neither auto-frames the
        // map — the view stays on the searched city, see focus handling.
        trail={activeTrail}
        entryRoute={entryRoutes?.routes?.[0] ?? null}
        // Keyed off where the trail CAME FROM, not off entryRoutes: that
        // arrives ~2.5s later (it waits on the narrator), so gating on it left
        // a window where the trail framed the whole corridor and zoomed away
        // from the searched city before the flag could ever flip.
        suppressTrailFit={trailSource === "search"}
        recenterSignal={recenterSignal}
      />

      {/* Cyber radar sonar sweep — plays over the map on each owl-logo reset */}
      <RecenterFX signal={recenterSignal} />

      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-24 bg-gradient-to-b from-zinc-950/80 to-transparent" />

      <TopNav
        health={health}
        alertCount={alertCount}
        activeTab={activeTab}
        onTabChange={changeTab}
        onBell={() => setActiveTab("alerts")}
        onSearch={handleSearch}
        onSearchClear={clearSearch}
        onLogoClick={handleRecenter}
        // Supply Trail is the only RIGHT-anchored panel the next-tab chevron can
        // collide with — the alerts drawer opens on the left, so listing it here
        // shifted the arrow aside for a panel that was never in its way.
        isRightPanelOpen={supplyTrailOpen && activeTab === "map"}
      />

      {/* Localized alerts panel (from search). Centred until dragged, then it
          sits where it was put. Stays until closed — no timer. */}
      {cityAlerts && (
        <div
          ref={cardScope}
          data-search-card
          // Capped at 70vh and column-flexed: the header stays put while the
          // body scrolls. Previously only the alerts list scrolled, so the entry
          // section grew the card past the viewport and ran off screen.
          className={`absolute z-40 flex h-[350px] max-h-[70vh] w-[320px] min-w-[320px] min-h-[200px] max-w-[90vw] flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/90 shadow-2xl backdrop-blur-md pointer-events-auto resize ${
            cardPos ? "" : "bottom-10 left-[180px]"
          }`}
          style={cardPos ? { left: cardPos.x, top: cardPos.y } : undefined}
        >
          <div
            onPointerDown={onCardPointerDown}
            onPointerMove={onCardPointerMove}
            onPointerUp={onCardPointerUp}
            onPointerCancel={onCardPointerUp}
            className="shrink-0 bg-zinc-800/50 px-4 py-2 border-b border-zinc-800 flex justify-between items-center cursor-grab active:cursor-grabbing select-none touch-none"
            title="Drag to move"
          >
            <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
              {cityAlerts.district} Alerts
            </h3>
            <button
              // Dismisses the popup only. The map highlights belong to the
              // search, not to this panel, and clear from the top nav.
              onClick={closeCard}
              className="text-zinc-400 hover:text-zinc-100"
            >
              &times;
            </button>
          </div>
          {/* One scroll region for everything under the header, so a long entry
              section scrolls instead of growing the card off the screen. */}
          <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="p-2">
            {cityAlerts.alerts.length === 0 ? (
              <p className="text-xs text-zinc-500 text-center py-4">No active alerts for this region.</p>
            ) : (
              cityAlerts.alerts.map((a, i) => (
                <div key={i} className="mb-2 p-2 bg-zinc-800/30 rounded-lg border border-zinc-800/50">
                  <div className="text-xs font-medium text-zinc-200">
                    {a.kind === 'ring'
                      ? 'Fraud Ring'
                      : a.verdict
                      ? (a.verdict === 'fake' ? 'Counterfeit Note' : 'Scam Call')
                      : 'Alert'}
                  </div>
                  <div className="text-[10px] text-zinc-500 mt-1">{a.summary || "Suspicious activity detected."}</div>
                </div>
              ))
            )}
          </div>

          {/* Entry channels: how notes physically reached this city. Ranked by
              the engine; the top one is highlighted on the map. */}
          {entryRoutes && entryRoutes.routes.length > 0 && (
            <div className="border-t border-zinc-800 bg-zinc-950/60 px-3 py-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-widest text-violet-400/70">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-400 shadow-[0_0_6px_rgba(168,85,247,0.9)]" />
                Probable entry channel
              </div>

              {entryRoutes.routes.map((r, i) => {
                const haul = r.legs.find((l) => l.kind === "haul");
                return (
                  <div
                    key={i}
                    className={`mb-1.5 rounded-lg border px-2 py-1.5 ${
                      i === 0
                        ? "border-violet-500/30 bg-violet-500/10"
                        : "border-zinc-800/60 bg-zinc-800/20"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className={`text-[11px] font-medium ${
                          i === 0 ? "text-violet-200" : "text-zinc-400"
                        }`}
                      >
                        {r.source} → {r.modes.join(" + ")}
                      </span>
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                          i === 0
                            ? "bg-violet-500/25 text-violet-200"
                            : "bg-zinc-700/40 text-zinc-500"
                        }`}
                      >
                        {Math.round(r.plausibility * 100)}%
                      </span>
                    </div>
                    <div className="mt-0.5 text-[9px] text-zinc-500">
                      {Math.round(r.total_km)} km
                      {haul ? ` · via ${haul.to}` : ""}
                      {r.passes_fir.length > 0
                        ? ` · ${r.passes_fir.length} FIR${r.passes_fir.length > 1 ? "s" : ""} on route`
                        : " · no FIRs on route"}
                    </div>
                  </div>
                );
              })}

              <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-400">
                {entryRoutes.narrative.summary}
              </p>

              {entryRoutes.narrative.recommended_actions.length > 0 && (
                <ul className="mt-1.5 space-y-0.5">
                  {entryRoutes.narrative.recommended_actions.slice(0, 3).map((a, i) => (
                    <li key={i} className="flex gap-1.5 text-[9px] leading-relaxed text-zinc-500">
                      <span className="text-violet-500/60">▸</span>
                      {a}
                    </li>
                  ))}
                </ul>
              )}

              <p className="mt-1.5 text-[9px] italic leading-relaxed text-zinc-600">
                Sources are printing presses on police/press record. Plausibility is a
                hypothesis score — a banknote carries no origin label.
              </p>
            </div>
          )}

          {/* Corridor direction — the older, coarser answer. Only worth showing
              when entry channels could not be computed; otherwise it repeats
              the section above with less detail. */}
          {cityOrigin && !entryRoutes && (
            <div className="border-t border-zinc-800 bg-zinc-950/60 px-3 py-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-widest text-zinc-500">
                <span>🚂</span>
                {cityOrigin.regional ? "Probable source · regional" : "Probable source"}
              </div>

              {cityOrigin.loading ? (
                <p className="py-1 text-[10px] text-zinc-500">Tracing corridors…</p>
              ) : cityOrigin.origin ? (
                <>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-orange-300">
                      {cityOrigin.origin.name}
                    </span>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${
                        cityOrigin.origin.band === "high"
                          ? "bg-orange-500/20 text-orange-300"
                          : cityOrigin.origin.band === "medium"
                          ? "bg-amber-500/20 text-amber-300"
                          : "bg-zinc-700/40 text-zinc-400"
                      }`}
                    >
                      {Math.round(cityOrigin.origin.confidence * 100)}% · {cityOrigin.origin.band}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-zinc-500">
                    via {cityOrigin.origin.mode}
                  </div>
                  {cityOrigin.regional && (
                    <p className="mt-1.5 rounded border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[9px] leading-relaxed text-amber-200/70">
                      {cityAlerts.district}&rsquo;s own seizures cannot trace a direction.
                      This is the regional trail across all {cityOrigin.seizuresUsed} seizures —
                      it shows how notes move through the corridor, not into this city
                      specifically.
                    </p>
                  )}
                  <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-500">
                    {cityOrigin.origin.reasoning}
                  </p>
                  <p className="mt-1.5 text-[9px] italic leading-relaxed text-zinc-600">
                    Investigative hypothesis, not forensic proof — a note carries no origin label.
                  </p>
                </>
              ) : (
                <p className="text-[10px] leading-relaxed text-zinc-500">{cityOrigin.note}</p>
              )}
            </div>
          )}
          </div>
        </div>
      )}

      {/* Research Lab — the three graph-ML experiments, made visible */}
      {activeTab === "research" && (
        <div className="absolute inset-0 z-40 bg-zinc-950/60 backdrop-blur-md flex flex-col items-center justify-center px-6 pb-6 pt-28 pointer-events-auto">
          <div ref={researchScope} className="w-full max-w-[95vw] max-h-[85vh] flex gap-4 relative">
            <div className="absolute -top-5 left-0 z-10 flex items-center">
              <span className="text-xs text-zinc-500 whitespace-nowrap">Press <kbd className="font-sans border border-white/10 bg-white/5 px-1.5 py-0.5 rounded text-zinc-400 mx-1">Esc</kbd> to exit</span>
            </div>
            <div className="absolute -top-2 -right-2 z-10 flex items-center gap-2">
              <button
                onClick={closeResearch}
                className="text-zinc-400 hover:text-zinc-100 p-2 hover:bg-white/10 transition bg-zinc-900/80 border border-white/10"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div className="gsap-panel w-full bg-zinc-900 border border-white/10 shadow-2xl flex flex-col overflow-hidden" style={{ opacity: 0 }}>
              <ResearchPanel onClose={closeResearch} />
            </div>
          </div>
        </div>
      )}

      {/* Disrupt & Respond — detections turned into concrete, auditable actions */}
      {activeTab === "disrupt" && (
        <div className="absolute inset-0 z-40 bg-zinc-950/60 backdrop-blur-md flex flex-col items-center justify-center px-6 pb-6 pt-28 pointer-events-auto">
          <div ref={disruptScope} className="w-full max-w-[95vw] max-h-[85vh] flex gap-4 relative">
            <div className="absolute -top-5 left-0 z-10 flex items-center">
              <span className="text-xs text-zinc-500 whitespace-nowrap">Press <kbd className="font-sans border border-white/10 bg-white/5 px-1.5 py-0.5 rounded text-zinc-400 mx-1">Esc</kbd> to exit</span>
            </div>
            <div className="absolute -top-2 -right-2 z-10 flex items-center gap-2">
              <button
                onClick={closeDisrupt}
                className="text-zinc-400 hover:text-zinc-100 p-2 hover:bg-white/10 transition bg-zinc-900/80 border border-white/10"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div className="gsap-panel w-full bg-zinc-900 border border-white/10 shadow-2xl flex flex-col overflow-hidden" style={{ opacity: 0 }}>
              <DisruptPanel onClose={closeDisrupt} />
            </div>
          </div>
        </div>
      )}

      {/* Metrics — Model Card (measured metrics, the evaluation focus) */}
      {activeTab === "metrics" && (
        <div className="absolute inset-0 z-40 bg-zinc-950/60 backdrop-blur-md flex flex-col items-center justify-center px-6 pb-6 pt-28 pointer-events-auto">
          <div ref={metricsScope} className="w-full max-w-[95vw] max-h-[85vh] flex gap-4 relative">
            <div className="absolute -top-5 left-0 z-10 flex items-center">
              <span className="text-xs text-zinc-500 whitespace-nowrap">Press <kbd className="font-sans border border-white/10 bg-white/5 px-1.5 py-0.5 rounded text-zinc-400 mx-1">Esc</kbd> to exit</span>
            </div>
            <div className="absolute -top-2 -right-2 z-10 flex items-center gap-2">
              <button
                onClick={closeMetrics}
                className="text-zinc-400 hover:text-zinc-100 p-2 hover:bg-white/10 transition bg-zinc-900/80 border border-white/10"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div className="gsap-panel w-full bg-zinc-900 border border-white/10 shadow-2xl flex flex-col overflow-hidden" style={{ opacity: 0 }}>
              <ModelCardPanel onClose={closeMetrics} />
            </div>
          </div>
        </div>
      )}

      {/* Bank Partner — financial-institution B2B console. Opened from the
          Modules → Stakeholder Surfaces list; sits above the modules overlay. */}
      {bankPartnerOpen && (
        <div className="absolute inset-0 z-[60] pointer-events-auto">
          <BankPartnerPanel onClose={() => setBankPartnerOpen(false)} />
        </div>
      )}

      {/* hero title + module pills */}
      {activeTab === "map" && (
        <div className="pointer-events-none absolute left-5 top-20 z-10 hidden lg:block">
          <h1 className="text-4xl font-extralight tracking-wide text-zinc-100 drop-shadow">
            Public Safety Intelligence
          </h1>
          <div className="mt-2 flex gap-2 text-[10px] uppercase tracking-widest text-zinc-500">
            {!events || !hotspots ? (
              <>
                <div className="glass px-2.5 py-1 w-28 h-[22px] animate-pulse !bg-zinc-800/50"></div>
                <div className="glass px-2.5 py-1 w-28 h-[22px] animate-pulse !bg-zinc-800/50"></div>
                <div className="glass px-2.5 py-1 w-28 h-[22px] animate-pulse !bg-zinc-800/50"></div>
              </>
            ) : (
              <>
                <span className="glass pointer-events-auto px-2.5 py-1">Scam · Fraud Shield</span>
                <span className="glass pointer-events-auto px-2.5 py-1">Counterfeit · Vision</span>
                <span className="glass pointer-events-auto px-2.5 py-1">Rings · Graph ML</span>
              </>
            )}
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

      {/* slide-out drawers for alerts and analytics */}
      {drawerOpen && (
        <Drawer scopeRef={drawerScope} onClose={() => setActiveTab("map")}>
          <AlertsDrawer
            events={events}
            hotspots={hotspots}
            fusion={lastFusion}
            ringAlerts={ringAlerts}
            onLocate={locate}
          />
        </Drawer>
      )}

      {/* Full screen blur overlay for Modules — side-by-side layout */}
      {activeTab === "modules" && (
        <div className="absolute inset-0 z-40 bg-zinc-950/60 backdrop-blur-md flex flex-col items-center justify-center px-6 pb-6 pt-28 pointer-events-auto">
          <div ref={modulesScope} className="w-full max-w-[95vw] max-h-[85vh] flex gap-4 relative">
            {/* Close button */}
            <div className="absolute -top-5 left-0 z-10 flex items-center">
              <span className="text-xs text-zinc-500 whitespace-nowrap">Press <kbd className="font-sans border border-white/10 bg-white/5 px-1.5 py-0.5 rounded text-zinc-400 mx-1">Esc</kbd> to exit</span>
            </div>
            <div className="absolute -top-2 -right-2 z-10 flex items-center gap-2">
              <button
                onClick={closeModules}
                className="text-zinc-400 hover:text-zinc-100 p-2 hover:bg-white/10 transition bg-zinc-900/80 border border-white/10"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>

            {/* LEFT: Modules list */}
            <div className="gsap-panel w-[380px] shrink-0 max-h-[90vh] overflow-y-auto bg-zinc-900 border border-white/10 shadow-2xl" style={{ opacity: 0 }}>
              <ModulesDrawer
                events={events}
                health={health}
                onSelectModule={setSelectedModule}
                onOpenBankPartner={() => setBankPartnerOpen(true)}
              />
            </div>

            {/* RIGHT: InfoPanel or GenAI summary */}
            <div className="gsap-panel flex-1 min-w-0 max-h-[90vh] overflow-y-auto bg-zinc-900 border border-white/10 shadow-2xl" style={{ opacity: 0 }}>
              {selectedModule ? (
                <InfoPanel
                  moduleType={selectedModule}
                  events={events}
                  onClose={() => setSelectedModule(null)}
                  inline
                />
              ) : (
                /* Default GenAI Summary */
                <div className="p-6 flex flex-col gap-6 h-full">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center bg-emerald-500/20">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5 text-emerald-400"><circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" /></svg>
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-zinc-100">Aegis Detection Modules</h2>
                      <p className="text-[11px] text-zinc-500">AI-powered threat detection suite</p>
                    </div>
                  </div>

                  <div className="bg-white/5 border border-white/10 p-5">
                    <div className="text-xs font-medium text-zinc-300 mb-3 flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      System Health
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-emerald-300">{Object.values(health?.modules ?? {}).filter(s => s === "up").length}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Modules Online</div>
                      </div>
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-red-300">{events?.scams.filter(s => s.verdict !== "legit").length ?? 0}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Scam Detections</div>
                      </div>
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-amber-300">{events?.counterfeits.filter(c => c.verdict === "fake").length ?? 0}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Counterfeits Found</div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-white/5 border border-white/10 p-5 flex-1 relative overflow-hidden">
                    <div className="text-xs font-medium text-zinc-300 mb-3 flex justify-between items-center">
                      AI Intelligence Overview
                      {aiSummaries && <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${aiSummaries.engine.includes("fallback") ? "text-amber-400 border-amber-400/30 bg-amber-400/10" : "text-emerald-400 border-emerald-400/30 bg-emerald-400/10 shadow-[0_0_8px_rgba(52,211,153,0.3)]"}`}>{aiSummaries.engine.split("/")[0]}</span>}
                    </div>
                    {aiSummaries ? (
                      <div className="text-[12px] leading-relaxed text-zinc-400 space-y-3">
                        <p>{aiSummaries.modules_overview}</p>
                        <p>
                          <strong className="text-zinc-200">Recommendation:</strong> Click on either the Scam Call or Note Scan card on the left 
                          to view detailed reports, individual verdicts, and a consolidated AI summary of the latest detections.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-3 mt-4 animate-pulse">
                        <div className="h-2 w-full bg-white/10 rounded"></div>
                        <div className="h-2 w-5/6 bg-white/10 rounded"></div>
                        <div className="h-2 w-4/6 bg-white/10 rounded"></div>
                        <div className="h-2 w-full bg-white/10 rounded mt-4"></div>
                        <div className="h-2 w-3/4 bg-white/10 rounded"></div>
                      </div>
                    )}
                  </div>

                  <div className="text-[10px] text-zinc-600 text-center">
                    Click a module on the left to view detailed analysis →
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Full screen blur overlay for Fraud Rings — side-by-side layout */}
      {activeTab === "fraud-rings" && (
        <div className="absolute inset-0 z-40 bg-zinc-950/60 backdrop-blur-md flex flex-col items-center justify-center px-6 pb-6 pt-28 pointer-events-auto">
          <div ref={ringsScope} className="w-full max-w-[95vw] max-h-[85vh] flex gap-4 relative">
            {/* Close button */}
            <div className="absolute -top-5 left-0 z-10 flex items-center">
              <span className="text-xs text-zinc-500 whitespace-nowrap">Press <kbd className="font-sans border border-white/10 bg-white/5 px-1.5 py-0.5 rounded text-zinc-400 mx-1">Esc</kbd> to exit</span>
            </div>
            <div className="absolute -top-2 -right-2 z-10 flex items-center gap-2">
              <button
                onClick={closeRings}
                className="text-zinc-400 hover:text-zinc-100 p-2 hover:bg-white/10 transition bg-zinc-900/80 border border-white/10"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>

            {/* LEFT: Fraud ring list */}
            <div className="gsap-panel w-[380px] shrink-0 max-h-[90vh] overflow-y-auto bg-zinc-900 border border-white/10 shadow-2xl" style={{ opacity: 0 }}>
              <FraudRingsDrawer
                events={events}
                onInjectRing={handleInjectRing}
                onViewRing={setViewRing}
                onOpenConsole={() => setConsoleOpen(true)}
                onError={(msg) => pushToast(msg, "error")}
                injecting={injecting}
              />
            </div>

            {/* RIGHT: GenAI summary OR RingViewer */}
            <div className="gsap-panel flex-1 min-w-0 max-h-[90vh] overflow-y-auto bg-zinc-900 border border-white/10 shadow-2xl" style={{ opacity: 0 }}>
              {viewRing && viewerData ? (
                <div className="p-5">
                  <RingViewer
                    title={`${viewRing.ring_id} · ${viewRing.label ?? "fraud ring"}`}
                    subtitle={`${viewRing.district ?? "unknown district"} · ${viewRing.size} accounts · risk ${Math.round(viewRing.risk_score * 100)}%${viewRing.total_amount != null ? ` · ₹${Math.round(viewRing.total_amount / 100000)}L` : ""}`}
                    badge="SIMULATED CITY"
                    label={viewRing.label}
                    nodes={viewerData.nodes}
                    edges={viewerData.edges}
                    trail={viewerData.trail}
                    onClose={() => setViewRing(null)}
                    inline
                  />
                </div>
              ) : (
                /* Default GenAI Summary Card */
                <div className="p-6 flex flex-col gap-6 h-full">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center bg-violet-500/20">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5 text-violet-400"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" /></svg>
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-zinc-100">Fraud Network AI Analysis</h2>
                      <p className="text-[11px] text-zinc-500">Graph ML · Real-time detection engine</p>
                    </div>
                  </div>

                  <div className="bg-white/5 border border-white/10 p-5">
                    <div className="text-xs font-medium text-zinc-300 mb-3 flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      Network Status
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-violet-300">{events?.fraud_graph?.rings?.length ?? 0}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Active Rings</div>
                      </div>
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-amber-300">{events?.fraud_graph?.accounts?.length ?? 0}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Flagged Accounts</div>
                      </div>
                      <div className="bg-black/20 p-3 text-center">
                        <div className="text-2xl font-semibold text-red-300">{events?.fraud_graph?.edges?.length ?? 0}</div>
                        <div className="text-[10px] text-zinc-500 mt-1">Transactions</div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-white/5 border border-white/10 p-5 flex-1 relative overflow-hidden">
                    <div className="text-xs font-medium text-zinc-300 mb-3 flex justify-between items-center">
                      Consolidated AI Summary
                      {aiSummaries && <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${aiSummaries.engine.includes("fallback") ? "text-amber-400 border-amber-400/30 bg-amber-400/10" : "text-emerald-400 border-emerald-400/30 bg-emerald-400/10 shadow-[0_0_8px_rgba(52,211,153,0.3)]"}`}>{aiSummaries.engine.split("/")[0]}</span>}
                    </div>
                    {aiSummaries ? (
                      <div className="text-[12px] leading-relaxed text-zinc-400 space-y-3">
                        <p>{aiSummaries.rings_summary}</p>
                        <p>
                          <strong className="text-zinc-200">Recommendation:</strong> Click any ring on the left panel to visualize its money flow topology, 
                          run the simulation, and inspect per-account evidence. Use the "Inject ring" feature to stress-test detection on synthetic fraud scenarios.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-3 mt-4 animate-pulse">
                        <div className="h-2 w-full bg-white/10 rounded"></div>
                        <div className="h-2 w-5/6 bg-white/10 rounded"></div>
                        <div className="h-2 w-4/6 bg-white/10 rounded"></div>
                        <div className="h-2 w-full bg-white/10 rounded mt-4"></div>
                        <div className="h-2 w-3/4 bg-white/10 rounded"></div>
                      </div>
                    )}
                  </div>

                  <div className="text-[10px] text-zinc-600 text-center">
                    Click a ring on the left to view its detailed money flow graph →
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}


      {/* ── Bottom-right action row ──
          One flex row so the buttons space themselves. They used to be two
          independently-fixed elements (right-16 and right-56) whose gap was a
          magic number that had to be kept in sync by hand — and Fusion's label
          changes width at runtime ("Run Fusion" → "Correlating…"), so the gap
          silently closed. right-16 clears the map's zoom controls, which own
          the actual corner. */}
      {/* Slides clear of the Supply Trail panel while it is open, instead of
          floating over its content. The offset mirrors that panel's own
          `w-[400px] max-w-[90vw]` exactly, so the two cannot drift apart; the
          duration matches its slide. Transform, not `right`, so the move is
          compositor-only over the live map — and the Fusion chat panel, being a
          child, comes along. */}
      <div
        className={`pointer-events-none fixed bottom-6 right-16 z-50 flex items-center gap-3 transition-transform duration-300 ${
          // Shift by the panel width MINUS most of this row's own `right-16`
          // inset. Translating the full 400px stacked that 64px inset on top of
          // the panel edge, leaving a wide gap — and on narrower windows it
          // carried the button off the left edge ("...usion").
          supplyTrailOpen ? "-translate-x-[calc(min(400px,90vw)-3rem)]" : ""
        }`}
      >
        {/* Hidden while its own panel is open: the row sits above that panel's
            z-index, and "open Supply Trail" is meaningless when it already is. */}
        {(!supplyTrailOpen && (activeTab === "map" || activeTab === "alerts")) && (
          !events || !hotspots ? (
            <div className="pointer-events-auto rounded-full border border-zinc-800 bg-zinc-900/80 mt-0.5 w-[140px] h-[36px] animate-pulse" />
          ) : (
            <button
              onClick={handleOpenSupplyTrail}
              className={`pointer-events-auto flex items-center gap-2 rounded-full border px-4 py-2.5 mt-0.5 text-[11px] font-semibold uppercase tracking-wide shadow-xl backdrop-blur-sm transition-all duration-300 ${
                activeTrail
                  ? "border-orange-500/60 bg-orange-500/20 text-orange-300 hover:bg-orange-500/30"
                  : "border-white/10 bg-zinc-900/80 text-zinc-400 hover:border-white/20 hover:text-zinc-200"
              }`}
              title="Open Supply Trail — counterfeit note provenance"
            >
              {activeTrail && (
                <span className="h-1.5 w-1.5 rounded-full bg-orange-400 animate-pulse" />
              )}
              🚂 Supply Trail
            </button>
          )
        )}
        {!events || !hotspots ? (
          <div className="pointer-events-auto rounded-full bg-zinc-800/80 shadow-lg w-[42px] h-[42px] animate-pulse border border-zinc-700/50" />
        ) : (
          <FusionChatBot
            fusion={lastFusion}
            events={events}
            onFused={handleFused}
            onError={(msg) => pushToast(msg, "error")}
          />
        )}
      </div>

      {consoleOpen && (
        <FraudConsole onClose={() => setConsoleOpen(false)} onCommitted={handleConsoleCommitted} />
      )}

      {/* ── Supply Trail slide-in panel (right side, over map) ──
          z-[60] puts the panel ABOVE the top nav (z-50). At z-40 the nav drew
          over it, so the search box, bell and clock landed on top of the
          panel's own header and its close button. */}
      {supplyTrailOpen && (
        <div
          className={`pointer-events-auto absolute right-0 top-0 flex h-full w-[400px] max-w-[90vw] flex-col border-l border-white/10 bg-zinc-950/95 shadow-2xl backdrop-blur-xl transition-transform duration-300 ${
            // Live Map and Alerts & Analytics are the only tabs this panel
            // belongs on — there it goes above the nav (z-50) so nothing draws
            // over its header. Every other tab is a full-screen overlay at
            // z-40, and the panel must sit BEHIND that, not float on top of
            // Modules/Disrupt/Research content.
            activeTab === "map" || activeTab === "alerts" ? "z-[60]" : "z-30"
          }`}
        >
          <SupplyTrailPanel
            trail={activeTrail}
            allTrails={supplyTrailData?.all_trails ?? []}
            loading={supplyTrailLoading}
            onClose={() => {
              setSupplyTrailOpen(false);
              setActiveTrail(null);
              setTrailSource(null);
            }}
            onFlyTo={(lat, lon) => setFocus({ lat, lon })}
            onSelectTrail={(t) => {
              setActiveTrail(t);
              setTrailSource("panel");
            }}
          />
        </div>
      )}

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </main>
  );
}
