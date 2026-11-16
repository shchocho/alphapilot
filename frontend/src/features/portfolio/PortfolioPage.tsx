/** 포트폴리오: 보유 종목, 주문 계획, 체결 내역, 매매일지, 전체 장부. */

import { useQuery } from "@tanstack/react-query";
import { Download, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PnlBars } from "@/components/charts";
import { Badge, Button, cx, Delta, Empty, ErrorState, PageHeader, Panel, SkeletonRows, Stat, Tabs, ToggleGroup, TD, TDR, TH, THR } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dayDots, dayLabel, labelOf, num, pct, won, wonExact, wonSigned } from "@/lib/format";
import { entryText, exitPlanText, heldText, INTENT_STATUS, INTENT_TONE } from "@/lib/labels";
import { notifyError, usePortfolio } from "@/lib/queries";
import type { IntentCard, JournalEntry, LedgerRow, Portfolio, PositionRow, Trade } from "@/lib/types";
import { LedgerTable } from "../dashboard/Passbook";

type Tab = "positions" | "orders" | "trades" | "journal" | "ledger";
const TABS: { value: Tab; label: string }[] = [
  { value: "positions", label: "보유 종목" },
  { value: "orders", label: "주문 계획" },
  { value: "trades", label: "체결 내역" },
  { value: "journal", label: "매매일지" },
  { value: "ledger", label: "장부" },
];

export default function PortfolioPage() {
  const [params, setParams] = useSearchParams();
  const portfolio = usePortfolio();
  const tab = (TABS.find((t) => t.value === params.get("tab"))?.value ?? "positions") as Tab;

  if (portfolio.isPending) return <SkeletonRows rows={8} label="포트폴리오를 불러오는 중" />;
  if (portfolio.isError) return <ErrorState message={errorMessage(portfolio.error)} onRetry={() => void portfolio.refetch()} />;
  const p = portfolio.data;
  const s = p.summary;

  return (
    <div>
      <PageHeader title="포트폴리오" lead={`${p.source_label} 계좌 · ${dayLabel(p.as_of)} 종가 기준`} />
      <dl className="mb-4 grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-divider bg-surface p-4 sm:grid-cols-3 xl:grid-cols-6">
        <Stat label="평가 금액">{won(s.equity)}</Stat>
        <Stat label="현금">{won(s.cash)}</Stat>
        <Stat label="주식">{won(s.invested)}</Stat>
        <Stat label="평가 손익" hint="보유 종목">
          <Delta value={s.unrealized}>{wonSigned(s.unrealized)}</Delta>
        </Stat>
        <Stat label="실현 손익" hint="판 종목 합계">
          <Delta value={s.realized}>{wonSigned(s.realized)}</Delta>
        </Stat>
        <Stat label="끝난 거래" hint={s.win_rate !== null ? `이익 본 비율 ${pct(s.win_rate, 0, false)}` : undefined}>
          {num(s.closed_trades)}건
        </Stat>
      </dl>

      <div className="mb-3">
        <Tabs label="포트폴리오 보기" value={tab} onChange={(value) => setParams(value === "positions" ? {} : { tab: value }, { replace: true })} items={TABS} />
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "positions" && <Positions rows={p.positions} equity={s.equity} />}
        {tab === "orders" && <Orders rows={p.intents} />}
        {tab === "trades" && <Trades rows={p.trades} />}
        {tab === "journal" && <Journal p={p} />}
        {tab === "ledger" && <Ledger />}
      </div>
    </div>
  );
}

// ── 보유 종목 ───────────────────────────────────────────────────────────

