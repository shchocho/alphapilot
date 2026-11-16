/** 판단 한 건의 전부: 결론 → 리스크 점검 → 토론 기록 → 그 뒤에 실제로 일어난 일(장부). */

import { ChevronLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Badge, ErrorState, Notice, Panel, SkeletonRows } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayLabel, labelOf, num } from "@/lib/format";
import { CONVICTION, entryText, INTENT_STATUS, INTENT_TONE } from "@/lib/labels";
import { useDecision } from "@/lib/queries";
import type { TranscriptStep } from "@/lib/types";
import { LedgerTable } from "../dashboard/Passbook";
import { ActionBadge, FinalCard, GateSteps, SeatList, sourceLabel, TechniqueChecks } from "./parts";

const FIELD: Record<string, string> = {
  points: "주장",
  strongest_evidence: "가장 강한 근거",
  weakest_spot: "가장 약한 부분",
  concerns: "우려",
  severity: "심각도",
  veto: "거부권",
  size: "수량",
  note: "덧붙임",
  action: "판단",
  conviction: "확신",
  tighter_stop: "더 좁힌 손절 가격",
  thesis: "결론",
  key_risks: "위험 요인",
  invalidation: "판단을 바꿀 조건",
  dissent: "반대 의견",
};
const VALUE: Record<string, string> = {
  ...CONVICTION,
  BUY: "매수",
  SELL: "매도",
  HOLD: "보류",
  full: "계획 수량 그대로",
  three_quarters: "계획의 75%",
  half: "계획의 절반",
  quarter: "계획의 25%",
};

function fieldValue(key: string, value: unknown): React.ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return "없음";
    return (
      <ul className="list-disc space-y-1 pl-5">
        {value.map((item, i) => (
          <li key={i}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "boolean") return key === "veto" ? (value ? "행사함(매수 불가)" : "행사하지 않음") : value ? "예" : "아니오";
  if (typeof value === "number") return key === "tighter_stop" ? (value > 0 ? `${num(value)}원` : "바꾸지 않음") : num(value);
  if (typeof value === "string") return value ? (VALUE[value] ?? value) : "없음";
  return "없음";
}

function Step({ step }: { step: TranscriptStep }) {
  return (
    <li className="border-b border-divider px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-body-sm font-bold text-ink">{step.label}</h3>
        <span className="num text-label text-ink-muted">
          {step.model} · 입력 {num(step.input_tokens)} · 출력 {num(step.output_tokens)} 토큰 · ${step.cost_usd.toFixed(4)}
        </span>
      </div>
      <dl className="mt-2 space-y-2">
        {Object.entries(step.content).map(([key, value]) => (
          <div key={key}>
            <dt className="text-label font-semibold text-ink-muted">{FIELD[key] ?? key}</dt>
            <dd className="text-body-sm text-ink-secondary">{fieldValue(key, value)}</dd>
          </div>
        ))}
      </dl>
    </li>
  );
}

export default function DecisionPage() {
  const { id } = useParams();
  const decision = useDecision(id);

  if (decision.isPending) return <SkeletonRows rows={8} label="판단 기록을 불러오는 중" />;
  if (decision.isError) return <ErrorState message={errorMessage(decision.error)} onRetry={() => void decision.refetch()} />;
  const d = decision.data;

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

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_calc(var(--spacing)*96)]">
        <div className="min-w-0 space-y-4">
          <Panel title="결론">
            <FinalCard final={d.final} />
          </Panel>

          {d.gate && (
            <Panel title="리스크 점검">
              <GateSteps gate={d.gate} />
            </Panel>
          )}

          {d.intent && (
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

          <Panel title="토론 기록" bodyClassName="">
            {d.transcript && d.transcript.steps.length > 0 ? (
              <>
                {d.transcript.error && (
                  <div className="p-4 pb-0">
                    <Notice tone="warning">토론이 중간에 멈췄습니다: {d.transcript.error}</Notice>
                  </div>
                )}
                <ol>
                  {d.transcript.steps.map((step, i) => (
                    <Step key={`${step.role}-${i}`} step={step} />
                  ))}
                </ol>
                <p className="num border-t border-divider px-4 py-3 text-label text-ink-muted">이 판단에 든 AI 비용 ${d.transcript.cost_usd.toFixed(4)}</p>
              </>
            ) : (
              <p className="p-4 text-body-sm text-ink-secondary">
                {d.source === "rules"
                  ? "규칙 위원회가 판단했습니다. 위원 의견을 가중 평균하고 반대 의견 수를 세어 결론을 내므로 토론 기록은 없습니다."
                  : (d.transcript?.error ?? "토론 기록이 남지 않았습니다.")}
              </p>
            )}
          </Panel>

          {d.chain.length > 0 && (
            <Panel title="이 판단 뒤에 일어난 일" bodyClassName="">
              <LedgerTable rows={d.chain} followChains={false} />
            </Panel>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <Panel title="위원 의견" bodyClassName="">
            <SeatList seats={d.seats} />
          </Panel>
          <Panel title="기법 점검표" bodyClassName="">
            <TechniqueChecks techniques={d.techniques} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
