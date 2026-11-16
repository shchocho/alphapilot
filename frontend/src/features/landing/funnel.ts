/** 메인 화면의 "걸러지는 과정" 계산(순수 함수). 3D 장면과 정지 그림이 같은 값을 쓴다. */

/** 단계별로 남는 수. 2026-10-02 시뮬레이션 장부의 "신호 38종목 → 심의 6 → 매수안 3"과 유니버스 143종목. */
export const FUNNEL = {
  counts: [143, 38, 6, 3] as const,
  source: "2026년 10월 2일 시뮬레이션 기록",
};

export interface Chapter {
  /** 이 장이 온전히 보이는 스크롤 진행률 구간 */
  from: number;
  to: number;
  count: number;
  unit: string;
  /** 숫자판에 붙는 짧은 이름 */
  label: string;
  title: string;
  body: string;
}

export const CHAPTERS: Chapter[] = [
  { from: 0, to: 0.16, count: 143, label: "살펴본 종목", unit: "종목", title: "매일 장이 끝나면 살펴봅니다", body: "거래대금이 충분한 코스피·코스닥 종목의 일봉을 받아 옵니다." },
  { from: 0.3, to: 0.46, count: 38, label: "기법 조건 통과", unit: "종목", title: "기법 조건을 통과했습니다", body: "추세, 돌파, 수급, 변동성 돌파. 조건을 하나라도 못 채우면 여기서 멈춥니다." },
  { from: 0.58, to: 0.74, count: 6, label: "위원회 심의", unit: "종목", title: "위원회가 심의했습니다", body: "점수 순으로 올라온 후보를 강세·약세로 따져 매수, 보류를 정합니다." },
  { from: 0.86, to: 1, count: 3, label: "주문 계획", unit: "건", title: "주문 계획이 됐습니다", body: "리스크 점검이 수량을 줄이거나 막고, 남은 것만 내 승인을 기다립니다." },
];

