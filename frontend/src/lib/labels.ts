/** 서버가 주는 영문 키의 화면 표기. */

import type { Tone } from "@/components/ui";
import { num } from "./format";
import type { IntentCard, Plan, PositionRow } from "./types";

export const CONVICTION: Record<string, string> = { very_low: "매우 낮음", low: "낮음", medium: "보통", high: "높음", very_high: "매우 높음" };

// "actionable"은 관문 기법(트렌드 템플릿)에도 붙는다. 관문은 매수 계획을 만들지 않으므로 "매수"라고 적지 않는다.
// "setup"은 조건은 갖췄고 돌파(장중 가격·피벗)를 기다리는 상태다(변동성 돌파, VCP).
export const TECH_STATE: Record<string, string> = {
  actionable: "조건 충족",
  setup: "돌파 대기",
  extended: "이미 오른 구간",
  none: "해당 없음",
  insufficient: "자료 부족",
};
export const TECH_STATE_TONE: Record<string, Tone> = { actionable: "success", setup: "warning", extended: "neutral", none: "neutral", insufficient: "neutral" };

export const ACTION: Record<string, string> = { BUY: "매수", SELL: "매도", HOLD: "보류" };
export const ACTION_TONE: Record<string, Tone> = { BUY: "up", SELL: "down", HOLD: "neutral" };

export const INTENT_STATUS: Record<string, string> = {
  pending_approval: "승인 대기",
  notified: "알림만(주문 안 함)",
  approved: "주문 예정",
  rejected: "거절",
  expired: "기한 만료",
  cancelled: "취소",
  filled: "체결",
  skipped: "미체결",
};
export const INTENT_TONE: Record<string, Tone> = {
  pending_approval: "accent",
  notified: "neutral",
  approved: "accent",
  rejected: "neutral",
  expired: "neutral",
  cancelled: "neutral",
  filled: "success",
  skipped: "warning",
};

export const STANCE: Record<string, string> = { bullish: "긍정", bearish: "부정", neutral: "중립", abstain: "기권" };
// 의견은 상태도 가격도 아니라서 색을 쓰지 않는다. 위험 빨강을 쓰면 바로 옆 '매수'(상승 빨강) 배지와 뜻이 섞인다.
// 방향은 단어(긍정·부정)와 부호(+0.71 / −0.20), 막대가 뻗는 쪽이 전한다.
export const STANCE_TONE: Record<string, Tone> = { bullish: "neutral", bearish: "neutral", neutral: "outline", abstain: "outline" };

export const GATE_OUTCOME: Record<string, string> = { pass: "통과", reduce: "축소", block: "거부", note: "참고" };

/**
 * 기법 점검 값. 기준에 %가 있으면 서버가 값을 퍼센트 단위로 준다(예: 187.3 = +187.3%). 기준처럼 %와 부호를 붙여
 * "187.30 · 기준 ≥ +25%"가 아니라 "+187.3% · 기준 ≥ +25%"로 읽히게 한다. 음수는 진짜 빼기 기호(−)로 적는다.
 */
export function checkValueText(value: number | string | null, threshold: string): string {
  if (value === null) return "자료 없음";
  if (typeof value === "string") return value;
  const minus = value < 0 ? "−" : "";
  if (threshold.includes("%")) {
    const sign = !/[+−-]/.test(threshold) ? (value < 0 ? "−" : "") : value > 0 ? "+" : minus;
    return `${sign}${Math.abs(value).toFixed(1)}%`;
  }
  if (Math.abs(value) >= 1000) return `${minus}${num(Math.abs(value))}`;
  return `${minus}${Number.isInteger(value) ? Math.abs(value) : Math.abs(value).toFixed(2)}`;
}

