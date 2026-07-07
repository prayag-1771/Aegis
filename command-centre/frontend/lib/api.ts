/** Command-centre backend client. One origin, no per-module URLs in the browser. */

const BASE = process.env.NEXT_PUBLIC_COMMAND_API ?? "http://127.0.0.1:8000";

export interface ScamEvent {
  event_id: string;
  source: string;
  timestamp: string;
  raw_text?: string;
  verdict: "scam" | "suspicious" | "legit";
  risk_score: number;
  scam_type?: string;
  markers?: string[];
  explanation?: string;
  phone_number?: string | null;
  location_hint?: { district?: string; lat?: number; lon?: number } | null;
}

export interface CounterfeitEvent {
  event_id: string;
  timestamp: string;
  denomination: string;
  verdict: "fake" | "genuine" | "uncertain";
  confidence: number;
  missing_features?: string[];
  location_hint?: { district?: string; lat?: number; lon?: number } | null;
}

export interface Ring {
  ring_id: string;
  account_ids: string[];
  risk_score: number;
  size: number;
  total_amount?: number | null;
  label?: string | null;
  district?: string | null;
}

export interface FraudGraph {
  generated_at: string;
  model?: string;
  rings: Ring[];
  accounts: { account_id: string; illicit_probability: number; ring_id?: string | null }[];
  edges?: { source: string; target: string; amount?: number | null }[];
}

export interface FusionOutput {
  generated_at: string;
  summary: string;
  threat_level: "critical" | "high" | "medium" | "low";
  linked_signals: { type: string; ref_event_id: string; reason?: string }[];
  correlation_basis?: string[];
  recommended_actions?: string[];
  map_hotspots?: MapPoint[];
  audit_trail?: { model: string; inputs_hash: string; prompt_version: string } | null;
}

export interface MapPoint {
  type: string;
  district?: string;
  lat: number;
  lon: number;
  weight?: number;
}

export interface Hub {
  hub_id: string;
  lat: number;
  lon: number;
  domains: string[];
  cross_domain: boolean;
  intensity: number;
  district?: string | null;
  n_points: number;
}

export interface EventsPayload {
  scams: ScamEvent[];
  counterfeits: CounterfeitEvent[];
  fraud_graph: FraudGraph | null;
  last_fusion: FusionOutput | null;
}

export interface HotspotsPayload {
  hubs: Hub[];
  n_cross_domain: number;
  points: MapPoint[];
}

export interface HealthPayload {
  status: string;
  modules: Record<string, string>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get<HealthPayload>("/health"),
  events: () => get<EventsPayload>("/events"),
  hotspots: () => get<HotspotsPayload>("/hotspots"),
  fuse: async (): Promise<FusionOutput> => {
    const res = await fetch(`${BASE}/fuse`, { method: "POST" });
    if (!res.ok) throw new Error(`/fuse -> ${res.status}`);
    return res.json();
  },
};
