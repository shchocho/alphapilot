/** 통장정리: 엔진이 한 일을 통장 거래내역처럼 한 줄씩 적는다. 절취선 위가 아직 확인하지 않은 기록이다. */

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button, cx, Empty, ErrorState, Modal, SkeletonRows } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { clock, dayShort, num, seqLabel } from "@/lib/format";
import { kindTone } from "@/lib/labels";
import { notifyError, queryClient } from "@/lib/queries";
import type { Dashboard, LedgerRow } from "@/lib/types";

const KIND_CLASS: Record<ReturnType<typeof kindTone>, string> = {
  plan: "font-semibold text-accent",
  warn: "font-semibold text-warning",
  danger: "font-semibold text-danger",
  strong: "font-bold text-ink",
  plain: "text-ink-secondary",
};

/** 매수는 돈이 나가므로 −, 매도는 들어오므로 +. 체결이 아닌 기록의 금액은 부호 없이 적는다. */
export function amountText(row: LedgerRow): string {
  if (row.amount === null) return "";
  if (row.kind === "fill_buy") return `−${num(row.amount)}`;
  if (row.kind === "fill_sell" || row.kind === "protective") return `+${num(row.amount)}`;
  return num(row.amount);
}

const hasNumbers = (row: LedgerRow): boolean => row.qty !== null || row.amount !== null || row.cash_after !== null;
const isFill = (row: LedgerRow): boolean => row.kind === "fill_buy" || row.kind === "fill_sell" || row.kind === "protective";

/** 내용이 적요와 같은 말로 시작하면 그 앞머리를 뗀다("장후 심의 · 신호 …" → "신호 …"). */
export function summaryText(row: LedgerRow): string {
  const prefix = `${row.kind_label} · `;
  return row.summary.startsWith(prefix) ? row.summary.slice(prefix.length) : row.summary;
}

/** 날짜 칸: 시뮬레이션은 하루 단위라 날짜만, 모의투자·실전은 시각까지 적는다. */
function When({ row }: { row: LedgerRow }) {
  const day = dayShort(row.day ?? row.ts);
  return row.env === "sim" ? <>{day}</> : (
    <>
      {day} <span className="text-ink-muted">{clock(row.ts)}</span>
    </>
  );
}

/** 거래번호. 같은 판단에서 나온 줄들이 사슬 번호로 묶여 있으면, 눌러서 그 사슬을 처음부터 따라가 볼 수 있다. */
function SeqNumber({ row, onFollow }: { row: LedgerRow; onFollow?: (chainId: string) => void }) {
  if (!onFollow || !row.chain_id) return <span className="stamp text-ink-muted">{seqLabel(row.seq)}</span>;
  return (
    <button
      type="button"
      onClick={() => onFollow(row.chain_id)}
      aria-label={`거래번호 ${seqLabel(row.seq)}의 판단 사슬 보기`}
      className="stamp tap -mx-1 -my-2 rounded-xs px-1 py-2 text-ink-secondary underline decoration-border decoration-dotted underline-offset-4 transition-colors duration-(--duration-fast) hover:text-ink hover:decoration-ink-muted"
    >
      {seqLabel(row.seq)}
    </button>
  );
}

function StockName({ row }: { row: LedgerRow }) {
  if (!row.name) return null;
  return row.code ? (
    <Link to={`/stocks/${row.code}`} className="font-semibold text-ink no-underline hover:underline">
      {row.name}
    </Link>
  ) : (
    <span className="font-semibold text-ink">{row.name}</span>
  );
}

interface LedgerTableProps {
  rows: LedgerRow[];
  tearAfter?: number;
  freshAfter?: number | null;
  /** 거래번호를 눌러 판단 사슬을 여는 기능. 사슬 자체를 보여주는 곳에서는 끈다. */
  followChains?: boolean;
  /** "list": 넓은 화면에서도 두 줄짜리 목록으로 그린다(대화상자 안처럼 좁은 곳). */
  layout?: "auto" | "list";
}

