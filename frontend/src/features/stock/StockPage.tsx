/** 종목 상세: 일봉 차트 위에 계획·손절 가격을 긋고, 기법 점검표와 위원 의견, 최근 위원회 판단을 함께 보여준다. */

import { ArrowRight, ChevronLeft } from "lucide-react";
import { useMemo } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { cx, Delta, Empty, ErrorState, Panel, SkeletonRows, Stat, TD, TDR, TH, THR } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayDots, dayLabel, labelOf, num, pct, wonShort, wonSigned } from "@/lib/format";
import { CONVICTION, DATA_SOURCE, EXIT_RULE, exitPlanText, heldText } from "@/lib/labels";
import { useStock } from "@/lib/queries";
import type { StockDetail } from "@/lib/types";
import { SingleApproval } from "../auto/ApprovalCard";
import { ActionBadge, IntentSummary, SeatList, sourceLabel, TechniqueChecks } from "../committee/parts";
import { CandleChart, type PriceLine } from "./CandleChart";

export default function StockPage() {
  const { code = "" } = useParams();
  const stock = useStock(code);

  if (!/^\d{6}$/.test(code)) return <Empty title="종목 코드가 올바르지 않습니다">여섯 자리 숫자 코드로 다시 찾아보세요.</Empty>;
  if (stock.isPending) return <SkeletonRows rows={8} label="종목 정보를 불러오는 중" />;
  if (stock.isError) return <ErrorState message={errorMessage(stock.error)} onRetry={() => void stock.refetch()} />;
  return <StockView s={stock.data} />;
}