function Positions({ rows, equity }: { rows: PositionRow[]; equity: number }) {
  if (rows.length === 0) {
    return (
      <Panel>
        <Empty title="보유 종목이 없습니다" action={<Link to="/discover">종목 발굴 보기</Link>}>
          지금은 평가 금액 {won(equity)}이 모두 현금입니다.
        </Empty>
      </Panel>
    );
  }
  return (
    <Panel bodyClassName="">
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                종목
              </th>
              {["수량", "평균 단가", "현재가", "평가 금액", "평가 손익", "비중", "손절 가격", "목표 가격"].map((h) => (
                <th key={h} scope="col" className={THR}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code}>
                <td className={TD}>
                  <Link to={`/stocks/${r.code}`} className="text-h6 font-semibold text-ink no-underline hover:underline">
                    {r.name}
                  </Link>
                  <span className="num block text-label text-ink-muted">
                    {r.technique_name} · {dayLabel(r.opened_on)} 매수 · {heldText(r.days_held)}
                  </span>
                </td>
                <td className={TDR}>{num(r.qty)}</td>
                <td className={TDR}>{num(r.avg_price)}</td>
                <td className={TDR}>{num(r.price)}</td>
                <td className={TDR}>{num(r.value)}</td>
                <td className={TDR}>
                  <Delta value={r.pnl}>{wonSigned(r.pnl)}</Delta>
                  <Delta value={r.pnl} className="block text-label">
                    {pct(r.pnl_pct)}
                  </Delta>
                </td>
                <td className={TDR}>{pct(r.weight, 1, false)}</td>
                <td className={TDR}>
                  {num(r.stop)}
                  {r.stop_distance !== null && <span className="block text-label text-ink-muted">{pct(-r.stop_distance, 1)}</span>}
                </td>
                <td className={TDR}>
                  {r.target ? num(r.target) : <span className="text-label whitespace-normal text-ink-muted">{exitPlanText(r)}</span>}
                  {r.target_distance !== null && <span className="block text-label text-ink-muted">{pct(r.target_distance, 1)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="lg:hidden">
        {rows.map((r) => (
          <li key={r.code} className="border-b border-divider px-4 py-3 last:border-b-0">
            <div className="flex items-baseline justify-between gap-3">
              <Link to={`/stocks/${r.code}`} className="min-w-0 truncate text-h6 font-semibold text-ink no-underline">
                {r.name}
              </Link>
              <Delta value={r.pnl} className="text-body-sm font-semibold">
                {wonSigned(r.pnl)} ({pct(r.pnl_pct)})
              </Delta>
            </div>
            <p className="num mt-1 text-body-sm text-ink-secondary">
              {num(r.qty)}주 · 평균 {num(r.avg_price)}원 · 현재 {num(r.price)}원 · 비중 {pct(r.weight, 1, false)}
            </p>
            <p className="num mt-1 text-label text-ink-muted">
              손절 {num(r.stop)}원{r.stop_distance !== null && <> ({pct(-r.stop_distance, 1)})</>} · {exitPlanText(r)} · {heldText(r.days_held)}
            </p>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// ── 주문 계획 ───────────────────────────────────────────────────────────

function Orders({ rows }: { rows: IntentCard[] }) {
  if (rows.length === 0) {
    return (
      <Panel>
        <Empty title="주문 계획이 없습니다">위원회가 매수·매도를 결정하면 다음 거래일 주문 계획이 여기에 쌓입니다.</Empty>
      </Panel>
    );
  }
  return (
    <Panel bodyClassName="overflow-x-auto">
      <table className="w-full min-w-160">
        <thead>
          <tr>
            <th scope="col" className={TH}>
              주문일
            </th>
            <th scope="col" className={TH}>
              종목
            </th>
            <th scope="col" className={TH}>
              계획
            </th>
            <th scope="col" className={THR}>
              수량
            </th>
            <th scope="col" className={THR}>
              예상 가격
            </th>
            <th scope="col" className={TH}>
              상태
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="align-top">
              <td className={cx(TD, "num whitespace-nowrap")}>{dayDots(r.trade_date)}</td>
              <td className={TD}>
                <Link to={`/stocks/${r.code}`} className="font-semibold text-ink no-underline hover:underline">
                  {r.name}
                </Link>
                {r.technique_name && <span className="block text-label text-ink-muted">{r.technique_name}</span>}
              </td>
              <td className={cx(TD, "num text-ink-secondary")}>
                <span className="font-semibold text-ink">{r.side === "buy" ? "매수" : "매도"}</span> · {entryText(r)}
                {r.note && <span className="block text-label text-ink-muted">{r.note}</span>}
              </td>
              <td className={TDR}>{num(r.qty)}</td>
              <td className={TDR}>{num(r.est_price)}</td>
              <td className={cx(TD, "whitespace-nowrap")}>
                <Badge tone={INTENT_TONE[r.status] ?? "neutral"}>{labelOf(INTENT_STATUS, r.status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

// ── 체결 내역 ───────────────────────────────────────────────────────────

function Trades({ rows }: { rows: Trade[] }) {
  if (rows.length === 0) {
    return (
      <Panel>
        <Empty title="체결된 거래가 없습니다">주문이 체결되면 가격·수수료·세금과 함께 여기에 적힙니다.</Empty>
      </Panel>
    );
  }
  return (
    <Panel bodyClassName="overflow-x-auto">
      <table className="w-full min-w-176">
        <thead>
          <tr>
            <th scope="col" className={TH}>
              날짜
            </th>
            <th scope="col" className={TH}>
              종목
            </th>
            <th scope="col" className={TH}>
              구분
            </th>
            {["수량", "가격", "금액", "수수료·세금", "손익"].map((h) => (
              <th key={h} scope="col" className={THR}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id}>
              <td className={cx(TD, "num whitespace-nowrap")}>{dayDots(t.day)}</td>
              <td className={TD}>
                <Link to={`/stocks/${t.code}`} className="font-semibold text-ink no-underline hover:underline">
                  {t.name}
                </Link>
              </td>
              <td className={cx(TD, "whitespace-nowrap")}>{t.reason_label ?? (t.side === "buy" ? "매수" : "매도")}</td>
              <td className={TDR}>{num(t.qty)}</td>
              <td className={TDR}>{num(t.price)}</td>
              <td className={TDR}>{num(t.amount)}</td>
              <td className={TDR}>{num(t.fee + t.tax)}</td>
              <td className={TDR}>
                {t.pnl !== null ? (
                  <Delta value={t.pnl}>
                    {wonSigned(t.pnl)}
                    {t.pnl_pct !== null && <> ({pct(t.pnl_pct, 1)})</>}
                  </Delta>
                ) : (
                  ""
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

// ── 매매일지 ────────────────────────────────────────────────────────────

function Journal({ p }: { p: Portfolio }) {
  const rows = p.journal;
  return (
    <div className="space-y-4">
      <Panel title="날짜별 실현 손익">
        {p.daily_pnl.length === 0 ? (
          <p className="text-body-sm text-ink-secondary">판 종목이 생기면 날짜별 손익을 막대로 보여줍니다.</p>
        ) : (
          <PnlBars data={p.daily_pnl.map((d) => ({ d: d.d, value: d.pnl }))} format={(v) => wonSigned(v)} tickFormat={(v) => wonExact(v)} label={`날짜별 실현 손익. ${p.daily_pnl.length}일 가운데 이익 본 날 ${p.daily_pnl.filter((d) => d.pnl > 0).length}일.`} />
        )}
      </Panel>
      <Panel title="매수에서 매도까지" bodyClassName={rows.length === 0 ? undefined : "overflow-x-auto"}>
        {rows.length === 0 ? (
          <Empty title="아직 끝난 거래가 없습니다">한 종목을 사서 팔 때까지를 한 줄로 묶어 보여줍니다.</Empty>
        ) : (
          <table className="w-full min-w-176">
            <thead>
              <tr>
                <th scope="col" className={TH}>
                  종목
                </th>
                <th scope="col" className={TH}>
                  매수
                </th>
                <th scope="col" className={TH}>
                  매도
                </th>
                <th scope="col" className={THR}>
                  보유
                </th>
                <th scope="col" className={THR}>
                  손익
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <JournalRow key={`${j.chain_id}-${j.buy?.id}`} j={j} />
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function JournalRow({ j }: { j: JournalEntry }) {
  return (
    <tr className="align-top">
      <td className={TD}>
        <Link to={`/stocks/${j.code}`} className="font-semibold text-ink no-underline hover:underline">
          {j.name}
        </Link>
        <span className="block text-label text-ink-muted">{j.technique_name}</span>
      </td>
      <td className={cx(TD, "num whitespace-nowrap")}>
        {j.buy && (
          <>
            {dayDots(j.buy.day)}
            <span className="block text-label text-ink-muted">
              {num(j.buy.qty)}주 · {num(j.buy.price)}원
            </span>
          </>
        )}
      </td>
      <td className={cx(TD, "num whitespace-nowrap")}>
        {j.sell ? (
          <>
            {dayDots(j.sell.day)}
            <span className="block text-label text-ink-muted">
              {num(j.sell.price)}원 · {j.sell.reason_label}
            </span>
          </>
        ) : (
          <Badge tone="neutral">보유 중</Badge>
        )}
      </td>
      <td className={TDR}>{j.sell?.hold_days !== null && j.sell?.hold_days !== undefined ? `${j.sell.hold_days}일` : ""}</td>
      <td className={TDR}>
        {j.sell && j.sell.pnl !== null ? (
          <Delta value={j.sell.pnl}>
            {wonSigned(j.sell.pnl)}
            {j.sell.pnl_pct !== null && <span className="block text-label">{pct(j.sell.pnl_pct, 1)}</span>}
          </Delta>
        ) : (
          ""
        )}
      </td>
    </tr>
  );
}

// ── 장부 ────────────────────────────────────────────────────────────────

const LEDGER_FILTERS = [
  { value: "all", label: "전체", kinds: "" },
  { value: "fills", label: "체결", kinds: "fill_buy,fill_sell,protective,stop_raise" },
  { value: "plans", label: "계획·승인", kinds: "intent,approve,reject,expire,skip" },
  { value: "judge", label: "판단·점검", kinds: "decision,gate_reduce,gate_block,precheck,screen_out,cycle,regime" },
  { value: "engine", label: "엔진·설정", kinds: "engine,settings,breaker,data,broker,error" },
] as const;
type LedgerFilter = (typeof LEDGER_FILTERS)[number]["value"];

function Ledger() {
  const [filter, setFilter] = useState<LedgerFilter>("all");
  const [limit, setLimit] = useState(100);
  const [checking, setChecking] = useState(false);
  const kinds = LEDGER_FILTERS.find((f) => f.value === filter)?.kinds ?? "";
  const ledger = useQuery({
    queryKey: ["ledger", filter, limit],
    queryFn: () => api.get<{ rows: LedgerRow[] }>(`/api/ledger?limit=${limit}${kinds ? `&kind=${kinds}` : ""}`),
    placeholderData: (prev) => prev,
  });

  const verify = async () => {
    setChecking(true);
    try {
      const result = await api.get<{ ok: boolean; broken_seq: number | null }>("/api/ledger/verify");
      if (result.ok) toast.success("장부가 처음부터 끝까지 이어져 있습니다. 고치거나 지운 줄이 없습니다");
      else toast.error(`거래번호 ${result.broken_seq}에서 기록이 어긋납니다. 누군가 장부를 고쳤을 수 있습니다`);
    } catch (e) {
      notifyError(e);
    } finally {
      setChecking(false);
    }
  };

  const rows = ledger.data?.rows ?? [];
  return (
    <Panel
      bodyClassName=""
      title="장부"
      actions={
        <>
          <Button size="sm" busy={checking} icon={<ShieldCheck aria-hidden className="size-4" />} onClick={() => void verify()}>
            위변조 검사
          </Button>
          <a href="/api/ledger/export.csv" download className="tap inline-flex h-8 items-center gap-1 rounded-md bg-secondary px-3 text-label font-semibold text-ink no-underline hover:bg-secondary">
            <Download aria-hidden className="size-4" />
            CSV 내려받기
          </a>
        </>
      }
    >
      <div className="border-b border-divider p-3">
        <ToggleGroup
          label="장부 종류 고르기"
          value={filter}
          onChange={(value) => {
            setFilter(value);
            setLimit(100);
          }}
          options={LEDGER_FILTERS.map((f) => ({ value: f.value, label: f.label }))}
        />
      </div>
      {ledger.isPending ? (
        <SkeletonRows rows={6} />
      ) : ledger.isError ? (
        <div className="p-4">
          <ErrorState message={errorMessage(ledger.error)} onRetry={() => void ledger.refetch()} />
        </div>
      ) : rows.length === 0 ? (
        <Empty title="해당하는 기록이 없습니다">다른 종류를 골라 보세요.</Empty>
      ) : (
        <>
          <LedgerTable rows={rows} />
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <p className="num text-label text-ink-muted">최근 {num(rows.length)}줄 · 엔진이 한 일은 지우거나 고칠 수 없게 앞줄과 이어서 적습니다</p>
            {rows.length >= limit && limit < 500 && (
              <Button size="sm" busy={ledger.isFetching} onClick={() => setLimit((v) => Math.min(500, v + 100))}>
                더 보기
              </Button>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
