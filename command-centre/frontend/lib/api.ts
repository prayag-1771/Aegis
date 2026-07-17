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
  // "coordinated" = all 3 crime types converge (the strongest signal);
  // "multi_signal" = exactly 2; null = single-domain cluster.
  tier: "coordinated" | "multi_signal" | null;
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
  const r = await fetch(`${API_BASE}/fuse`, { method: "POST" });
  if (!r.ok) throw new Error(`fusion failed: ${r.status}`);
  return r.json();
}

export async function injectDemoRing(
  district: string,
  accounts?: string[]
): Promise<DemoRingResponse> {
  const r = await fetch(`${API_BASE}/demo/inject-ring`, {
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
}) => post<ConsoleResult>("/demo/score-custom", payload);

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
) => post<ScamEvent>("/analyze/scam", { text, source, location_hint });

/** Wow moment #2: analyse a note photo (data URL) and auto-ingest. */
export const analyzeCounterfeit = (image_b64: string, location_hint?: LocationHint | null) =>
  post<CounterfeitEvent>("/analyze/counterfeit", { image_b64, location_hint });

// ── Supply Trail types ───────────────────────────────────────────────────────

export interface TrailNode {
  name: string;
  lat: number;
  lon: number;
  is_major_hub?: boolean;
}

export interface TrailCorridor {
  id: string;
  name: string;
  mode: string;
  node_path: TrailNode[];
}

export interface TrailEvidence {
  type: string;
  detail: string;
  ref?: string;
  weight?: number;
}

export interface TrailSeizure {
  event_id: string;
  lat: number;
  lon: number;
  district: string;
  denomination?: string;
  timestamp?: string;
}

export interface TrailFlow {
  direction_toward: string;
  speed_km_per_day: number;
  consistency: number; // R² of the position-vs-time fit, 0..1
  basis: string;
  next_hub_at_risk?: {
    name: string;
    lat: number;
    lon: number;
    distance_km: number;
    eta_days_min: number;
    eta_days_max: number;
  } | null;
  origin_consistent?: boolean | null;
  note?: string;
}

export interface SupplyTrail {
  schema_version: string;
  trail_id: string;
  generated_at: string;
  commodity: string;
  mode: string;
  seizures: TrailSeizure[];
  corridor: TrailCorridor;
  cluster_centroid?: { lat: number; lon: number; radius_km: number };
  inferred_origin: { name: string; lat: number; lon: number; reasoning: string };
  confidence: number;
  confidence_band: "low" | "medium" | "high";
  evidence: TrailEvidence[];
  disclaimer: string;
  flow?: TrailFlow | null;
}

// ── Intelligence layer: plate families + scam campaigns ─────────────────────

export interface PlateFamily {
  family_id: string;
  denomination: string;
  tier: "high" | "probable" | "possible";
  n_notes: number;
  shared_defects: string[];
  districts: string[];
  span_km: number;
  first_seen?: string;
  last_seen?: string;
  events: { event_id: string; district?: string; lat?: number; lon?: number; timestamp?: string; missing_features: string[] }[];
  links: { a: string; b: string; tier: string; shared: string[] }[];
  note: string;
}

export interface ScamCampaign {
  campaign_id: string;
  tier: "high" | "probable" | "possible";
  n_events: number;
  scam_type: string;
  district_spread: string[];
  phone_numbers: string[];
  first_seen?: string;
  last_seen?: string;
  sample_text: string;
  events: { event_id: string; district?: string; timestamp?: string; phone_number?: string | null }[];
  links: { a: string; b: string; tier: string; similarity: number; basis: string[] }[];
  note: string;
}

export interface PlateFamiliesResponse {
  families: PlateFamily[];
  summary: { n_families: number; n_linked_notes: number; multi_district: number };
  disclaimer: string;
}

export interface CampaignsResponse {
  campaigns: ScamCampaign[];
  summary: { n_campaigns: number; n_linked_events: number; multi_district: number };
  disclaimer: string;
}

export async function fetchPlateFamilies(): Promise<PlateFamiliesResponse> {
  const r = await fetch(`${API_BASE}/intel/plate-families`);
  if (!r.ok) throw new Error(`plate-families failed: ${r.status}`);
  return r.json();
}

export async function fetchCampaigns(): Promise<CampaignsResponse> {
  const r = await fetch(`${API_BASE}/intel/campaigns`);
  if (!r.ok) throw new Error(`campaigns failed: ${r.status}`);
  return r.json();
}

// ── AI Case Officer ──────────────────────────────────────────────────────────

export interface CaseFile {
  summary: string;
  timeline: string[];
  hypothesis: string;
  recommended_actions: string[];
}

export interface CaseFileResponse {
  district: string;
  case_file: CaseFile;
  dossier: Record<string, unknown> & {
    counts: { scams: number; fake_notes: number; rings: number; ring_accounts: number };
  };
  engine: string;
  disclaimer: string;
}

export const fetchCaseFile = (district: string) =>
  post<CaseFileResponse>("/case-file", { district });

export interface SupplyTrailResponse {
  best_trail: SupplyTrail | null;
  all_trails: SupplyTrail[];
  seizures_used: number;
  /** Echo of the district filter, null for the store-wide trail. */
  district: string | null;
  disclaimer: string;
}

/** Fetch a provenance trail. `district` scopes it to one city ("where are
 *  Jamtara's notes coming from?"); omit it for the store-wide question. */
