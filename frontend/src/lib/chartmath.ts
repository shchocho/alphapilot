/** 차트 눈금 계산(순수 함수). */

/** 보기 좋은 눈금 값 3~5개. 범위 안의 1·2·2.5·5 배수만 고른다. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / magnitude;
  // 가장 가까운 보기 좋은 간격으로 맞춘다(올리기만 하면 눈금이 두 개만 남는 경우가 생긴다).
  const step = (fraction < 1.5 ? 1 : fraction < 2.25 ? 2 : fraction < 3.75 ? 2.5 : fraction < 7.5 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  // 더해 가지 않고 곱해서 구한다(0.025를 네 번 더하면 0이 아니라 −7e-18이 나온다).
  for (let k = Math.ceil(min / step - 1e-9); k * step <= max + step * 1e-9; k += 1) ticks.push(k === 0 ? 0 : Number((k * step).toPrecision(12)));
  return ticks;
}

/** 12px 글자의 대략적인 너비(한글은 넓고 숫자·기호는 좁다). 축 눈금이 잘리지 않게 왼쪽 여백을 잡는 데 쓴다. */
export function textWidth(text: string): number {
  let width = 0;
  for (const ch of text) width += /[\u3131-\uD79D]/.test(ch) ? 12 : ch === " " ? 4 : 7;
  return width;
}

const NICE_STEPS = [1, 2, 2.5, 5, 10];

export interface Scale {
  lo: number;
  hi: number;
  step: number;
  ticks: number[];
}

/**
 * 축 범위와 눈금. 범위의 양 끝을 눈금 간격의 배수로 넓혀서, 모든 값이 가장 아래 눈금과 가장 위 눈금 사이에 놓인다
 * (선이 눈금 없는 곳으로 내려가 값을 읽을 수 없게 되는 일이 없다).
 */
export function niceScale(min: number, max: number, count = 5): Scale {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { lo: 0, hi: 1, step: 1, ticks: [0, 1] };
  if (min > max) [min, max] = [max, min];
  if (min === max) {
    const spread = Math.abs(min) * 0.01 || 1;
    min -= spread;
    max += spread;
  }
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / magnitude;
  let pick = fraction < 1.5 ? 0 : fraction < 2.25 ? 1 : fraction < 3.75 ? 2 : fraction < 7.5 ? 3 : 4;
  let scale = magnitude;
  for (;;) {
    const step = NICE_STEPS[pick] * scale;
    const from = Math.floor(min / step + 1e-9);
    const to = Math.ceil(max / step - 1e-9);
    if (to - from + 1 <= 8) {
      // 더해 가지 않고 곱해서 구한다(떠다니는 오차가 쌓이지 않게)
      const ticks: number[] = [];
      for (let k = from; k <= to; k += 1) ticks.push(k === 0 ? 0 : Number((k * step).toPrecision(12)));
      return { lo: ticks[0], hi: ticks[ticks.length - 1], step: Number(step.toPrecision(12)), ticks };
    }
    pick += 1;
    if (pick === NICE_STEPS.length - 1) {
      pick = 0;
      scale *= 10;
    }
  }
}

/** 간격의 배수를 반올림 없이 적는 데 필요한 소수 자릿수(2.5 → 1, 0.025 → 3, 20 → 0). */
export function stepDigits(step: number): number {
  for (let digits = 0; digits < 6; digits += 1) {
    const scaled = Math.abs(step) * 10 ** digits;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-6) return digits;
  }
  return 6;
}

export interface DateTick {
  index: number;
  label: string;
}

/**
 * 날짜 축 눈금: 달이 바뀌는 첫 거래일. 많으면 2·3·6·12달 간격으로 줄이되 1월·4월·7월·10월처럼 달력에 맞춘다.
 * 달이 바뀌지 않는 짧은 기간은 처음과 끝 날짜를 그대로 적는다. dates는 "YYYY-MM-DD" 오름차순.
 */
export function monthTicks(dates: readonly string[], maxCount: number): DateTick[] {
  const full = (iso: string) => iso.slice(0, 10).replaceAll("-", ".");
  const starts: number[] = [];
  for (let i = 1; i < dates.length; i += 1) if (dates[i].slice(0, 7) !== dates[i - 1].slice(0, 7)) starts.push(i);
  for (const every of [1, 2, 3, 6, 12, 24, 60]) {
    const picked = starts.filter((i) => {
      const year = Number(dates[i].slice(0, 4));
      const month = Number(dates[i].slice(5, 7));
      return every <= 12 ? (month - 1) % every === 0 : month === 1 && year % (every / 12) === 0;
    });
    if (picked.length <= Math.max(1, maxCount)) {
      if (picked.length === 0) break;
      return picked.map((index) => ({ index, label: dates[index].slice(0, 7).replace("-", ".") }));
    }
  }
  if (dates.length === 0) return [];
  if (dates.length === 1) return [{ index: 0, label: full(dates[0]) }];
  return [
    { index: 0, label: full(dates[0]) },
    { index: dates.length - 1, label: full(dates[dates.length - 1]) },
  ];
}
