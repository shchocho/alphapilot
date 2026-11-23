/** 백테스트: 가정을 먼저 적고, 같은 기간 코스피와 나란히 놓는다. 좋은 숫자만 크게 보여주지 않는다. */

import { useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { TimeChart } from "@/components/charts";
import { Button, Check, cx, Delta, DisclosureIcon, Empty, ErrorState, Field, Notice, PageHeader, Panel, Select, SkeletonRows, TD, TDR, TextInput, TH, THR } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { stepDigits } from "@/lib/chartmath";
import { dayDots, num, pct, won, wonExact, wonShort, wonSigned } from "@/lib/format";
import { DATA_SOURCE, FILL_REASON } from "@/lib/labels";
import { notifyError, queryClient, useBacktest, useBacktests, useSettings } from "@/lib/queries";
import type { BacktestResult, SettingsView } from "@/lib/types";

export default function BacktestPage() {
  const [params, setParams] = useSearchParams();
  const runs = useBacktests();
  const settings = useSettings();
  const selected = params.get("run") ?? runs.data?.runs[0]?.id ?? null;
  const result = useBacktest(selected);
  const select = (id: string) => setParams({ run: id }, { replace: true });

  return (
    <div>
      <PageHeader
        title="백테스트"
        lead="같은 규칙을 지난 일봉에 그대로 적용해 봅니다. 과거에 통했다고 앞으로도 통한다는 뜻은 아닙니다."
        actions={
          runs.data && runs.data.runs.length > 0 ? (
            <Select aria-label="지난 실행 고르기" value={selected ?? ""} onChange={(e) => select(e.target.value)} className="num w-80 max-w-full">
              {runs.data.runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {dayDots(run.start)}~{dayDots(run.end)} · {run.total_return !== null ? pct(run.total_return, 1) : "–"} · {run.created_at.slice(5, 16).replace("T", " ")} 실행
                </option>
              ))}
            </Select>
          ) : undefined
        }
      />
      <div className="space-y-4">
        {settings.data && runs.data && <RunForm view={settings.data} onDone={select} startOpen={runs.data.runs.length === 0} />}
        {runs.isPending || (selected && result.isPending) ? (
          <SkeletonRows rows={6} label="백테스트 결과를 불러오는 중" />
        ) : result.isError ? (
          <ErrorState message={errorMessage(result.error)} onRetry={() => void result.refetch()} />
        ) : result.data ? (
          <ResultView r={result.data} view={settings.data} />
        ) : (
          <Panel>
            <Empty title="아직 돌려 본 백테스트가 없습니다">위에서 기간과 기법을 정하고 실행하세요. 종목 수와 기간에 따라 수십 초 걸릴 수 있습니다.</Empty>
          </Panel>
        )}
      </div>
    </div>
  );
}

// ── 실행 ────────────────────────────────────────────────────────────────