export async function fetchSupplyTrail(
  mode?: string,
  district?: string,
): Promise<SupplyTrailResponse> {
  const qs = new URLSearchParams();
  if (mode) qs.set("mode", mode);
  if (district) qs.set("district", district);
  const url = qs.toString()
    ? `${API_BASE}/supply-trail?${qs}`
    : `${API_BASE}/supply-trail`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`supply-trail failed: ${r.status}`);
  return r.json();
}

// ── Entry routes: how notes physically REACHED a city ────────────────────────

export interface RouteLeg {
  mode: string;
  from: string;
  to: string;
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  distance_km: number;
  /** "haul" = long-distance leg, "access" = last mile, "transfer" = mode change */
  kind: string;
}

export interface EntryRoute {
  modes: string[];
  total_km: number;
  /** Hypothesis score in [0, 0.9] — never a probability of guilt. */
  plausibility: number;
  passes_fir: string[];
  legs: RouteLeg[];
  /** District of the FIR-documented printing press this route starts from. */
  source: string;
  source_ref: string;
  source_evidence: string;
}

export interface EntryRoutesResponse {
  district: string;
  seizures_in_district: number;
  sources_considered: { district: string; ref: string; evidence: string }[];
  routes: EntryRoute[];
  narrative: { summary: string; recommended_actions: string[] };
  narrator: string;
  disclaimer: string;
}

/** Rank the transport channels by which fake notes could have entered a city.
 *  Unlike fetchSupplyTrail (which reads direction from cluster shape and needs
 *  several seizures), this works from a single seizure — a city's entry
 *  channels exist regardless of how many notes were found there.
 *  Throws on 404 when the district has no located seizures. */
export async function fetchEntryRoutes(
  district: string,
  k = 3,
): Promise<EntryRoutesResponse> {
  const qs = new URLSearchParams({ district, k: String(k) });
  const r = await fetch(`${API_BASE}/supply-trail/routes?${qs}`);
  if (!r.ok) throw new Error(`entry-routes failed: ${r.status}`);
  return r.json();
}

// ── Research modules: results served from precomputed artifacts ──────────────

export interface GhostRing {
  n_banks: number;
  per_bank_ring_recall: Record<string, number>;
  fused_ring_recall: number;
  matching_precision: number;
  false_merge_rate: number;
  recall_gap: number;
  best_min_score?: number;
}

export interface ArmsRace {
  generation: number[];
  escape_rate: number[];
  detector_recall: number[];
  retrained_generations: number[];
}

export interface SpectralCommunity {
  id: number;
  size: number;
  rayleigh: number;
  anomaly: boolean;
  eigenvalues: number[];
  sed: number[];
}

export interface SpectralData {
  communities: SpectralCommunity[];
  shift: {
    clean_rayleigh: number;
    ring_rayleigh: number;
    shift_magnitude: number;
    clean_high_freq_energy: number;
    ring_high_freq_energy: number;
  };
}

export interface ResearchResponse {
  ghost_ring: GhostRing | null;
  arms_race: ArmsRace | null;
  spectral: SpectralData | null;
}

/** The three research modules' results. Any block may be null when its artifact
 *  has not been generated — the panel renders each independently. */
export async function fetchResearch(): Promise<ResearchResponse> {
  const r = await fetch(`${API_BASE}/research`);
  if (!r.ok) throw new Error(`research failed: ${r.status}`);
  return r.json();
}

// ── Response / Disrupt actions ───────────────────────────────────────────────

export type ActionType =
  | "account_freeze"
  | "telecom_block"
  | "mha_alert"
  | "citizen_intercept"
  | "review_queue";
export type ActionStatus = "proposed" | "dispatched" | "acknowledged" | "dismissed";
export type ActionPriority = "critical" | "high" | "medium";

export interface AuditEntry {
  at: string;
  actor: string;
  event: string;
  note?: string;
}

export interface ResponseAction {
  action_id: string;
  created_at: string;
  action_type: ActionType;
  title: string;
  priority: ActionPriority;
  status: ActionStatus;
  recipient: string;
  trigger: { source: string; refs: string[]; rationale: string };
  target: {
    account_id?: string | null;
    ring_id?: string | null;
    phone_number?: string | null;
    amount?: number | null;
    district?: string | null;
    scam_event_id?: string | null;
  };
  payload?: Record<string, unknown> | null;
  sla_minutes?: number | null;
  audit?: AuditEntry[];
  dispatched_at?: string;
  simulated: boolean;
  disclaimer?: string;
}

export interface ActionsResponse {
  actions: ResponseAction[];
  counts_by_status: Record<string, number>;
  counts_by_type: Record<string, number>;
  open: number;
  disclaimer: string;
}

/** The disrupt/respond queue — concrete actions derived from current detections. */
export async function fetchActions(): Promise<ActionsResponse> {
  const r = await fetch(`${API_BASE}/actions`);
  if (!r.ok) throw new Error(`actions failed: ${r.status}`);
  return r.json();
}

export const deriveActions = () => post<ActionsResponse>("/actions/derive", {});

/** Transition an action (dispatch = simulated send; acknowledge; dismiss). */
export async function actOnAction(
  actionId: string,
  op: "dispatch" | "acknowledge" | "dismiss",
): Promise<ResponseAction> {
  const r = await fetch(`${API_BASE}/actions/${encodeURIComponent(actionId)}/${op}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`action ${op} failed: ${r.status}`);
  return r.json();
}
