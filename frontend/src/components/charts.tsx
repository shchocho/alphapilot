/** SVG 차트: 추이선(십자선 + 값 표시), 손익 막대, 스파크라인. 색은 토큰만 쓴다. */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { monthTicks, niceScale, textWidth } from "@/lib/chartmath";
import { dayDots } from "@/lib/format";
import { cx, DisclosureIcon, SUMMARY } from "./ui";

export function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => setWidth(Math.round(entries[0]?.contentRect.width ?? 0)));
    observer.observe(node);
    setWidth(Math.round(node.getBoundingClientRect().width));
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export interface Series {
  name: string;
  color: string; // CSS 색(예: "var(--data-1)")
  values: (number | null)[];
  dashed?: boolean;
  area?: boolean; // 0부터 값까지 옅게 채운다(낙폭)
}

interface TimeChartProps {
  dates: string[];
  series: Series[];
  /** 값 표시(십자선 옆 상자). 반올림하지 않은 값을 적는다. */
  format: (value: number) => string;
  /** 축 눈금 글자. step은 눈금 간격이다(그 배수를 반올림 없이 적을 자릿수를 정하는 데 쓴다). 없으면 format을 쓴다. */
  tickFormat?: (value: number, step: number) => string;
  /** 기준선(예: 시작 금액). 축 범위에 포함되고 이름표가 붙는다. */
  baseline?: { value: number; label: string };
  height?: number;
  label: string; // 화면 낭독기용 설명
  zeroBased?: boolean;
  legend?: boolean;
}

const PAD = { top: 12, right: 12, bottom: 24 };

