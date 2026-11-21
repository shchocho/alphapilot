/** 내 종목 운용(바구니) API 응답 모양. 백엔드: backend/app/sleeves/service.py */

export type Cadence = "daily" | "weekly" | "monthly";
export type Decider = "rules" | "ai" | "hybrid";
export type Mode = "alert" | "paper";
export type Kind = "stock" | "etf";
export type Depth = "light" | "standard" | "deep";
export type SleeveAction = "BUY_MORE" | "BUY" | "WAIT" | "TRIM" | "SELL";

export interface WatchItem {
  code: string;
  name: string;
  kind: Kind;
  weight: number;
}

export interface SleeveConfig {
  id: string;
  name: string;
  amount: number;
  items: WatchItem[];
  mandate: string;
  decider: Decider;
  depth: Depth;
  cadence: Cadence;
  installments: number;
  mode: Mode;
}

export interface PlanConfig {
  total: number;
  sleeves: SleeveConfig[];
}

export interface SleeveSignal {
  id: string;
  run_id: string;
  sleeve_id: string;
  rev: number;
  as_of: string;
  code: string;
  name: string;
  action: SleeveAction;
  action_label: string;
  rules_action: SleeveAction;
  conviction: string;
  conviction_label: string;
  source: "rules" | "ai";
  status: "ok" | "review";
  score: number;
  close: number;
  qty: number;
  amount: number;
  cost_usd: number;
  has_transcript: boolean;
  thesis: string;
  key_risks: string[];
  invalidation: string;
  dissent: string;
  note: string;
  status_detail?: string;
  seats: { label: string; stance: string; value: number; summary: string }[];
  votes?: Record<string, number>;
  kind?: Kind;
  pnl_pct?: number | null;
  branch?: { reason: string; rules_action: string; ai_action: string | null; adopted: boolean; outcome: string; ai_conviction?: string } | null;
}

export interface TranscriptStep {
  role: string;
  label: string;
  content: Record<string, unknown>;
  model: string;
  cost_usd: number;
}

export interface SignalDetail extends SleeveSignal {
  transcript: { depth: string; model: string; steps: TranscriptStep[]; error: string; cost_usd: number } | null;
}

export interface SleevePosition {
  code: string;
  name: string;
  kind: Kind;
  qty: number;
  avg: number;
  close: number;
  value: number;
  pnl_pct: number;
}

export interface SleeveView extends SleeveConfig {
  cadence_label: string;
  decider_label: string;
  mode_label: string;
  due: boolean;
  book: {
    cash: number;
    equity: number;
    contributed: number;
    return_pct: number | null;
    installments_done: number;
    started_on: string | null;
    last_run: string | null;
    carry: number;
    positions: SleevePosition[];
  };
  latest: SleeveSignal[];
  pending: { id: string; code: string; name: string; side: "buy" | "sell"; qty: number; made_on: string; note: string }[];
}

export interface Estimate {
  ai_configured: boolean;
  model: string;
  budget_usd: number;
  spent_today_usd: number;
  day: string | null;
  due: string[];
  targets: string[];
  calls: number;
  est_usd: number;
}

export interface RunSummary {
  id: string;
  as_of: string;
  rev: number;
  trigger: "manual" | "schedule";
  created_at: string;
  sleeves: { sleeve_id: string; name: string; mode: Mode; decider: Decider; tally: Record<string, number>; orders: number; ai_calls: number; cost_usd: number }[];
  ai_calls: number;
  cost_usd: number;
}

export interface SleevesOverview {
  busy: string;
  data_day: string | null;
  estimate: Estimate;
  options: {
    cadence: Record<Cadence, string>;
    decider: Record<Decider, string>;
    mode: Record<Mode, string>;
    kind: Record<Kind, string>;
    actions: Record<SleeveAction, string>;
    multipliers: Record<string, number>;
  };
  plan: { rev: number; created_at: string; day: string; note: string; total: number; allocated: number; config: PlanConfig } | null;
  sleeves: SleeveView[];
  prices?: Record<string, number>;
  last_run: RunSummary | null;
}

export interface Revision {
  rev: number;
  created_at: string;
  day: string;
  note: string;
  restored_from: number | null;
  current: boolean;
  changes: string[];
  config: PlanConfig;
  runs: number;
  signals: Partial<Record<SleeveAction, number>>;
  fills: number;
  period: { start: string; end: string | null; return_pct: number | null };
}

export interface Curve {
  dates: string[];
  equity: number[];
  summary: { return_pct: number; mdd_pct?: number; buys?: number; sells?: number; runs?: number; invested_pct?: number; end_equity?: number };
}

export interface Comparison {
  sleeve_id: string;
  name: string;
  start: string;
  end: string;
  dca: Curve;
  rules: Curve;
  book?: Curve & { contributed: number[] };
  started_on?: string;
}

export interface Preview {
  start: string;
  end: string;
  sleeves: Comparison[];
  kospi: { dates: string[]; value: number[] };
  note: string;
}

export interface Lookup {
  code: string;
  name: string;
  kind: Kind;
  kind_label: string;
  in_universe: boolean;
  close: number;
  day: string;
  bars: number;
}
