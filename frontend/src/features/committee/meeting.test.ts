import { describe, expect, it } from "vitest";
import type { DecisionDetail, Seat, TranscriptStep } from "@/lib/types";
import { buildMeeting, signed, tableSides } from "./meeting";

const seat = (key: string, label: string, value: number, stance: Seat["stance"], abstained = false): Seat => ({
  seat: key,
  label,
  value,
  confidence: 1,
  abstained,
  summary: `${label} 요약`,
  stance,
  components: [],
  as_of: "2026-08-14",
});

const step = (role: string, label: string, content: Record<string, unknown>): TranscriptStep => ({
  role,
  label,
  content,
  model: "claude-opus-5-5",
  input_tokens: 100,
  output_tokens: 50,
  cache_read_tokens: 0,
  cost_usd: 0.01,
});

const SEATS: Seat[] = [
  seat("trend", "추세", 1, "bullish"),
  seat("breakout", "돌파", 1, "bullish"),
  seat("growth", "성장·수급", 0.6, "bullish"),
  seat("momentum", "모멘텀", 0.839, "bullish"),
  seat("overheat", "과열·눌림", -0.36, "bearish"),
  seat("value", "가치", 0, "abstain", true),
  seat("risk", "리스크", -0.2, "bearish"),
  seat("regime", "시장 국면", 0.147, "neutral"),
];

function decision(patch: Partial<DecisionDetail> = {}): DecisionDetail {
  const base = {
    id: "260814-001450-e",
    as_of: "2026-08-14",
    code: "001450",
    name: "현대해상",
    kind: "entry",
    action: "BUY",
    conviction: "high",
    source: "rules",
    status: "ok",
    chain_id: "8734",
    seats: SEATS,
    techniques: [],
    plan: null,
    max_qty: {},
    final: {
      action: "BUY",
      conviction: "high",
      size_fraction: 1,
      stop: null,
      thesis: "요지",
      key_risks: [],
      invalidation: "",
      dissent: "",
      source: "rules",
      status: "ok",
      status_detail: "",
      votes: { bullish: 4, bearish: 2, neutral: 1, abstain: 1 },
    },
    gate: { approved: true, qty: 58, stop: 42150, order_value: 2630300, risk_amount: 185600, base_qty: 58, summary: "통과", steps: [] },
    transcript: null,
    intent: null,
    chain: [],
    market: "KOSPI",
  };
  return { ...base, ...patch } as unknown as DecisionDetail;
}

const ai = (steps: TranscriptStep[], extra: Record<string, unknown> = {}): DecisionDetail["transcript"] =>
  ({ depth: "standard", model: "claude-opus-5-5", steps, error: "", cost_usd: 0.04, ...extra }) as DecisionDetail["transcript"];

describe("signed", () => {
  it("부호를 붙이고 음수는 진짜 빼기 기호로 적는다", () => {
    expect(signed(1)).toBe("+1.00");
    expect(signed(-0.36)).toBe("−0.36");
    expect(signed(0)).toBe("0.00");
  });
});

