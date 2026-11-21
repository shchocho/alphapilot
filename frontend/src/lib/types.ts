/** API 응답 타입(백엔드 app/api/views.py와 짝을 이룬다). */

export type Env = "sim" | "mock" | "live";
export type EngineState = "running" | "paused" | "stopped";
export type SessionPhase = "closed" | "pre_open" | "regular" | "closing_auction" | "after_close";

export interface AuthState {
  setup: "none" | "pending" | "done";
  authenticated: boolean;
  csrf: string | null;
  elevated: boolean;
  setup_token_required: boolean;
}

export interface Account {
  username: string;
  recovery_codes_left: number;
}

/** 증권사 키가 어디서 왔는지. 키 값은 화면으로 내려오지 않는다. */
export type BrokerKeySources = Record<"mock" | "live", "db" | "env" | null>;

export interface RegimeBrief {
  label: string;
  score: number;
  exposure_cap: number;
  allow_new_buys: boolean;
  day: string;
}

export interface Status {
  env: Env;
  env_label: string;
  state: EngineState;
  state_label: string;
  automation_level: number;
  automation_label: string;
  resume_check_required: boolean;
  decider: "ai" | "rules" | "hybrid";
  sim_day: string | null;
  data_day: string | null;
  data_source: string;
  data_refreshed_at: string | null;
  has_data: boolean;
  behind_days: number;
  session: { phase: SessionPhase; seconds_to_close: number | null; now: string; calendar_confirmed_through: string };
  regime: RegimeBrief | null;
  pending_approvals: number;
  risk: { daily_pct: number; daily_limit_pct: number; daily_used: number; equity: number };
  ai: { configured: boolean; model: string; spent_today_usd: number; budget_usd: number };
  broker: { kind: "paper" | "kiwoom"; mock_keys: boolean; live_keys: boolean; live_allowed: boolean };
  busy: string;
  last_error: string;
  ledger_last_seq: number;
  ledger_seen_seq: number;
}

export interface LedgerRow {
  seq: number;
  ts: string;
  env: Env;
  day: string | null;
  kind: string;
  kind_label: string;
  chain_id: string;
  code: string | null;
  name: string | null;
  summary: string;
  qty: number | null;
  amount: number | null;
  cash_after: number | null;
  payload: Record<string, unknown>;
}

export interface Votes {
  bullish?: number;
  bearish?: number;
  neutral?: number;
  abstain?: number;
}

export interface IntentCard {
  id: string;
  chain_id: string;
  decision_id: string | null;
  created_on: string;
  trade_date: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  qty: number;
  status: string;
  entry_type: "open" | "trigger" | "vb";
  source: string;
  technique: string;
  technique_name?: string;
  reason: string;
  est_price: number;
  trigger: number | null;
  chase_limit: number | null;
  stop: number | null;
  target: number | null;
  conviction: string | null;
  conviction_label?: string;
  expires_at: string | null;
  decided_at?: string | null;
  note: string;
  thesis?: string;
  votes?: Votes;
  gate_summary?: string | null;
  decision_source?: string | null;
  amount?: number;
  last_price?: number | null;
  risk_pct?: number | null;
}

export interface PositionRow {
  code: string;
  name: string;
  sector: string;
  qty: number;
  avg_price: number;
  price: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  weight: number;
  technique: string;
  technique_name: string;
  opened_on: string;
  days_held: number;
  stop: number;
  target: number | null;
  stop_distance: number | null;
  target_distance: number | null;
  trailing: boolean;
  exit_on_next_open: boolean;
  exit_rule: string | null;
  open_risk: number;
  chain_id: string;
}

export interface RegimeFull {
  day: string;
  score: number;
  label: string;
  exposure_cap: number;
  allow_new_buys: boolean;
  dist_level: string;
  dist_label: string;
  dist_counts: [number, number, number];
  cycle: string;
  cycle_label: string;
  index_distance: number | null;
  breadth_above200: number | null;
  uptrend_ratio: number | null;
  components: { key: string; name: string; weight: number; score: number; detail: string }[];
  missing: string[];
}

export interface Dashboard {
  as_of: string;
  source_label: string;
  account: {
    equity: number;
    cash: number;
    invested: number;
    exposure: number;
    initial_cash: number;
    total_return: number;
    day_pnl: number;
    day_pct: number;
    realized_pnl: number;
    unrealized_pnl: number;
  };
  risk: {
    daily_used: number;
    daily_limit_pct: number;
    daily_limit_amount: number;
    heat_pct: number;
    heat_limit_pct: number;
    positions: number;
    max_positions: number;
    drawdown_pct: number;
    drawdown_halt_pct: number;
    exposure_cap: number | null;
  };
  pending: IntentCard[];
  plans: IntentCard[];
  passbook: {
    seen_seq: number;
    last_seq: number;
    new_count: number;
    counts: Record<string, number>;
    fills: number;
    blocks: number;
    passes: number;
    rows: LedgerRow[];
    older: LedgerRow[];
  };
  watch: PositionRow[];
  curve: { d: string; equity: number; benchmark: number | null }[];
  regime: RegimeFull | null;
}

