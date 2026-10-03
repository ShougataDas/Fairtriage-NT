// Typed client for the FairTriage FastAPI service (proxied at /api).

export type Tier = "Immediate" | "Urgent" | "Routine" | "NotInQueue";

export interface Flag {
  code: string;
  detail?: unknown;
  action?: string;
  audience?: string;
}

export interface WaitFacts {
  low: number;
  high: number;
  central: number;
  darwin: number;
  range_text: string;
  gap_days: number;
  ratio: number;
}

/** The wait from now, recomputed from today's queue (counts down as the job waits). */
export interface WaitNow {
  low: number;
  high: number;
  central: number;
  range_text: string;
  on_trip: boolean;
  days_open: number;
}

export interface Reachability {
  community: string;
  remote: boolean;
  access: string;
  road_km_est: number;
  road_status: string;
  road_snapshot_at: string | null;
  access_mode: string;
}

export interface Component {
  name: string;
  raw: number;
  weight: number;
  contribution: number;
  detail: string;
}

export interface LodgeResult {
  request_id: string;
  status: string;
  question?: string;
  tier?: Tier;
  rank?: number | null;
  tier_size?: number | null;
  wait?: WaitFacts | null;
  explanation_tenant?: string;
  flags?: Flag[];
}

export interface TripInfo {
  trip_id: string;
  stop: number;
  stops: number;
  eta_at: string;
  eta_days: number;
  tenant_update: string | null;
}

export interface RequestView {
  request_id: string;
  status: string;
  lodged_at: string;
  text_original: string;
  text_normalised: string | null;
  community: string;
  address: string | null;
  phone: string | null;
  question: string | null;
  answer: string | null;
  prior_deferrals: number;
  advanced_by: string | null;
  trip: TripInfo | null;
  wait_now: WaitNow | null;
  assessment: null | {
    tier: Tier;
    need: number;
    facts: {
      evidence?: string;
      tier_reason?: string;
      components?: Component[];
      rank?: number | null;
      tier_size?: number | null;
      darwin_rank?: number | null;
      wait?: WaitFacts | null;
      emergency?: boolean;
    };
    flags: Flag[];
    reachability: Reachability | null;
    explanation_tenant: string;
    explanation_coordinator: string;
    weights_version: string;
    created_at: string;
  };
  decisions: { actor: string; action: string; from: string; to: string; reason: string | null; at: string }[];
  extractions: {
    source: string;
    extractor: string;
    cache_hit: boolean;
    fallback: boolean;
    payload: Record<string, unknown>;
  }[];
}

export interface QueueRow {
  request_id: string;
  tier: Tier;
  need: number;
  community: string;
  area: string;
  address: string | null;
  remote: boolean;
  text: string;
  status: string;
  evidence: string;
  trade: string;
  reachability: Partial<Reachability>;
  wait_low: number | null;
  wait_high: number | null;
  wait_text: string | null;
  wait_on_trip: boolean;
  told_low: number | null;
  told_high: number | null;
  wait_darwin: number | null;
  days_open: number;
  target_days: number;
  pct_of_target: number;
  past_target: boolean;
  target_label: string;
  deferrals: number;
  advanced_by: string | null;
  flags: Flag[];
  position: number;
  shift: number;
  display_pos: number;
}

export interface Contact {
  request_id: string;
  community: string;
  address: string | null;
  phone: string | null;
  status: string;
  text: string;
  answer: string | null;
  lodged_at: string;
  danger?: boolean;
}

export interface CommunityGroup {
  group: string;
  communities: { name: string; remote: boolean }[];
}

export interface Health {
  ok: boolean;
  database?: "connected" | "unreachable";
  policy: string;
  rules: string;
  reader: { mode: string; ok: boolean; label: string };
}

export interface TripStop {
  order: number;
  request_id: string;
  community: string;
  address: string | null;
  trade: string;
  evidence: string;
  tier: Tier;
  need: number;
  reason: string;
  eta_hours: number;
  eta_days: number;
  prev_wait_days: number | null;
  slack_hours: number;
  on_time: boolean;
}

export interface TripOption {
  name: string;
  nodes: string[];
  modes: string[];
  hours: number;
  km: number;
  extra_hours: number;
  by_air: boolean;
  score: number;
  serves: number;
  passes: number;
  chosen: boolean;
  feasible: boolean;
  note: string;
}

export interface TripPlan {
  id: string;
  community: string;
  trigger: string;
  trigger_detail: string;
  trade: string;
  anchor: string;
  start: string;
  crew: number;
  start_offset_h: number;
  headline: string;
  explanation: string;
  target_missed: boolean;
  capacity_hours: number;
  route: null | {
    name: string;
    roads: string[];
    nodes: string[];
    hours: number;
    km: number;
    by_air: boolean;
  };
  stops: TripStop[];
  options: TripOption[];
  coords: Record<string, [number, number]>;
  benefit: TripBenefit | null;
  left_behind: { request_id: string; community: string; tier: Tier; reason: string }[];
  workday_hours: number;
}

export interface TripBenefit {
  jobs: number;
  communities: number;
  trip_hours: number;
  trip_km: number;
  separate_trips: number;
  separate_hours: number;
  separate_km: number;
  hours_saved: number;
  km_saved: number;
  sooner_jobs: number;
  sooner_days: number;
  destination_delay_h: number;
  destination_on_time: boolean;
  destination_slack_left_h: number;
  on_time_jobs: number;
  why: string[];
}

export interface TripRules {
  community_threshold_multiple: number;
  capacity_hours_per_day: number;
  trip_days: number;
  workday_hours: number;
  routing: {
    direct_tiers: string[];
    anchor_slack_reserve: number;
    overdue_delay_cap_hours: number;
    extra_hour_cost: number;
    charter_cost: number;
    stop_value: Record<string, number>;
    wait_bonus_cap: number;
    restricted_speed_factor: number;
  };
}

export interface TripPreview {
  teams: Record<string, string>;
  rules: TripRules;
  trips: TripPlan[];
}

export interface ConfirmedTrip {
  id: string;
  community: string;
  trade: string;
  headline: string | null;
  explanation: string | null;
  created_at: string;
  jobs: {
    request_id: string; community: string; tier: Tier; reason: string; eta_hours?: number;
    address?: string | null; removed?: boolean;
  }[];
  left_behind: { request_id: string; community: string; tier: Tier; reason: string }[];
  status?: "approved" | "completed" | "cancelled";
  active_jobs?: number;
  route?: { by_air?: boolean } | null;
  history?: { action: string; at: string; actor: string; reason: string | null; request_id?: string }[];
}

export interface Equity {
  rank_location_invariance: { checked: number; identical: number; pct: number | null };
  wait_gap_by_tier: Record<
    string,
    { remote_days: number | null; urban_days: number | null; gap_days: number | null; ratio: number | null; n_remote: number; n_urban: number }
  >;
  deferrals: Record<string, { mean: number; at_or_above_2: number; n: number }>;
  remote_jobs_scheduled: { on_own_trip: number; as_passengers: number; passenger_share_pct: number | null };
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function unwrap<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>;
  let message = `The service replied ${res.status}.`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
  } catch {
    if (res.status >= 500) message = "The FairTriage service is not reachable. Is it running?";
  }
  throw new ApiError(message, res.status);
}

export const fetcher = <T,>(url: string): Promise<T> => fetch(url).then((r) => unwrap<T>(r));

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return unwrap<T>(res);
}
