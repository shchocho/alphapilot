/** 관제: "지금 내가 끼어들어야 하나?"에 먼저 답하고, 그다음에 엔진이 한 일(통장정리)과 지키고 있는 조건을 보여준다. */

import { Link } from "react-router-dom";
import { DataTableToggle, TimeChart } from "@/components/charts";
import { Badge, cx, Delta, Empty, ErrorState, Panel, SkeletonRows, TD, TDR, TH, THR } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayDots, dayLabel, num, pct, won, wonExact, wonShort, wonSigned } from "@/lib/format";
import { entryText, EXIT_RULE, exitPlanText, heldText } from "@/lib/labels";
import { useDashboard, useStatus } from "@/lib/queries";
import type { Dashboard, IntentCard, PositionRow, RegimeFull, Status } from "@/lib/types";
import { ApprovalCard, useStableCards } from "../auto/ApprovalCard";
import { Passbook } from "./Passbook";

export default function DashboardPage() {
  const dashboard = useDashboard();
  const status = useStatus();

  if (dashboard.isPending) return <SkeletonRows rows={8} label="관제 화면을 불러오는 중" />;
  if (dashboard.isError) return <ErrorState message={errorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />;
  return <DashboardView d={dashboard.data} status={status.data} />;
}

function DashboardView({ d, status }: { d: Dashboard; status: Status | undefined }) {
  // 글 순서(승인 → 통장정리 → 감시)는 좁은 화면의 보는 순서와 같고, 넓은 화면에서는 격자로 자리만 옮긴다.
  const stable = useStableCards(d.pending);
  const hasApprovals = stable.kept.length > 0 || d.plans.length > 0;

  return (
    <div className="space-y-4">
      <Verdict d={d} status={status} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_calc(var(--spacing)*88)] xl:grid-rows-[auto_1fr]">
        {hasApprovals && <Approvals pendingCount={d.pending.length} stable={stable} plans={d.plans} className="xl:col-start-2 xl:row-start-1" />}
        <Passbook book={d.passbook} className="xl:col-start-1 xl:row-span-2 xl:row-start-1 xl:self-start" />
        <Watch positions={d.watch} max={d.risk.max_positions} className={cx("xl:col-start-2 xl:self-start", hasApprovals ? "xl:row-start-2" : "xl:row-start-1")} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_calc(var(--spacing)*88)]">
        <EquityPanel d={d} />
        {d.regime && <RegimePanel regime={d.regime} />}
      </div>
    </div>
  );
}

// ── 판정 문장과 한도 계기 ───────────────────────────────────────────────

function verdictOf(d: Dashboard, status: Status | undefined): { text: string; sub: string; tone: "plan" | "danger" | "warn" | "calm" } {
  if (status?.last_error) return { tone: "danger", text: "엔진에 오류가 있습니다", sub: "위 안내의 오류 내용을 확인하세요. 오류가 풀릴 때까지 새 주문은 나가지 않습니다." };
  if (d.pending.length > 0) return { tone: "plan", text: `승인을 기다리는 주문 계획이 ${d.pending.length}건 있습니다`, sub: "승인한 계획만 주문으로 나갑니다. 기한이 지나면 계획은 사라집니다." };
  if (d.risk.daily_used >= 0.8) return { tone: "danger", text: `오늘 손실이 한도의 ${pct(d.risk.daily_used, 0, false)}에 닿았습니다`, sub: "한도를 다 쓰면 오늘은 새 매수를 멈춥니다. 보유 종목의 손절·익절은 계속 지킵니다." };
  if (status?.state === "stopped") return { tone: "warn", text: "엔진이 정지해 있습니다", sub: "새 주문은 나가지 않습니다. 켜려면 위쪽의 '엔진 켜기'를 누르세요." };
  if (status?.state === "paused") return { tone: "warn", text: "일시정지 중입니다", sub: "새 매수만 멈췄습니다. 보유 종목의 손절·익절은 계속 지킵니다." };
  if (d.regime && !d.regime.allow_new_buys) return { tone: "calm", text: "지금 할 일은 없습니다", sub: `시장이 ${d.regime.label} 국면이라 새 매수를 쉬고 있습니다. 보유 종목은 규칙대로 지킵니다.` };
  return { tone: "calm", text: "지금 할 일은 없습니다", sub: "엔진이 정한 규칙대로 지켜보고 있습니다." };
}

