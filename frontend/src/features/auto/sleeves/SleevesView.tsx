/** 자동매매 › 내 종목 운용: 총액을 바구니로 나누고, 바구니마다 위원회가 동시에 심의해 모으기·매수·매도 타이밍을 알려 준다. */

import { useQuery } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Check, cx, Empty, ErrorState, Notice, Panel, SkeletonRows, Stat } from "@/components/ui";
import { api, DEMO, errorMessage } from "@/lib/api";
import { dayDots, num, pct, won, wonShort } from "@/lib/format";
import { notifyError, refreshAll } from "@/lib/queries";
import { emptyPlan, refreshSleeves, useSleeves } from "./data";
import { PlanEditor } from "./PlanEditor";
import { RevisionsPanel } from "./Revisions";
import { SleeveCard } from "./SleeveCard";
import type { Estimate, SleevesOverview } from "./types";
import { ValidationPanel } from "./Validation";

export default function SleevesView() {
  const q = useSleeves(!DEMO);
  const [editing, setEditing] = useState(false);

  if (DEMO) {
    return (
      <Panel>
        <Empty title="공개 데모에서는 내 종목 운용을 쓸 수 없습니다">바구니 계획과 심의는 내 PC에서 서버를 켜야 저장되고 돌아갑니다. README의 "내 PC에서 실행"을 따르세요.</Empty>
      </Panel>
    );
  }
  if (q.isPending) return <SkeletonRows rows={8} label="운용 계획을 불러오는 중" />;
  if (q.isError) return <ErrorState message={errorMessage(q.error)} onRetry={() => void q.refetch()} />;
  const view = q.data;

  if (editing) return <PlanEditor view={view} initial={view.plan?.config ?? emptyPlan()} onDone={() => setEditing(false)} />;

  if (!view.plan) {
    return (
      <Panel>
        <Empty
          title="아직 운용 계획이 없습니다"
          action={
            <Button variant="primary" onClick={() => setEditing(true)} disabled={!view.data_day}>
              운용 계획 만들기
            </Button>
          }
        >
          총 투입 금액을 바구니로 나누고(예: 100만 원 → 중장기 50만 원, ETF 50만 원), 바구니마다 종목과 운용 지침을 정합니다. 위원회가 바구니별로 동시에 심의해 이번 회차에 더 모을지, 쉴지, 줄일지를 알려 줍니다.
          {!view.data_day && " 먼저 설정에서 일봉을 갱신하세요."}
        </Empty>
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <PlanPanel view={view} onEdit={() => setEditing(true)} />
      <RunPanel view={view} />
      <div className="grid gap-4 xl:grid-cols-2">
        {view.sleeves.map((s) => (
          <SleeveCard key={s.id} sleeve={s} total={view.plan?.total ?? 0} />
        ))}
      </div>
      <ValidationPanel view={view} />
      <RevisionsPanel />
    </div>
  );
}

// 바구니 구분은 색이 아니라 잉크 농도와 이름표로 한다(색은 가격·상태·계획에만 쓴다)
const SEGMENT = ["bg-ink", "bg-ink-secondary", "bg-ink-muted", "bg-border", "bg-ink-secondary", "bg-ink-muted"];

function PlanPanel({ view, onEdit }: { view: SleevesOverview; onEdit: () => void }) {
  const plan = view.plan!;
  const left = plan.total - plan.allocated;
  return (
    <Panel
      title={
        <span className="flex flex-wrap items-baseline gap-2">
          운용 계획 <span className="num">r{plan.rev}</span>
          <span className="num text-body-sm font-normal text-ink-muted">
            {dayDots(plan.created_at)} 저장{plan.note ? ` · ${plan.note}` : ""}
          </span>
        </span>
      }
      actions={<Button onClick={onEdit}>계획 고치기</Button>}
    >
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="총 투입 금액">{won(plan.total)}</Stat>
        <Stat label="바구니에 배정" hint={`${view.sleeves.length}개`}>
          {won(plan.allocated)}
        </Stat>
        <Stat label="남은 금액" hint="어느 바구니에도 넣지 않음">
          {won(left)}
        </Stat>
        <Stat label="기준 일봉" hint="최신 일봉 기준으로 앞으로 쌓음">
          {dayDots(view.data_day)}
        </Stat>
      </dl>
      <div className="mt-4">
        <div
          role="img"
          aria-label={`총액 나눔: ${view.sleeves.map((s) => `${s.name} ${wonShort(s.amount)}`).join(", ")}${left > 0 ? `, 남은 금액 ${wonShort(left)}` : ""}`}
          className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-divider"
        >
          {view.sleeves.map((s, i) => (
            <span key={s.id} className={cx("h-full", SEGMENT[i % SEGMENT.length])} style={{ width: `${(s.amount / plan.total) * 100}%` }} />
          ))}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-body-sm">
          {view.sleeves.map((s, i) => (
            <li key={s.id} className="flex items-center gap-2">
              <span aria-hidden className={cx("size-3 rounded-xs", SEGMENT[i % SEGMENT.length])} />
              <span className="text-ink">{s.name}</span>
              <span className="num text-ink-secondary">
                {wonShort(s.amount)} · {pct(s.amount / plan.total, 0, false)}
              </span>
            </li>
          ))}
          {left > 0 && (
            <li className="flex items-center gap-2">
              <span aria-hidden className="size-3 rounded-xs bg-divider" />
              <span className="text-ink-secondary">남은 금액</span>
              <span className="num text-ink-secondary">{wonShort(left)}</span>
            </li>
          )}
        </ul>
      </div>
    </Panel>
  );
}

function RunPanel({ view }: { view: SleevesOverview }) {
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const est = useQuery({
    queryKey: ["sleeves", "estimate", force],
    queryFn: () => api.get<Estimate>(`/api/sleeves/estimate?force=${force}`),
    initialData: force ? undefined : view.estimate,
  }).data;
  const usesAi = view.sleeves.some((s) => s.decider !== "rules");
  const targets = est?.targets.length ?? 0;
  const names = view.sleeves.filter((s) => est?.targets.includes(s.id)).map((s) => s.name);
  const last = view.last_run;

  const run = async () => {
    setBusy(true);
    try {
      const out = await api.post<{ run_id: string | null; sleeves: unknown[]; fills: unknown[]; message?: string; ai_calls?: number; cost_usd?: number }>(
        "/api/sleeves/run",
        { force },
      );
      if (out.run_id) toast.success(`바구니 ${out.sleeves.length}개를 심의했습니다${out.fills.length ? ` · 가상 체결 ${out.fills.length}건` : ""}`);
      else toast(out.message ?? "심의할 바구니가 없습니다");
      setForce(false);
      refreshSleeves();
      refreshAll();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="심의">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-reading space-y-1 text-body-sm">
          <p className="text-ink">
            {targets > 0 ? <>지금 심의할 바구니 {num(targets)}개: {names.join(", ")}</> : <>오늘 심의할 차례인 바구니가 없습니다.</>}
          </p>
          {usesAi && est && targets > 0 && (
            <p className="num text-ink-secondary">
              AI 호출 최대 {num(est.calls)}회 · 약 ${est.est_usd.toFixed(2)}(어림) · 오늘 쓴 금액 ${est.spent_today_usd.toFixed(2)} / 하루 예산 ${est.budget_usd.toFixed(2)}
            </p>
          )}
          <p className="text-caption text-ink-muted">
            장 마감 뒤 일봉이 갱신되면 차례가 된 바구니를 자동으로 심의합니다(서버가 켜져 있을 때). 바구니끼리는 동시에 심의하고, 가상 주문은 다음 거래일 시가에 체결합니다.
          </p>
          <Check checked={force} onChange={(e) => setForce(e.target.checked)} label="차례가 아니어도 모든 바구니를 다시 심의" hint="같은 날 이미 심의한 바구니는 그날의 앞선 결과를 되돌리고 새로 만듭니다" />
        </div>
        <Button variant="primary" busy={busy} disabled={busy || targets === 0} icon={<Play aria-hidden className="size-4" />} onClick={() => void run()}>
          지금 심의
        </Button>
      </div>
      {usesAi && est && !est.ai_configured && (
        <div className="mt-3">
          <Notice tone="warning">서버에 AI 키(ANTHROPIC_API_KEY)가 없습니다. AI 위원회 바구니는 모든 종목을 쉬기로 기록하고, 규칙 + AI 분기 바구니는 규칙 결론을 씁니다.</Notice>
        </div>
      )}
      {(busy || view.busy) && (
        <p role="status" className="mt-3 text-body-sm text-ink-secondary">
          {view.busy || "심의하고 있습니다"}. AI 위원회를 쓰면 종목마다 수십 초가 걸릴 수 있습니다.
        </p>
      )}
      {last && (
        <p className="num mt-3 border-t border-divider pt-3 text-caption text-ink-muted">
          마지막 심의 {dayDots(last.as_of)} 장 마감 기준 · r{last.rev} · {last.trigger === "schedule" ? "자동" : "직접"} · 바구니 {last.sleeves.length}개 · AI {num(last.ai_calls)}회 · 약 ${last.cost_usd.toFixed(3)}
        </p>
      )}
    </Panel>
  );
}
