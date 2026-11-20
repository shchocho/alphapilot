import { describe, expect, it } from "vitest";
import { LEDGER_SAMPLE } from "./ledgerSample";
import { barAt, CAMERA, CHAPTERS, chapterOpacity, chapters, fates, FIELD, field, FUNNEL, INTRO, introScale, normalize, PHASES, phaseAt, PLANS, projector, seeded, smoothstep, standing, travelAt } from "./funnel";

describe("걸러지는 수", () => {
  it("관문마다 남는 수가 기록과 같다", () => {
    const f = fates();
    expect(f).toHaveLength(143);
    expect(f.filter((s) => s >= 1)).toHaveLength(38);
    expect(f.filter((s) => s >= 2)).toHaveLength(6);
    expect(f.filter((s) => s === 3)).toHaveLength(3);
  });
  it("같은 씨앗이면 같은 종목이 통과한다(새로 고쳐도 장면이 같다)", () => {
    expect(fates()).toEqual(fates());
    expect(fates(FUNNEL.counts, 1)).not.toEqual(fates(FUNNEL.counts, 2));
    const a = seeded(7);
    const b = seeded(7);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
  it("장의 숫자는 걸러지는 수와 같은 순서다", () => {
    expect(CHAPTERS.map((c) => c.count)).toEqual([...FUNNEL.counts]);
  });
});

describe("스크롤에 따른 장 표시", () => {
  it("구간 안에서는 다 보이고 멀어지면 사라진다", () => {
    const second = CHAPTERS[1];
    expect(chapterOpacity(second, (second.from + second.to) / 2)).toBe(1);
    expect(chapterOpacity(second, second.from - 0.2)).toBe(0);
    expect(chapterOpacity(second, second.to + 0.2)).toBe(0);
  });
  it("첫 장은 처음부터, 마지막 장은 끝까지 보인다", () => {
    expect(chapterOpacity(CHAPTERS[0], 0)).toBe(1);
    expect(chapterOpacity(CHAPTERS[3], 1)).toBe(1);
  });
  it("어느 위치에서도 두 장이 함께 다 보이지 않는다(글이 겹치지 않게)", () => {
    for (let p = 0; p <= 1.0001; p += 0.01) {
      const full = CHAPTERS.filter((c) => chapterOpacity(c, p) > 0.6);
      expect(full.length).toBeLessThanOrEqual(1);
    }
  });
  it("smoothstep은 양 끝에서 0과 1", () => {
    expect(smoothstep(0, 1, -1)).toBe(0);
    expect(smoothstep(0, 1, 0.5)).toBe(0.5);
    expect(smoothstep(0, 1, 2)).toBe(1);
  });
});

describe("장면 배치(3D와 정지 그림이 함께 쓰는 값)", () => {
  it("종목은 143개이고 끝까지 가는 3건만 자리 번호를 받는다", () => {
    const bars = field();
    expect(bars).toHaveLength(143);
    expect(bars.filter((b) => b.slot >= 0).map((b) => b.slot).sort()).toEqual([0, 1, 2]);
    expect(field()).toEqual(bars);
  });
  it("처음에는 모두 제자리에 서 있다", () => {
    for (const bar of field()) {
      const s = barAt(bar, 0);
      expect(s.z).toBe(bar.z);
      expect(s.height).toBe(bar.height);
      expect(s.tint).toBe(0);
    }
  });
  it("끝에서는 멈춘 종목이 자기 관문 앞에 납작하게 남는다", () => {
    for (const bar of field().filter((b) => b.stage < 3)) {
      const s = barAt(bar, 1);
      const gate = FIELD.gateZ[bar.stage];
      expect(s.z).toBeGreaterThan(gate);
      expect(s.z).toBeLessThan(bar.stage === 0 ? 0 : FIELD.gateZ[bar.stage - 1]);
      expect(s.height).toBeLessThan(0.1);
      expect(s.tint).toBe(-1);
    }
  });
  it("끝까지 간 3건은 마지막 관문 뒤에 한 줄로 서고 계획 색이 된다", () => {
    const done = field().filter((b) => b.stage === 3).map((b) => barAt(b, 1));
    expect(done).toHaveLength(3);
    for (const s of done) {
      expect(s.z).toBe(FIELD.endZ);
      expect(s.tint).toBe(1);
    }
    expect(new Set(done.map((s) => s.x)).size).toBe(3);
  });
  it("장의 글이 보이는 동안 장면은 그 관문까지만 걸러진 상태다(다음 관문은 아직 시작하지 않는다)", () => {
    const bars = field();
    for (const gate of [1, 2]) {
      const chapter = CHAPTERS[gate];
      for (const p of [chapter.from, (chapter.from + chapter.to) / 2, chapter.to]) {
        const passed = bars.filter((b) => b.stage >= gate).map((b) => barAt(b, p));
        expect(passed).toHaveLength(CHAPTERS[gate].count);
        for (const s of passed) {
          expect(s.z).toBeLessThan(FIELD.gateZ[gate - 1]);
          expect(s.z).toBeGreaterThan(FIELD.gateZ[gate]);
          expect(s.tint).toBe(0);
        }
        for (const b of bars.filter((x) => x.stage < gate)) expect(barAt(b, p).tint).toBe(-1);
      }
    }
  });
  it("앞으로 나아가는 거리는 뒤로 가지 않는다", () => {
    expect(travelAt(0)).toBe(0);
    expect(travelAt(1)).toBe(FIELD.travel);
    for (let p = 0.01, last = 0; p <= 1; p += 0.01) {
      expect(travelAt(p)).toBeGreaterThanOrEqual(last);
      last = travelAt(p);
    }
  });
  it("숫자판은 지금 서 있는 종목 수를 센다: 장마다 기록의 수와 같고, 늘어나지 않는다", () => {
    const bars = field();
    CHAPTERS.forEach((chapter) => expect(standing(bars, (chapter.from + chapter.to) / 2)).toBe(chapter.count));
    for (let p = 0, last = 143; p <= 1.0001; p += 0.005) {
      const now = standing(bars, p);
      expect(now).toBeLessThanOrEqual(last);
      last = now;
    }
  });
  it("숫자판의 이름은 걸러지는 중과 끝난 뒤를 구분한다", () => {
    expect(PHASES[phaseAt(0)].label).toBe("살펴본 종목");
    expect(PHASES[phaseAt(0.2)].label).toBe("기법 조건 확인 중");
    CHAPTERS.forEach((chapter) => {
      const phase = PHASES[phaseAt((chapter.from + chapter.to) / 2)];
      expect(phase.label).toBe(chapter.label);
      expect(phase.unit).toBe(chapter.unit);
    });
    expect(PHASES.map((ph) => ph.step)).toEqual([1, 1, 2, 2, 3, 3, 4]);
  });
});

describe("투영(정지 그림용)", () => {
  const view = projector([0, 5, 10], [0, 0, 0], 40, 1.5);
  it("바라보는 점은 화면 한가운데", () => {
    const c = view(0, 0, 0);
    expect(c.x).toBeCloseTo(0, 6);
    expect(c.y).toBeCloseTo(0, 6);
    expect(c.depth).toBeCloseTo(Math.hypot(5, 10), 6);
  });
  it("오른쪽·위에 있는 점은 오른쪽·위로, 뒤에 있는 점은 깊이가 음수", () => {
    expect(view(2, 0, 0).x).toBeGreaterThan(0);
    expect(view(0, 2, 0).y).toBeGreaterThan(0);
    expect(view(0, 10, 20).depth).toBeLessThan(0);
  });
  it("세로 화면은 화각을 넓힌다", () => {
    expect(CAMERA.fov(0.6)).toBeGreaterThan(CAMERA.fov(1.6));
  });
});

describe("등장(처음 한 번, 기둥이 바닥에서 올라온다)", () => {
  const bars = field();
  const end = INTRO.duration + INTRO.spread;
  it("시작에는 모두 바닥에 있고, 끝나면 모두 제 높이다", () => {
    for (const bar of bars) {
      expect(introScale(bar, 0)).toBe(0);
      expect(introScale(bar, end)).toBe(1);
      expect(introScale(bar, end * 3)).toBe(1);
    }
  });
  it("시간이 가면 낮아지지 않는다", () => {
    for (const bar of bars.slice(0, 20)) {
      for (let t = 0, last = 0; t <= end; t += 40) {
        const now = introScale(bar, t);
        expect(now).toBeGreaterThanOrEqual(last);
        last = now;
      }
    }
  });
  it("카메라에 가까운 줄이 먼저 올라오고, 한꺼번에 똑같이 올라오지 않는다", () => {
    const front = bars.reduce((a, b) => (b.z > a.z ? b : a));
    const back = bars.reduce((a, b) => (b.z < a.z ? b : a));
    expect(introScale(front, 300)).toBeGreaterThan(introScale(back, 300));
    expect(new Set(bars.map((b) => introScale(b, 400).toFixed(2))).size).toBeGreaterThan(8);
  });
});

describe("매일 바뀌는 수(공개 데모는 최신 거래일을 보여 준다)", () => {
  it("주문 계획이 없는 날: 끝까지 가는 종목이 없고 숫자판이 장마다 그날의 수와 같다", () => {
    const counts = [143, 22, 0, 0];
    const bars = field(counts, 20261117);
    expect(bars.filter((b) => b.slot >= 0)).toHaveLength(0);
    const story = chapters(counts);
    story.forEach((chapter) => expect(standing(bars, (chapter.from + chapter.to) / 2)).toBe(chapter.count));
    expect(story[2].title).toBe("위원회에 올라간 종목이 없습니다");
    expect(story[3].title).toBe("이날은 주문 계획이 없습니다");
    expect(new Set(story.map((chapter) => chapter.label)).size).toBe(4); // 화면의 목록 key로 쓴다(수는 0이 겹칠 수 있다)
  });
  it("주문 계획이 많은 날에도 관문 너비 안에 한 줄로 선다", () => {
    const xs = field([143, 40, 8, 8], 1).filter((b) => b.stage === 3).map((b) => barAt(b, 1).x);
    expect(new Set(xs).size).toBe(8);
    expect(Math.max(...xs.map(Math.abs))).toBeLessThan(FIELD.gateWidth / 2);
  });
  it("받은 수를 다듬는다: 뒤 단계가 앞 단계를 넘지 않고, 주문 계획 수는 이름표 수와 같다", () => {
    const plan = { name: "가", qty: 1 };
    expect(normalize({ day: "2026-11-17", counts: [143, 22, 30, 9], plans: [plan] }).counts).toEqual([143, 22, 22, 1]);
    expect(normalize({ day: "2026-11-17", counts: [143, 22, 0, 0], plans: [plan] })).toEqual({ day: "2026-11-17", counts: [143, 22, 0, 0], plans: [] });
  });
});

describe("주문 계획 이름표", () => {
  it("장부 표본의 주문 계획 3건과 이름·수량이 같다", () => {
    const intents = LEDGER_SAMPLE.filter((row) => row.kind === "intent");
    expect(intents).toHaveLength(FUNNEL.counts[3]);
    expect([...PLANS].map((plan) => `${plan.name} ${plan.qty}`).sort()).toEqual(intents.map((row) => `${row.name} ${row.qty}`).sort());
  });
  it("장부 표본의 장후 심의 줄이 장면의 수(38 → 6 → 3)와 같다", () => {
    const cycle = LEDGER_SAMPLE.find((row) => row.kind === "cycle");
    expect(cycle?.summary).toContain(`신호 ${FUNNEL.counts[1]}종목 → 심의 ${FUNNEL.counts[2]} → 매수안 ${FUNNEL.counts[3]}`);
  });
});
