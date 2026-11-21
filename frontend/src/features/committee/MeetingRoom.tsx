/**
 * 판단 한 건을 회의로 보여준다: 탁자 둘레에 참석자가 앉아 있고, 한 명을 고르면 그 사람이 한 말이 옆에 나온다.
 * 처음에는 위원장(결론)이 골라져 있어 답이 먼저 보이고, 이전·다음으로 발언 차례를 거슬러 가거나 따라갈 수 있다.
 * 분석 위원은 규칙으로 계산한 의견이고 토론자는 AI다. 누가 낸 의견인지는 발언 머리에 항상 적는다.
 */

import { ChevronLeft, ChevronRight, ShieldCheck, UserRound, UserRoundCheck, UserRoundPen, UserRoundSearch } from "lucide-react";
import { type KeyboardEvent, useMemo, useRef, useState } from "react";
import { Badge, Button, cx, Notice, Panel } from "@/components/ui";
import { labelOf, num } from "@/lib/format";
import { CONVICTION, STANCE, STANCE_TONE } from "@/lib/labels";
import type { DecisionDetail, TranscriptStep } from "@/lib/types";
import { votesText } from "../auto/ApprovalCard";
import { type Attendee, buildMeeting, signed, tableSides } from "./meeting";
import { ActionBadge, FinalCard, GateSteps, OpinionBar, SeatEvidence, sourceLabel } from "./parts";

// ── AI 발언 내용 ────────────────────────────────────────────────────────

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
/** 심각도의 medium·high는 확신 단계와 낱말이 같아도 뜻이 다르다. */
const SEVERITY_VALUE: Record<string, string> = { low: "낮음", medium: "보통", high: "높음" };

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
  if (typeof value === "string") return value ? (key === "severity" ? (SEVERITY_VALUE[value] ?? value) : (VALUE[value] ?? value)) : "없음";
  return "없음";
}

function usageLine(step: TranscriptStep): string {
  return `${step.model} · 입력 ${num(step.input_tokens)} · 출력 ${num(step.output_tokens)} 토큰 · $${step.cost_usd.toFixed(4)}`;
}

function Speech({ step, heading }: { step: TranscriptStep; heading: boolean }) {
  return (
    <div>
      {/* 한 사람이 두 번 말한 경우에만 붙인다. 첫 발언의 이름은 발언 머리와 같아서 차례로 적는다 */}
      {heading && <h4 className="text-body-sm font-semibold text-ink">{step.role.endsWith("_rebuttal") ? "재반박" : "처음 발언"}</h4>}
      <dl className={cx("space-y-2", heading && "mt-1")}>
        {Object.entries(step.content).map(([key, value]) => (
          <div key={key}>
            <dt className="text-label font-semibold text-ink-muted">{FIELD[key] ?? key}</dt>
            <dd className="text-body-sm text-ink-secondary">{fieldValue(key, value)}</dd>
          </div>
        ))}
      </dl>
      <p className="num mt-2 text-caption text-ink-muted">{usageLine(step)}</p>
    </div>
  );
}

// ── 자리 ────────────────────────────────────────────────────────────────

function seatIcon(a: Attendee) {
  if (a.kind === "gate") return ShieldCheck; // 사람이 아니라 규칙이 지키는 문이다
  if (a.kind === "chair") return UserRoundPen;
  if (a.kind === "analyst") return UserRound;
  return a.id === "ai-risk" ? UserRoundCheck : UserRoundSearch;
}

function SeatTab({ a, selected, onSelect, onKeyDown, bind }: { a: Attendee; selected: boolean; onSelect: () => void; onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void; bind: (node: HTMLButtonElement | null) => void }) {
  const Icon = seatIcon(a);
  const abstained = a.seat?.abstained ?? false;
  return (
    <button
      ref={bind}
      type="button"
      role="tab"
      id={`meeting-tab-${a.id}`}
      aria-selected={selected}
      aria-controls="meeting-statement"
      tabIndex={selected ? 0 : -1}
      onClick={onSelect}
      onKeyDown={onKeyDown}
      className="group flex min-h-11 max-w-28 min-w-0 grow basis-1/4 flex-col items-center gap-1 rounded-md px-1 py-2 text-center transition-colors duration-(--duration-fast) hover:bg-secondary focus-visible:outline-none"
    >
      <span
        aria-hidden
        className={cx(
          "grid size-10 place-items-center rounded-full transition-colors duration-(--duration-fast) group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-focus",
          selected ? "border-2 border-ink bg-secondary text-ink" : cx("border bg-surface-sunken", abstained ? "border-dashed border-border text-ink-muted" : "border-divider text-ink-secondary"),
        )}
      >
        <Icon className="size-5" />
      </span>
      <span className={cx("max-w-full text-label leading-tight", selected ? "font-semibold text-ink" : "font-medium text-ink-secondary")}>{a.name}</span>
      <span className="num max-w-full text-caption leading-tight text-ink-muted">{a.mark}</span>
    </button>
  );
}