function StockView({ s }: { s: StockDetail }) {
  const pending = s.intents.filter((intent) => intent.status === "pending_approval");
  const actionable = s.techniques.find((t) => t.passed && t.plan);
  const lines = useMemo<PriceLine[]>(() => {
    if (s.position) {
      const out: PriceLine[] = [
        { price: s.position.avg_price, title: "평균 단가", tone: "ink" },
        { price: s.position.stop, title: "손절", tone: "danger" },
      ];
      if (s.position.target) out.push({ price: s.position.target, title: "목표", tone: "ok" });
      return out;
    }
    if (actionable?.plan) {
      const plan = actionable.plan;
      const out: PriceLine[] = [{ price: plan.stop, title: "계획 손절", tone: "danger" }];
      if (plan.trigger) out.push({ price: plan.trigger, title: "매수 기준", tone: "plan" });
      if (plan.target) out.push({ price: plan.target, title: "계획 목표", tone: "plan" });
      return out;
    }
    return [];
  }, [s.position, actionable]);

  return (
    <div className="space-y-4">
      <div>
        <BackLink />
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <h1 className="text-h4 font-bold text-ink">{s.name}</h1>
            <p className="num text-body-sm text-ink-muted">
              {s.code} · {s.market} · {s.sector}
            </p>
          </div>
          <p className="num text-right">
            <span className="text-h3 font-bold text-ink">{num(s.close)}원</span>{" "}
            <Delta value={s.change} className="text-h6 font-semibold">
              {num(Math.abs(s.change))} ({pct(s.change_pct)})
            </Delta>
            <span className="block text-label text-ink-muted">
              {dayLabel(s.as_of)} 종가 · {DATA_SOURCE[s.data_source] ?? s.data_source}
            </span>
          </p>
        </div>
      </div>

      {/* 좁은 화면에서는 오른쪽 열이 차트·점검표 아래로 내려가 승인 대기 계획이 2,000px 아래에 묻힌다. 그래서 차트 위에 따로 둔다. */}
      {pending.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:hidden">
          {pending.map((intent) => (
            <SingleApproval key={intent.id} card={intent} />
          ))}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_calc(var(--spacing)*96)]">
        <div className="min-w-0 space-y-4">
          <Panel>
            <CandleChart
              bars={s.bars}
              overlays={s.overlays}
              lines={lines}
              label={`${s.name} 일봉 차트. 최근 ${s.bars.length}거래일, ${dayDots(s.as_of)} 종가 ${num(s.close)}원. 52주 최고 ${num(s.stats.hi252)}원, 최저 ${num(s.stats.lo252)}원.`}
            />
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-divider pt-3 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="52주 최고">{num(s.stats.hi252)}</Stat>
              <Stat label="52주 최저">{num(s.stats.lo252)}</Stat>
              <Stat label="상대강도" hint="1년 수익률 백분위">
                {s.stats.rs !== null ? num(s.stats.rs) : "자료 없음"}
              </Stat>
              <Stat label="하루 변동폭" hint="14일 평균(ATR)">
                {s.stats.atr_pct !== null ? pct(s.stats.atr_pct, 1, false) : "자료 없음"}
              </Stat>
              <Stat label="하루 거래대금" hint="20일 평균">
                {wonShort(s.stats.value20)}
              </Stat>
              <Stat label="거래량" hint={s.stats.vol_ratio !== null ? `50일 평균의 ${pct(s.stats.vol_ratio, 0, false)}` : undefined}>
                {num(s.stats.volume)}
              </Stat>
            </dl>
          </Panel>

          <Panel title="기법 점검표" bodyClassName="">
            <TechniqueChecks techniques={s.techniques} />
          </Panel>

          {s.trades.length > 0 && (
            <Panel title="이 종목의 체결 내역" bodyClassName="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th scope="col" className={TH}>
                      날짜
                    </th>
                    <th scope="col" className={TH}>
                      구분
                    </th>
                    <th scope="col" className={THR}>
                      수량
                    </th>
                    <th scope="col" className={THR}>
                      가격
                    </th>
                    <th scope="col" className={THR}>
                      손익
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {s.trades.map((t) => (
                    <tr key={t.id}>
                      <td className={cx(TD, "num")}>{dayDots(t.day)}</td>
                      <td className={TD}>{t.reason_label ?? (t.side === "buy" ? "매수" : "매도")}</td>
                      <td className={TDR}>{num(t.qty)}</td>
                      <td className={TDR}>{num(t.price)}</td>
                      <td className={TDR}>{t.pnl !== null ? <Delta value={t.pnl}>{wonSigned(t.pnl)}</Delta> : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          {pending.map((intent) => (
            <div key={intent.id} className="hidden xl:block">
              <SingleApproval card={intent} />
            </div>
          ))}
          {s.intents
            .filter((intent) => intent.status !== "pending_approval")
            .map((intent) => (
              <IntentSummary key={intent.id} intent={intent} label="이 종목의 주문 계획" />
            ))}

          {s.position && (
            <Panel title="보유 중">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
                <Stat label="수량 · 평균 단가">
                  {num(s.position.qty)}주 · {num(s.position.avg_price)}
                </Stat>
                <Stat label="평가 손익" hint={pct(s.position.pnl_pct)}>
                  <Delta value={s.position.pnl}>{wonSigned(s.position.pnl)}</Delta>
                </Stat>
                <Stat label="손절 가격" hint={s.position.stop_distance !== null ? `현재가에서 ${pct(-s.position.stop_distance, 1)}` : undefined}>
                  {num(s.position.stop)}
                </Stat>
                <Stat label="목표 가격" hint={s.position.target_distance !== null ? `현재가에서 ${pct(s.position.target_distance, 1)}` : undefined}>
                  {s.position.target ? num(s.position.target) : <span className="text-body-sm font-normal">{exitPlanText(s.position)}</span>}
                </Stat>
              </dl>
              <p className="num mt-3 text-label text-ink-muted">
                {s.position.technique_name} · {dayLabel(s.position.opened_on)} 매수 · {heldText(s.position.days_held)}
                {s.position.exit_rule && <> · {EXIT_RULE[s.position.exit_rule] ?? s.position.exit_rule}</>}
              </p>
            </Panel>
          )}

          <Panel
            title="최근 위원회 판단"
            actions={
              s.decision && (
                <Link to={`/committee/${s.decision.id}`} className="inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold text-accent hover:text-accent-hover">
                  회의 보기
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              )
            }
          >
            {s.decision ? (
              <>
                <p className="flex flex-wrap items-center gap-2">
                  <ActionBadge action={s.decision.final.action} review={s.decision.final.status !== "ok"} />
                  <span className="num text-label text-ink-muted">
                    {dayLabel(s.decision.as_of)} 장 마감 뒤 · 확신 {labelOf(CONVICTION, s.decision.final.conviction)} · {sourceLabel(s.decision.final.source)}
                  </span>
                </p>
                <p className="mt-2 line-clamp-3 text-body-sm text-ink">{s.decision.final.thesis}</p>
              </>
            ) : (
              <Empty title="아직 심의한 적이 없습니다">진입 기법의 조건을 통과하면 그날 장 마감 뒤 위원회에 올라갑니다.</Empty>
            )}
          </Panel>

          <Panel
            title={
              <>
                위원 의견{" "}
                <span className="num text-body-sm font-normal text-ink-muted">
                  종합 {s.seat_blend > 0 ? "+" : s.seat_blend < 0 ? "−" : ""}
                  {Math.abs(s.seat_blend).toFixed(2)}
                </span>
              </>
            }
            bodyClassName=""
          >
            <SeatList seats={s.seats} />
            <p className="border-t border-divider px-4 py-3 text-label text-ink-muted">
              규칙으로 계산한 의견입니다(−1 부정 ~ +1 긍정). AI 위원회는 이 의견을 읽고 토론해 결론을 냅니다. 시장 국면은 {s.regime.label}
              {s.regime.allow_new_buys ? "" : "이라 새 매수를 쉬는 중"}입니다.
            </p>
          </Panel>

          <Panel title="재무">
            {s.fundamentals ? (
              <dl className="grid grid-cols-3 gap-x-6 gap-y-3">
                <Stat label="PER">{s.fundamentals.per !== null ? num(s.fundamentals.per, 1) : "없음"}</Stat>
                <Stat label="PBR">{s.fundamentals.pbr !== null ? num(s.fundamentals.pbr, 2) : "없음"}</Stat>
                <Stat label="ROE">{s.fundamentals.roe !== null ? pct(s.fundamentals.roe / 100, 1, false) : "없음"}</Stat>
              </dl>
            ) : (
              <Empty title="재무 자료 없음">키움증권 계좌를 연결한 뒤에 받아옵니다. 그 전까지 가치 의견은 기권합니다.</Empty>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** 앱 안에서 들어왔으면 온 곳으로(종목 발굴·포트폴리오·판단 상세 등), 주소로 바로 열었으면 종목 발굴로 돌아간다. */
function BackLink() {
  const navigate = useNavigate();
  const inApp = useLocation().key !== "default";
  return (
    <Link
      to="/discover"
      onClick={(event) => {
        if (!inApp || event.metaKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        navigate(-1);
      }}
      className="inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold text-ink-secondary no-underline hover:text-ink"
    >
      <ChevronLeft aria-hidden className="size-4" />
      {inApp ? "뒤로" : "종목 발굴"}
    </Link>
  );
}
