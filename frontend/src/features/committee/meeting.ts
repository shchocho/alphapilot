/**
 * 판단 한 건을 '회의'로 풀어낸 모델: 누가 참석했고, 어떤 차례로 말했고, 각자 한 줄로 무엇을 말했는가.
 * 화면(MeetingRoom)이 자리와 발언을 그릴 때 쓴다. 서버 응답을 바꾸지 않고 있는 값만 다시 묶는다.
 */

import { labelOf, num, signed } from "@/lib/format";
import { ACTION, STANCE } from "@/lib/labels";
import type { DecisionDetail, Seat, TranscriptStep } from "@/lib/types";

/** analyst: 규칙으로 계산한 분석 위원 · debater: AI 토론자 · chair: 결론 · gate: 주문 전 리스크 점검 */
export type AttendeeKind = "analyst" | "debater" | "chair" | "gate";

export interface Attendee {
  id: string;
  kind: AttendeeKind;
  name: string;
  /** 이 의견을 낸 것이 규칙인지 AI인지. 화면에 항상 적는다. */
  basis: "rules" | "ai";
  /** 자리 아래 한 줄: "긍정 +1.00", "반대 논거 2개", "매수", "통과 58주" */
  mark: string;
  seat?: Seat;
  /** AI가 한 발언. 심층 심의에서는 한 사람이 두 번 말한다(주장 → 재반박). */
  steps: TranscriptStep[];
}

export interface Meeting {
  /** 발언 차례: 분석 위원 → 토론 → 위원장 → 리스크 점검 */
  attendees: Attendee[];
  analysts: Attendee[];
  debaters: Attendee[];
  chair: Attendee;
  gate: Attendee;
}

/** 재반박은 같은 사람의 두 번째 발언이다. */
const SPEAKER: Record<string, string> = { bull: "bull", bull_rebuttal: "bull", bear: "bear", bear_rebuttal: "bear", risk: "risk", branch: "branch" };
const SPEAKER_NAME: Record<string, string> = { bull: "강세 연구원", bear: "약세 연구원", risk: "리스크 검토자", branch: "분기 판단" };
const SEVERITY: Record<string, string> = { low: "낮음", medium: "보통", high: "높음" };

function analystMark(seat: Seat): string {
  return seat.abstained ? labelOf(STANCE, "abstain") : `${labelOf(STANCE, seat.stance)} ${signed(seat.value)}`;
}

function debaterMark(speaker: string, steps: TranscriptStep[], d: DecisionDetail): string {
  if (speaker === "risk") {
    const last = steps[steps.length - 1]?.content ?? {};
    if (last.veto === true) return "거부권 행사";
    return typeof last.severity === "string" ? `심각도 ${SEVERITY[last.severity] ?? last.severity}` : "검토함";
  }
  if (speaker === "branch") return d.transcript?.branch?.adopted ? "의견 반영됨" : "규칙 결론 유지";
  const points = steps.reduce((n, step) => n + (Array.isArray(step.content.points) ? step.content.points.length : 0), 0);
  const side = speaker === "bull" ? "찬성" : speaker === "bear" ? "반대" : "";
  return side ? `${side} 논거 ${points}개` : "발언함";
}

function gateMark(d: DecisionDetail): string {
  if (!d.gate) return "해당 없음";
  return d.gate.approved ? `통과 ${num(d.gate.qty)}주` : "거부";
}

export function buildMeeting(d: DecisionDetail): Meeting {
  const analysts: Attendee[] = d.seats.map((seat) => ({ id: `seat-${seat.seat}`, kind: "analyst", name: seat.label, basis: "rules", mark: analystMark(seat), seat, steps: [] }));

  const steps = d.transcript?.steps ?? [];
  const order: string[] = [];
  const spoken: Record<string, TranscriptStep[]> = {};
  const names: Record<string, string> = {};
  for (const step of steps) {
    if (step.role === "chair") continue;
    const speaker = SPEAKER[step.role] ?? step.role;
    if (!spoken[speaker]) {
      spoken[speaker] = [];
      order.push(speaker);
      names[speaker] = SPEAKER_NAME[speaker] ?? step.label;
    }
    spoken[speaker].push(step);
  }
  const debaters: Attendee[] = order.map((speaker) => ({ id: `ai-${speaker}`, kind: "debater", name: names[speaker], basis: "ai", mark: debaterMark(speaker, spoken[speaker], d), steps: spoken[speaker] }));

  const chair: Attendee = {
    id: "chair",
    kind: "chair",
    name: "위원장",
    basis: d.final.source === "ai" ? "ai" : "rules",
    mark: d.final.status !== "ok" ? "확인 필요" : labelOf(ACTION, d.final.action),
    steps: steps.filter((step) => step.role === "chair"),
  };
  const gate: Attendee = { id: "gate", kind: "gate", name: "리스크 점검", basis: "rules", mark: gateMark(d), steps: [] };

  return { attendees: [...analysts, ...debaters, chair, gate], analysts, debaters, chair, gate };
}

/**
 * 탁자 위쪽·아래쪽에 앉힐 사람. 토론자가 있으면 분석 위원이 위, 토론자가 아래에 마주 앉고,
 * 없으면(규칙 위원회) 분석 위원을 반씩 나눠 앉힌다.
 */
export function tableSides(m: Meeting): { top: Attendee[]; bottom: Attendee[] } {
  if (m.debaters.length > 0) return { top: m.analysts, bottom: m.debaters };
  const half = Math.ceil(m.analysts.length / 2);
  return { top: m.analysts.slice(0, half), bottom: m.analysts.slice(half) };
}