export function TimeChart({ dates, series, format, tickFormat, baseline, height = 240, label, zeroBased = false, legend = true }: TimeChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = dates.length;

  const geometry = useMemo(() => {
    const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v)));
    if (all.length === 0 || width === 0) return null;
    let min = Math.min(...all);
    let max = Math.max(...all);
    if (zeroBased) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    if (baseline) {
      min = Math.min(min, baseline.value);
      max = Math.max(max, baseline.value);
    }
    const innerH = height - PAD.top - PAD.bottom;
    // 축의 양 끝은 눈금 간격의 배수다: 모든 값이 가장 아래 눈금과 가장 위 눈금 사이에 놓여 읽을 수 있다
    const { lo, hi, step, ticks } = niceScale(min, max, Math.max(2, Math.round(innerH / 44)));
    const tickText = ticks.map((t) => (tickFormat ? tickFormat(t, step) : format(t)));
    const left = Math.max(32, ...tickText.map(textWidth)) + 12;
    const innerW = Math.max(10, width - left - PAD.right);
    const x = (i: number) => left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
    const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * innerH;
    return { x, y, lo, hi, left, innerW, innerH, ticks, tickText };
    // format·tickFormat은 호출할 때마다 새 함수라 의존성에 넣지 않는다(눈금 값이 같으면 글자도 같다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, width, height, n, zeroBased, baseline?.value]);

  const paths = useMemo(() => {
    if (!geometry) return [];
    return series.map((s) => {
      let d = "";
      let pen = false;
      let first = -1;
      let last = -1;
      s.values.forEach((v, i) => {
        if (v === null || !Number.isFinite(v)) {
          pen = false;
          return;
        }
        d += `${pen ? "L" : "M"}${geometry.x(i).toFixed(1)},${geometry.y(v).toFixed(1)}`;
        pen = true;
        if (first < 0) first = i;
        last = i;
      });
      const area = s.area && first >= 0 ? `${d}L${geometry.x(last).toFixed(1)},${geometry.y(0).toFixed(1)}L${geometry.x(first).toFixed(1)},${geometry.y(0).toFixed(1)}Z` : "";
      return { d, area };
    });
  }, [geometry, series]);

  const onMove = (clientX: number, target: SVGSVGElement) => {
    if (!geometry || n === 0) return;
    const rect = target.getBoundingClientRect();
    const ratio = (clientX - rect.left - geometry.left) / geometry.innerW;
    setHover(Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1)))));
  };

  const lastValue = series[0]?.values.findLast((v): v is number => v !== null && Number.isFinite(v));
  const baselineBelow = baseline !== undefined && lastValue !== undefined && lastValue >= baseline.value;
  // 날짜 눈금: 달이 바뀌는 첫 거래일. 너비에 들어갈 만큼만 고른다
  const dateTicks = useMemo(() => (geometry ? monthTicks(dates, Math.max(2, Math.floor(geometry.innerW / 80))) : []), [dates, geometry]);

  return (
    <figure className="m-0">
      {legend && series.length > 1 && (
        <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-label text-ink-secondary">
          {series.map((s) => (
            <li key={s.name} className="flex items-center gap-2">
              <svg aria-hidden width="18" height="8">
                <line x1="0" y1="4" x2="18" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "4 3" : undefined} />
              </svg>
              {s.name}
            </li>
          ))}
        </ul>
      )}
      <div ref={ref} className="relative" style={{ height }}>
        {geometry && (
          <svg
            role="img"
            aria-label={label}
            width={width}
            height={height}
            className="block touch-pan-y"
            onPointerMove={(e) => onMove(e.clientX, e.currentTarget)}
            onPointerDown={(e) => onMove(e.clientX, e.currentTarget)}
            onPointerLeave={() => setHover(null)}
          >
            {geometry.ticks.map((t, k) => (
              <g key={t}>
                <line x1={geometry.left} x2={width - PAD.right} y1={geometry.y(t)} y2={geometry.y(t)} stroke="var(--divider)" strokeWidth="1" />
                <text x={geometry.left - 8} y={geometry.y(t)} textAnchor="end" dominantBaseline="middle" className="num fill-ink-muted text-caption">
                  {geometry.tickText[k]}
                </text>
              </g>
            ))}
            {dateTicks.map((tick) => {
              const tx = geometry.x(tick.index);
              const half = textWidth(tick.label) / 2;
              const anchor = tx - half < geometry.left ? "start" : tx + half > width - PAD.right ? "end" : "middle";
              return (
                <g key={tick.index}>
                  <line x1={tx} x2={tx} y1={PAD.top} y2={height - PAD.bottom + 4} stroke="var(--divider)" strokeWidth="1" />
                  <text x={tx} y={height - 6} textAnchor={anchor} className="num fill-ink-muted text-caption">
                    {tick.label}
                  </text>
                </g>
              );
            })}
            {baseline && (
              <g>
                <line x1={geometry.left} x2={width - PAD.right} y1={geometry.y(baseline.value)} y2={geometry.y(baseline.value)} stroke="var(--ink-muted)" strokeWidth="1" strokeDasharray="2 3" />
                {/* 이름표는 선이 지나가지 않는 쪽에 둔다: 마지막 값이 기준선 위에 있으면 아래에, 아니면 위에 */}
                <text x={width - PAD.right} y={geometry.y(baseline.value) + (baselineBelow ? 14 : -5)} textAnchor="end" className="num fill-ink-muted text-caption">
                  {baseline.label}
                </text>
              </g>
            )}
            {series.map((s, i) => (
              <g key={s.name}>
                {paths[i]?.area && <path d={paths[i].area} fill={s.color} opacity="0.16" />}
                <path d={paths[i]?.d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.dashed ? "5 4" : undefined} />
              </g>
            ))}
            {hover !== null && (
              <g pointerEvents="none">
                <line x1={geometry.x(hover)} x2={geometry.x(hover)} y1={PAD.top} y2={height - PAD.bottom} stroke="var(--ink-muted)" strokeWidth="1" />
                {series.map((s) => {
                  const v = s.values[hover];
                  return v === null || v === undefined ? null : (
                    <circle key={s.name} cx={geometry.x(hover)} cy={geometry.y(v)} r="4.5" fill={s.color} stroke="var(--surface)" strokeWidth="2" />
                  );
                })}
              </g>
            )}
          </svg>
        )}
        {geometry && hover !== null && (
          <div
            className="pointer-events-none absolute top-1 z-(--z-dropdown) min-w-36 rounded-lg bg-surface-raised px-3 py-2 text-label shadow-2"
            style={geometry.x(hover) > width / 2 ? { right: width - geometry.x(hover) + 10 } : { left: geometry.x(hover) + 10 }}
          >
            <div className="num mb-1 font-semibold text-ink">{dayDots(dates[hover])}</div>
            {series.map((s) => (
              <div key={s.name} className="flex items-center justify-between gap-3 text-ink-secondary">
                <span className="flex items-center gap-2">
                  <span aria-hidden className="inline-block size-2 rounded-full" style={{ background: s.color }} />
                  {s.name}
                </span>
                <span className="num font-semibold text-ink">{s.values[hover] === null || s.values[hover] === undefined ? "–" : format(s.values[hover] as number)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </figure>
  );
}

/** 날짜별 손익 막대. 이익은 빨강, 손실은 파랑이고 기준선(0)에 붙는다. */
export function PnlBars({ data, format, tickFormat, height = 180, label }: { data: { d: string; value: number }[]; format: (v: number) => string; tickFormat?: (v: number, step: number) => string; height?: number; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  // 0을 포함하고, 가장 큰 이익·손실이 눈금 안에 들어오게 한다
  const { lo, hi, step, ticks } = niceScale(Math.min(0, ...data.map((p) => p.value)), Math.max(0, ...data.map((p) => p.value), data.some((p) => p.value !== 0) ? 0 : 1), 4);
  const tickText = ticks.map((t) => (tickFormat ? tickFormat(t, step) : format(t)));
  const pad = { top: 10, right: 8, bottom: 22, left: Math.max(32, ...tickText.map(textWidth)) + 12 };
  const innerW = Math.max(10, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const y = (v: number) => pad.top + (1 - (v - lo) / (hi - lo || 1)) * innerH;
  const band = innerW / Math.max(1, data.length);
  const barW = Math.max(2, Math.min(18, band - 2));

  return (
    <div ref={ref} className="relative" style={{ height }}>
      {width > 0 && (
        <svg role="img" aria-label={label} width={width} height={height} className="block" onPointerLeave={() => setHover(null)}>
          {ticks.map((t, k) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--ink-muted)" : "var(--divider)"} strokeWidth="1" />
              <text x={pad.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle" className="num fill-ink-muted text-caption">
                {tickText[k]}
              </text>
            </g>
          ))}
          {data.map((p, i) => {
            const x = pad.left + i * band + (band - barW) / 2;
            const top = Math.min(y(p.value), y(0));
            const h = Math.max(1, Math.abs(y(p.value) - y(0)));
            return (
              <g key={p.d} onPointerEnter={() => setHover(i)} onPointerDown={() => setHover(i)}>
                <rect x={pad.left + i * band} y={pad.top} width={band} height={innerH} fill="transparent" />
                <rect x={x} y={top} width={barW} height={h} rx={Math.min(3, barW / 2)} fill={p.value >= 0 ? "var(--up-solid)" : "var(--down-solid)"} opacity={hover === null || hover === i ? 1 : 0.55} />
              </g>
            );
          })}
          {data.length > 0 && (
            <>
              <text x={pad.left} y={height - 5} className="num fill-ink-muted text-caption">
                {dayDots(data[0].d)}
              </text>
              <text x={width - pad.right} y={height - 5} textAnchor="end" className="num fill-ink-muted text-caption">
                {dayDots(data[data.length - 1].d)}
              </text>
            </>
          )}
        </svg>
      )}
      {hover !== null && data[hover] && (
        <div
          className="pointer-events-none absolute top-1 z-(--z-dropdown) rounded-lg bg-surface-raised px-3 py-2 text-label shadow-2"
          style={pad.left + hover * band > width / 2 ? { right: width - (pad.left + hover * band) + 6 } : { left: pad.left + (hover + 1) * band + 6 }}
        >
          <div className="num text-ink-secondary">{dayDots(data[hover].d)}</div>
          <div className={cx("num font-semibold", data[hover].value > 0 ? "text-up" : data[hover].value < 0 ? "text-down" : "text-ink")}>{format(data[hover].value)}</div>
        </div>
      )}
    </div>
  );
}

/** 표 안의 작은 추이선(장식). 방향은 옆의 등락률 글자가 전한다. */
export function Sparkline({ values, width = 88, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="inline-block" style={{ width, height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => `${((i / (values.length - 1)) * (width - 2) + 1).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg aria-hidden width={width} height={height} className="block">
      <polyline points={points} fill="none" stroke={up ? "var(--up-solid)" : "var(--down-solid)"} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** 차트 아래에 같은 수치를 표로 펼쳐 볼 수 있게 한다. */
export function DataTableToggle({ summary = "표로 보기", children }: { summary?: string; children: ReactNode }) {
  return (
    <details className="group/disclosure mt-2 text-body-sm">
      <summary className={SUMMARY}>
        <DisclosureIcon />
        {summary}
      </summary>
      <div className="mt-1 max-h-64 overflow-auto rounded-md border border-divider">{children}</div>
    </details>
  );
}
