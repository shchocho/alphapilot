/** 일봉 차트의 값 읽기(순수 함수). 십자선이 가리키는 날의 전일 대비·이동평균·거래정지 여부를 계산한다. */

export interface Bar {
  d: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Overlays {
  sma20: (number | null)[];
  sma50: (number | null)[];
  sma200: (number | null)[];
}

export interface Readout {
  bar: Bar;
  /** 바로 앞 거래일 종가와의 차이. 첫 봉은 null */
  change: number | null;
  changePct: number | null;
  halted: boolean;
  sma: { sma20: number | null; sma50: number | null; sma200: number | null };
}

/** 거래정지일: 거래가 없어 값이 직전 종가에 멈춰 있는 날(거래량 0, 시가·고가·저가·종가가 같음). */
export function isHalted(bar: Bar): boolean {
  return bar.v === 0 && bar.o === bar.c && bar.h === bar.c && bar.l === bar.c;
}

export function readout(bars: readonly Bar[], overlays: Overlays, index: number): Readout {
  const i = Math.min(bars.length - 1, Math.max(0, index));
  const bar = bars[i];
  const prev = i > 0 ? bars[i - 1].c : null;
  return {
    bar,
    change: prev === null ? null : bar.c - prev,
    changePct: prev === null || prev === 0 ? null : bar.c / prev - 1,
    halted: isHalted(bar),
    sma: { sma20: overlays.sma20[i] ?? null, sma50: overlays.sma50[i] ?? null, sma200: overlays.sma200[i] ?? null },
  };
}
