/** 일봉 차트(lightweight-charts). 상승 봉은 빨강, 하락 봉은 파랑. 계획 가격은 보라 점선, 손절은 위험색 점선으로 긋는다. */

import { CandlestickSeries, ColorType, createChart, HistogramSeries, LineSeries, LineStyle, type IChartApi, type Time } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { Delta } from "@/components/ui";
import { dayDots, num, pct } from "@/lib/format";
import { cssVar, useThemeVersion } from "@/lib/theme";
import { isHalted, readout, type Bar } from "./candle";

export type { Bar };

export interface PriceLine {
  price: number;
  title: string;
  tone: "plan" | "danger" | "ok" | "ink";
}

interface Props {
  bars: Bar[];
  overlays: { sma20: (number | null)[]; sma50: (number | null)[]; sma200: (number | null)[] };
  lines?: PriceLine[];
  height?: number;
  label: string;
}

const MA = [
  { key: "sma20", name: "20일선", token: "--data-1" },
  { key: "sma50", name: "50일선", token: "--ink-muted" },
  { key: "sma200", name: "200일선", token: "--data-2" },
] as const;

const LINE_TOKEN: Record<PriceLine["tone"], string> = { plan: "--accent", danger: "--danger", ok: "--success", ink: "--ink-muted" };

export function CandleChart({ bars, overlays, lines = [], height = 400, label }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const theme = useThemeVersion();
  /** 십자선이 가리키는 봉의 위치. 없으면 마지막 봉을 읽는다. */
  const [focus, setFocus] = useState<number | null>(null);
  const shown = bars.length > 0 ? readout(bars, overlays, focus ?? bars.length - 1) : null;

  useEffect(() => {
    const node = ref.current;
    if (!node || bars.length === 0) return;
    const up = cssVar("--up-solid");
    const down = cssVar("--down-solid");
    const chart: IChartApi = createChart(node, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: cssVar("--ink-muted"), fontFamily: getComputedStyle(document.body).fontFamily, fontSize: 12 },
      grid: { vertLines: { visible: false }, horzLines: { color: cssVar("--divider") } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, rightOffset: 3, fixLeftEdge: true },
      crosshair: { vertLine: { color: cssVar("--ink-muted"), labelBackgroundColor: cssVar("--ink-secondary") }, horzLine: { color: cssVar("--ink-muted"), labelBackgroundColor: cssVar("--ink-secondary") } },
      localization: { locale: "ko-KR", priceFormatter: (price: number) => Math.round(price).toLocaleString("ko-KR"), dateFormat: "yyyy.MM.dd" },
    });

    const candles = chart.addSeries(CandlestickSeries, { upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false, priceLineVisible: false, lastValueVisible: false });
    // 거래정지일(거래 없이 값이 멈춘 날)은 오른 날·내린 날과 다른 회색으로 긋는다
    const halt = cssVar("--data-2");
    candles.setData(bars.map((b) => ({ time: b.d as Time, open: b.o, high: b.h, low: b.l, close: b.c, ...(isHalted(b) ? { color: halt, wickColor: halt } : {}) })));

    const volume = chart.addSeries(HistogramSeries, { priceScaleId: "", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    volume.setData(bars.map((b, i) => ({ time: b.d as Time, value: b.v, color: `${i > 0 && b.c < bars[i - 1].c ? down : up}59` })));

    for (const ma of MA) {
      const series = chart.addSeries(LineSeries, { color: cssVar(ma.token), lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      series.setData(bars.flatMap((b, i) => (overlays[ma.key][i] === null || overlays[ma.key][i] === undefined ? [] : [{ time: b.d as Time, value: overlays[ma.key][i] as number }])));
    }
    const last = bars[bars.length - 1];
    candles.createPriceLine({ price: last.c, color: cssVar("--ink-muted"), lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "" });
    for (const line of lines) {
      candles.createPriceLine({ price: line.price, color: cssVar(LINE_TOKEN[line.tone]), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: line.title });
    }

    const byDay = new Map(bars.map((b, i) => [b.d, i]));
    chart.subscribeCrosshairMove((param) => {
      const time = param.time;
      setFocus(typeof time === "string" ? (byDay.get(time) ?? null) : null);
    });
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 130), to: bars.length + 2 });

    return () => chart.remove();
    // lines는 내용이 같으면 다시 그릴 필요가 없어 글자열로 비교한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, overlays, theme, JSON.stringify(lines)]);

  return (
    <figure className="m-0">
      <figcaption className="num mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-ink-secondary">
        {shown && (
          <span>
            <span className="font-semibold text-ink">{dayDots(shown.bar.d)}</span> 시 {num(shown.bar.o)} · 고 {num(shown.bar.h)} · 저 {num(shown.bar.l)} · 종 <span className="font-semibold text-ink">{num(shown.bar.c)}</span>
            {shown.change !== null && (
              <>
                {" "}
                <Delta value={shown.change}>
                  {num(Math.abs(shown.change))} ({pct(shown.changePct)})
                </Delta>
              </>
            )}
            {" · "}
            {shown.halted ? <span className="font-semibold text-ink">거래정지(거래 없음)</span> : <>거래량 {num(shown.bar.v)}</>}
          </span>
        )}
        <span className="flex flex-wrap gap-x-3">
          {MA.map((ma) => (
            <span key={ma.key} className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-0.5 w-4" style={{ background: `var(${ma.token})` }} />
              {ma.name}
              {shown && <span className="text-ink">{shown.sma[ma.key] === null ? "–" : num(shown.sma[ma.key])}</span>}
            </span>
          ))}
        </span>
      </figcaption>
      <div ref={ref} role="img" aria-label={label} style={{ height }} />
    </figure>
  );
}
