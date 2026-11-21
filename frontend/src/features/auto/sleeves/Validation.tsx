/** 검증: 바구니를 시작한 뒤 실제(가상) 운용 vs 기준선 두 가지, 그리고 과거 미리 보기. */

import { useState } from "react";
import { Button, Delta, Empty, ErrorState, Field, Notice, Panel, SkeletonRows, TD, TDR, TextInput, TH, THR, ToggleGroup } from "@/components/ui";
import { DataTableToggle, TimeChart, type Series } from "@/components/charts";
import { api, errorMessage } from "@/lib/api";
import { dayDots, num, pct, won, wonExact } from "@/lib/format";
import { notifyError } from "@/lib/queries";
import { usePerformance } from "./data";
import type { Comparison, Curve, Preview, SleevesOverview } from "./types";

const POLICY_TEXT = {
  book: "실제 운용",
  rules: "규칙만",
  dca: "단순 적립",
} as const;

function align(dates: string[], curve: { dates: string[]; equity: number[] } | undefined): (number | null)[] {
  if (!curve) return dates.map(() => null);
  const map = new Map(curve.dates.map((d, i) => [d, curve.equity[i]]));
  return dates.map((d) => map.get(d) ?? null);
}

function SummaryTable({ rows, caption }: { rows: { label: string; curve: Curve | undefined }[]; caption: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className={TH}>
              방식
            </th>
            <th scope="col" className={THR}>
              수익률
            </th>
            <th scope="col" className={THR}>
              최대 낙폭
            </th>
            <th scope="col" className={THR}>
              매수
            </th>
            <th scope="col" className={THR}>
              매도
            </th>
            <th scope="col" className={THR}>
              끝 평가금액
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, curve }) => (
            <tr key={label}>
              <th scope="row" className={`${TD} text-left font-medium`}>
                {label}
              </th>
              <td className={TDR}>{curve ? <Delta value={curve.summary.return_pct}>{pct(curve.summary.return_pct)}</Delta> : "–"}</td>
              <td className={TDR}>{curve?.summary.mdd_pct !== undefined ? pct(curve.summary.mdd_pct) : "–"}</td>
              <td className={TDR}>{curve?.summary.buys !== undefined ? `${num(curve.summary.buys)}회` : "–"}</td>
              <td className={TDR}>{curve?.summary.sells !== undefined ? `${num(curve.summary.sells)}회` : "–"}</td>
              <td className={TDR}>{curve && curve.equity.length ? won(curve.equity[curve.equity.length - 1]) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonChart({ cmp, amount, withBook }: { cmp: Comparison; amount: number; withBook: boolean }) {
  const dates = cmp.dca.dates;
  const series: Series[] = [];
  if (withBook && cmp.book) series.push({ name: POLICY_TEXT.book, color: "var(--data-1)", values: align(dates, cmp.book) });
  series.push({ name: POLICY_TEXT.rules, color: withBook ? "var(--ink-secondary)" : "var(--data-1)", values: align(dates, cmp.rules) });
  series.push({ name: POLICY_TEXT.dca, color: "var(--data-2)", dashed: true, values: align(dates, cmp.dca) });
  return (
    <>
      <TimeChart dates={dates} series={series} format={won} tickFormat={(v) => wonExact(v)} baseline={{ value: amount, label: "배정 금액" }}
        label={`${cmp.name} 바구니 평가금액 추이: ${series.map((s) => s.name).join(", ")}`} />
      <DataTableToggle>
        <div className="max-h-64 overflow-auto">
          <table className="w-full">
            <caption className="sr-only">{cmp.name} 날짜별 평가금액</caption>
            <thead>
              <tr>
                <th scope="col" className={TH}>
                  날짜
                </th>
                {series.map((s) => (
                  <th key={s.name} scope="col" className={THR}>
                    {s.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dates.map((d, i) => (
                <tr key={d}>
                  <td className={`${TD} num`}>{dayDots(d)}</td>
                  {series.map((s) => (
                    <td key={s.name} className={TDR}>
                      {s.values[i] === null ? "–" : won(s.values[i] as number)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataTableToggle>
    </>
  );
}

/** 과거 미리 보기 결과(저장 전 계획·지금 계획 공통). */
export function PreviewResult({ preview }: { preview: Preview }) {
  const kospiEnd = preview.kospi.value[preview.kospi.value.length - 1];
  return (
    <div className="mt-4 space-y-6">
      <p className="num text-body-sm text-ink-secondary">
        {dayDots(preview.start)} ~ {dayDots(preview.end)} · 같은 기간 코스피 <Delta value={kospiEnd}>{pct(kospiEnd)}</Delta>
      </p>
      {preview.sleeves.map((cmp) => {
        const amount = cmp.dca.equity[0] ?? 0;
        return (
          <section key={cmp.sleeve_id} aria-label={`${cmp.name} 미리 보기`} className="border-t border-divider pt-4">
            <h3 className="mb-2 text-h6 font-semibold text-ink">{cmp.name}</h3>
            <SummaryTable caption={`${cmp.name} 미리 보기 요약`} rows={[{ label: POLICY_TEXT.rules, curve: cmp.rules }, { label: POLICY_TEXT.dca, curve: cmp.dca }]} />
            <div className="mt-3">
              <ComparisonChart cmp={cmp} amount={amount} withBook={false} />
            </div>
          </section>
        );
      })}
      <p className="text-caption text-ink-muted">{preview.note}</p>
    </div>
  );
}

/** 바구니를 시작한 뒤의 검증과 지금 계획의 과거 미리 보기. */
export function ValidationPanel({ view }: { view: SleevesOverview }) {
  const sleeves = view.sleeves;
  const [picked, setPicked] = useState<string>(sleeves[0]?.id ?? "");
  const current = sleeves.find((s) => s.id === picked) ?? sleeves[0];
  const perf = usePerformance(current?.id ?? null);
  const [start, setStart] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);

  if (!current) return null;
  const runPreview = async () => {
    setBusy(true);
    try {
      setPreview(await api.post<Preview>("/api/sleeves/preview", { start }));
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const days = perf.data?.dca.dates.length ?? 0;
  return (
    <Panel title="검증: 실제 운용과 기준선">
      <p className="max-w-reading text-body-sm text-ink-secondary">
        같은 종목·같은 주기·같은 금액으로 <b className="font-semibold text-ink">규칙만</b>과 <b className="font-semibold text-ink">단순 적립</b>을 함께 계산합니다. 지금 판단 주체가 이 둘보다 나은지는 비용을 빼고 몇 주 이상 쌓인 뒤에 판단하세요.
      </p>
      {sleeves.length > 1 && (
        <div className="mt-3">
          <ToggleGroup label="비교할 바구니" value={current.id} onChange={setPicked} options={sleeves.map((s) => ({ value: s.id, label: s.name }))} />
        </div>
      )}
      <div className="mt-3">
        {perf.isPending ? (
          <SkeletonRows rows={4} label="비교를 계산하는 중" />
        ) : perf.isError ? (
          <ErrorState message={errorMessage(perf.error)} onRetry={() => void perf.refetch()} />
        ) : days < 2 ? (
          <Empty title="아직 비교할 날이 없습니다">
            {dayDots(perf.data.started_on ?? null)}에 시작했습니다. 장 마감 뒤 일봉이 하루씩 쌓이면 여기서 {current.mode === "paper" ? "실제 운용과 " : ""}두 기준선을 나란히 봅니다. 그 전에는 아래 과거 미리 보기로 확인하세요.
          </Empty>
        ) : (
          <>
            <SummaryTable
              caption={`${current.name} 시작 뒤 비교`}
              rows={[
                ...(current.mode === "paper" ? [{ label: `${POLICY_TEXT.book}(${current.decider_label})`, curve: perf.data.book }] : []),
                { label: POLICY_TEXT.rules, curve: perf.data.rules },
                { label: POLICY_TEXT.dca, curve: perf.data.dca },
              ]}
            />
            <div className="mt-3">
              <ComparisonChart cmp={perf.data} amount={current.amount} withBook={current.mode === "paper"} />
            </div>
            <p className="mt-2 text-caption text-ink-muted">
              {dayDots(perf.data.start)}부터 · 기준선은 지금 판 설정으로 계산 · {current.mode === "alert" ? "알림만 바구니는 가상 장부가 없어 기준선만 보입니다" : "실제 운용은 체결 기록으로 다시 계산"}
            </p>
          </>
        )}
      </div>

      <div className="mt-6 border-t border-divider pt-4">
        <h3 className="text-h6 font-semibold text-ink">지금 계획을 과거로 돌려 보기</h3>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <Field label="시작일" className="w-48">
            {(p) => <TextInput {...p} type="date" value={start} max={view.data_day ?? undefined} onChange={(e) => setStart(e.target.value)} className="num" />}
          </Field>
          <Button className="mb-5" busy={busy} disabled={busy || !start} onClick={() => void runPreview()}>
            과거로 돌려 보기
          </Button>
        </div>
        {preview ? <PreviewResult preview={preview} /> : <Notice>규칙과 단순 적립만 과거로 돌립니다. AI 판단은 과거 주가를 이미 알 수 있어 넣지 않습니다.</Notice>}
      </div>
    </Panel>
  );
}
