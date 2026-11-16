import { describe, expect, it } from "vitest";
import { isHalted, readout } from "./candle";

const bars = [
  { d: "2026-10-01", o: 210_000, h: 216_000, l: 209_000, c: 215_500, v: 900_000 },
  { d: "2026-10-02", o: 215_500, h: 215_500, l: 215_500, c: 215_500, v: 0 },
  { d: "2026-10-06", o: 227_000, h: 235_000, l: 226_000, c: 233_000, v: 1_262_283 },
];
const overlays = { sma20: [null, 214_000.4, 215_120.6], sma50: [null, null, 201_000], sma200: [150_000, 150_100, 150_200] };

describe("일봉 읽기(십자선이 가리키는 날)", () => {
  it("전일 대비는 바로 앞 거래일의 종가와 견준다", () => {
    const r = readout(bars, overlays, 2);
    expect(r.change).toBe(17_500);
    expect(r.changePct).toBeCloseTo(17_500 / 215_500, 10);
  });
  it("첫 봉은 견줄 전일이 없다", () => {
    const r = readout(bars, overlays, 0);
    expect(r.change).toBeNull();
    expect(r.changePct).toBeNull();
  });
  it("그날의 이동평균 값을 함께 준다(아직 계산되지 않은 날은 null)", () => {
    expect(readout(bars, overlays, 2).sma).toEqual({ sma20: 215_120.6, sma50: 201_000, sma200: 150_200 });
    expect(readout(bars, overlays, 0).sma).toEqual({ sma20: null, sma50: null, sma200: 150_000 });
  });
  it("거래량이 0이고 시가·고가·저가·종가가 같으면 거래정지일이다", () => {
    expect(isHalted(bars[1])).toBe(true);
    expect(isHalted(bars[0])).toBe(false);
    expect(isHalted({ ...bars[1], v: 10 })).toBe(false);
    expect(readout(bars, overlays, 1).halted).toBe(true);
  });
  it("범위를 벗어난 위치는 마지막 봉으로 읽는다", () => {
    expect(readout(bars, overlays, 99).bar.d).toBe("2026-10-06");
  });
});