export interface Check {
  key: string;
  label: string;
  value: number | string | null;
  threshold: string;
  passed: boolean;
}

export interface Plan {
  entry_type: "open" | "trigger" | "vb";
  stop: number;
  reference_price: number;
  trigger: number | null;
  chase_limit: number | null;
  vb_k: number | null;
  vb_range: number | null;
  target: number | null;
  trail_mult: number | null;
  exit_on_next_open: boolean;
  max_hold_days: number | null;
  exit_rule: string | null;
}

export interface TechniqueResult {
  key: string;
  name: string;
  passed: boolean;
  score: number;
  state: string;
  checks: Check[];
  plan: Plan | null;
  notes: string[];
}

export interface TechniqueMeta {
  key: string;
  name: string;
  origin: string;
  kind: "gate" | "entry" | "value";
  summary: string;
  rules: string[];
  holding: string;
  data: string;
  count?: number;
  enabled?: boolean;
}

export interface Seat {
  seat: string;
  label: string;
  value: number;
  confidence: number;
  abstained: boolean;
  summary: string;
  stance: "bullish" | "bearish" | "neutral" | "abstain";
  components: { name: string; points: number; max_points: number | null; detail: string }[];
  as_of: string;
}

export interface ScreenerRow {
  code: string;
  name: string;
  market: string;
  sector: string;
  close: number;
  change: number;
  change_pct: number;
  score: number;
  passed: number;
  total: number;
  state: string;
  value20: number;
  rs: number | null;
  spark: number[];
  also: string[];
  plan: Plan | null;
  notes: string[];
}

export interface Screener {
  as_of: string;
  technique: string;
  techniques: TechniqueMeta[];
  rows: ScreenerRow[];
  universe: number;
  excluded_illiquid: number;
  no_bar: number;
  min_avg_value: number;
  data_source: string;
}

export interface GateStep {
  rule: string;
  outcome: "pass" | "reduce" | "block" | "note";
  detail: string;
  qty_after: number | null;
}

export interface Gate {
  approved: boolean;
  qty: number;
  stop: number | null;
  order_value: number;
  risk_amount: number;
  base_qty: number;
  summary: string;
  steps: GateStep[];
}

export interface FinalDecision {
  action: "BUY" | "SELL" | "HOLD";
  conviction: string;
  size_fraction: number;
  stop: number | null;
  thesis: string;
  key_risks: string[];
  invalidation: string;
  dissent: string;
  source: "ai" | "rules";
  status: "ok" | "review";
  status_detail: string;
  votes: Votes;
}

export interface TranscriptStep {
  role: string;
  label: string;
  content: Record<string, unknown>;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
}

export interface DecisionBrief {
  id: string;
  as_of: string;
  code: string;
  name: string;
  kind: "entry" | "holding";
  action: "BUY" | "SELL" | "HOLD";
  conviction: string;
  conviction_label?: string;
  source: "ai" | "rules";
  status: "ok" | "review";
  chain_id: string;
  cost_usd: number;
  thesis: string;
  votes: Votes;
  status_detail: string;
  gate_summary: string | null;
  gate_qty: number | null;
  intent_id: string | null;
  technique: string;
  technique_name?: string;
  close: number | null;
  sector: string | null;
}

export interface DecisionDetail extends Omit<DecisionBrief, "thesis" | "votes" | "status_detail" | "gate_summary" | "gate_qty"> {
  seats: Seat[];
  techniques: TechniqueResult[];
  plan: Plan | null;
  max_qty: Record<string, number>;
  final: FinalDecision;
  gate: Gate | null;
  transcript: { depth: string; model: string; steps: TranscriptStep[]; error: string; cost_usd: number; branch?: { reason: string; outcome: string; adopted: boolean } } | null;
  intent: IntentCard | null;
  chain: LedgerRow[];
  market: string;
}

export interface Trade {
  id: number;
  day: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
  tax: number;
  reason: string;
  reason_label?: string;
  technique: string;
  technique_name?: string;
  chain_id: string;
  pnl: number | null;
  pnl_pct: number | null;
  hold_days: number | null;
  amount: number;
}

