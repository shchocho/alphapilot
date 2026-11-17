import { describe, expect, it } from "vitest";
import { checkValueText, entryText, exitPlanText, GATE_RULE, heldText, kindTone } from "./labels";

describe("기법 점검 값", () => {
  it("기준에 %가 있으면 값도 퍼센트로, 기준에 부호가 있으면 값에도 부호를 붙인다", () => {
    expect(checkValueText(187.3, "≥ +25%")).toBe("+187.3%");
    expect(checkValueText(-50.8, "≥ −25%")).toBe("−50.8%");
    expect(checkValueText(3.7, "2% ~ 12%")).toBe("3.7%");
    expect(checkValueText(0, "≥ −25%")).toBe("0.0%");
  });
  it("퍼센트가 아닌 값은 그대로, 음수는 진짜 빼기 기호로", () => {
    expect(checkValueText(215_500, "> 194,958")).toBe("215,500");
    expect(checkValueText(96, "> 70")).toBe("96");
    expect(checkValueText(-0.35, "> 0")).toBe("−0.35");
    expect(checkValueText(null, "> 0")).toBe("자료 없음");
    expect(checkValueText("3단계", "")).toBe("3단계");
  });
});

describe("리스크 점검 규칙 이름", () => {
  it("서버 키 대신 설정 화면의 한도 이름으로 적는다", () => {
    expect(GATE_RULE.max_stop).toBe("손절 폭 상한");
    expect(GATE_RULE.max_heat).toBe("손절 시 총손실 상한");
    expect(GATE_RULE.cash).toBe("남겨 둘 현금");
  });
});

describe("주문 계획 설명", () => {
  it("매도는 진입 방식과 상관없이 다음 거래일 시가", () => {
    expect(entryText({ side: "sell", entry_type: "trigger", trigger: 50_000, chase_limit: null })).toBe("다음 거래일 시가에 매도");
  });
  it("돌파 매수는 기준 가격과 따라 사지 않는 상한을 적는다", () => {
    expect(entryText({ side: "buy", entry_type: "trigger", trigger: 50_000, chase_limit: 51_500 })).toBe("장중 50,000원을 넘으면 매수 (51,500원 위로는 따라 사지 않음)");
    expect(entryText({ side: "buy", entry_type: "open", trigger: null, chase_limit: null })).toBe("다음 거래일 시가에 매수");
  });
  it("변동성 돌파는 기준 가격이 아직 없어도 설명한다", () => {
    expect(entryText({ side: "buy", entry_type: "vb", trigger: null, chase_limit: null })).toContain("다음 날 시가에 청산");
  });
});

describe("보유 종목 문구", () => {
  it("산 날은 0일째가 아니라 매수 당일이라고 적는다", () => {
    expect(heldText(0)).toBe("매수 당일");
    expect(heldText(3)).toBe("3거래일째");
  });
  it("목표가가 없으면 어떻게 팔리는지 적는다", () => {
    expect(exitPlanText({ target: 60_000, exit_on_next_open: false, trailing: false })).toBe("목표 60,000원");
    expect(exitPlanText({ target: null, exit_on_next_open: true, trailing: false })).toBe("다음 거래일 시가에 청산");
    expect(exitPlanText({ target: null, exit_on_next_open: false, trailing: true })).toBe("목표가 없이 손절 가격을 따라 올림");
  });
});

describe("장부 적요의 색", () => {
  it("계획은 보라, 거부·오류는 위험, 체결은 굵게, 나머지는 보통", () => {
    expect(kindTone("intent")).toBe("plan");
    expect(kindTone("gate_block")).toBe("danger");
    expect(kindTone("fill_buy")).toBe("strong");
    expect(kindTone("precheck")).toBe("plain");
  });
});