// ── 발언 ────────────────────────────────────────────────────────────────

function roleLine(a: Attendee, d: DecisionDetail): string {
  if (a.kind === "analyst") return "분석 위원 · 규칙으로 계산한 의견";
  if (a.kind === "debater") return a.id === "ai-branch" ? "AI에게 물은 분기" : "토론 · AI";
  if (a.kind === "chair") return `결론 · ${sourceLabel(d.source)}`;
  return "주문 전 점검 · 규칙(AI가 바꿀 수 없음)";
}

function Statement({ a, d }: { a: Attendee; d: DecisionDetail }) {
  if (a.kind === "analyst" && a.seat) {
    const seat = a.seat;
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STANCE_TONE[seat.stance] ?? "neutral"}>{labelOf(STANCE, seat.stance)}</Badge>
          {!seat.abstained && <span className="num text-label text-ink-muted">의견 값 {signed(seat.value)} (−1부터 +1까지)</span>}
        </div>
        <OpinionBar value={seat.value} abstained={seat.abstained} />
        <p className="num text-body-sm text-ink">{seat.summary}</p>
        {seat.components.length > 0 && (
          <div>
            <h4 className="text-label font-semibold text-ink-muted">근거 {seat.components.length}개</h4>
            <div className="mt-1">
              <SeatEvidence components={seat.components} />
            </div>
          </div>
        )}
      </div>
    );
  }
  if (a.kind === "debater") {
    return (
      <div className="space-y-4">
        {a.steps.map((step, i) => (
          <Speech key={`${step.role}-${i}`} step={step} heading={a.steps.length > 1} />
        ))}
      </div>
    );
  }
  if (a.kind === "chair") {
    // 합계는 여러 번 호출했을 때만 적는다. 위원장 한 번뿐이면 바로 위 줄과 같은 값이다
    const cost = (d.transcript?.steps.length ?? 0) > 1 ? (d.transcript?.cost_usd ?? 0) : 0;
    return (
      <div className="space-y-3">
        <FinalCard final={d.final} />
        {a.basis === "rules" && <p className="text-label text-ink-muted">규칙 위원회는 위원 의견을 가중 평균하고 반대 의견 수를 세어 결론을 냅니다. 토론은 열지 않습니다.</p>}
        {a.steps.map((step, i) => (
          <p key={`${step.role}-${i}`} className="num text-caption text-ink-muted">
            {usageLine(step)}
          </p>
        ))}
        {cost > 0 && <p className="num text-caption text-ink-muted">이 판단에 든 AI 비용 ${cost.toFixed(4)}</p>}
      </div>
    );
  }
  if (d.gate) return <GateSteps gate={d.gate} />;
  return <p className="text-body-sm text-ink-secondary">매수 판단이 아니어서 리스크 점검을 하지 않았습니다. 점검은 새로 사는 주문의 수량을 줄이거나 막을 때만 합니다.</p>;
}

// ── 회의 ────────────────────────────────────────────────────────────────

// 한 줄에 네 자리. 자리가 넷보다 적은 줄(토론자 셋)은 가운데로 모이고 자리가 조금 넓어져 이름이 한 줄에 들어간다
const SIDE = "flex flex-wrap justify-center gap-y-1";