describe("buildMeeting", () => {
  it("규칙 위원회: 분석 위원 → 위원장 → 리스크 점검 차례로 앉고 토론자는 없다", () => {
    const m = buildMeeting(decision());
    expect(m.attendees.map((a) => a.id)).toEqual(["seat-trend", "seat-breakout", "seat-growth", "seat-momentum", "seat-overheat", "seat-value", "seat-risk", "seat-regime", "chair", "gate"]);
    expect(m.debaters).toEqual([]);
    expect(m.chair).toMatchObject({ basis: "rules", mark: "매수" });
    expect(m.gate.mark).toBe("통과 58주");
  });

  it("분석 위원의 한 줄은 의견과 부호 붙은 값이고, 기권은 값 없이 적는다", () => {
    const marks = Object.fromEntries(buildMeeting(decision()).analysts.map((a) => [a.name, a.mark]));
    expect(marks["추세"]).toBe("긍정 +1.00");
    expect(marks["과열·눌림"]).toBe("부정 −0.36");
    expect(marks["가치"]).toBe("기권");
    expect(marks["시장 국면"]).toBe("중립 +0.15");
  });

  it("AI 표준 심의: 강세·약세·리스크 검토자가 토론자로 앉고 위원장 발언은 위원장에게 붙는다", () => {
    const m = buildMeeting(
      decision({
        source: "ai",
        final: { ...decision().final, source: "ai" },
        transcript: ai([
          step("bull", "강세 연구원", { points: ["a", "b", "c"], strongest_evidence: "x", weakest_spot: "y" }),
          step("bear", "약세 연구원", { points: ["d", "e"], strongest_evidence: "x", weakest_spot: "y" }),
          step("risk", "리스크 검토자", { concerns: ["f"], severity: "medium", veto: false, size: "half", note: "" }),
          step("chair", "위원장", { action: "BUY" }),
        ]),
      }),
    );
    expect(m.debaters.map((a) => [a.id, a.name, a.mark])).toEqual([
      ["ai-bull", "강세 연구원", "찬성 논거 3개"],
      ["ai-bear", "약세 연구원", "반대 논거 2개"],
      ["ai-risk", "리스크 검토자", "심각도 보통"],
    ]);
    expect(m.chair.basis).toBe("ai");
    expect(m.chair.steps.map((s) => s.role)).toEqual(["chair"]);
    expect(m.attendees.map((a) => a.id).slice(-5)).toEqual(["ai-bull", "ai-bear", "ai-risk", "chair", "gate"]);
  });

  it("심층 심의: 재반박은 새 사람이 아니라 같은 사람의 두 번째 발언이다", () => {
    const m = buildMeeting(
      decision({
        transcript: ai([
          step("bull", "강세 연구원", { points: ["a"] }),
          step("bear", "약세 연구원", { points: ["b"] }),
          step("bull_rebuttal", "강세 재반박", { points: ["c", "d"] }),
          step("bear_rebuttal", "약세 재반박", { points: ["e"] }),
          step("risk", "리스크 검토자", { concerns: [], severity: "high", veto: true, size: "quarter", note: "" }),
          step("chair", "위원장", { action: "HOLD" }),
        ]),
      }),
    );
    expect(m.debaters.map((a) => a.id)).toEqual(["ai-bull", "ai-bear", "ai-risk"]);
    expect(m.debaters[0].steps.map((s) => s.label)).toEqual(["강세 연구원", "강세 재반박"]);
    expect(m.debaters[0].mark).toBe("찬성 논거 3개");
    expect(m.debaters[2].mark).toBe("거부권 행사");
  });

  it("규칙 + AI 분기: 물어본 분기가 한 자리로 앉고 반영 여부를 적는다", () => {
    const steps = [step("branch", "분기 판단", { action: "HOLD" })];
    const kept = buildMeeting(decision({ transcript: ai(steps, { depth: "branch", branch: { reason: "의견이 갈림", outcome: "규칙 결론 유지", adopted: false } }) }));
    const adopted = buildMeeting(decision({ transcript: ai(steps, { depth: "branch", branch: { reason: "의견이 갈림", outcome: "보류로 바꿈", adopted: true } }) }));
    expect(kept.debaters.map((a) => [a.id, a.name, a.mark])).toEqual([["ai-branch", "분기 판단", "규칙 결론 유지"]]);
    expect(adopted.debaters[0].mark).toBe("의견 반영됨");
  });

  it("AI를 쓰지 못해 보류로 처리한 판단은 위원장 자리에 '확인 필요'로 적는다", () => {
    const m = buildMeeting(decision({ final: { ...decision().final, action: "HOLD", status: "review", status_detail: "하루 AI 예산을 다 썼습니다" } }));
    expect(m.chair.mark).toBe("확인 필요");
  });

  it("리스크 점검: 거부와 점검하지 않은 경우를 구분한다", () => {
    expect(buildMeeting(decision({ gate: { ...decision().gate!, approved: false, qty: 0 } })).gate.mark).toBe("거부");
    expect(buildMeeting(decision({ gate: null })).gate.mark).toBe("해당 없음");
  });

  it("모르는 역할은 서버가 준 이름 그대로 한 자리를 차지한다", () => {
    const m = buildMeeting(decision({ transcript: ai([step("macro", "거시 분석가", { note: "n" })]) }));
    expect(m.debaters.map((a) => [a.id, a.name, a.mark])).toEqual([["ai-macro", "거시 분석가", "발언함"]]);
  });
});

describe("tableSides", () => {
  it("토론자가 없으면 분석 위원을 반씩 나눠 앉힌다", () => {
    const { top, bottom } = tableSides(buildMeeting(decision()));
    expect(top.map((a) => a.name)).toEqual(["추세", "돌파", "성장·수급", "모멘텀"]);
    expect(bottom.map((a) => a.name)).toEqual(["과열·눌림", "가치", "리스크", "시장 국면"]);
  });

  it("토론자가 있으면 분석 위원이 위, 토론자가 아래에 앉는다", () => {
    const m = buildMeeting(decision({ transcript: ai([step("bull", "강세 연구원", { points: [] }), step("bear", "약세 연구원", { points: [] })]) }));
    const { top, bottom } = tableSides(m);
    expect(top).toHaveLength(8);
    expect(bottom.map((a) => a.name)).toEqual(["강세 연구원", "약세 연구원"]);
  });

  it("위원이 홀수면 위쪽에 한 명 더 앉힌다", () => {
    const { top, bottom } = tableSides(buildMeeting(decision({ seats: SEATS.slice(0, 5) })));
    expect([top.length, bottom.length]).toEqual([3, 2]);
  });
});