function RunForm({ view, onDone, startOpen }: { view: SettingsView; onDone: (id: string) => void; startOpen: boolean }) {
  const [open, setOpen] = useState(startOpen);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [cash, setCash] = useState(String(view.engine.sim_initial_cash));
  const [candidates, setCandidates] = useState(String(view.engine.max_candidates));
  const [techniques, setTechniques] = useState<string[]>(view.engine.enabled_techniques);
  const [busy, setBusy] = useState(false);
  const cashValue = Number(cash.replace(/\D/g, ""));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.post<BacktestResult>("/api/backtests", {
        start: start || null,
        end: end || null,
        initial_cash: cashValue,
        techniques,
        max_candidates: Math.max(1, Math.min(30, Number(candidates) || 8)),
      });
      queryClient.setQueryData(["backtest", result.id], result);
      await queryClient.invalidateQueries({ queryKey: ["backtests"] });
      toast.success(`백테스트를 마쳤습니다(${result.elapsed_sec.toFixed(0)}초)`);
      setOpen(false);
      onDone(result.id);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="group/disclosure rounded-lg border border-divider bg-surface" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-lg px-4 text-h6 font-semibold text-ink transition-colors duration-(--duration-fast) hover:bg-surface-sunken [&::-webkit-details-marker]:hidden">
        <DisclosureIcon className="text-ink-secondary" />
        새 백테스트 돌리기
      </summary>
      <form onSubmit={submit} className="border-t border-divider p-4">
        <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="시작일" hint="비우면 일봉이 충분해지는 첫날부터">
            {(p) => <TextInput {...p} type="date" value={start} max={end || view.data.day || undefined} onChange={(e) => setStart(e.target.value)} className="num" />}
          </Field>
          <Field label="종료일" hint={view.data.day ? `비우면 ${dayDots(view.data.day)}까지` : "비우면 가장 최근 일봉까지"}>
            {(p) => <TextInput {...p} type="date" value={end} min={start || undefined} max={view.data.day ?? undefined} onChange={(e) => setEnd(e.target.value)} className="num" />}
          </Field>
          <Field label="시작 자금(원)" error={cashValue < 1_000_000 ? "100만 원 이상이어야 합니다" : null}>
            {(p) => <TextInput {...p} inputMode="numeric" value={num(cashValue)} onChange={(e) => setCash(e.target.value)} className="num" />}
          </Field>
          <Field label="하루 최대 후보 수" hint="1~30">
            {(p) => <TextInput {...p} inputMode="numeric" value={candidates} onChange={(e) => setCandidates(e.target.value.replace(/\D/g, "").slice(0, 2))} className="num" />}
          </Field>
        </div>
        <fieldset className="mt-2">
          <legend className="text-body-sm font-semibold text-ink">쓸 진입 기법</legend>
          <div className="grid gap-x-6 sm:grid-cols-2 xl:grid-cols-3">
            {view.options.techniques.map((t) => (
              <Check
                key={t.key}
                checked={techniques.includes(t.key)}
                onChange={(e) => setTechniques((prev) => (e.target.checked ? [...prev, t.key] : prev.filter((k) => k !== t.key)))}
                label={t.name}
                hint={`보유 ${t.holding}`}
              />
            ))}
          </div>
        </fieldset>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" busy={busy} disabled={techniques.length === 0 || cashValue < 1_000_000}>
            백테스트 실행
          </Button>
          <p role="status" className="text-body-sm text-ink-secondary">
            {busy ? "돌리는 중입니다. 20초쯤 걸립니다." : "판단은 규칙 위원회로 합니다(AI 비용 없음). 지금 설정한 리스크 한도와 수수료·세금을 그대로 씁니다."}
          </p>
        </div>
      </form>
    </details>
  );
}

// ── 결과 ────────────────────────────────────────────────────────────────

