import { describe, expect, it } from "vitest";
import { monthTicks, niceScale, niceTicks, stepDigits, textWidth } from "./chartmath";

describe("눈금", () => {
  it("범위 안에서 보기 좋은 배수만 고른다", () => {
    expect(niceTicks(0, 100)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(28_100_000, 30_400_000)).toEqual([28_500_000, 29_000_000, 29_500_000, 30_000_000]);
  });
  it("음수와 양수에 걸친 범위는 0을 포함한다", () => {
    expect(niceTicks(-600_000, 600_000, 3)).toEqual([-500_000, 0, 500_000]);
  });
  it("소수 범위에서도 떠다니는 오차 없이 떨어진다", () => {
    expect(niceTicks(-0.105, 0)).toEqual([-0.1, -0.075, -0.05, -0.025, 0]);
  });
  it("값이 하나뿐이거나 숫자가 아니면 안전하게 돌려준다", () => {
    expect(niceTicks(5, 5)).toEqual([5]);
    expect(niceTicks(Number.NaN, 1)).toEqual([]);
  });
});

describe("글자 너비 어림", () => {
  it("한글은 넓게, 숫자와 기호는 좁게 센다", () => {
    expect(textWidth("3,000만 원")).toBe(7 * 5 + 12 + 4 + 12);
    expect(textWidth("−10%")).toBe(28);
    expect(textWidth("")).toBe(0);
  });
});

describe("축 범위(niceScale)", () => {
  it("모든 값이 가장 아래 눈금과 가장 위 눈금 사이에 들어온다", () => {
    const s = niceScale(28_435_248, 105_637_974);
    expect(s.lo).toBeLessThanOrEqual(28_435_248);
    expect(s.hi).toBeGreaterThanOrEqual(105_637_974);
    expect(s.ticks[0]).toBe(s.lo);
    expect(s.ticks[s.ticks.length - 1]).toBe(s.hi);
    expect(s.ticks).toEqual([20_000_000, 40_000_000, 60_000_000, 80_000_000, 100_000_000, 120_000_000]);
  });
  it("눈금은 간격의 배수이고 3~8개다", () => {
    for (const [min, max] of [[-0.10466, 0], [29_100_000, 30_050_000], [-859_294, 446_598], [0.3, 0.31], [99, 101]] as const) {
      const s = niceScale(min, max);
      expect(s.ticks.length).toBeGreaterThanOrEqual(3);
      expect(s.ticks.length).toBeLessThanOrEqual(8);
      for (const t of s.ticks) expect(Math.abs(t / s.step - Math.round(t / s.step))).toBeLessThan(1e-6);
      expect(s.lo).toBeLessThanOrEqual(min);
      expect(s.hi).toBeGreaterThanOrEqual(max);
    }
  });
  it("값이 하나뿐이어도 위아래로 범위를 만든다", () => {
    const s = niceScale(30_000_000, 30_000_000);
    expect(s.lo).toBeLessThan(30_000_000);
    expect(s.hi).toBeGreaterThan(30_000_000);
  });
});

describe("눈금 글자의 소수 자리(stepDigits)", () => {
  it("간격의 배수를 반올림 없이 적는 데 필요한 자릿수", () => {
    expect(stepDigits(25)).toBe(0);
    expect(stepDigits(2.5)).toBe(1);
    expect(stepDigits(0.5)).toBe(1);
    expect(stepDigits(0.025)).toBe(3);
    expect(stepDigits(2)).toBe(0);
  });
  it("낙폭 눈금 −2.5%가 −3%로 적히지 않는다", () => {
    const s = niceScale(-0.10466, 0);
    const labels = s.ticks.map((t) => (t * 100).toFixed(stepDigits(s.step * 100)));
    expect(new Set(labels).size).toBe(labels.length);
    for (let i = 0; i < labels.length; i += 1) expect(Number(labels[i])).toBeCloseTo(s.ticks[i] * 100, 9);
  });
});

describe("날짜 눈금(monthTicks)", () => {
  const days = (from: string, count: number) => {
    const out: string[] = [];
    const d = new Date(`${from}T00:00:00Z`);
    while (out.length < count) {
      if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(d.toISOString().slice(0, 10));
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return out;
  };
  it("달이 바뀌는 첫 거래일에 눈금을 둔다", () => {
    const dates = days("2026-07-01", 65);
    const ticks = monthTicks(dates, 6);
    expect(ticks.map((t) => t.label)).toEqual(["2026.08", "2026.09"]);
    for (const t of ticks) expect(dates[t.index].slice(0, 7)).not.toBe(dates[t.index - 1].slice(0, 7));
  });
  it("기간이 길면 석 달·여섯 달·한 해 간격으로 줄이고, 1월·4월처럼 달력에 맞춘다", () => {
    const dates = days("2024-08-09", 548);
    const ticks = monthTicks(dates, 6);
    expect(ticks.length).toBeLessThanOrEqual(6);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.every((t) => ["01", "07"].includes(t.label.slice(5)))).toBe(true);
  });
  it("달이 바뀌지 않는 짧은 기간은 처음과 끝 날짜를 적는다", () => {
    const dates = days("2026-10-05", 5);
    expect(monthTicks(dates, 6)).toEqual([
      { index: 0, label: "2026.10.05" },
      { index: 4, label: "2026.10.09" },
    ]);
  });
});
