/** 승인 대기 카드. 아직 일어나지 않은 계획이라 보라색 잉크로 적는다. 단추 이름에 결과(수량·금액)를 그대로 쓴다. */

import { ArrowRight, Check, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Badge, Button, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { dayLabel, labelOf, num, pct, wonAbout } from "@/lib/format";
import { CONVICTION, entryText } from "@/lib/labels";
import { notifyError, refreshAll } from "@/lib/queries";
import type { IntentCard, Votes } from "@/lib/types";

export function votesText(votes: Votes | undefined): string {
  if (!votes) return "";
  const parts = [
    votes.bullish ? `긍정 ${votes.bullish}` : "",
    votes.bearish ? `부정 ${votes.bearish}` : "",
    votes.neutral ? `중립 ${votes.neutral}` : "",
    votes.abstain ? `기권 ${votes.abstain}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

export type Outcome = "approved" | "rejected";

/**
 * 결정한 카드를 그 자리에 남겨 둔다.
 * 카드가 바로 사라지면 다음 카드의 승인 단추가 마우스 아래로 올라와, 연달아 누르면 의도하지 않은 주문을 승인하게 된다.
 */
export function useStableCards(cards: IntentCard[]) {
  const [kept, setKept] = useState<IntentCard[]>(cards);
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});

  useEffect(() => {
    setKept((prev) => {
      const live = new Map(cards.map((c) => [c.id, c]));
      // 서버 목록에서 빠졌는데 내가 결정한 것도 아니면(기한 만료 등) 지운다.
      const base = prev.filter((c) => live.has(c.id) || outcomes[c.id]).map((c) => live.get(c.id) ?? c);
      const known = new Set(base.map((c) => c.id));
      return [...base, ...cards.filter((c) => !known.has(c.id))];
    });
  }, [cards, outcomes]);

  const onDecided = useCallback((id: string, outcome: Outcome) => setOutcomes((prev) => ({ ...prev, [id]: outcome })), []);
  return { kept, outcomes, onDecided };
}

interface Props {
  card: IntentCard;
  outcome?: Outcome;
  onDecided?: (id: string, outcome: Outcome) => void;
}

export function ApprovalCard({ card, outcome, onDecided }: Props) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const sideWord = card.side === "buy" ? "매수" : "매도";
  const amount = card.amount ?? card.qty * card.est_price;

  const decide = async (approve: boolean) => {
    setBusy(approve ? "approve" : "reject");
    try {
      await api.post(`/api/intents/${card.id}/decide`, { approve, note: "" });
      onDecided?.(card.id, approve ? "approved" : "rejected");
      toast.success(approve ? `${card.name} ${sideWord} 계획을 승인했습니다. ${dayLabel(card.trade_date)}에 주문이 나갑니다` : `${card.name} ${sideWord} 계획을 거절했습니다`);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
      refreshAll();
    }
  };

  const votes = votesText(card.votes);
  const rows: [string, React.ReactNode][] = [["예상 가격", `${num(card.est_price)}원`]];
  if (card.stop) rows.push(["손절 가격", <>{num(card.stop)}원{card.risk_pct ? <span className="font-normal text-ink-secondary"> ({pct(-card.risk_pct, 1)})</span> : null}</>]);
  if (card.target) rows.push(["목표 가격", `${num(card.target)}원`]);
  if (card.technique_name) rows.push(["기법", card.technique_name]);

  return (
    <article className={cx("rounded-lg border p-4 transition-colors duration-(--duration-base)", outcome ? "border-divider bg-surface" : "border-transparent bg-accent-subtle")} aria-label={`${card.name} ${sideWord} 계획`}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {outcome ? (
          <Badge tone={outcome === "approved" ? "success" : "neutral"}>
            {outcome === "approved" ? <Check aria-hidden className="size-3" /> : <X aria-hidden className="size-3" />}
            {outcome === "approved" ? "승인함" : "거절함"}
          </Badge>
        ) : (
          <Badge tone="accent">
            {sideWord} 계획
          </Badge>
        )}
        <h3 className="text-h6 font-bold text-ink">
          <Link to={`/stocks/${card.code}`} className="no-underline hover:underline">
            {card.name}
          </Link>
        </h3>
        <span className="num text-label text-ink-muted">{card.code}</span>
      </div>

      <p className="num mt-2 text-h5 font-bold text-ink">
        {sideWord} {num(card.qty)}주 · {wonAbout(amount)}
      </p>
      <p className="num text-body-sm text-ink-secondary">
        {dayLabel(card.trade_date)} · {entryText(card)}
      </p>

      {outcome ? (
        <p role="status" className="mt-3 text-body-sm text-ink-secondary">
          {outcome === "approved" ? `승인했습니다. ${dayLabel(card.trade_date)}에 조건이 맞으면 주문이 나갑니다.` : "거절했습니다. 이 계획은 주문으로 나가지 않습니다."}
        </p>
      ) : (
        <>
          <dl className="num mt-3 space-y-1 text-body-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3">
                <dt className="shrink-0 text-ink-muted">{label}</dt>
                <dd className="min-w-0 truncate text-right font-semibold text-ink">{value}</dd>
              </div>
            ))}
          </dl>

          {(card.thesis || card.reason) && <p className="mt-3 line-clamp-3 text-body-sm text-ink-secondary">{card.thesis || card.reason}</p>}

          {(votes || card.conviction || card.gate_summary) && (
            <p className="mt-2 text-label text-ink-muted">
              {card.conviction && <>확신 {card.conviction_label ?? labelOf(CONVICTION, card.conviction)}</>}
              {card.conviction && votes && " · "}
              {votes && <>위원 의견 {votes}</>}
              {card.gate_summary && (
                <>
                  <br />
                  리스크 점검: {card.gate_summary}
                </>
              )}
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button variant="primary" busy={busy === "approve"} disabled={busy !== null} onClick={() => void decide(true)} className="num min-w-0 flex-1">
              {sideWord} 승인 · {num(card.qty)}주 · {wonAbout(amount)}
            </Button>
            <Button busy={busy === "reject"} disabled={busy !== null} onClick={() => void decide(false)}>
              거절
            </Button>
          </div>
        </>
      )}
      {card.decision_id && (
        <Link to={`/committee/${card.decision_id}`} className={cx("mt-2 inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold", outcome ? "text-ink-secondary" : "text-accent")}>
          판단 근거 보기
          <ArrowRight aria-hidden className="size-4" />
        </Link>
      )}
    </article>
  );
}