function Verdict({ d, status }: { d: Dashboard; status: Status | undefined }) {
  const v = verdictOf(d, status);
  const a = d.account;
  const r = d.risk;
  return (
    <section className="rounded-lg border border-divider bg-surface" aria-labelledby="verdict-title">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3 px-4 pt-4 pb-3 lg:px-5">
        <div className="min-w-0">
          <h1 id="verdict-title" className="text-h3 font-bold text-ink lg:text-h2">
            {v.text}
          </h1>
          <p className="mt-1 max-w-reading text-body-sm text-ink-secondary">{v.sub}</p>
        </div>
        <p className="num text-body-sm text-ink-secondary">
          {d.source_label} · {dayLabel(d.as_of)} 기준
          <br />
          오늘 손익{" "}
          <Delta value={a.day_pnl} className="text-h5 font-bold">
            {wonSigned(a.day_pnl)} ({pct(a.day_pct)})
          </Delta>
          <br />
          평가 금액 <span className="font-semibold text-ink">{won(a.equity)}</span> · 누적 <Delta value={a.total_return}>{pct(a.total_return)}</Delta>
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-divider px-4 py-3 lg:grid-cols-[1.7fr_1fr_1fr_1fr] lg:px-5">
        <Gauge
          lead
          label="오늘 손실 한도"
          used={r.daily_used}
          value={`${pct(r.daily_used, 0, false)} 사용`}
          hint={`${r.daily_used > 0 ? `오늘 ${wonShort(Math.round(r.daily_used * r.daily_limit_amount))} 잃음 · ` : ""}한도 ${wonShort(r.daily_limit_amount)} (하루 ${pct(r.daily_limit_pct, 1, false)}) · 다 쓰면 오늘 새 매수 중단`}
        />
        <Gauge
          label="손절 시 잃는 금액"
          used={r.heat_limit_pct ? r.heat_pct / r.heat_limit_pct : 0}
          value={`계좌의 ${pct(r.heat_pct, 1, false)}`}
          hint={`상한 ${pct(r.heat_limit_pct, 0, false)} · 모든 손절이 한꺼번에 걸릴 때`}
        />
        <Gauge
          label="투자 비중"
          used={r.exposure_cap ? a.exposure / r.exposure_cap : a.exposure}
          value={pct(a.exposure, 0, false)}
          hint={r.exposure_cap !== null ? `시장 국면 상한 ${pct(r.exposure_cap, 0, false)} · 현금 ${wonShort(a.cash)}` : `현금 ${wonShort(a.cash)}`}
        />
        <Gauge label="고점 대비 낙폭" used={r.drawdown_halt_pct ? Math.abs(r.drawdown_pct) / r.drawdown_halt_pct : 0} value={pct(r.drawdown_pct, 1)} hint={`${pct(-r.drawdown_halt_pct, 0)}에 닿으면 엔진 정지`} />
      </dl>
    </section>
  );
}

/** 한도 계기. lead는 첫 화면에서 가장 먼저 읽혀야 하는 계기(오늘 손실 한도)로, 글자와 막대를 한 단계 키운다. */
function Gauge({ label, used, value, hint, lead = false }: { label: string; used: number; value: string; hint: string; lead?: boolean }) {
  const ratio = Math.max(0, Math.min(1, Number.isFinite(used) ? used : 0));
  const level = ratio >= 0.8 ? "높음" : ratio >= 0.5 ? "보통" : "여유";
  return (
    <div className={cx("min-w-0", lead && "col-span-2 lg:col-span-1")}>
      <dt className={cx("text-ink-muted", lead ? "text-body-sm font-semibold" : "text-label")}>{label}</dt>
      <dd className={cx("num mt-1 flex items-baseline gap-2 font-semibold text-ink", lead ? "text-h3" : "text-h6")}>
        {value}
        {ratio >= 0.5 && <Badge tone={ratio >= 0.8 ? "danger" : "warning"}>{level}</Badge>}
      </dd>
      <dd aria-hidden className={cx("mt-2 overflow-hidden rounded-full bg-surface-sunken", lead ? "h-2" : "h-1")}>
        <span className={cx("block h-full rounded-full transition-[width] duration-(--duration-base)", ratio >= 0.8 ? "bg-danger" : ratio >= 0.5 ? "bg-warning" : "bg-success")} style={{ width: `${ratio > 0 ? Math.max(ratio * 100, 3) : 0}%` }} />
      </dd>
      <dd className="num mt-1 text-label text-ink-muted">{hint}</dd>
    </div>
  );
}