/** 0 → 1로 부드럽게 넘어가는 보간. */
export function smoothstep(edge0: number, edge1: number, x: number): number {
  if (edge0 === edge1) return x < edge0 ? 0 : 1;
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/** 장 하나의 불투명도: 구간 안에서는 1, 앞뒤 fade 폭만큼 걸쳐 0으로. */
export function chapterOpacity(chapter: Chapter, progress: number, fade = 0.06): number {
  const rise = chapter.from <= 0 ? 1 : smoothstep(chapter.from - fade, chapter.from, progress);
  const fall = chapter.to >= 1 ? 1 : 1 - smoothstep(chapter.to, chapter.to + fade, progress);
  return Math.min(rise, fall);
}

/** 씨앗이 같으면 항상 같은 수열을 내는 난수(장면이 새로 고칠 때마다 달라지지 않게). */
export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * 종목마다 "어느 관문까지 가는가"를 정한다.
 * 0: 첫 관문(기법 조건)에서 멈춤, 1: 둘째(위원회)에서, 2: 셋째(리스크 점검)에서, 3: 끝까지 통과.
 */
export function fates(counts: readonly number[] = FUNNEL.counts, seed = 20261002): number[] {
  const total = counts[0];
  const order = Array.from({ length: total }, (_, i) => i);
  const random = seeded(seed);
  for (let i = total - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const out = new Array<number>(total).fill(0);
  // 섞은 순서의 앞에서부터 counts[k]개가 k번째 관문을 통과한다.
  for (let stage = 1; stage < counts.length; stage += 1) {
    for (let k = 0; k < counts[stage]; k += 1) out[order[k]] = stage;
  }
  return out;
}


/** 장면의 치수. 길이 단위는 3D 공간의 1. */
export const FIELD = {
  cols: 13,
  rows: 11,
  gapX: 0.92,
  gapZ: 0.72,
  barWidth: 0.36,
  /** 관문 셋의 z 위치: 기법 조건, 위원회 심의, 리스크 점검 */
  gateZ: [-10, -21, -32] as const,
  gateWidth: 15,
  gateHeight: 4.4,
  endZ: -39,
  /** 진행률 0 → 1 동안 종목이 나아가는 거리 */
  travel: 44,
};

/**
 * 진행률 → 종목이 나아간 거리. 장의 글이 보이는 구간(CHAPTERS의 from~to)에서는 천천히 가고 그 사이에서 빨리 간다.
 * 그래서 글이 "38종목이 통과했습니다"라고 할 때 장면에는 첫 관문만 끝나 있고 둘째 관문은 아직 시작하지 않았다.
 */
const TRAVEL_KEYS: readonly (readonly [number, number])[] = [
  [0, 0],
  [0.12, 3.5],
  [0.3, 13.8],
  [0.46, 16.1],
  [0.58, 24.8],
  [0.74, 27.1],
  [0.86, 33],
  [1, 44],
];

/** 숫자판의 이름. TRAVEL_KEYS의 구간과 하나씩 짝이 맞는다: 걸러지는 중인 구간과 끝난 구간(장의 글이 보이는 구간). */
export const PHASES: readonly { label: string; unit: string; step: number }[] = [
  { label: "살펴본 종목", unit: "종목", step: 1 },
  { label: "기법 조건 확인 중", unit: "종목", step: 1 },
  { label: "기법 조건 통과", unit: "종목", step: 2 },
  { label: "위원회 심의 중", unit: "종목", step: 2 },
  { label: "위원회 심의", unit: "종목", step: 3 },
  { label: "리스크 점검 중", unit: "종목", step: 3 },
  { label: "주문 계획", unit: "건", step: 4 },
];

export function phaseAt(progress: number): number {
  for (let i = 1; i < TRAVEL_KEYS.length - 1; i += 1) {
    if (progress < TRAVEL_KEYS[i][0]) return i - 1;
  }
  return PHASES.length - 1;
}

export function travelAt(progress: number): number {
  const p = Math.min(1, Math.max(0, progress));
  for (let i = 1; i < TRAVEL_KEYS.length; i += 1) {
    const [p1, t1] = TRAVEL_KEYS[i];
    if (p <= p1) {
      const [p0, t0] = TRAVEL_KEYS[i - 1];
      return t0 + ((t1 - t0) * (p - p0)) / (p1 - p0);
    }
  }
  return FIELD.travel;
}

export const GATE_LABELS = ["기법 조건", "위원회 심의", "리스크 점검"] as const;

/** 관문 이름표가 붙는 자리(관문 윗변 위의 x). 정지 구도에서는 뒤에 선 기둥과 겹치지 않게 왼쪽으로 옮긴다. */
export function labelX(still: boolean): number {
  return still ? -4.4 : 0;
}

export type Vec3 = readonly [number, number, number];

export const CAMERA = {
  /** 스크롤을 따라 지나가는 카메라 길(스플라인의 제어점)과 그때 바라보는 점 */
  // 진행률 0, 0.2, 0.4, 0.6, 0.8, 1에서 지나는 자리. 관문마다 앞에 남은 것과 지나간 것이 함께 보이도록 옆에서 본다.
  // 마지막에는 주문 계획 3건 뒤로 돌아가, 걸러진 것 전체를 되돌아본다.
  path: [
    [-9, 4.2, 11.5],
    [5, 6.8, 11],
    [11.5, 6, 0],
    [10, 4.2, -12.5],
    [11, 4.8, -23],
    [3.4, 2.5, -46.5],
  ] as readonly Vec3[],
  looks: [
    [1.5, 1.3, -6],
    [0, 0.6, -8],
    [0, 0.5, -12.5],
    [0, 0.9, -23],
    [0, 0.8, -33],
    [-0.6, 1.5, -31],
  ] as readonly Vec3[],
  /** 정지 구도(모션 줄이기·WebGL 없음): 걸러진 결과 전체가 한 장에 보이는 자리 */
  overview(aspect: number): { eye: Vec3; target: Vec3 } {
    return aspect < 1 ? { eye: [9, 21, 15], target: [0, 0, -19] } : { eye: [18, 11, 6], target: [-1, 0, -19.5] };
  },
  fov(aspect: number): number {
    return aspect < 1 ? 50 : 38;
  },
  /** 좁은 화면에서는 바라보는 점에서 이만큼 더 물러나 장면이 양옆으로 잘리지 않게 한다. */
  pullBack(aspect: number): number {
    return aspect < 1 ? 1.3 : 1;
  },
};

export interface Bar {
  x: number;
  z: number;
  height: number;
  /** 0~2: 그 번호의 관문에서 멈춤, 3: 끝까지 통과 */
  stage: number;
  /** 끝까지 간 종목이 마지막에 설 자리(0~2). 나머지는 -1 */
  slot: number;
}

/** 143종목의 처음 자리와 높이(씨앗 고정). */
export function field(): Bar[] {
  const stage = fates();
  const random = seeded(143);
  let slot = 0;
  return stage.map((s, i) => {
    const col = i % FIELD.cols;
    const row = Math.floor(i / FIELD.cols);
    const x = (col - (FIELD.cols - 1) / 2) * FIELD.gapX + (random() - 0.5) * 0.12;
    const height = 0.8 + random() * 2.1;
    const z = (row - (FIELD.rows - 1) / 2) * FIELD.gapZ;
    return { x, z, height, stage: s, slot: s === 3 ? slot++ : -1 };
  });
}

export interface BarState {
  x: number;
  z: number;
  height: number;
  /** 0: 그대로, -1 쪽: 멈춰서 회색으로, +1 쪽: 주문 계획 색으로 */
  tint: number;
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** 진행률 p에서 종목 하나의 상태. out을 주면 새 객체를 만들지 않는다(프레임마다 143번 부른다). */
export function barAt(bar: Bar, p: number, out: BarState = { x: 0, z: 0, height: 0, tint: 0 }): BarState {
  out.x = bar.x;
  out.z = bar.z - travelAt(p);
  out.height = bar.height;
  out.tint = 0;
  if (bar.stage < 3) {
    // 자기 관문 앞에서 멈추고 납작해진다. 줄 간격은 좁혀서 다음 관문을 넘지 않게 한다.
    const depth = ((FIELD.rows - 1) / 2) * FIELD.gapZ;
    const stop = FIELD.gateZ[bar.stage] + 1.1 + (bar.z + depth) * 0.62;
    if (out.z < stop) {
      const flat = smoothstep(0, 2.4, stop - out.z);
      out.z = stop;
      out.height = lerp(bar.height, 0.05, flat);
      out.tint = -flat;
    }
  } else {
    // 끝까지 간 3건은 한 줄로 모여 계획 색이 된다
    const arrive = smoothstep(0.86, 0.98, p);
    out.x = lerp(bar.x, (bar.slot - 1) * 1.9, arrive);
    out.z = Math.max(lerp(out.z, FIELD.endZ, arrive), FIELD.endZ);
    out.height = lerp(bar.height, 3.1, arrive);
    out.tint = arrive;
  }
  return out;
}

/**
 * 원근 투영(정지 그림용). 돌려주는 x·y는 화면 중심이 0, 가장자리가 ±1이고 depth는 카메라 앞쪽 거리다.
 * 3D 장면의 카메라와 같은 화각·자리를 주면 같은 구도가 나온다.
 */
export function projector(eye: Vec3, target: Vec3, fovDegrees: number, aspect: number): (x: number, y: number, z: number) => { x: number; y: number; depth: number } {
  const f = [target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]];
  const fl = Math.hypot(f[0], f[1], f[2]);
  f[0] /= fl;
  f[1] /= fl;
  f[2] /= fl;
  // 오른쪽 = 앞 × 위(0,1,0), 위 = 오른쪽 × 앞
  const r = [-f[2], 0, f[0]];
  const rl = Math.hypot(r[0], r[2]);
  r[0] /= rl;
  r[2] /= rl;
  const u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
  const scale = 1 / Math.tan((fovDegrees * Math.PI) / 360);
  return (x, y, z) => {
    const dx = x - eye[0];
    const dy = y - eye[1];
    const dz = z - eye[2];
    const depth = dx * f[0] + dy * f[1] + dz * f[2];
    const cx = dx * r[0] + dy * r[1] + dz * r[2];
    const cy = dx * u[0] + dy * u[1] + dz * u[2];
    return { x: (cx * scale) / aspect / depth, y: (cy * scale) / depth, depth };
  };
}

/** 지금 장면에 서 있는 종목 수(멈춰서 절반 넘게 납작해진 것은 뺀다). 숫자판이 이 값을 보인다. */
export function standing(bars: readonly Bar[], progress: number): number {
  const state: BarState = { x: 0, z: 0, height: 0, tint: 0 };
  let count = 0;
  for (const bar of bars) if (barAt(bar, progress, state).tint > -0.5) count += 1;
  return count;
}

/** 끝까지 간 주문 계획 3건(장부 8734~8736번). 기둥이 서는 자리(slot) 순서대로 붙는 이름표다. */
export const PLANS: readonly { name: string; qty: number }[] = [
  { name: "하나마이크론", qty: 40 },
  { name: "HPSP", qty: 28 },
  { name: "LG전자", qty: 13 },
];

/**
 * 등장: 화면을 처음 열 때 한 번, 기둥이 바닥에서 올라온다(ms).
 * 카메라에 가까운 줄부터 시작하고, 뒤로 갈수록 시작 간격이 좁아져 한 번의 물결로 읽힌다.
 */
export const INTRO = { duration: 900, spread: 520 };

export function introScale(bar: Bar, elapsedMs: number): number {
  const depth = ((FIELD.rows - 1) / 2) * FIELD.gapZ;
  const width = ((FIELD.cols - 1) / 2) * FIELD.gapX;
  // 0: 카메라 쪽 앞줄 왼쪽, 1: 맨 뒷줄 오른쪽
  const order = Math.min(1, Math.max(0, ((depth - bar.z) / (depth * 2)) * 0.8 + ((bar.x + width) / (width * 2)) * 0.2));
  const delay = INTRO.spread * (1 - (1 - order) * (1 - order));
  const t = Math.min(1, Math.max(0, (elapsedMs - delay) / INTRO.duration));
  return 1 - (1 - t) ** 3;
}