function ResultView({ r, view }: { r: BacktestResult; view: SettingsView | undefined }) {
  const s = r.summary;
  const costs = r.params.costs;
  const techniqueName = (key: string) => view?.options.techniques.find((t) => t.key === key)?.name ?? key;
  const sells = useMemo(() => r.trades.filter((t) => t.side === "sell").reverse(), [r.trades]);
  const rejected = useMemo(() => [...r.rejected].reverse(), [r.rejected]);
  const [sellLimit, setSellLimit] = useState(15);
  const [rejectLimit, setRejectLimit] = useState(8);

  return (
    <>
      <section className="rounded-lg border border-divider bg-surface p-4" aria-labelledby="assumptions-title">
        <h2 id="assumptions-title" className="text-h6 font-bold text-ink">
          이 결과가 깔고 있는 가정
        </h2>
        <ul className="num mt-2 grid gap-x-8 gap-y-1 text-body-sm text-ink-secondary md:grid-cols-2">
          <li>
            기간 {dayDots(r.start)}~{dayDots(r.end)} ({num(s.days)}거래일) · 시작 자금 {won(r.initial_cash)}
          </li>
          <li>
            종목 {num(r.params.universe)}개 · {DATA_SOURCE[r.params.data_source] ?? r.params.data_source}
          </li>
          <li>그날 종가로 판단하고 다음 거래일에 체결 (미래 가격을 미리 보지 않음)</li>
          <li>
            수수료 {pct(costs.commission_rate, 3, false)} · 매도세 {pct(costs.sell_tax_rate, 2, false)} · 체결 오차 {pct(costs.slippage_rate, 2, false)}
          </li>
          <li>판단은 규칙 위원회 · 기법 {r.params.techniques.map(techniqueName).join(", ")}</li>
          <li>코스피 비교는 같은 날 같은 금액을 지수에 넣었다고 가정</li>
        </ul>
        <div className="mt-3 space-y-2">
          <Notice tone="warning">
            지금 상장돼 있는 종목만으로 돌렸습니다. 그 사이 상장폐지되거나 크게 무너져 빠진 종목의 손실은 들어 있지 않아, 실제 성과는 이보다 나쁠 수 있습니다.
          </Notice>
          {!s.trades.enough_trades && (
            <Notice tone="warning">
              끝난 거래가 {num(s.trades.trades)}건뿐이라 표본이 적습니다. 승률과 손익비는 우연의 영향이 큽니다.
            </Notice>
          )}
          {r.halted_on && (
            <Notice tone="danger">
              {dayDots(r.halted_on)}에 낙폭 한도에 닿아 엔진이 정지했습니다. 그 뒤로는 새 매수를 하지 않은 결과입니다.
            </Notice>
          )}
        </div>
      </section>

      <Panel title="코스피와 나란히" bodyClassName="">
        <table className="w-full">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                항목
              </th>
              <th scope="col" className={THR}>
                이 전략
              </th>
              <th scope="col" className={THR}>
                코스피
              </th>
              <th scope="col" className={THR}>
                차이
              </th>
            </tr>
          </thead>
          <tbody>
            <CompareRow label="총수익률" mine={s.total_return} bench={s.benchmark.total_return} />
            <CompareRow label="연평균 수익률" mine={s.cagr} bench={s.benchmark.cagr} />
            <CompareRow label="가장 크게 빠진 폭" mine={s.max_drawdown.pct} bench={s.benchmark.max_drawdown} />
            <tr>
              <th scope="row" className={cx(TD, "text-left font-normal")}>
                위험 대비 수익(샤프)
              </th>
              <td className={cx(TDR, "font-semibold")}>{s.sharpe.toFixed(2)}</td>
              <td className={TDR}>{s.benchmark.sharpe.toFixed(2)}</td>
              <td className={TDR}>{(s.sharpe - s.benchmark.sharpe >= 0 ? "+" : "−") + Math.abs(s.sharpe - s.benchmark.sharpe).toFixed(2)}</td>
            </tr>
          </tbody>
        </table>
        <p className="num border-t border-divider px-3 py-3 text-label text-ink-muted">
          평균 투자 비중 {pct(s.avg_exposure, 0, false)} · 연 변동성 {pct(s.volatility, 1, false)} · 소르티노 {s.sortino.toFixed(2)}
          {s.max_drawdown.peak && s.max_drawdown.trough && (
            <>
              {" "}
              · 가장 크게 빠진 구간 {dayDots(s.max_drawdown.peak)}~{dayDots(s.max_drawdown.trough)}
              {s.max_drawdown.recovered ? `, ${dayDots(s.max_drawdown.recovered)}에 회복` : ", 아직 회복하지 못함"}
            </>
          )}
          {" "}· 끝날 때 보유 {s.open_positions}종목, 현금 {wonShort(s.final_cash)}
        </p>
      </Panel>

      <Panel title="자산 추이와 낙폭">
        <TimeChart
          dates={r.curve.map((c) => c.d)}
          series={[
            { name: "이 전략", color: "var(--data-1)", values: r.curve.map((c) => c.equity) },
            { name: "코스피에 같은 금액", color: "var(--data-2)", values: r.curve.map((c) => c.benchmark), dashed: true },
          ]}
          format={(v) => won(v)}
          tickFormat={(v) => wonExact(v)}
          baseline={{ value: r.initial_cash, label: `시작 ${wonExact(r.initial_cash)}` }}
          height={260}
          label={`${dayDots(r.start)}부터 ${dayDots(r.end)}까지 전략과 코스피의 평가 금액. 전략 ${pct(s.total_return, 1)}, 코스피 ${pct(s.benchmark.total_return, 1)}.`}
        />
        <h3 className="mt-4 mb-1 text-body-sm font-semibold text-ink">고점 대비 낙폭</h3>
        <TimeChart
          dates={r.curve.map((c) => c.d)}
          series={[{ name: "전략 낙폭", color: "var(--down-solid)", values: r.curve.map((c) => c.drawdown), area: true }]}
          format={(v) => pct(v, 2)}
          tickFormat={(v, step) => pct(v, stepDigits(step * 100))}
          height={130}
          zeroBased
          legend={false}
          label={`전략의 고점 대비 낙폭. 가장 깊은 곳 ${pct(s.max_drawdown.pct, 1)}.`}
        />
      </Panel>

      <MonthlyTable monthly={r.monthly} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="거래 통계">
          {s.trades.trades === 0 ? (
            <p className="text-body-sm text-ink-secondary">이 기간에는 끝난 거래가 없습니다.</p>
          ) : (
            <>
              <dl className="num grid grid-cols-2 gap-x-6 gap-y-2 text-body-sm sm:grid-cols-3">
                {[
                  ["끝난 거래", `${num(s.trades.trades)}건`],
                  ["이익 본 비율", pct(s.trades.win_rate, 0, false)],
                  ["이익 합 ÷ 손실 합", s.trades.profit_factor !== null ? s.trades.profit_factor.toFixed(2) : "손실 없음"],
                  ["평균 이익 ÷ 평균 손실", s.trades.payoff_ratio !== null ? s.trades.payoff_ratio.toFixed(2) : "손실 없음"],
                  ["평균 보유", `${s.trades.avg_hold_days.toFixed(1)}일`],
                  ["가장 좋은·나쁜 거래", `${pct(s.trades.best_pct, 1)} / ${pct(s.trades.worst_pct, 1)}`],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-label text-ink-muted">{label}</dt>
                    <dd className="font-semibold text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
              <h3 className="mt-4 mb-1 text-body-sm font-semibold text-ink">기법별</h3>
              <table className="w-full">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      기법
                    </th>
                    <th scope="col" className={THR}>
                      거래
                    </th>
                    <th scope="col" className={THR}>
                      이익 본 거래
                    </th>
                    <th scope="col" className={THR}>
                      손익 합
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(s.trades.by_technique).map(([key, v]) => (
                    <tr key={key}>
                      <td className={TD}>{techniqueName(key)}</td>
                      <td className={TDR}>{num(v.trades)}</td>
                      <td className={TDR}>
                        {num(v.wins)} ({v.trades ? pct(v.wins / v.trades, 0, false) : "–"})
                      </td>
                      <td className={TDR}>
                        <Delta value={v.pnl}>{wonSigned(v.pnl)}</Delta>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3 className="mt-4 mb-1 text-body-sm font-semibold text-ink">어떻게 팔았나</h3>
              <p className="num text-body-sm text-ink-secondary">
                {Object.entries(s.trades.by_reason)
                  .map(([reason, count]) => `${FILL_REASON[reason] ?? reason} ${num(count)}건`)
                  .join(" · ")}
              </p>
            </>
          )}
        </Panel>

        <Panel title={<span className="num">사지 않은 후보 {num(r.rejected_total)}건</span>} bodyClassName="">
          {r.rejected.length === 0 ? (
            <p className="p-4 text-body-sm text-ink-secondary">걸러진 후보가 없습니다.</p>
          ) : (
            <div>
              <table className="w-full">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      날짜
                    </th>
                    <th scope="col" className={TH}>
                      종목
                    </th>
                    <th scope="col" className={TH}>
                      이유
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rejected.slice(0, rejectLimit).map((x, i) => (
                    <tr key={`${x.day}-${x.code}-${i}`} className="align-top">
                      <td className={cx(TD, "num whitespace-nowrap")}>{dayDots(x.day)}</td>
                      <td className={cx(TD, "whitespace-nowrap")}>{x.name ?? ""}</td>
                      <td className={cx(TD, "num text-ink-secondary")}>
                        <span className="font-semibold text-ink">{x.stage}</span> · {x.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(rejected.length > rejectLimit || r.rejected_total > r.rejected.length) && (
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2">
              <p className="num text-label text-ink-muted">
                {num(Math.min(rejectLimit, rejected.length))}건 표시{r.rejected_total > r.rejected.length && <> · 가장 최근 {num(r.rejected.length)}건까지만 보관합니다</>}
              </p>
              {rejected.length > rejectLimit && (
                <Button size="sm" onClick={() => setRejectLimit((v) => v + 40)}>
                  더 보기
                </Button>
              )}
            </div>
          )}
        </Panel>
      </div>

      <Panel title={<span className="num">판 거래 {num(sells.length)}건</span>} bodyClassName="">
        {sells.length === 0 ? (
          <Empty title="판 거래가 없습니다" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-160">
              <thead>
                <tr>
                  <th scope="col" className={TH}>
                    판 날
                  </th>
                  <th scope="col" className={TH}>
                    종목
                  </th>
                  <th scope="col" className={TH}>
                    기법 · 판 이유
                  </th>
                  <th scope="col" className={THR}>
                    보유
                  </th>
                  <th scope="col" className={THR}>
                    손익
                  </th>
                </tr>
              </thead>
              <tbody>
                {sells.slice(0, sellLimit).map((t, i) => (
                  <tr key={`${t.day}-${t.code}-${i}`}>
                    <td className={cx(TD, "num whitespace-nowrap")}>{dayDots(t.day)}</td>
                    <td className={cx(TD, "whitespace-nowrap")}>
                      <Link to={`/stocks/${t.code}`} className="text-ink no-underline hover:underline">
                        {t.name}
                      </Link>
                    </td>
                    <td className={cx(TD, "text-ink-secondary")}>
                      {techniqueName(t.technique)} · {FILL_REASON[t.reason] ?? t.reason}
                    </td>
                    <td className={TDR}>{t.hold_days !== null ? `${t.hold_days}일` : ""}</td>
                    <td className={TDR}>
                      {t.pnl !== null && (
                        <Delta value={t.pnl}>
                          {wonSigned(t.pnl)}
                          {t.pnl_pct !== null && <> ({pct(t.pnl_pct, 1)})</>}
                        </Delta>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sells.length > sellLimit && (
              <div className="flex items-center justify-between gap-3 px-4 py-2">
                <p className="num text-label text-ink-muted">
                  최근 {num(sellLimit)}건 표시 · 전체 {num(sells.length)}건
                </p>
                <Button size="sm" onClick={() => setSellLimit((v) => v + 50)}>
                  더 보기
                </Button>
              </div>
            )}
          </div>
        )}
      </Panel>
    </>
  );
}

function CompareRow({ label, mine, bench }: { label: string; mine: number; bench: number }) {
  const gap = mine - bench;
  return (
    <tr>
      <th scope="row" className={cx(TD, "text-left font-normal")}>
        {label}
      </th>
      <td className={cx(TDR, "font-semibold")}>{pct(mine, 1)}</td>
      <td className={TDR}>{pct(bench, 1)}</td>
      <td className={TDR}>
        {gap >= 0 ? "+" : "−"}
        {Math.abs(gap * 100).toFixed(1)}%p
      </td>
    </tr>
  );
}

/** 달마다의 수익률. 오른 달은 빨강, 내린 달은 파랑이 짙어지고 0 근처는 무채색이다. 숫자는 항상 먹색으로 적는다. */
function MonthlyTable({ monthly }: { monthly: BacktestResult["monthly"] }) {
  if (monthly.length === 0) return null;
  const years = [...new Set(monthly.map((m) => m.year))].sort();
  const cell = (year: number, month: number) => monthly.find((m) => m.year === year && m.month === month);
  const shade = (ret: number): string => {
    const strength = Math.min(1, Math.abs(ret) / 0.1);
    if (strength < 0.05) return "var(--surface-sunken)";
    return `color-mix(in srgb, var(${ret > 0 ? "--up-solid" : "--down-solid"}) ${Math.round(10 + strength * 34)}%, var(--surface))`;
  };
  return (
    <Panel title="달마다의 수익률" bodyClassName="overflow-x-auto p-4">
      <table className="w-full min-w-200 border-separate border-spacing-1 whitespace-nowrap">
        <caption className="sr-only">연도와 달별 전략 수익률(%)</caption>
        <thead>
          <tr>
            <th scope="col" className="px-1 py-1 text-left text-label font-semibold text-ink-muted">
              연도
            </th>
            {Array.from({ length: 12 }, (_, i) => (
              <th key={i} scope="col" className="num px-1 py-1 text-right text-label font-semibold text-ink-muted">
                {i + 1}월
              </th>
            ))}
            <th scope="col" className="px-1 py-1 text-right text-label font-semibold text-ink-muted">
              한 해
            </th>
          </tr>
        </thead>
        <tbody>
          {years.map((year) => {
            const total = monthly.filter((m) => m.year === year).reduce((acc, m) => acc * (1 + m.ret), 1) - 1;
            return (
              <tr key={year}>
                <th scope="row" className="num px-1 py-1 text-left text-body-sm font-semibold text-ink">
                  {year}
                </th>
                {Array.from({ length: 12 }, (_, i) => {
                  const m = cell(year, i + 1);
                  return m ? (
                    <td key={i} className="num rounded-xs px-2 py-2 text-right text-body-sm text-ink" style={{ background: shade(m.ret) }}>
                      {pct(m.ret, 1).replace("%", "")}
                    </td>
                  ) : (
                    <td key={i} />
                  );
                })}
                <td className="num px-2 py-2 text-right text-body-sm font-semibold text-ink">{pct(total, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-label text-ink-muted">단위 %. 색이 짙을수록 그달의 움직임이 큽니다(±10%에서 가장 짙음).</p>
    </Panel>
  );
}