export function LedgerTable({ rows, tearAfter, freshAfter, followChains = true, layout = "auto" }: LedgerTableProps) {
  const [chainId, setChainId] = useState<string | null>(null);
  const onFollow = followChains ? setChainId : undefined;
  // tearAfter: 이 번호보다 큰 줄이 새 기록. 새 기록과 확인한 기록 사이에 절취선을 넣는다.
  const tearIndex = tearAfter === undefined ? -1 : rows.findIndex((r) => r.seq <= tearAfter);
  const showTear = tearAfter !== undefined && (tearIndex >= 0 || rows.length > 0);
  const tearAt = tearIndex >= 0 ? tearIndex : rows.length;
  const justIn = (row: LedgerRow) => freshAfter !== null && freshAfter !== undefined && row.seq > freshAfter;

  const tear = (
    <div className="flex items-center gap-3 px-3 py-2 text-label text-ink-muted" role="separator" aria-label="여기까지 확인함">
      <span className="tear flex-1" />
      여기까지 확인함
      <span className="tear flex-1" />
    </div>
  );

  return (
    <>
      <table className={cx("w-full table-fixed", layout === "list" ? "hidden" : "hidden md:table")}>
        <colgroup>
          <col className="w-14" />
          <col className="w-16" />
          <col className="w-28" />
          <col />
          <col className="w-14" />
          <col className="w-26" />
          <col className="w-28" />
        </colgroup>
        <thead>
          <tr className="text-label text-ink-muted">
            {["번호", "날짜", "적요", "종목 · 내용"].map((h) => (
              <th key={h} scope="col" className="border-b border-divider px-3 py-2 text-left font-semibold">
                {h}
              </th>
            ))}
            {["수량", "금액", "현금 잔액"].map((h) => (
              <th key={h} scope="col" className="border-b border-divider px-3 py-2 text-right font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <FragmentRow key={row.seq} tear={showTear && i === tearAt ? tear : null}>
              <tr className={cx("align-top", justIn(row) && "row-new")}>
                <td className="border-b border-divider px-3 py-2">
                  <SeqNumber row={row} onFollow={onFollow} />
                </td>
                <td className="num border-b border-divider px-3 py-2 text-body-sm text-ink-secondary">
                  <When row={row} />
                </td>
                <td className={cx("border-b border-divider px-3 py-2 text-body-sm whitespace-nowrap", KIND_CLASS[kindTone(row.kind)])}>{row.kind_label}</td>
                <td colSpan={hasNumbers(row) ? 1 : 4} className="border-b border-divider px-3 py-2 text-body-sm">
                  <StockName row={row} />
                  <span className={cx("num text-ink-secondary", row.name ? "ml-2" : "text-ink")}>{summaryText(row)}</span>
                </td>
                {hasNumbers(row) && (
                  <>
                    <td className="num border-b border-divider px-3 py-2 text-right text-body-sm text-ink">{row.qty !== null ? num(row.qty) : ""}</td>
                    <td className={cx("num border-b border-divider px-3 py-2 text-right text-body-sm", kindTone(row.kind) === "strong" || row.kind === "protective" ? "font-semibold text-ink" : "text-ink-secondary")}>{amountText(row)}</td>
                    <td className="num border-b border-divider px-3 py-2 text-right text-body-sm text-ink">{row.cash_after !== null ? num(row.cash_after) : ""}</td>
                  </>
                )}
              </tr>
            </FragmentRow>
          ))}
          {showTear && tearAt === rows.length && (
            <tr>
              <td colSpan={7} className="p-0">
                {tear}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <ul className={layout === "list" ? "" : "md:hidden"}>
        {rows.map((row, i) => (
          <li key={row.seq}>
            {showTear && i === tearAt && tear}
            <div className={cx("border-b border-divider px-4 py-3", justIn(row) && "row-new")}>
              <div className="flex items-baseline justify-between gap-3">
                <p className="min-w-0 text-body-sm">
                  <span className={KIND_CLASS[kindTone(row.kind)]}>{row.kind_label}</span> <StockName row={row} />
                </p>
                {/* 체결된 줄의 금액만 잉크로 굵게. 아직 일어나지 않은 계획의 금액은 보통 굵기(넓은 화면의 표와 같다) */}
                <span className={cx("num shrink-0 text-body-sm", isFill(row) ? "font-semibold text-ink" : "text-ink-secondary")}>{amountText(row)}</span>
              </div>
              <p className="num mt-1 text-body-sm text-ink-secondary">
                {summaryText(row)}
                {isFill(row) && row.qty !== null && <> · {num(row.qty)}주</>}
              </p>
              <p className="num mt-1 flex justify-between gap-3 text-label text-ink-muted">
                <span>
                  <SeqNumber row={row} onFollow={onFollow} /> · <When row={row} />
                </span>
                {row.cash_after !== null && <span>현금 잔액 {num(row.cash_after)}</span>}
              </p>
            </div>
          </li>
        ))}
        {showTear && tearAt === rows.length && <li>{tear}</li>}
      </ul>
      {followChains && <ChainDialog chainId={chainId} onClose={() => setChainId(null)} />}
    </>
  );
}

interface ChainView {
  chain_id: string;
  code: string | null;
  name: string | null;
  decision_id: string | null;
  rows: LedgerRow[];
}

/** 판단 사슬: 한 종목에 대한 한 번의 판단이 신호 → 심의 → 리스크 점검 → 계획 → 승인 → 체결 → 청산으로 이어진 줄들. */
function ChainDialog({ chainId, onClose }: { chainId: string | null; onClose: () => void }) {
  const chain = useQuery({ queryKey: ["chain", chainId], queryFn: () => api.get<ChainView>(`/api/ledger/chain/${chainId}`), enabled: chainId !== null });
  return (
    <Modal
      open={chainId !== null}
      onOpenChange={(open) => !open && onClose()}
      title={chain.data?.name ? `${chain.data.name} · 판단 사슬` : "판단 사슬"}
      description="같은 판단에서 나온 기록을 처음부터 차례로 적었습니다. 위가 먼저 일어난 일입니다."
      wide
    >
      {chain.isPending ? (
        <SkeletonRows rows={4} />
      ) : chain.isError ? (
        <ErrorState message={errorMessage(chain.error)} onRetry={() => void chain.refetch()} />
      ) : chain.data.rows.length === 0 ? (
        <p className="text-body-sm text-ink-secondary">이 번호로 묶인 다른 기록이 없습니다.</p>
      ) : (
        <>
          {/* 대화상자 안쪽 여백(p-6)만큼 넓혀 줄 구분선이 가장자리까지 닿게 한다 */}
          <div className="-mx-6 border-y border-divider">
            <LedgerTable rows={chain.data.rows} followChains={false} layout="list" />
          </div>
          {chain.data.decision_id && (
            <Link to={`/committee/${chain.data.decision_id}`} onClick={onClose} className="mt-2 inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold text-accent hover:text-accent-hover">
              회의 보기
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          )}
        </>
      )}
    </Modal>
  );
}

function FragmentRow({ tear, children }: { tear: React.ReactNode; children: React.ReactNode }) {
  return (
    <>
      {tear && (
        <tr>
          <td colSpan={7} className="p-0">
            {tear}
          </td>
        </tr>
      )}
      {children}
    </>
  );
}

/** 심의 전에 걸러진 후보(순위 밖, 시장 국면 등으로 사전 제외). 양이 많고 내가 할 일이 없어서 기본으로 접어 둔다. */
const QUIET_KINDS = new Set(["screen_out", "precheck"]);
const FIRST_ROWS = 14;

export function Passbook({ book, className }: { book: Dashboard["passbook"]; className?: string }) {
  const [busy, setBusy] = useState(false);
  const [showQuiet, setShowQuiet] = useState(false);
  const all = [...book.rows, ...book.older];
  const quiet = all.filter((r) => QUIET_KINDS.has(r.kind)).length;
  const filtered = showQuiet ? all : all.filter((r) => !QUIET_KINDS.has(r.kind));
  const [limit, setLimit] = useState(FIRST_ROWS);
  const rows = filtered.slice(0, limit);
  // 절취선은 그 자리가 지금 보이는 줄 안에 있을 때만 긋는다(가려진 줄에도 새 기록이 있으면 끝에 긋지 않는다).
  const tearInView = filtered.length <= limit || rows.some((r) => r.seq <= book.seen_seq);

  // 화면이 열린 뒤에 새로 들어온 줄만 잠깐 보라색으로 비춘다(처음 그릴 때는 비추지 않는다).
  const shownSeq = useRef<number | null>(null);
  const freshAfter = shownSeq.current;
  useEffect(() => {
    shownSeq.current = book.last_seq;
  }, [book.last_seq]);

  const markSeen = async () => {
    setBusy(true);
    try {
      await api.post("/api/ledger/seen", { seq: book.last_seq });
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["dashboard"] }), queryClient.invalidateQueries({ queryKey: ["status"] })]);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const parts = [`새 기록 ${num(book.new_count)}건`];
  if (book.fills) parts.push(`체결 ${num(book.fills)}건`);
  if (book.blocks) parts.push(`리스크 거부 ${num(book.blocks)}건`);
  if (book.passes) parts.push(`걸러지거나 체결 안 된 계획 ${num(book.passes)}건`);

  return (
    <section className={cx("overflow-hidden rounded-lg border border-divider bg-surface", className)} aria-labelledby="passbook-title">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-4 py-3">
        <div className="min-w-0">
          <h2 id="passbook-title" className="text-h6 font-bold text-ink">
            통장정리
          </h2>
          <p className="num text-body-sm text-ink-secondary">{book.new_count > 0 ? parts.join(" · ") : "지난번 확인한 뒤로 새 기록이 없습니다"}</p>
        </div>
        <Button size="sm" busy={busy} disabled={book.new_count === 0} onClick={() => void markSeen()}>
          여기까지 확인
        </Button>
      </header>
      {quiet > 0 && (
        <p className="num flex flex-wrap items-center justify-between gap-x-3 border-b border-divider px-4 py-1 text-body-sm text-ink-secondary">
          <span>{showQuiet ? `심의 전에 걸러진 후보 ${num(quiet)}건도 함께 보는 중입니다` : `심의 전에 걸러진 후보 ${num(quiet)}건은 접어 두었습니다`}</span>
          <Button size="sm" variant="ghost" aria-pressed={showQuiet} onClick={() => setShowQuiet((v) => !v)} className="-mr-3">
            {showQuiet ? "접기" : "펼쳐 보기"}
          </Button>
        </p>
      )}
      {all.length === 0 ? (
        <Empty title="아직 적힌 거래가 없습니다" action={<Link to="/auto">자동매매에서 거래일 진행하기</Link>}>
          엔진을 켜고 거래일을 진행하면 매수·매도·거절한 이유가 여기에 한 줄씩 적힙니다.
        </Empty>
      ) : (
        <>
          <LedgerTable rows={rows} tearAfter={tearInView ? book.seen_seq : undefined} freshAfter={freshAfter} />
          <div className="flex flex-wrap items-center justify-between gap-x-4 px-4 py-2">
            {filtered.length > limit ? (
              <Button size="sm" variant="ghost" onClick={() => setLimit(filtered.length)} className="num -ml-3">
                나머지 {num(filtered.length - limit)}줄 더 보기
              </Button>
            ) : (
              <span />
            )}
            <Link to="/portfolio?tab=ledger" className="inline-flex min-h-11 items-center gap-1 text-body-sm font-semibold text-accent hover:text-accent-hover">
              장부 전체 보기
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
        </>
      )}
    </section>
  );
}
