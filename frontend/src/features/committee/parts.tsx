/** 위원회 판단을 보여주는 공용 부품: 위원 의견, 기법 점검표, 최종 판단, 리스크 점검 단계. */

import { Check, CircleAlert, X } from "lucide-react";
import { Badge, DisclosureIcon, SUMMARY } from "@/components/ui";
import { labelOf, num, pct } from "@/lib/format";
import { ACTION, ACTION_TONE, checkValueText, CONVICTION, GATE_OUTCOME, GATE_RULE, GATE_TONE, planText, STANCE, STANCE_TONE, TECH_STATE, TECH_STATE_TONE } from "@/lib/labels";
import type { FinalDecision, Gate, Seat, TechniqueResult } from "@/lib/types";

export function ActionBadge({ action, review = false }: { action: string; review?: boolean }) {
  if (review) {
    return (
      <Badge tone="warning">
        <CircleAlert aria-hidden className="size-3" />
        확인 필요
      </Badge>
    );
  }
  return <Badge tone={ACTION_TONE[action] ?? "neutral"}>{labelOf(ACTION, action)}</Badge>;
}

export const sourceLabel = (source: string | null | undefined): string =>
  source === "ai" ? "AI 위원회" : source === "rules" ? "규칙 위원회" : source === "hybrid" ? "규칙 위원회(애매한 분기만 AI에게 물음)" : "–";

// ── 위원 의견 ───────────────────────────────────────────────────────────

/** 의견 값(−1~+1)을 가운데 0에서 좌우로 뻗는 막대로 그린다. 방향은 뻗는 쪽과 옆의 글자(긍정·부정)·부호가 전한다. */
function OpinionBar({ value, abstained }: { value: number; abstained: boolean }) {
  const half = Math.max(0, Math.min(1, Math.abs(value))) * 50;
  return (
    <div aria-hidden className="relative h-1 rounded-full bg-divider">
      <span className="absolute top-1/2 left-1/2 h-3 w-px -translate-y-1/2 bg-ink-muted" />
      {!abstained && half > 0 && <span className="absolute top-0 h-full rounded-full bg-ink-secondary" style={value >= 0 ? { left: "50%", width: `${half}%` } : { right: "50%", width: `${half}%` }} />}
    </div>
  );
}

