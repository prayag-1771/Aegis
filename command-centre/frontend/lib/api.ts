/** Types mirror contracts/*.schema.json — the team's locked data contract. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:4000";

export interface LocationHint {
  district?: string;
  lat?: number;
  lon?: number;
}

export interface ScamEvent {
  event_id: string;
  source: string;
  timestamp: string;
  raw_text: string;
  verdict: "scam" | "suspicious" | "legit";
  risk_score: number;
  scam_type?: string;
  markers?: string[];
  explanation?: string;
  phone_number?: string;
  location_hint?: LocationHint;
}

export interface CounterfeitEvent {
  event_id: string;
  timestamp: string;
  denomination: string;
  verdict: "fake" | "genuine" | "uncertain";
  confidence: number;
  missing_features?: string[];
  image_ref?: string;
  location_hint?: LocationHint;
}

export interface Ring {
  ring_id: string;
  account_ids: string[];
  risk_score: number;
  size: number;
  total_amount: number;
  label?: string;
  district?: string;
}

export interface AccountFeatures {
  degree_centrality?: number;
  clustering_coefficient?: number;
  in_degree?: number;
  out_degree?: number;
  throughput_ratio?: number | null;
  burst_ratio?: number | null;
  round_amount_ratio?: number | null;
  tx_count?: number | null;
}

export interface GraphAccount {
  account_id: string;
  illicit_probability: number;
  ring_id: string | null;
  features?: AccountFeatures | null;
}

export interface FraudGraph {
  generated_at?: string;
  model?: string;
  rings: Ring[];
  accounts?: GraphAccount[];
  edges?: { source: string; target: string; amount: number; timestamp?: string }[];
}

export interface MoneyTrail {
  scam_event_id: string;
  ring_id: string;
  account_id: string;
  amount: number;
  district?: string | null;
}

export interface FusionOutput {
  generated_at?: string;
  summary: string;
  threat_level: string;
  linked_signals: { type: string; ref_event_id: string; reason: string }[];
  correlation_basis: string[];
  recommended_actions: string[];
  map_hotspots: MapPoint[];
  money_trails?: MoneyTrail[];
  audit_trail?: { model: string; inputs_hash: string; prompt_version: string };
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
  district: string | null;
  n_points: number;
  points: MapPoint[];
}

export interface EventsResponse {
  scams: ScamEvent[];
  counterfeits: CounterfeitEvent[];
  fraud_graph: FraudGraph | null;
  last_fusion: FusionOutput | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  version?: string;
  modules: Record<string, string>;
}

export interface HotspotsResponse {
  hubs: Hub[];
  n_cross_domain: number;
  points: MapPoint[];
}

export type DemoRingResponse = FraudGraph;

export async function runFusion(): Promise<FusionOutput> {
  const r = await fetch(`${API_BASE}/api/fuse`, { method: "POST" });
  if (!r.ok) throw new Error(`fusion failed: ${r.status}`);
  return r.json();
}

export async function injectDemoRing(
  district: string,
  accounts?: string[]
): Promise<DemoRingResponse> {
  const r = await fetch(`${API_BASE}/api/demo/inject-ring`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      district,
      topology: "cycle",
      ...(accounts && accounts.length >= 3 ? { accounts } : {}),
    }),
  });
  if (!r.ok) throw new Error(`demo inject failed: ${r.status}`);
  return r.json();
}

export interface ConsoleTx {
  source: string;
  target: string;
  amount: number;
}

export interface ConsoleResult {
  accounts: { account_id: string; illicit_probability: number; in_ring: boolean }[];
  ring: {
    ring_id: string;
    label?: string | null;
    size: number;
    risk_score: number;
    district?: string | null;
    total_amount?: number | null;
    account_ids: string[];
  } | null;
  committed: boolean;
  rings_total: number;
}

/** Fraud console: the human designs the transactions; the engine scores them. */
export const scoreCustom = (payload: {
  district: string;
  speed: "minutes" | "days";
  transactions: ConsoleTx[];
}) => post<ConsoleResult>("/api/demo/score-custom", payload);

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

/** Wow moment #1: analyse text via Fraud Shield and auto-ingest into the command centre. */
export const analyzeScam = (
  text: string,
  source = "manual_demo",
  location_hint?: LocationHint | null
) => post<ScamEvent>("/api/analyze/scam", { text, source, location_hint });

/** Wow moment #2: analyse a note photo (data URL) and auto-ingest. */
export const analyzeCounterfeit = (image_b64: string, location_hint?: LocationHint | null) =>
  post<CounterfeitEvent>("/api/analyze/counterfeit", { image_b64, location_hint });
