/**
 * 로그인 전 첫 화면(Brand 레이어). 제품이 하는 일을 실시간 3D 장면으로 보여 주고, 맨 아래에서 로그인한다.
 * 로그인한 뒤의 화면(Utility 레이어)에는 3D도 장식 모션도 없다.
 */

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { ArrowDown, Moon, Sun } from "lucide-react";
import { Button, cx } from "@/components/ui";
import { applyTheme, resolvedTheme, useThemeVersion } from "@/lib/theme";
import { LedgerTable } from "@/features/dashboard/Passbook";
import { chapterOpacity, CHAPTERS, field, FUNNEL, GATE_LABELS, PHASES, phaseAt, PLANS, smoothstep, standing } from "./funnel";
import type { Anchor, FunnelHandle } from "./FunnelScene";
import { FunnelStill } from "./FunnelStill";
import { DEMO } from "@/lib/api";
import { LEDGER_SAMPLE } from "./ledgerSample";

type Action = "login" | "setup" | "demo";
const ACTION_LABEL: Record<Action, string> = { login: "로그인", setup: "처음 등록", demo: "데모 보기" };
const HEADER_HEIGHT = 64;

export function Landing({ action, children }: { action: Action; children: ReactNode }) {
  const [pastHero, setPastHero] = useState(false);
  const hero = useRef<HTMLElement>(null);

  useEffect(() => {
    const check = () => {
      const bottom = hero.current?.getBoundingClientRect().bottom ?? 0;
      setPastHero(bottom < HEADER_HEIGHT);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, []);

  const goEnter = () => {
    const panel = document.getElementById("enter");
    if (!panel) return;
    panel.scrollIntoView({ block: "start" });
    panel.querySelector<HTMLElement>("input, button")?.focus({ preventScroll: true });
  };

  return (
    <div id="top" className="bg-canvas text-body text-ink">
      <header className={cx("fixed inset-x-0 top-0 z-(--z-sticky) border-b transition-colors duration-(--duration-base)", pastHero ? "border-divider bg-canvas" : "border-transparent")}>
        <div className="mx-auto flex h-16 max-w-wide items-center justify-between px-5 md:px-10">
          <a href="#top" className="rounded-xs text-h5 font-bold text-ink no-underline">
            AlphaPilot
          </a>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={goEnter}>
              {ACTION_LABEL[action]}
            </Button>
          </div>
        </div>
      </header>

      <main>
        <Hero sectionRef={hero} action={action} onEnter={goEnter} />
        <Ledger />
        <Product />
        <Rules />
        <Record />
        <Enter>{children}</Enter>
      </main>

      <footer className="border-t border-divider">
        <div className="mx-auto flex max-w-wide flex-col gap-2 px-5 py-8 text-label text-ink-muted md:flex-row md:items-baseline md:justify-between md:px-10">
          <p className="font-semibold text-ink-secondary">AlphaPilot · 국내 주식 자동매매 관제</p>
          <p className="max-w-reading">투자 판단과 손실의 책임은 사용자에게 있습니다. 지난 기록이 앞으로의 수익을 보장하지 않습니다.</p>
        </div>
      </footer>
    </div>
  );
}

function ThemeToggle() {
  useThemeVersion();
  const dark = resolvedTheme() === "dark";
  const Icon = dark ? Sun : Moon;
  return (
    <Button variant="ghost" size="icon" className="size-8" aria-label={dark ? "밝은 화면으로" : "어두운 화면으로"} onClick={() => applyTheme(dark ? "light" : "dark")}>
      <Icon aria-hidden className="size-4" />
    </Button>
  );
}

function useMedia(condition: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(condition).matches);
  useEffect(() => {
    const query = window.matchMedia(condition);
    const update = () => setMatches(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, [condition]);
  return matches;
}

function useBox(ref: RefObject<HTMLElement | null>): { width: number; height: number } {
  const [box, setBox] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setBox({ width: el.clientWidth, height: el.clientHeight }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return box;
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

/** 첫 화면: 살펴본 종목이 관문 셋을 지나 주문 계획으로 걸러지는 과정(표본은 143종목 → 3건). 스크롤이 장면을 앞으로 보낸다. */
function Hero({ sectionRef, action, onEnter }: { sectionRef: RefObject<HTMLElement | null>; action: Action; onEnter: () => void }) {
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)");
  // 화면이 아주 낮으면(가로로 눕힌 휴대폰) 고정한 무대에 글이 다 들어가지 않으므로 고정하지 않는다
  const short = useMedia("(max-height: 560px)");
  const reduced = reducedMotion || short;
  const [webgl, setWebgl] = useState<"pending" | "live" | "none">("pending");
  /** 정지 구도 + 단계 목록으로 보여 주는 경우: 모션 줄이기를 켰거나, 화면이 아주 낮거나, WebGL2를 쓸 수 없을 때 */
  const fixed = reduced || webgl === "none";
  const visual = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const handle = useRef<FunnelHandle | null>(null);
  const blocks = useRef<(HTMLDivElement | null)[]>([]);
  const labels = useRef<(HTMLSpanElement | null)[]>([]);
  const planLabels = useRef<(HTMLSpanElement | null)[]>([]);
  const intro = useRef<HTMLDivElement>(null);
  const counter = useRef<HTMLDivElement>(null);
  const count = useRef<HTMLSpanElement>(null);
  const [phase, setPhase] = useState(0);
  const box = useBox(visual);
  const theme = useThemeVersion();

  const progress = () => {
    const el = sectionRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    const span = rect.height - window.innerHeight;
    return span > 0 ? clamp01(-rect.top / span) : 0;
  };

  // 3D 묶음은 따로 내려받는다. 그동안과 WebGL2가 없을 때는 같은 구도의 정지 그림이 보인다.
  useEffect(() => {
    let cancelled = false;
    let mounted: FunnelHandle | null = null;
    const place = (anchors: Anchor[], plans: Anchor[]) => {
      plans.forEach((a, i) => {
        const el = planLabels.current[i];
        if (!el) return;
        el.style.transform = `translate(${a.x.toFixed(1)}px, ${a.y.toFixed(1)}px) translate(-50%, -100%)`;
        el.style.opacity = a.visible ? "1" : "0";
      });
      // 이름표끼리 겹치면 카메라에 가까운 관문의 것만 남긴다
      const shown = anchors.map((a) => a.visible && a.y > HEADER_HEIGHT - 8);
      anchors.forEach((a, i) => {
        if (shown[i] && anchors.some((b, j) => j !== i && shown[j] && b.distance < a.distance && Math.abs(b.y - a.y) < 26 && Math.abs(b.x - a.x) < 150)) shown[i] = false;
        // 주문 계획 이름표(종목 이름)와 겹치면 관문 이름표가 물러난다
        if (shown[i] && plans.some((b) => b.visible && Math.abs(b.y - a.y) < 48 && Math.abs(b.x - a.x) < 150)) shown[i] = false;
      });
      anchors.forEach((a, i) => {
        const el = labels.current[i];
        if (!el) return;
        // 관문 위쪽에 자리가 있으면 테두리 위에, 머리띠에 가리면 테두리 안쪽에 둔다
        const above = a.y - 28 > HEADER_HEIGHT;
        el.style.transform = `translate(${a.x.toFixed(1)}px, ${a.y.toFixed(1)}px) translate(-50%, ${above ? "-100%" : "0"})`;
        el.style.opacity = shown[i] ? "1" : "0";
      });
    };
    import("./FunnelScene")
      .then(async (scene) => {
        if (cancelled || !canvas.current) return;
        if (!scene.supportsWebGL2()) {
          setWebgl("none");
          return;
        }
        // 맨 위에서 열었을 때만 등장을 보인다(스크롤한 채 새로 고치면 그 자리의 장면이 바로 나온다)
        const next = await scene.mountFunnel(canvas.current, { still: reduced, intro: progress() < 0.02, onAnchors: place });
        if (cancelled) {
          next.dispose();
          return;
        }
        mounted = next;
        handle.current = next;
        next.setProgress(progress());
        setWebgl("live");
      })
      .catch(() => {
        if (!cancelled) setWebgl("none");
      });
    return () => {
      cancelled = true;
      mounted?.dispose();
      handle.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced]);

  // 스크롤 진행률 하나가 장면과 글을 함께 움직인다
  useEffect(() => {
    if (fixed) return;
    let frame = 0;
    const bars = field();
    const apply = () => {
      frame = 0;
      const p = progress();
      handle.current?.setProgress(p);
      blocks.current.forEach((el, i) => {
        if (!el) return;
        const opacity = chapterOpacity(CHAPTERS[i], p);
        el.style.opacity = opacity.toFixed(3);
        el.style.transform = `translateY(${((1 - opacity) * 8).toFixed(1)}px)`;
      });
      // 첫 장의 안내글·단추가 먼저 물러나고, 그 자리에 숫자판이 들어온다(둘이 겹쳐 보이는 순간이 없게 차례로)
      const first = 1 - smoothstep(0.12, 0.17, p);
      if (intro.current) {
        intro.current.style.opacity = first.toFixed(3);
        intro.current.inert = first < 0.05; // 보이지 않는 단추에 포커스가 가지 않게
      }
      if (counter.current) counter.current.style.opacity = smoothstep(0.17, 0.22, p).toFixed(3);
      if (count.current) count.current.textContent = String(standing(bars, p));
      setPhase(phaseAt(p));
    };
    const request = () => {
      if (!frame) frame = requestAnimationFrame(apply);
    };
    apply();
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", request);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", request);
      window.removeEventListener("resize", request);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fixed]);

  // 화면 밖에서는 그리지 않는다
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => handle.current?.setRunning(entry.isIntersecting));
    observer.observe(el);
    return () => observer.disconnect();
  }, [sectionRef, webgl]);

  useEffect(() => {
    handle.current?.refreshColors();
  }, [theme]);

  return (
    <section ref={sectionRef} data-scene={webgl} aria-labelledby="hero-title" className="relative" style={fixed ? undefined : { height: "400vh" }}>
      <div className={cx("flex flex-col overflow-hidden", fixed ? "min-h-svh" : "sticky top-0 h-svh")}>
        <div ref={visual} className="relative min-h-72 flex-1">
          <canvas ref={canvas} aria-hidden className={cx("absolute inset-0 size-full", webgl !== "live" && "invisible")} />
          {webgl !== "live" && (
            <div className="absolute inset-0">
              <FunnelStill width={box.width} height={box.height} view={fixed ? "overview" : "start"} />
            </div>
          )}
          {webgl === "live" && (
            <div aria-hidden className="pointer-events-none absolute inset-0">
              {GATE_LABELS.map((label, i) => (
                <span
                  key={label}
                  ref={(el) => {
                    labels.current[i] = el;
                  }}
                  className="absolute top-0 left-0 py-2 text-label font-medium whitespace-nowrap text-ink-secondary opacity-0 transition-opacity duration-(--duration-base) will-change-transform"
                >
                  <span className="stamp mr-2 text-ink-muted">{String(i + 1).padStart(2, "0")}</span>
                  {label}
                </span>
              ))}
              {PLANS.map((plan, i) => (
                <span
                  key={plan.name}
                  ref={(el) => {
                    planLabels.current[i] = el;
                  }}
                  className="absolute top-0 left-0 pb-3 text-center whitespace-nowrap opacity-0 transition-opacity duration-(--duration-base) will-change-transform"
                >
                  <span className="block text-body-sm font-semibold text-ink">{plan.name}</span>
                  <span className="num block text-label text-ink-secondary">매수 {plan.qty}주</span>
                </span>
              ))}
            </div>
          )}
          {/* 장면의 아래 가장자리를 바탕색으로 풀어 글이 놓이는 띠와 잇는다 */}
          <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-linear-to-t from-canvas to-transparent" />
        </div>

        <div className="relative bg-canvas">
          <div className="mx-auto grid max-w-wide gap-x-6 gap-y-5 px-5 pb-8 md:px-10 lg:grid-cols-12 lg:items-end lg:pb-12">
            <div className="grid items-end lg:col-span-7 [&>*]:col-start-1 [&>*]:row-start-1">
              <div
                ref={(el) => {
                  blocks.current[0] = el;
                }}
              >
                <h1 id="hero-title" className="enter-rise max-w-[16em] text-display font-bold text-ink [--enter-distance:12px]">
                  사기 전에 세 번 걸러내는 국내 주식 자동매매
                </h1>
              </div>
              {!fixed &&
                CHAPTERS.slice(1).map((chapter, i) => (
                  <div
                    key={chapter.label}
                    ref={(el) => {
                      blocks.current[i + 1] = el;
                    }}
                    className="pointer-events-none opacity-0"
                  >
                    <h2 className="text-h1 font-bold text-ink">
                      <span className="sr-only">
                        {chapter.count}
                        {chapter.unit}:{" "}
                      </span>
                      {chapter.title}
                    </h2>
                    <p className="mt-3 max-w-reading text-body-lg text-ink-secondary">{chapter.body}</p>
                  </div>
                ))}
            </div>
            <div className="grid items-end lg:col-span-4 lg:col-start-9 [&>*]:col-start-1 [&>*]:row-start-1">
              <div ref={intro}>
                <p className="enter-rise text-body-lg text-ink-secondary [--enter-delay:110ms] [--enter-distance:8px]">매일 장이 끝나면 종목을 살펴 기법 조건, 위원회 심의, 리스크 점검으로 걸러냅니다. 남은 주문 계획만 내 승인을 기다립니다.</p>
                <div className="enter-rise mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 [--enter-delay:190ms] [--enter-distance:6px]">
                  <Button variant="primary" size="lg" onClick={onEnter}>
                    {ACTION_LABEL[action]}
                  </Button>
                  {!fixed && (
                    <p className="flex items-center gap-1 text-label text-ink-muted">
                      <ArrowDown aria-hidden className="size-4" />
                      스크롤하면 과정이 이어집니다
                    </p>
                  )}
                </div>
              </div>
              {!fixed && (
                <div ref={counter} className="pointer-events-none opacity-0">
                  <Counter phase={phase} countRef={count} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {fixed && (
        <div className="mx-auto max-w-wide px-5 pb-16 md:px-10">
          <ol className="grid gap-x-6 gap-y-8 border-t border-ink pt-6 sm:grid-cols-2 lg:grid-cols-4">
            {CHAPTERS.map((chapter) => (
              <li key={chapter.label}>
                <p className="num font-mono text-h2 font-medium text-ink">
                  {chapter.count}
                  <span className="ml-1 font-sans text-h5 font-semibold">{chapter.unit}</span>
                </p>
                <h2 className="mt-2 text-h5 font-semibold text-ink">{chapter.title}</h2>
                <p className="mt-1 text-body-sm text-ink-secondary">{chapter.body}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-caption text-ink-muted">{FUNNEL.source}</p>
        </div>
      )}
    </section>
  );
}

/** 지금 장면에 서 있는 종목 수. 스크롤을 따라 143에서 3까지 줄어든다(숫자는 스크롤 처리에서 직접 고쳐 쓴다). */
function Counter({ phase, countRef }: { phase: number; countRef: RefObject<HTMLSpanElement | null> }) {
  const now = PHASES[phase];
  return (
    <div>
      <p className="flex items-baseline gap-2">
        <span ref={countRef} className="num font-mono text-h2 font-medium text-ink lg:text-display">
          {FUNNEL.counts[0]}
        </span>
        <span className="text-h5 font-semibold text-ink lg:text-h4">{now.unit}</span>
        <span className="ml-1 text-body-sm font-medium text-ink-secondary lg:text-body">{now.label}</span>
      </p>
      <ol aria-hidden className="mt-3 grid grid-cols-4 gap-1">
        {CHAPTERS.map((c, i) => (
          <li key={c.label} className={cx("h-0.5 transition-colors duration-(--duration-base)", i < now.step ? "bg-ink" : "bg-divider")} />
        ))}
      </ol>
      <p className="mt-2 text-caption text-ink-muted">{FUNNEL.source}</p>
    </div>
  );
}

const SECTION = "mx-auto max-w-wide px-5 py-20 md:px-10 lg:py-28";

/** 3D 장면이 보여 준 수가 실제 장부의 어느 줄인지. 제품의 장부 표를 그대로 쓰고, 줄은 시뮬레이션 기록 그대로다. */
function Ledger() {
  return (
    <section aria-labelledby="ledger-title" className="border-t border-divider">
      <div className={cx(SECTION, "grid items-start gap-x-6 gap-y-10 lg:grid-cols-12")}>
        <div className="lg:col-span-4">
          <h2 id="ledger-title" className="text-h1 font-bold text-ink">
            {FUNNEL.sample ? "방금 본 장면은 장부의 한 줄입니다" : "걸러진 하루는 장부에 이렇게 남습니다"}
          </h2>
          <p className="mt-5 max-w-reading text-body text-ink-secondary">
            {/* 장면이 최신 거래일을 보여 주는 날에는 아래 표본이 다른 날(10월 2일)의 것임을 밝힌다 */}
            {FUNNEL.sample ? "8737번 줄이 그날의 심의입니다." : "주문 계획이 나온 2026년 10월 2일의 예입니다. 8737번 줄이 그날의 심의입니다."} 신호 38종목, 심의 6종목, 매수안 3건. 그 아래로 주문 계획 세 건이, 위로 내가 두 건을 승인하고 한 건을 거절한 것과 다음 거래일의 체결이 이어집니다.
          </p>
          <p className="mt-4 text-caption text-ink-muted">2026년 10월 2일~6일 시뮬레이션 장부 8734~8742번</p>
        </div>
        <div className="overflow-hidden rounded-lg border border-divider bg-surface text-body-sm lg:col-span-8">
          <LedgerTable rows={LEDGER_SAMPLE} followChains={false} />
        </div>
      </div>
    </section>
  );
}

function Product() {
  useThemeVersion();
  const tone = resolvedTheme() === "dark" ? "dark" : "light";
  return (
    <section aria-labelledby="product-title" className="border-t border-divider">
      <div className={cx(SECTION, "grid items-center gap-x-6 gap-y-10 lg:grid-cols-12")}>
        <div className="lg:col-span-4">
          <h2 id="product-title" className="text-h1 font-bold text-ink">
            걸러진 결과는 관제 화면 한 장에 모입니다
          </h2>
          <dl className="mt-8 divide-y divide-divider border-y border-divider">
            {[
              ["승인 대기", "주문 계획마다 수량과 근거를 보고 승인하거나 거절합니다."],
              ["장부", "산 것, 판 것, 사지 않은 이유까지 번호를 매겨 남깁니다. 지우거나 고칠 수 없습니다."],
              ["판단 사슬", "거래번호를 누르면 그 종목이 거친 단계를 처음부터 따라갑니다."],
            ].map(([term, text]) => (
              <div key={term} className="grid grid-cols-[6.5em_1fr] gap-x-4 py-4">
                <dt className="text-body-sm font-semibold text-ink">{term}</dt>
                <dd className="m-0 text-body-sm text-ink-secondary">{text}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="lg:col-span-8">
          <picture className="block overflow-hidden rounded-lg border border-divider bg-surface">
            <source media="(max-width: 767px)" srcSet={`${import.meta.env.BASE_URL}landing/console-mobile-${tone}.webp`} width={750} height={1100} />
            <img
              src={`${import.meta.env.BASE_URL}landing/console-desktop-${tone}.webp`}
              width={2160}
              height={1350}
              loading="lazy"
              decoding="async"
              alt="관제 화면: 오늘 판정, 승인을 기다리는 주문 계획, 보유 종목, 장부가 한 화면에 있다. 시뮬레이션 데이터로 찍었다."
              className="block h-auto w-full"
            />
          </picture>
        </div>
      </div>
    </section>
  );
}

const RULES = [
  "AI가 답하지 못한 날은 신규 매수를 모두 보류합니다.",
  "리스크 점검은 수량을 줄이거나 막기만 합니다. 늘리지 못합니다.",
  "손절과 손실 차단은 AI를 거치지 않고 정해 둔 값에서 실행됩니다.",
  "서버가 다시 켜지면 내가 확인할 때까지 주문을 내지 않습니다.",
];

function Rules() {
  return (
    <section aria-labelledby="rules-title" className="bg-surface-inverse text-ink-inverse">
      <div className={cx(SECTION, "grid gap-x-6 gap-y-10 lg:grid-cols-12")}>
        <h2 id="rules-title" className="text-display font-bold lg:col-span-6">
          AI가 답하지 못하면 사지 않습니다
        </h2>
        <ol className="lg:col-span-5 lg:col-start-8">
          {RULES.map((rule, i) => (
            <li key={rule} className="grid grid-cols-[3em_1fr] items-baseline border-t border-ink-inverse/25 py-5 last:border-b">
              <span aria-hidden className="stamp text-ink-inverse/70">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-body-lg font-medium">{rule}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Record() {
  return (
    <section aria-labelledby="record-title">
      <div className={cx(SECTION, "grid gap-x-6 gap-y-10 lg:grid-cols-12")}>
        <div className="lg:col-span-5">
          <h2 id="record-title" className="text-h1 font-bold text-ink">
            수익률은 코스피보다 낮았고, 낙폭은 4분의 1이었습니다
          </h2>
          <p className="mt-5 max-w-reading text-body-sm text-ink-secondary">
            143종목을 2024년 8월 9일부터 2026년 11월 13일까지 기본 규칙으로 돌린 백테스트입니다. 조정하지 않은 측정값이고, 지금 상장된 종목만으로 돌려서 실제는 이보다 나쁠 수 있습니다.
          </p>
        </div>
        <div className="lg:col-span-6 lg:col-start-7">
          <table className="w-full text-left">
            <caption className="sr-only">기본 규칙과 코스피의 같은 기간 수익률과 최대 낙폭</caption>
            <thead>
              <tr className="border-b border-ink text-label text-ink-secondary">
                <td className="py-3" />
                <th scope="col" className="py-3 text-right font-semibold">
                  기본 규칙
                </th>
                <th scope="col" className="py-3 text-right font-semibold">
                  코스피
                </th>
              </tr>
            </thead>
            <tbody className="num font-mono text-h3 font-medium text-ink md:text-h1">
              <tr className="border-b border-divider">
                <th scope="row" className="py-5 font-sans text-body-sm font-semibold text-ink-secondary">
                  수익률
                </th>
                <td className="py-5 text-right">+19.3%</td>
                <td className="py-5 text-right">+104.4%</td>
              </tr>
              <tr className="border-b border-divider">
                <th scope="row" className="py-5 font-sans text-body-sm font-semibold text-ink-secondary">
                  최대 낙폭
                </th>
                <td className="py-5 text-right">−10.5%</td>
                <td className="py-5 text-right">−44.9%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Enter({ children }: { children: ReactNode }) {
  return (
    <section aria-labelledby="enter-title" className="border-t border-divider bg-surface-sunken">
      <div className={cx(SECTION, "grid items-start gap-x-6 gap-y-10 lg:grid-cols-12")}>
        <div className="lg:col-span-6">
          <h2 id="enter-title" className="text-h1 font-bold text-ink">
            {DEMO ? "저장해 둔 예시로 둘러봅니다" : "한 사람이 쓰는 서버입니다"}
          </h2>
          {DEMO ? (
            <ul className="mt-6 max-w-reading space-y-3 text-body text-ink-secondary">
              <li>이 페이지는 개인 프로젝트의 공개 데모입니다. 서버·증권 계좌와 연결되지 않고, 미리 저장한 예시 데이터만 보여 줍니다.</li>
              <li>아무 정보도 입력받지 않습니다. 실제로 쓰려면 내 PC에 설치해 실행합니다.</li>
            </ul>
          ) : (
            <ul className="mt-6 max-w-reading space-y-3 text-body text-ink-secondary">
              <li>비밀번호와 인증 앱의 6자리 코드가 둘 다 있어야 들어옵니다.</li>
              <li>지금은 지난 일봉으로 가상 계좌를 굴리는 시뮬레이션만 주문합니다. 키움 모의투자·실전 주문 실행은 아직 없습니다.</li>
            </ul>
          )}
        </div>
        <div id="enter" className="scroll-mt-24 rounded-lg border border-divider bg-surface p-6 text-body-sm lg:col-span-5 lg:col-start-8">
          {children}
        </div>
      </div>
    </section>
  );
}