export function MeetingRoom({ d }: { d: DecisionDetail }) {
  const meeting = useMemo(() => buildMeeting(d), [d]);
  const { attendees, chair, gate } = meeting;
  const { top, bottom } = tableSides(meeting);
  const [selectedId, setSelectedId] = useState(chair.id);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const statement = useRef<HTMLElement>(null);

  const index = Math.max(0, attendees.findIndex((a) => a.id === selectedId));
  const current = attendees[index];
  const last = attendees.length - 1;

  const go = (next: number, focus: boolean) => {
    const target = attendees[Math.max(0, Math.min(last, next))];
    setSelectedId(target.id);
    if (focus) refs.current[target.id]?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const next = event.key === "ArrowRight" || event.key === "ArrowDown" ? (index === last ? 0 : index + 1) : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (index === 0 ? last : index - 1) : event.key === "Home" ? 0 : event.key === "End" ? last : -1;
    if (next < 0) return;
    event.preventDefault();
    go(next, true);
  };
  // 좁은 화면에서는 발언이 자리 아래에 있어, 자리를 눌러도 화면에서 바뀌는 것이 없어 보인다.
  // 눌러서 골랐을 때 발언이 화면 밖이면 발언 머리로 옮겨 준다(그다음은 발언 머리의 이전·다음으로 넘긴다).
  const pick = (id: string) => {
    setSelectedId(id);
    requestAnimationFrame(() => {
      const node = statement.current;
      if (!node) return;
      const { top } = node.getBoundingClientRect();
      if (top < 0 || top > window.innerHeight - 160) node.scrollIntoView({ block: "start" });
    });
  };
  const seat = (a: Attendee) => (
    <SeatTab
      key={a.id}
      a={a}
      selected={a.id === current.id}
      onSelect={() => pick(a.id)}
      onKeyDown={onKeyDown}
      bind={(node) => {
        refs.current[a.id] = node;
      }}
    />
  );

  const votes = votesText(d.final.votes);
  const branch = d.transcript?.branch;
  // 토론이 시작된 뒤 멈춘 경우에만 따로 알린다. 한 번도 말하지 못한 경우는 위원장 발언의 '보류로 처리' 안내 하나로 충분하다
  const halted = d.transcript?.error && d.transcript.steps.length > 0 ? d.transcript.error : "";

  return (
    <Panel title="회의" bodyClassName="@container">
      {(branch || halted) && (
        <div className="space-y-2 p-3 pb-0 sm:p-4 sm:pb-0">
          {branch && (
            <Notice>
              규칙만으로 가르기 애매해 AI에게 물었습니다. {branch.reason}. → {branch.outcome}
            </Notice>
          )}
          {halted && <Notice tone="warning">토론이 중간에 멈췄습니다: {halted}</Notice>}
        </div>
      )}
      <div className="grid gap-4 p-3 sm:p-4 @4xl:grid-cols-[minmax(0,30rem)_minmax(0,1fr)] @4xl:gap-6">
        {/* 탁자와 자리. 좁으면 탁자 아래로 자리를 쌓고, 넓으면 탁자 머리에 위원장, 맞은편 끝에 리스크 점검이 앉는다 */}
        <div className="grid grid-cols-2 gap-2 self-start [grid-template-areas:'table_table'_'top_top'_'bottom_bottom'_'head_foot'] @lg:grid-cols-[5.5rem_minmax(0,1fr)_5.5rem] @lg:items-center @lg:[grid-template-areas:'._top_.'_'head_table_foot'_'._bottom_.']">
          <div className="rounded-xl border border-divider bg-surface-sunken px-3 py-3 text-center [grid-area:table] @lg:py-5">
            <p className="text-caption text-ink-muted">안건</p>
            <p className="text-body-sm font-semibold text-ink">{d.kind === "entry" ? "새로 살지" : "계속 보유할지"}</p>
            <p className="mt-2 flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
              <ActionBadge action={d.final.action} review={d.final.status !== "ok"} />
              <span className="text-label text-ink-secondary">확신 {labelOf(CONVICTION, d.final.conviction)}</span>
            </p>
            {votes && <p className="num mt-1 text-caption text-ink-muted">{votes}</p>}
          </div>
          {/* 자리 묶음만 탭 목록이다(탁자 글은 탭이 아니다). contents라 자리들이 바깥 격자에 그대로 놓인다 */}
          <div role="tablist" aria-label="회의 참석자" className="contents">
            <div role="presentation" className={cx(SIDE, "[grid-area:top]")}>
              {top.map(seat)}
            </div>
            <div role="presentation" className={cx(SIDE, "[grid-area:bottom]")}>
              {bottom.map(seat)}
            </div>
            <div role="presentation" className="flex justify-center [grid-area:head]">
              {seat(chair)}
            </div>
            <div role="presentation" className="flex justify-center [grid-area:foot]">
              {seat(gate)}
            </div>
          </div>
        </div>

        <section
          ref={statement}
          role="tabpanel"
          id="meeting-statement"
          aria-labelledby={`meeting-tab-${current.id}`}
          tabIndex={0}
          className="min-w-0 scroll-mt-16 border-t border-divider pt-4 @4xl:min-h-72 @4xl:border-t-0 @4xl:border-l @4xl:pt-0 @4xl:pl-6"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-h6 font-semibold text-ink">{current.name}</h3>
              <p className="text-caption text-ink-muted">{roleLine(current, d)}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <span className="num mr-1 text-caption text-ink-muted" aria-label={`${attendees.length}명 가운데 ${index + 1}번째`}>
                {index + 1} / {attendees.length}
              </span>
              <Button size="icon" variant="ghost" aria-label="이전 발언자" disabled={index === 0} onClick={() => go(index - 1, false)} icon={<ChevronLeft aria-hidden className="size-4" />} />
              <Button size="icon" variant="ghost" aria-label="다음 발언자" disabled={index === last} onClick={() => go(index + 1, false)} icon={<ChevronRight aria-hidden className="size-4" />} />
            </div>
          </div>
          {/* 아주 넓은 화면에서도 발언은 읽기 좋은 폭(680px) 안에서 줄을 바꾼다 */}
          <div className="mt-3 max-w-reading">
            <Statement a={current} d={d} />
          </div>
        </section>
      </div>
    </Panel>
  );
}
