import { describe, expect, it } from "vitest";
import { arrow, clock, dayDots, dayLabel, dayShort, direction, labelOf, duration, num, pct, seqLabel, won, wonAbout, wonExact, wonShort, wonSigned } from "./format";

describe("금액", () => {
  it("천 단위 쉼표와 원을 붙인다", () => {
    expect(won(31240000)).toBe("31,240,000원");
    expect(won(null)).toBe("–");
  });
  it("큰 금액은 억·조로 줄인다", () => {
    expect(wonShort(1_234_000_000)).toBe("12.3억 원");
    expect(wonShort(2_500_000_000_000)).toBe("2.5조 원");
    expect(wonShort(52_000_000_000)).toBe("520억 원");
    expect(wonShort(710_000)).toBe("71만 원");
    expect(wonShort(-300_000_000)).toBe("−3억 원");
  });
  it("승인 버튼용 어림 금액", () => {
    expect(wonAbout(707_000)).toBe("약 71만 원");
    expect(wonAbout(123_000_000)).toBe("약 1.2억 원");
  });
  it("부호 있는 금액은 − 기호를 쓴다", () => {
    expect(wonSigned(12300)).toBe("+12,300원");
    expect(wonSigned(-4500)).toBe("−4,500원");
    expect(wonSigned(0)).toBe("0원");
  });
});

describe("비율과 방향", () => {
  it("퍼센트에 부호를 붙인다", () => {
    expect(pct(0.0123)).toBe("+1.23%");
    expect(pct(-0.051, 1)).toBe("−5.1%");
    expect(pct(0)).toBe("0.00%");
    expect(pct(0.32, 0, false)).toBe("32%");
    expect(pct(undefined)).toBe("–");
  });
  it("방향과 화살표", () => {
    expect(direction(3)).toBe("up");
    expect(direction(-1)).toBe("down");
    expect(direction(0)).toBe("flat");
    expect([arrow(1), arrow(-1), arrow(0)]).toEqual(["▲", "▼", "–"]);
  });
});

describe("날짜·시간", () => {
  it("날짜 표기", () => {
    expect(dayLabel("2026-11-03")).toBe("11월 3일");
    expect(dayDots("2026-11-13")).toBe("2026.11.13");
    expect(dayShort("2026-01-05")).toBe("01.05");
    expect(dayShort(null)).toBe("–");
    expect(clock("2026-11-13T10:31:02+09:00")).toBe("10:31");
  });
  it("남은 시간", () => {
    expect(duration(17280)).toBe("4시간 48분");
    expect(duration(720)).toBe("12분");
    expect(duration(null)).toBe("");
  });
  it("거래번호는 네 자리로 채운다", () => {
    expect(seqLabel(57)).toBe("0057");
    expect(seqLabel(12345)).toBe("12345");
    expect(num(1234.5, 1)).toBe("1,234.5");
  });
});

describe("서버 키를 화면 말로", () => {
  it("아는 키는 바꾸고 모르는 키는 그대로 둔다", () => {
    expect(labelOf({ high: "높음" }, "high")).toBe("높음");
    expect(labelOf({ high: "높음" }, "odd")).toBe("odd");
    expect(labelOf({ high: "높음" }, null)).toBe("–");
  });
});

describe("축 눈금용 금액(wonExact): 줄여 쓰되 반올림하지 않는다", () => {
  it("만·억으로 떨어지는 값은 줄여 쓴다", () => {
    expect(wonExact(27_500_000)).toBe("2,750만 원");
    expect(wonExact(100_000_000)).toBe("1억 원");
    expect(wonExact(120_000_000)).toBe("1.2억 원");
    expect(wonExact(102_500_000)).toBe("1억 250만 원");
    expect(wonExact(0)).toBe("0");
  });
  it("만으로 떨어지지 않으면 원 단위로 다 적는다(2만 5천 원을 3만 원이라 하지 않는다)", () => {
    expect(wonExact(25_000)).toBe("2.5만 원");
    expect(wonExact(125_000)).toBe("12.5만 원");
    expect(wonExact(12_345)).toBe("12,345원");
    expect(wonExact(-500_000)).toBe("−50만 원");
    expect(wonExact(2_500)).toBe("2,500원");
  });
});
