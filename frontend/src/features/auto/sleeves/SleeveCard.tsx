/** 바구니 한 개: 장부 요약, 최근 판단(매수·매도 타이밍), 대기 주문, 가상 보유. */

import { useState } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Badge, Button, Delta, DisclosureIcon, ErrorState, Modal, Notice, Panel, SkeletonRows, Stat, SUMMARY } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dayDots, num, pct, signed, won, wonShort } from "@/lib/format";
import { notifyError } from "@/lib/queries";
import { ACTION_TONE, ACTION_WORD, refreshSleeves, useSignal } from "./data";
import type { SleeveSignal, SleeveView, TranscriptStep } from "./types";

export function SleeveCard({ sleeve, total }: { sleeve: SleeveView; total: number }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [selling, setSelling] = useState(false);
  const paper = sleeve.mode === "paper";
  const book = sleeve.book;
  const perRound = sleeve.installments > 0 ? sleeve.amount / sleeve.installments : 0;
  const lastDay = sleeve.latest[0]?.as_of ?? null;

  const liquidate = async () => {
    setSelling(true);
    try {
      const out = await api.post<{ orders: number }>(`/api/sleeves/${sleeve.id}/liquidate`);
      toast.success(`${out.orders}종목을 다음 거래일 시가에 모두 팔도록 예약했습니다`);
      refreshSleeves();
    } catch (e) {
      notifyError(e);
    } finally {
      setSelling(false);
    }
  };

  return (
    <Panel
      title={
        <span className="flex flex-wrap items-center gap-2">
          {sleeve.name}
          <span className="num text-body-sm font-normal text-ink-muted">
            {wonShort(sleeve.amount)} · 총액의 {total > 0 ? Math.round((sleeve.amount / total) * 100) : 0}%
          </span>
        </span>
      }
      actions={
        <>
          <Badge tone="outline">{sleeve.mode_label}</Badge>
          <Badge tone="outline">{sleeve.decider_label}</Badge>
          <Badge tone="outline">{sleeve.cadence_label}</Badge>
        </>
      }
    >
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {paper ? (
          <>
            <Stat label="평가 금액" hint={`넣은 돈 ${wonShort(book.contributed)}`}>
              {won(book.equity)}
            </Stat>
            <Stat label="수익률" hint="가상 운용">
              <Delta value={book.return_pct}>{pct(book.return_pct)}</Delta>
            </Stat>
            <Stat label="남은 현금" hint={book.carry > 0 ? `다음 회차로 넘긴 금액 ${won(book.carry)}` : undefined}>
              {won(book.cash)}
            </Stat>
          </>
        ) : (
          <>
            <Stat label="배정 금액" hint="알림만 · 실제 매매는 직접">
              {won(sleeve.amount)}
            </Stat>
            <Stat label="회차 금액" hint={`${sleeve.installments}회로 나눔`}>
              {won(perRound)}
            </Stat>
            <Stat label="종목" hint="이 바구니에서 지켜봄">
              {num(sleeve.items.length)}개
            </Stat>
          </>
        )}
        <Stat label="진행 회차" hint={sleeve.due ? "오늘 심의할 차례" : book.last_run ? `마지막 심의 ${dayDots(book.last_run)}` : "아직 심의 전"}>
          {num(book.installments_done)} / {num(sleeve.installments)}
        </Stat>
      </dl>

      <section aria-label={`${sleeve.name} 최근 판단`} className="mt-4">
        <h3 className="text-body-sm font-bold text-ink">
          최근 판단{lastDay ? <span className="num ml-2 font-normal text-ink-muted">{dayDots(lastDay)} 장 마감 기준</span> : null}
        </h3>
        {sleeve.latest.length === 0 ? (
          <p className="mt-1 text-body-sm text-ink-secondary">아직 심의하지 않았습니다. 위의 "지금 심의"를 누르거나 장 마감 뒤 자동 심의를 기다리세요.</p>
        ) : (
          <ul className="mt-1 divide-y divide-divider border-y border-divider">
            {sleeve.latest.map((g) => (
              <SignalRow key={g.id} signal={g} paper={paper} onOpen={() => setOpenId(g.id)} />
            ))}
          </ul>
        )}
      </section>

      {sleeve.pending.length > 0 && (
        <section aria-label={`${sleeve.name} 대기 주문`} className="mt-4 rounded-md bg-accent-subtle p-3">
          <h3 className="text-body-sm font-bold text-ink">다음 거래일 시가에 가상 체결할 주문 {sleeve.pending.length}건</h3>
          <ul className="mt-1 space-y-1">
            {sleeve.pending.map((o) => (
              <li key={o.id} className="num flex flex-wrap gap-x-2 text-body-sm text-ink">
                <span className={o.side === "buy" ? "text-up" : "text-down"}>{o.side === "buy" ? "매수" : "매도"}</span>
                <span>{o.name}</span>
                <span>{num(o.qty)}주</span>
                {o.note && <span className="text-ink-secondary">· {o.note}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {paper && book.positions.length > 0 && (
        <details className="mt-3">
          <summary className={SUMMARY}>
            <DisclosureIcon />
            가상 보유 {book.positions.length}종목
          </summary>
          <ul className="mt-1 divide-y divide-divider">
            {book.positions.map((p) => (
              <li key={p.code} className="num flex flex-wrap items-baseline justify-between gap-x-3 py-2 text-body-sm">
                <span className="text-ink">
                  <Link to={`/stocks/${p.code}`} className="text-ink no-underline hover:underline">
                    {p.name}
                  </Link>{" "}
                  <span className="text-caption text-ink-muted">{p.code}</span>
                </span>
                <span className="text-ink-secondary">
                  {num(p.qty)}주 · 평균 {won(p.avg)} · {won(p.value)} <Delta value={p.pnl_pct}>{pct(p.pnl_pct)}</Delta>
                </span>
              </li>
            ))}
          </ul>
          <Button size="sm" variant="ghost" className="mt-2" busy={selling} onClick={() => void liquidate()}>
            모두 팔기 예약
          </Button>
        </details>
      )}

      <details className="mt-2">
        <summary className={SUMMARY}>
          <DisclosureIcon />
          운용 지침{sleeve.decider === "rules" ? "(규칙 판단에서는 쓰지 않음)" : ""}
        </summary>
        <p className="mt-1 max-w-reading text-body-sm whitespace-pre-wrap text-ink-secondary">{sleeve.mandate || "적지 않았습니다."}</p>
      </details>

      <SignalDialog id={openId} onClose={() => setOpenId(null)} />
    </Panel>
  );
}

function SignalRow({ signal: g, paper, onOpen }: { signal: SleeveSignal; paper: boolean; onOpen: () => void }) {
  const qtyText =
    g.action === "BUY" || g.action === "BUY_MORE"
      ? g.qty > 0
        ? `${paper ? "" : "권장 "}${num(g.qty)}주 · 약 ${wonShort(g.amount)}`
        : g.note || "이번에는 살 수량이 없음"
      : g.action === "WAIT"
        ? "이번 회차는 사지 않음"
        : paper
          ? g.qty > 0
            ? `${num(g.qty)}주 매도`
            : "보유 없음"
          : g.note;
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="mr-1 text-body-sm font-medium text-ink">
          <Link to={`/stocks/${g.code}`} className="text-ink no-underline hover:underline">
            {g.name}
          </Link>{" "}
          <span className="num text-caption font-normal text-ink-muted">{g.code}</span>
        </span>
        <Badge tone={ACTION_TONE[g.action]}>{g.action_label}</Badge>
        {g.status === "review" && <Badge tone="warning">검토 필요</Badge>}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={onOpen} aria-label={`${g.name} 판단 근거 보기`}>
          근거 보기
        </Button>
      </div>
      <p className="num text-body-sm text-ink">{qtyText}</p>
      <p className="num text-caption text-ink-muted">
        {g.source === "ai" ? `AI 판단 · 확신 ${g.conviction_label}` : `규칙 판단 · 좌석 점수 ${signed(g.score)}`}
        {g.action !== g.rules_action ? ` · 규칙만이었다면 ${ACTION_WORD[g.rules_action]}` : ""}
      </p>
      <p className="mt-1 line-clamp-2 max-w-reading text-body-sm text-ink-secondary">{g.thesis}</p>
    </li>
  );
}

const STANCE_WORD: Record<string, string> = { bullish: "긍정", bearish: "부정", neutral: "중립", abstain: "기권" };

function SignalDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useSignal(id);
  const g = q.data;
  return (
    <Modal open={id !== null} onOpenChange={(open) => !open && onClose()} wide title={g ? `${g.name} · ${g.action_label}` : "판단 근거"}
      description={g ? `${dayDots(g.as_of)} 장 마감 기준 · r${g.rev} · ${g.source === "ai" ? `AI 판단 · 확신 ${g.conviction_label}` : `규칙 판단 · 좌석 점수 ${signed(g.score)}`}` : undefined}>
      {q.isPending ? (
        <SkeletonRows rows={5} label="판단 근거를 불러오는 중" />
      ) : q.isError || !g ? (
        <ErrorState message={errorMessage(q.error)} onRetry={() => void q.refetch()} />
      ) : (
        <div className="space-y-4 text-body-sm">
          {g.status === "review" && <Notice tone="warning">AI 판단을 받지 못해 쉬기로 기록했습니다. {g.status_detail}</Notice>}
          <p className="max-w-reading text-ink">{g.thesis}</p>
          {g.note && <p className="text-ink-secondary">{g.note}</p>}
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-label font-medium text-ink-muted">핵심 위험</dt>
              <dd className="text-ink">{g.key_risks.length ? g.key_risks.join(" · ") : "–"}</dd>
            </div>
            <div>
              <dt className="text-label font-medium text-ink-muted">판단을 바꿀 조건</dt>
              <dd className="text-ink">{g.invalidation || "–"}</dd>
            </div>
            {g.dissent && (
              <div className="sm:col-span-2">
                <dt className="text-label font-medium text-ink-muted">반대 의견</dt>
                <dd className="text-ink">{g.dissent}</dd>
              </div>
            )}
            <div>
              <dt className="text-label font-medium text-ink-muted">좌석 종합 점수</dt>
              <dd className="num text-ink">
                {g.score >= 0 ? "+" : "−"}
                {Math.abs(g.score).toFixed(2)} · 규칙 결론 {ACTION_WORD[g.rules_action]}
              </dd>
            </div>
            <div>
              <dt className="text-label font-medium text-ink-muted">그날 종가</dt>
              <dd className="num text-ink">{won(g.close)}</dd>
            </div>
          </dl>
          {g.branch && (
            <Notice>
              애매한 분기라 AI에게 물었습니다: {g.branch.reason}. {g.branch.outcome}.
            </Notice>
          )}
          {g.seats.length > 0 && (
            <section aria-label="좌석 의견">
              <h3 className="mb-1 text-label font-semibold text-ink">좌석 의견</h3>
              <ul className="divide-y divide-divider border-y border-divider">
                {g.seats.map((s) => (
                  <li key={s.label} className="flex flex-wrap gap-x-3 py-1">
                    <span className="w-24 shrink-0 font-medium text-ink">{s.label}</span>
                    <Badge tone={s.stance === "neutral" || s.stance === "abstain" ? "outline" : "neutral"}>{STANCE_WORD[s.stance] ?? s.stance}</Badge>
                    <span className="num w-14 text-ink-secondary">
                      {s.value >= 0 ? "+" : "−"}
                      {Math.abs(s.value).toFixed(2)}
                    </span>
                    <span className="min-w-0 flex-1 text-ink-secondary">{s.summary}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {g.transcript && g.transcript.steps.length > 0 && (
            <details>
              <summary className={SUMMARY}>
                <DisclosureIcon />
                AI 심의 기록 {g.transcript.steps.length}단계 · 약 ${g.transcript.cost_usd.toFixed(3)}
              </summary>
              <ol className="mt-2 space-y-3">
                {g.transcript.steps.map((step, i) => (
                  <TranscriptItem key={`${step.role}-${i}`} step={step} />
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </Modal>
  );
}

function TranscriptItem({ step }: { step: TranscriptStep }) {
  const c = step.content;
  const lines: string[] = [];
  for (const key of ["points", "concerns", "key_risks"]) {
    const v = c[key];
    if (Array.isArray(v)) lines.push(...v.map(String));
  }
  for (const key of ["strongest_evidence", "weakest_spot", "note", "thesis", "invalidation", "dissent"]) {
    const v = c[key];
    if (typeof v === "string" && v) lines.push(v);
  }
  const head = [c.action ? ACTION_WORD[String(c.action)] ?? String(c.action) : "", c.veto === true ? "거부권" : "", c.severity ? `심각도 ${String(c.severity)}` : ""].filter(Boolean).join(" · ");
  return (
    <li>
      <p className="text-label font-semibold text-ink">
        {step.label}
        {head && <span className="ml-2 font-normal text-ink-secondary">{head}</span>}
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-secondary">
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </li>
  );
}
