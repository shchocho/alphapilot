/** 서버가 주는 영문 키의 화면 표기. */

import type { Tone } from "@/components/ui";
import { num } from "./format";
import type { IntentCard, Plan, PositionRow } from "./types";

export const CONVICTION: Record<string, string> = { very_low: "매우 낮음", low: "낮음", medium: "보통", high: "높음", very_high: "매우 높음" };

export const TECH_STATE: Record<string, string> = {
  actionable: "매수 조건 충족",
  setup: "준비 단계",
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
export const STANCE_TONE: Record<string, Tone> = { bullish: "success", bearish: "danger", neutral: "neutral", abstain: "neutral" };

export const GATE_OUTCOME: Record<string, string> = { pass: "통과", reduce: "축소", block: "거부", note: "참고" };
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