/** 리스크 점검 규칙(서버 backend/app/risk/gate.py의 키). 이름은 설정 화면의 한도 이름과 맞춘다. */
export const GATE_RULE: Record<string, string> = {
  action: "판단 결론",
  decision_status: "판단 상태",
  circuit_breaker: "손실 차단",
  market_regime: "시장 국면",
  stock_flags: "매매 제한 종목",
  already_held: "이미 보유",
  duplicate: "중복 계획",
  max_positions: "최대 보유 종목 수",
  max_orders: "하루 최대 주문 수",
  conviction: "매수에 필요한 최소 확신",
  liquidity_floor: "하루 평균 거래대금 하한",
  stop_adjust: "손절 가격 조정",
  stop_invalid: "손절 가격 확인",
  max_stop: "손절 폭 상한",
  cost_to_risk: "비용 ÷ 위험 상한",
  reward_to_risk: "최소 손익비",
  costs: "거래 비용",
  risk_budget: "한 건에 거는 위험",
  max_position: "한 종목 최대 비중",
  max_order_value: "주문 한 건 최대 금액",
  liquidity: "주문 ÷ 하루 거래대금 상한",
  max_sector: "한 업종 최대 비중",
  max_heat: "손절 시 총손실 상한",
  exposure_cap: "시장 국면 투자 비중 상한",
  cash: "남겨 둘 현금",
  zero_qty: "살 수 있는 수량",
  not_held: "보유 확인",
  sell: "매도 수량",
};
export const GATE_TONE: Record<string, Tone> = { pass: "success", reduce: "warning", block: "danger", note: "neutral" };

/** 장부 적요의 색: 계획은 보라, 보호 청산은 주의, 거부·차단·오류는 위험, 체결은 굵은 먹색. */
export function kindTone(kind: string): "plan" | "warn" | "danger" | "strong" | "plain" {
  if (kind === "intent" || kind === "approve") return "plan";
  if (kind === "protective" || kind === "gate_reduce" || kind === "stop_raise") return "warn";
  if (kind === "gate_block" || kind === "breaker" || kind === "error") return "danger";
  if (kind === "fill_buy" || kind === "fill_sell") return "strong";
  return "plain";
}

/** 주문 계획이 언제 어떤 가격으로 나가는지 한 줄로 설명한다. */
export function entryText(card: Pick<IntentCard, "side" | "entry_type" | "trigger" | "chase_limit">): string {
  if (card.side === "sell") return "다음 거래일 시가에 매도";
  if (card.entry_type === "trigger" && card.trigger) {
    return `장중 ${num(card.trigger)}원을 넘으면 매수${card.chase_limit ? ` (${num(card.chase_limit)}원 위로는 따라 사지 않음)` : ""}`;
  }
  if (card.entry_type === "vb" && card.trigger) return `장중 ${num(card.trigger)}원을 넘으면 매수하고 다음 날 시가에 청산`;
  if (card.entry_type === "vb") return "장중 변동성 돌파 가격을 넘으면 매수하고 다음 날 시가에 청산";
  return "다음 거래일 시가에 매수";
}

export function planText(plan: Plan): string {
  if (plan.entry_type === "trigger" && plan.trigger) return `${num(plan.trigger)}원 돌파 시 매수`;
  if (plan.entry_type === "vb") return plan.trigger ? `${num(plan.trigger)}원 돌파 시 매수, 다음 날 시가 청산` : "변동성 돌파 시 매수, 다음 날 시가 청산";
  return "다음 거래일 시가 매수";
}

export const EXIT_RULE: Record<string, string> = { close_below_sma50: "종가가 50일선 아래로 내려오면 매도", close_below_low10: "종가가 10일 최저가 아래로 내려오면 매도" };

export const DATA_SOURCE: Record<string, string> = { naver: "네이버 금융 일봉", sample: "견본 데이터", kiwoom: "키움증권" };

/** 체결 사유(백엔드 FILL_SUMMARY와 같은 말). */
export const FILL_REASON: Record<string, string> = {
  entry_open: "시가 매수",
  entry_trigger: "돌파 매수",
  entry_vb: "변동성 돌파 매수",
  stop: "손절",
  trail_stop: "추적 손절",
  target: "목표가 익절",
  next_open_exit: "다음 날 시가 청산",
  time_exit: "보유 기간 만료 청산",
  rule_exit: "청산 규칙 매도",
  committee_sell: "위원회 매도",
  liquidate: "전량 매도",
  manual: "수동 주문",
};

/** 보유 기간: 산 날은 "매수 당일", 그 뒤로는 장 마감을 넘긴 횟수로 센다. */
export function heldText(daysHeld: number): string {
  return daysHeld <= 0 ? "매수 당일" : `${daysHeld}거래일째`;
}

/** 목표가가 없는 보유 종목이 어떻게 팔리는지 짧게 적는다. */
export function exitPlanText(p: Pick<PositionRow, "target" | "exit_on_next_open" | "trailing">): string {
  if (p.target) return `목표 ${num(p.target)}원`;
  if (p.exit_on_next_open) return "다음 거래일 시가에 청산";
  return p.trailing ? "목표가 없이 손절 가격을 따라 올림" : "목표가 없음";
}