export function SeatList({ seats }: { seats: Seat[] }) {
  return (
    <ul>
      {seats.map((seat) => (
        <li key={seat.seat} className="border-b border-divider px-4 py-3 last:border-b-0">
          <div className="flex items-center justify-between gap-3">
            <span className="text-body-sm font-semibold text-ink">{seat.label}</span>
            <span className="flex items-center gap-2">
              {!seat.abstained && <span className="num text-label text-ink-muted">{seat.value > 0 ? "+" : seat.value < 0 ? "−" : ""}{Math.abs(seat.value).toFixed(2)}</span>}
              <Badge tone={STANCE_TONE[seat.stance] ?? "neutral"}>{labelOf(STANCE, seat.stance)}</Badge>
            </span>
          </div>
          <div className="mt-2">
            <OpinionBar value={seat.value} abstained={seat.abstained} />
          </div>
          <p className="num mt-2 text-body-sm text-ink-secondary">{seat.summary}</p>
          {seat.components.length > 0 && (
            <details className="group/disclosure mt-1">
              <summary className={SUMMARY}>
                <DisclosureIcon />
                근거 {seat.components.length}개 보기
              </summary>
              <ul className="mt-1 space-y-1">
                {seat.components.map((c) => (
                  <li key={c.name} className="num flex items-start gap-2 text-label text-ink-secondary">
                    {c.max_points === 1 ? c.points >= 1 ? <Check aria-label="통과" className="mt-1 size-4 shrink-0 text-success" /> : <X aria-label="미달" className="mt-1 size-4 shrink-0 text-danger" /> : null}
                    <span>
                      <span className="text-ink">{c.name}</span> · {c.detail}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

// ── 기법 점검표 ─────────────────────────────────────────────────────────

export function TechniqueChecks({ techniques }: { techniques: TechniqueResult[] }) {
  return (
    <div>
      {techniques.map((t) => {
        const passed = t.checks.filter((c) => c.passed).length;
        return (
          <details key={t.key} className="group/disclosure border-b border-divider last:border-b-0" open={t.passed}>
            <summary className="flex min-h-12 cursor-pointer list-none flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-2 transition-colors duration-(--duration-fast) hover:bg-surface-sunken [&::-webkit-details-marker]:hidden">
              <span className="flex items-center gap-2">
                <DisclosureIcon className="text-ink-muted" />
                {t.passed ? <Check aria-label="통과" className="size-4 shrink-0 text-success" /> : <X aria-label="통과 못 함" className="size-4 shrink-0 text-ink-muted" />}
                <span className="text-body-sm font-semibold text-ink">{t.name}</span>
              </span>
              <span className="num flex items-center gap-2 text-label text-ink-muted">
                {t.checks.length > 0 && (
                  <>
                    조건 {passed}/{t.checks.length}
                  </>
                )}
                <Badge tone={TECH_STATE_TONE[t.state] ?? "neutral"}>{labelOf(TECH_STATE, t.state)}</Badge>
              </span>
            </summary>
            <div className="px-4 pb-3">
              {t.checks.length > 0 && (
                <table className="w-full">
                  <thead className="sr-only">
                    <tr>
                      <th scope="col">결과</th>
                      <th scope="col">조건</th>
                      <th scope="col">지금 값</th>
                      <th scope="col">기준</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.checks.map((c) => (
                      <tr key={c.key} className="text-body-sm">
                        <td className="w-6 py-1 align-top">{c.passed ? <Check aria-label="통과" className="mt-1 size-4 text-success" /> : <X aria-label="미달" className="mt-1 size-4 text-danger" />}</td>
                        <td className="py-1 pr-3 align-top text-ink">{c.label}</td>
                        <td className="num py-1 pr-3 text-right align-top font-semibold text-ink sm:whitespace-nowrap">{checkValueText(c.value, c.threshold)}</td>
                        <td className="num py-1 text-right align-top text-label text-ink-muted sm:whitespace-nowrap">기준 {c.threshold}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {t.plan && (
                <p className="num mt-2 rounded-md border border-divider bg-accent-subtle px-3 py-2 text-body-sm text-ink">
                  <span className="font-semibold text-accent">계획</span> {planText(t.plan)} · 손절 {num(t.plan.stop)}원{t.plan.target ? ` · 목표 ${num(t.plan.target)}원` : ""}
                  {t.plan.max_hold_days ? ` · 최대 ${t.plan.max_hold_days}거래일 보유` : ""}
                </p>
              )}
              {t.notes.map((note) => (
                <p key={note} className="mt-2 text-label text-ink-muted">
                  {note}
                </p>
              ))}
            </div>
          </details>
        );
      })}
    </div>
  );
}

// ── 최종 판단 ───────────────────────────────────────────────────────────

export function FinalCard({ final }: { final: FinalDecision }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ActionBadge action={final.action} />
        {final.status !== "ok" && <ActionBadge action={final.action} review />}
        <span className="text-body-sm text-ink-secondary">
          확신 {labelOf(CONVICTION, final.conviction)} · {sourceLabel(final.source)}
          {final.action === "BUY" && final.size_fraction < 1 && <> · 계획 수량의 {pct(final.size_fraction, 0, false)}</>}
        </span>
      </div>
      {final.status !== "ok" && final.status_detail && (
        <p className="rounded-md border border-warning/50 bg-warning-subtle px-3 py-2 text-body-sm text-warning">AI 판단을 쓸 수 없어 보류로 처리했습니다. 사유: {final.status_detail}</p>
      )}
      <p className="text-h6 text-ink">{final.thesis}</p>
      {final.key_risks.length > 0 && (
        <div>
          <h3 className="text-body-sm font-semibold text-ink">위험 요인</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-body-sm text-ink-secondary">
            {final.key_risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      )}
      {final.invalidation && (
        <div>
          <h3 className="text-body-sm font-semibold text-ink">판단을 바꿀 조건</h3>
          <p className="mt-1 text-body-sm text-ink-secondary">{final.invalidation}</p>
        </div>
      )}
      {final.dissent && (
        <div>
          <h3 className="text-body-sm font-semibold text-ink">반대 의견</h3>
          <p className="mt-1 text-body-sm text-ink-secondary">{final.dissent}</p>
        </div>
      )}
    </div>
  );
}

// ── 리스크 점검 ─────────────────────────────────────────────────────────

export function GateSteps({ gate }: { gate: Gate }) {
  return (
    <div>
      <p className="text-body-sm text-ink">
        <Badge tone={gate.approved ? "success" : "danger"}>{gate.approved ? "통과" : "거부"}</Badge>{" "}
        <span className="num">
          {gate.approved ? (
            <>
              {num(gate.qty)}주 · 주문 금액 {num(gate.order_value)}원 · 손절 시 손실 {num(gate.risk_amount)}원
              {gate.base_qty > gate.qty && <> (처음 계산한 {num(gate.base_qty)}주에서 줄임)</>}
            </>
          ) : (
            gate.summary
          )}
        </span>
      </p>
      <ol className="mt-3 space-y-2">
        {gate.steps.map((step, i) => (
          <li key={`${step.rule}-${i}`} className="flex items-start gap-2 text-body-sm">
            <Badge tone={GATE_TONE[step.outcome] ?? "neutral"} className="mt-1 shrink-0">
              {labelOf(GATE_OUTCOME, step.outcome)}
            </Badge>
            <span className="num min-w-0 text-ink-secondary">
              <span className="font-semibold text-ink">{labelOf(GATE_RULE, step.rule)}</span> · {step.detail}
              {/* 줄인 수량이 설명에 이미 있으면("18주 → 13주") 다시 붙이지 않는다 */}
              {step.qty_after !== null && step.outcome === "reduce" && !step.detail.includes("→") && <> → {num(step.qty_after)}주</>}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-label text-ink-muted">리스크 점검은 수량을 줄이거나 거부할 수만 있고, 늘리지는 못합니다.</p>
    </div>
  );
}