export interface StockDetail {
  as_of: string;
  code: string;
  name: string;
  market: string;
  sector: string;
  close: number;
  change: number;
  change_pct: number;
  prev_day: string | null;
  stats: { hi252: number | null; lo252: number | null; value20: number | null; atr_pct: number | null; rs: number | null; volume: number; vol_ratio: number | null };
  bars: { d: string; o: number; h: number; l: number; c: number; v: number }[];
  overlays: Record<"sma20" | "sma50" | "sma150" | "sma200", (number | null)[]>;
  techniques: TechniqueResult[];
  seats: Seat[];
  seat_blend: number;
  regime: RegimeFull;
  decision: (DecisionDetail & { created_at: string }) | null;
  position: PositionRow | null;
  trades: Trade[];
  intents: IntentCard[];
  fundamentals: { per: number | null; pbr: number | null; roe: number | null; eps: number | null; bps: number | null; as_of: string } | null;
  data_source: string;
}

export interface Committee {
  days: string[];
  day: string | null;
  decisions: DecisionBrief[];
  tally: Record<string, number>;
  cost_usd: number;
  decider: "ai" | "rules" | "hybrid";
  depth_label: string;
  scorecard: Record<"ai" | "rules", { closed: number; wins: number; win_rate: number | null; avg_pct: number | null; enough: boolean }>;
  seat_labels: Record<string, string>;
}

export interface JournalEntry {
  chain_id: string;
  code: string;
  name: string;
  technique_name: string;
  buy: Trade | null;
  sell: Trade | null;
}

export interface Portfolio {
  as_of: string;
  source_label: string;
  summary: { equity: number; cash: number; invested: number; unrealized: number; realized: number; closed_trades: number; win_rate: number | null };
  positions: PositionRow[];
  intents: IntentCard[];
  trades: Trade[];
  journal: JournalEntry[];
  daily_pnl: { d: string; pnl: number }[];
}

export interface BacktestSummary {
  total_return: number;
  cagr: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: { pct: number; peak: string | null; trough: string | null; recovered: string | null; days_to_trough: number };
  avg_exposure: number;
  benchmark: { total_return: number; cagr: number; max_drawdown: number; sharpe: number };
  trades: {
    trades: number;
    win_rate: number;
    profit_factor: number | null;
    avg_win: number;
    avg_loss: number;
    payoff_ratio: number | null;
    avg_hold_days: number;
    best_pct: number;
    worst_pct: number;
    by_reason: Record<string, number>;
    by_technique: Record<string, { trades: number; pnl: number; wins: number }>;
    enough_trades: boolean;
  };
  days: number;
  open_positions: number;
  final_cash: number;
}

export interface BacktestResult {
  id: string;
  created_at?: string;
  params: {
    start: string | null;
    end: string | null;
    initial_cash: number;
    techniques: string[];
    max_candidates: number;
    costs: { commission_rate: number; sell_tax_rate: number; slippage_rate: number };
    universe: number;
    data_source: string;
    decider: string;
  };
  start: string;
  end: string;
  initial_cash: number;
  curve: { d: string; equity: number; benchmark: number; drawdown: number; exposure: number }[];
  monthly: { year: number; month: number; ret: number }[];
  trades: (Omit<Trade, "id" | "amount" | "chain_id"> & { technique: string })[];
  rejected: { day: string; code: string | null; name: string | null; stage: string; reason: string }[];
  rejected_total: number;
  summary: BacktestSummary;
  halted_on: string | null;
  elapsed_sec: number;
}

export interface BacktestRun {
  id: string;
  created_at: string;
  start: string;
  end: string;
  total_return: number | null;
  cagr: number | null;
  mdd: number | null;
  sharpe: number | null;
  trades: number | null;
  params: BacktestResult["params"];
}

export interface EngineSettings {
  env: Env;
  state: EngineState;
  resume_check_required: boolean;
  automation_level: number;
  auto_max_order_value: number;
  decider: "ai" | "rules" | "hybrid";
  ai_model: string;
  ai_depth: "light" | "standard" | "deep";
  ai_effort: string;
  ai_daily_budget_usd: number;
  max_candidates: number;
  enabled_techniques: string[];
  commission_rate: number;
  sell_tax_rate: number;
  slippage_rate: number;
  sim_initial_cash: number;
  extra_holidays: string[];
}

export type RiskLimits = Record<string, number | string>;

export interface SettingsView {
  engine: EngineSettings;
  limits: RiskLimits;
  options: {
    automation: { value: number; label: string }[];
    models: { value: string; label: string }[];
    depths: { value: string; label: string }[];
    techniques: TechniqueMeta[];
  };
  ai: { configured: boolean; usage: { day: string; cost_usd: number; calls: number }[] };
  broker: {
    mock: { configured: boolean; base_url: string };
    live: { configured: boolean; base_url: string; allowed_by_server: boolean };
    runner_available: boolean;
  };
  data: { source: string; day: string | null; stocks: number; refreshed_at: string | null };
  sim_start: string | null;
  server: { env: string; allowed_hosts: string[] };
}