// ── 승인 대기와 예정된 주문 ─────────────────────────────────────────────

function Approvals({ pendingCount, stable, plans, className }: { pendingCount: number; stable: ReturnType<typeof useStableCards>; plans: IntentCard[]; className?: string }) {
  const { kept, outcomes, onDecided } = stable;
  return (
    <section className={cx("space-y-3", className)} aria-labelledby="approvals-title">
      {kept.length > 0 && (
        <>
          <h2 id="approvals-title" className="text-h6 font-bold text-ink">
            승인 대기 {pendingCount}건
          </h2>
          {kept.slice(0, 4).map((card) => (
            <ApprovalCard key={card.id} card={card} outcome={outcomes[card.id]} onDecided={onDecided} />
          ))}
          {kept.length > 4 && (
            <Link to="/auto" className="inline-flex min-h-11 items-center text-body-sm font-semibold text-accent">
              나머지 {kept.length - 4}건 모두 보기
            </Link>
          )}
        </>
      )}
      {plans.length > 0 && (
        <div className="rounded-lg border border-dashed border-divider bg-surface p-4">
          <h2 id={kept.length === 0 ? "approvals-title" : undefined} className="text-h6 font-bold text-ink">
            다음 거래일에 나갈 주문 {plans.length}건
          </h2>
          <ul className="mt-2 space-y-2">
            {plans.map((p) => (
              <li key={p.id} className="text-body-sm">
                <span className="font-semibold text-accent">{p.side === "buy" ? "매수" : "매도"}</span>{" "}
                <Link to={`/stocks/${p.code}`} className="font-semibold text-ink no-underline hover:underline">
                  {p.name}
                </Link>{" "}
                <span className="num text-ink-secondary">
                  {num(p.qty)}주 · {dayLabel(p.trade_date)}
                </span>
                <span className="num block text-label text-ink-muted">{entryText(p)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// ── 감시 중인 조건 ──────────────────────────────────────────────────────

function Watch({ positions, max, className }: { positions: PositionRow[]; max: number; className?: string }) {
  return (
    <Panel
      className={className}
      title={
        <>
          감시 중인 조건{" "}
          <span className="num text-body-sm font-normal text-ink-muted">
            보유 {positions.length}/{max}종목
          </span>
        </>
      }
      bodyClassName=""
    >
      {positions.length === 0 ? (
        <Empty title="보유 종목이 없습니다">매수가 체결되면 종목마다 손절·목표 가격까지 남은 거리를 여기서 지켜봅니다.</Empty>
      ) : (
        <ul>
          {positions.map((p) => (
            <WatchItem key={p.code} p={p} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function WatchItem({ p }: { p: PositionRow }) {
  // 손절가(왼쪽 끝)와 목표가(오른쪽 끝) 사이에서 현재가가 어디쯤인지 보여준다.
  const high = p.target ?? Math.max(p.price, p.avg_price) * 1.06;
  const span = high - p.stop || 1;
  const at = (price: number) => `${Math.max(0, Math.min(100, ((price - p.stop) / span) * 100))}%`;
  return (
    <li className="border-b border-divider px-4 py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <Link to={`/stocks/${p.code}`} className="min-w-0 truncate text-h6 font-semibold text-ink no-underline hover:underline">
          {p.name}
        </Link>
        <Delta value={p.pnl} className="text-body-sm font-semibold">
          {pct(p.pnl_pct)}
        </Delta>
      </div>
      <p className="num text-label text-ink-muted">
        {num(p.qty)}주 · 평균 {num(p.avg_price)}원 · 현재 {num(p.price)}원 · {heldText(p.days_held)}
      </p>
      <div aria-hidden className="relative mt-3 h-1 rounded-full bg-surface-sunken">
        <span className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-ink-muted" style={{ left: at(p.avg_price) }} />
        <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-ink" style={{ left: at(p.price) }} />
      </div>
      <p className="num mt-2 flex justify-between gap-3 text-label text-ink-secondary">
        <span>
          손절 {num(p.stop)}원{p.stop_distance !== null && <> ({pct(-p.stop_distance, 1)})</>}
        </span>
        <span className="text-right">
          {exitPlanText(p)}
          {p.target && p.target_distance !== null && <> ({pct(p.target_distance, 1)})</>}
        </span>
      </p>
      {p.exit_rule && <p className="mt-1 text-label text-ink-muted">{EXIT_RULE[p.exit_rule] ?? p.exit_rule}</p>}
    </li>
  );
}

// ── 자산 추이와 시장 국면 ───────────────────────────────────────────────

function EquityPanel({ d }: { d: Dashboard }) {
  const curve = d.curve;
  const hasBenchmark = curve.some((c) => c.benchmark !== null);
  return (
    <Panel title="자산 추이">
      {curve.length < 2 ? (
        <Empty title="아직 그릴 기록이 없습니다" action={<Link to="/auto">자동매매에서 거래일 진행하기</Link>}>
          거래일을 이틀 넘게 진행하면 내 계좌와 코스피를 같은 금액으로 놓고 비교합니다.
        </Empty>
      ) : (
        <>
          <TimeChart
            dates={curve.map((c) => c.d)}
            series={[
              { name: "내 계좌", color: "var(--data-1)", values: curve.map((c) => c.equity) },
              ...(hasBenchmark ? [{ name: "코스피에 같은 금액을 넣었다면", color: "var(--data-2)", values: curve.map((c) => c.benchmark), dashed: true }] : []),
            ]}
            format={(v) => won(v)}
            tickFormat={(v) => wonExact(v)}
            baseline={{ value: curve[0].equity, label: `첫날 ${wonExact(curve[0].equity)}` }}
            label={`${dayDots(curve[0].d)}부터 ${dayDots(curve[curve.length - 1].d)}까지 내 계좌 평가 금액 추이. 시작 ${won(curve[0].equity)}, 지금 ${won(curve[curve.length - 1].equity)}.`}
          />
          <DataTableToggle>
            <table className="w-full">
              <thead>
                <tr>
                  <th scope="col" className={TH}>
                    날짜
                  </th>
                  <th scope="col" className={THR}>
                    내 계좌
                  </th>
                  {hasBenchmark && (
                    <th scope="col" className={THR}>
                      코스피 환산
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {curve
                  .slice(-30)
                  .reverse()
                  .map((c) => (
                    <tr key={c.d}>
                      <td className={cx(TD, "num")}>{dayDots(c.d)}</td>
                      <td className={TDR}>{won(c.equity)}</td>
                      {hasBenchmark && <td className={TDR}>{c.benchmark !== null ? won(c.benchmark) : ""}</td>}
                    </tr>
                  ))}
              </tbody>
            </table>
          </DataTableToggle>
        </>
      )}
    </Panel>
  );
}

export function RegimePanel({ regime }: { regime: RegimeFull }) {
  return (
    <Panel title="시장 국면">
      <p className="text-h5 font-bold text-ink">
        {regime.label}{" "}
        <span className="num text-body-sm font-normal text-ink-secondary">
          점수 {num(regime.score)}/100 · {dayLabel(regime.day)}
        </span>
      </p>
      <p className="mt-1 text-body-sm text-ink-secondary">
        {regime.allow_new_buys ? <>새 매수를 허용하고, 투자 비중은 계좌의 {pct(regime.exposure_cap, 0, false)}까지 씁니다.</> : "새 매수를 쉽니다. 보유 종목은 손절·익절 규칙대로 지킵니다."}
      </p>
      <ul className="mt-3 space-y-3">
        {regime.components.map((c) => (
          <li key={c.key}>
            <div className="flex items-baseline justify-between gap-3 text-body-sm">
              <span className="text-ink">{c.name}</span>
              <span className="num font-semibold text-ink">{num(c.score)}</span>
            </div>
            <div aria-hidden className="mt-1 h-1 overflow-hidden rounded-full bg-surface-sunken">
              <span className="block h-full rounded-full bg-ink-muted" style={{ width: `${Math.max(0, Math.min(100, c.score))}%` }} />
            </div>
            <p className="num mt-1 text-label text-ink-muted">{c.detail}</p>
          </li>
        ))}
      </ul>
      <p className="num mt-3 text-label text-ink-muted">
        매도 압력: {regime.dist_label} · 시장 흐름: {regime.cycle_label}
        {regime.missing.length > 0 && <> · 빠진 자료: {regime.missing.join(", ")}</>}
      </p>
    </Panel>
  );
}
