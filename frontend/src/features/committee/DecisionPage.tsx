/** 판단 한 건의 전부: 회의(참석자와 발언, 결론, 리스크 점검) → 주문 계획 → 그 뒤에 실제로 일어난 일(장부). */

import { ChevronLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Badge, cx, ErrorState, Panel, SkeletonRows } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayLabel, labelOf, num } from "@/lib/format";
import { entryText, INTENT_STATUS, INTENT_TONE } from "@/lib/labels";
import { useDecision } from "@/lib/queries";
import { SingleApproval } from "../auto/ApprovalCard";
import { LedgerTable } from "../dashboard/Passbook";
import { MeetingRoom } from "./MeetingRoom";
import { ActionBadge, sourceLabel, TechniqueChecks } from "./parts";

export default function DecisionPage() {
  const { id } = useParams();
  const decision = useDecision(id);

  if (decision.isPending) return <SkeletonRows rows={8} label="판단 기록을 불러오는 중" />;
  if (decision.isError) return <ErrorState message={errorMessage(decision.error)} onRetry={() => void decision.refetch()} />;
  const d = decision.data;
  // 주문 계획도 장부 줄도 없으면(보류 판단 등) 왼쪽 열을 비워 두지 않고 기법 점검표를 넓게 편다
  const after = Boolean(d.intent) || d.chain.length > 0;

  return (
    <div className="space-y-4">
      <div>
        <Link to={`/committee?day=${d.as_of}`} className="inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold text-ink-secondary no-underline hover:text-ink">
          <ChevronLeft aria-hidden className="size-4" />
          {dayLabel(d.as_of)} 심의 목록
        </Link>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-h4 font-bold text-ink">
            <Link to={`/stocks/${d.code}`} className="no-underline hover:underline">
              {d.name}
            </Link>
          </h1>
          <ActionBadge action={d.final.action} review={d.final.status !== "ok"} />
        </div>
        <p className="num text-body-sm text-ink-muted">
          {d.code} · {d.kind === "entry" ? "새로 살지 심의" : "보유 다시 심의"}
          {d.technique_name && <> · {d.technique_name}</>} · {dayLabel(d.as_of)} 장 마감 뒤 · {sourceLabel(d.source)}
          {d.close ? <> · 그날 종가 {num(d.close)}원</> : null}
        </p>
      </div>

      <MeetingRoom key={d.id} d={d} />

      <div className={cx("grid gap-4", after && "xl:grid-cols-[minmax(0,1fr)_calc(var(--spacing)*96)]")}>
        {after && (
          <div className="min-w-0 space-y-4">
            {d.intent?.status === "pending_approval" && <SingleApproval card={d.intent} showDecisionLink={false} />}

            {d.intent && d.intent.status !== "pending_approval" && (
              <section className="rounded-lg border border-divider bg-accent-subtle p-4" aria-label="이 판단으로 만든 주문 계획">
                <p className="flex flex-wrap items-center gap-2 text-body-sm">
                  <Badge tone={INTENT_TONE[d.intent.status] ?? "accent"}>
                    {labelOf(INTENT_STATUS, d.intent.status)}
                  </Badge>
                  <span className="num font-semibold text-ink">
                    {d.intent.side === "buy" ? "매수" : "매도"} 계획 {num(d.intent.qty)}주 · {dayLabel(d.intent.trade_date)}
                  </span>
                </p>
                <p className="num mt-1 text-body-sm text-ink-secondary">
                  {entryText(d.intent)}
                  {d.intent.stop ? ` · 손절 ${num(d.intent.stop)}원` : ""}
                  {d.intent.note ? ` · ${d.intent.note}` : ""}
                </p>
              </section>
            )}

            {d.chain.length > 0 && (
              <Panel title="이 판단 뒤에 일어난 일" bodyClassName="">
                <LedgerTable rows={d.chain} followChains={false} />
              </Panel>
            )}
          </div>
        )}

        <div className="min-w-0">
          <Panel title="기법 점검표" bodyClassName="">
            <TechniqueChecks techniques={d.techniques} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
