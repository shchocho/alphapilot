/** 리비전: 운용 계획의 판(r1, r2, …). 판마다 바뀐 점, 그 기간 성과, 되돌리기. 지난 판은 지우지 않는다. */

import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Delta, DisclosureIcon, ErrorState, Field, Modal, Panel, SkeletonRows, SUMMARY, TextInput } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dayDots, num, pct, wonShort } from "@/lib/format";
import { notifyError } from "@/lib/queries";
import { ACTION_WORD, refreshSleeves, useRevisions } from "./data";
import type { Revision } from "./types";

const CADENCE: Record<string, string> = { daily: "매일", weekly: "매주", monthly: "매월" };
const DECIDER: Record<string, string> = { rules: "규칙", ai: "AI 위원회", hybrid: "규칙 + AI 분기" };
const MODE: Record<string, string> = { paper: "가상 운용", alert: "알림만" };

export function RevisionsPanel() {
  const q = useRevisions();
  const [restoring, setRestoring] = useState<Revision | null>(null);

  return (
    <Panel title="리비전 기록">
      {q.isPending ? (
        <SkeletonRows rows={3} label="리비전 기록을 불러오는 중" />
      ) : q.isError ? (
        <ErrorState message={errorMessage(q.error)} onRetry={() => void q.refetch()} />
      ) : (
        <>
          <p className="max-w-reading text-body-sm text-ink-secondary">
            계획을 저장할 때마다 새 판이 생깁니다. 예전 판으로 되돌리면 그 내용으로 새 판을 하나 더 만들고, 지난 판은 그대로 남습니다. 모든 판단에 그때의 판 번호가 붙습니다.
          </p>
          <ol className="mt-3 divide-y divide-divider border-y border-divider">
            {q.data.revisions.map((r) => (
              <RevisionRow key={r.rev} rev={r} onRestore={() => setRestoring(r)} />
            ))}
          </ol>
        </>
      )}
      <RestoreDialog rev={restoring} onClose={() => setRestoring(null)} />
    </Panel>
  );
}

function RevisionRow({ rev: r, onRestore }: { rev: Revision; onRestore: () => void }) {
  const signalText = Object.entries(r.signals)
    .map(([k, v]) => `${ACTION_WORD[k] ?? k} ${v}`)
    .join(" · ");
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="num text-h6 font-semibold text-ink">r{r.rev}</span>
        {r.current && <Badge tone="accent">지금 쓰는 판</Badge>}
        {r.restored_from && <Badge tone="outline">r{r.restored_from}에서 되돌림</Badge>}
        <span className="num text-caption text-ink-muted">
          {dayDots(r.day)}부터{r.period.end ? ` ${dayDots(r.period.end)}까지` : " 지금까지"} · 저장 {dayDots(r.created_at)}
        </span>
        {!r.current && (
          <Button size="sm" className="ml-auto" onClick={onRestore}>
            이 판으로 되돌리기
          </Button>
        )}
      </div>
      {r.note && <p className="mt-1 text-body-sm font-medium text-ink">{r.note}</p>}
      <ul className="mt-1 list-disc pl-5 text-body-sm text-ink-secondary">
        {r.changes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <p className="num mt-1 text-caption text-ink-muted">
        심의 {num(r.runs)}회{signalText ? ` (${signalText})` : ""} · 가상 체결 {num(r.fills)}건 · 이 판 기간 가상 운용 수익률{" "}
        {r.period.return_pct === null ? "아직 없음" : <Delta value={r.period.return_pct}>{pct(r.period.return_pct)}</Delta>}
      </p>
      <details className="mt-1">
        <summary className={SUMMARY}>
          <DisclosureIcon />이 판의 내용
        </summary>
        <div className="mt-1 space-y-3">
          <p className="num text-body-sm text-ink">총 투입 금액 {wonShort(r.config.total)}</p>
          {r.config.sleeves.map((s) => (
            <div key={s.id} className="border-t border-divider pt-2">
              <p className="text-body-sm font-semibold text-ink">
                {s.name} <span className="num font-normal text-ink-secondary">{wonShort(s.amount)}</span>
              </p>
              <p className="text-caption text-ink-muted">
                {MODE[s.mode]} · {DECIDER[s.decider]} · {CADENCE[s.cadence]} · {s.installments}회로 나눔 · 종목 {s.items.map((i) => i.name || i.code).join(", ")}
              </p>
              <p className="mt-1 max-w-reading text-body-sm whitespace-pre-wrap text-ink-secondary">{s.mandate || "운용 지침 없음"}</p>
            </div>
          ))}
        </div>
      </details>
    </li>
  );
}

function RestoreDialog({ rev, onClose }: { rev: Revision | null; onClose: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!rev) return;
    setBusy(true);
    try {
      const out = await api.post<{ rev: number }>(`/api/sleeves/revisions/${rev.rev}/restore`, { note });
      toast.success(`r${rev.rev}의 내용으로 r${out.rev}을 만들었습니다`);
      refreshSleeves();
      setNote("");
      onClose();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={rev !== null} onOpenChange={(open) => !open && onClose()} title={rev ? `r${rev.rev}으로 되돌리기` : "되돌리기"}
      description="그 판의 총액·바구니·지침·종목으로 새 판을 만듭니다. 지금까지의 판과 판단 기록은 지우지 않습니다. 가상 보유가 있는 바구니를 빼야 하거나 현금보다 많이 줄여야 하면 되돌릴 수 없습니다.">
      <Field label="변경 메모" hint="비워 두면 'r번호로 되돌림'으로 남습니다">
        {(p) => <TextInput {...p} value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      <div className="mt-2 flex justify-end gap-2">
        <Button onClick={onClose} disabled={busy}>
          취소
        </Button>
        <Button variant="primary" busy={busy} onClick={() => void submit()}>
          새 판으로 되돌리기
        </Button>
      </div>
    </Modal>
  );
}
