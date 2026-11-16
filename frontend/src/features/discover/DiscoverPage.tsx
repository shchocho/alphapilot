/** 종목 발굴: 기법마다 조건을 통과한 종목을 보여준다. 기법의 규칙을 먼저 적고, 그 아래에 결과를 둔다. */

import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Sparkline } from "@/components/charts";
import { Badge, cx, Delta, Empty, ErrorState, Notice, PageHeader, Panel, SkeletonRows, TextInput } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayLabel, labelOf, num, pct, wonShort } from "@/lib/format";
import { DATA_SOURCE, planText, TECH_STATE, TECH_STATE_TONE } from "@/lib/labels";
import { useScreener, useStockSearch } from "@/lib/queries";
import type { ScreenerRow, TechniqueMeta } from "@/lib/types";

const KIND_NOTE: Record<TechniqueMeta["kind"], string> = {
  gate: "관문 기법입니다. 이 조건을 통과한 종목만 아래 진입 기법의 후보가 됩니다.",
  entry: "진입 기법입니다. 조건을 통과하면 위원회 심의에 올라갑니다.",
  value: "가치 확인용입니다. 재무 데이터가 있을 때만 의견을 내고, 매수 신호를 만들지는 않습니다.",
};

type SortKey = "score" | "change_pct" | "rs" | "value20";

export default function DiscoverPage() {
  const [params, setParams] = useSearchParams();
  const screener = useScreener(params.get("t"));
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "score", desc: true });

  const rows = useMemo(() => {
    const list = [...(screener.data?.rows ?? [])];
    list.sort((a, b) => {
      const av = a[sort.key] ?? -Infinity;
      const bv = b[sort.key] ?? -Infinity;
      return (sort.desc ? bv - av : av - bv) || a.code.localeCompare(b.code);
    });
    return list;
  }, [screener.data, sort]);

  if (screener.isPending) return <SkeletonRows rows={8} label="종목 발굴 결과를 불러오는 중" />;
  if (screener.isError) return <ErrorState message={errorMessage(screener.error)} onRetry={() => void screener.refetch()} />;
  const data = screener.data;
  const active = data.techniques.find((t) => t.key === data.technique) ?? data.techniques[0];

  const sortButton = (key: SortKey, label: string) => {
    const on = sort.key === key;
    return (
      <th scope="col" aria-sort={on ? (sort.desc ? "descending" : "ascending") : "none"} className="border-b border-divider px-3 py-0 text-right text-label font-semibold whitespace-nowrap text-ink-muted">
        <button type="button" onClick={() => setSort({ key, desc: on ? !sort.desc : true })} className={cx("inline-flex min-h-11 items-center gap-1", on && "text-ink")}>
          {label}
          {on ? sort.desc ? <ArrowDown aria-hidden className="size-4" /> : <ArrowUp aria-hidden className="size-4" /> : null}
        </button>
      </th>
    );
  };

  return (
    <div>
      <PageHeader
        title="종목 발굴"
        lead={
          <>
            {dayLabel(data.as_of)} 종가 기준으로 기법의 조건을 통과한 종목입니다. 통과했다고 바로 사지 않고, 위원회 심의와 리스크 점검을 거칩니다.
          </>
        }
        actions={<StockSearch />}
      />

      <div role="group" aria-label="기법 고르기" className="mb-3 flex gap-2 overflow-x-auto pb-1">
        {data.techniques.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-pressed={t.key === data.technique}
            onClick={() => setParams({ t: t.key }, { replace: true })}
            className={cx(
              "tap num flex h-8 shrink-0 items-center gap-2 rounded-md border px-3 text-label whitespace-nowrap transition-colors duration-(--duration-fast)",
              t.key === data.technique ? "border-ink bg-secondary font-semibold text-ink" : "border-border bg-surface font-medium text-ink-secondary hover:bg-secondary hover:text-ink",
            )}
          >
            {t.name}
            <span className="text-ink-muted">{t.count ?? 0}</span>
          </button>
        ))}
      </div>

      {active && (
        <section className="mb-4 rounded-lg border border-divider bg-surface p-4" aria-label={`${active.name} 기법 설명`}>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="text-h5 font-bold text-ink">{active.name}</h2>
            <span className="text-body-sm text-ink-muted">
              {active.origin} · 보유 기간 {active.holding} · 쓰는 자료 {active.data}
            </span>
          </div>
          <p className="mt-1 text-body-sm text-ink-secondary">{active.summary}</p>
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="통과 조건">
            {active.rules.map((rule) => (
              <li key={rule} className="num rounded-full border border-border px-2 py-1 text-label text-ink-secondary">
                {rule}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-label text-ink-muted">
            {KIND_NOTE[active.kind]}
            {active.kind === "entry" && active.enabled === false && (
              <>
                {" "}
                지금은 자동매매에서 꺼 둔 기법입니다. <Link to="/auto">자동매매에서 켜기</Link>
              </>
            )}
          </p>
        </section>
      )}

      <Panel bodyClassName="" title={<span className="num">통과 종목 {rows.length}개</span>}>
        {rows.length === 0 ? (
          <Empty title="조건을 통과한 종목이 없습니다">{dayLabel(data.as_of)} 종가로는 이 기법의 조건을 모두 채운 종목이 없습니다. 다른 기법을 고르거나 다음 거래일을 기다리세요.</Empty>
        ) : (
          <>
            <div className="hidden overflow-x-auto lg:block">
              <table className="w-full">
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-divider px-3 py-2 text-left text-label font-semibold text-ink-muted">
                      종목
                    </th>
                    <th scope="col" className="border-b border-divider px-3 py-2 text-right text-label font-semibold text-ink-muted">
                      종가
                    </th>
                    {sortButton("change_pct", "전일 대비")}
                    <th scope="col" className="border-b border-divider px-3 py-2 text-left text-label font-semibold text-ink-muted">
                      40일 추이
                    </th>
                    {sortButton("score", "점수")}
                    <th scope="col" className="border-b border-divider px-3 py-2 text-left text-label font-semibold text-ink-muted">
                      상태
                    </th>
                    {sortButton("rs", "상대강도")}
                    {sortButton("value20", "하루 거래대금")}
                    <th scope="col" className="border-b border-divider px-3 py-2 text-left text-label font-semibold text-ink-muted">
                      매수 계획
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.code} className="transition-colors duration-(--duration-fast) hover:bg-surface-sunken">
                      <td className="border-b border-divider px-3 py-2">
                        <Link to={`/stocks/${row.code}`} className="text-h6 font-semibold text-ink no-underline hover:underline">
                          {row.name}
                        </Link>
                        <span className="num block text-label text-ink-muted">
                          {row.code} · {row.market} · {row.sector}
                        </span>
                      </td>
                      <td className="num border-b border-divider px-3 py-2 text-right text-body-sm font-semibold text-ink">{num(row.close)}</td>
                      <td className="border-b border-divider px-3 py-2 text-right text-body-sm">
                        <Delta value={row.change}>{pct(row.change_pct)}</Delta>
                      </td>
                      <td className="border-b border-divider px-3 py-2">
                        <Sparkline values={row.spark} />
                      </td>
                      <td className="num border-b border-divider px-3 py-2 text-right text-body-sm">
                        <span className="font-semibold text-ink">{num(row.score)}</span>
                        <span className="block text-label text-ink-muted">
                          조건 {row.passed}/{row.total}
                        </span>
                      </td>
                      <td className="border-b border-divider px-3 py-2">
                        <Badge tone={TECH_STATE_TONE[row.state] ?? "neutral"}>{labelOf(TECH_STATE, row.state)}</Badge>
                      </td>
                      <td className="num border-b border-divider px-3 py-2 text-right text-body-sm text-ink">{row.rs !== null ? num(row.rs) : ""}</td>
                      <td className="num border-b border-divider px-3 py-2 text-right text-body-sm text-ink">{wonShort(row.value20)}</td>
                      <td className="num border-b border-divider px-3 py-2 text-body-sm text-ink-secondary">
                        <PlanCell row={row} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="lg:hidden">
              {rows.map((row) => (
                <li key={row.code} className="border-b border-divider last:border-b-0">
                  <Link to={`/stocks/${row.code}`} className="block px-4 py-3 no-underline">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-h6 font-semibold text-ink">{row.name}</p>
                        <p className="num text-label text-ink-muted">
                          {row.code} · {row.sector}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="num text-h6 font-semibold text-ink">{num(row.close)}원</p>
                        <Delta value={row.change} className="text-body-sm">
                          {pct(row.change_pct)}
                        </Delta>
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-3">
                      <span className="num flex flex-wrap items-center gap-2 text-label text-ink-secondary">
                        <Badge tone={TECH_STATE_TONE[row.state] ?? "neutral"}>{labelOf(TECH_STATE, row.state)}</Badge>
                        점수 {num(row.score)} · 조건 {row.passed}/{row.total}
                        {row.rs !== null && <> · 상대강도 {num(row.rs)}</>}
                      </span>
                      <Sparkline values={row.spark} width={72} height={24} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <p className="num mt-3 text-label text-ink-muted">
        살펴본 종목 {num(data.universe)}개 가운데 하루 평균 거래대금이 {wonShort(data.min_avg_value)}에 못 미치는 {num(data.excluded_illiquid)}개
        {data.no_bar > 0 && <>와 이날 봉이 없는 {num(data.no_bar)}개</>}는 뺐습니다. 자료: {DATA_SOURCE[data.data_source] ?? data.data_source}. 상대강도는 1년 수익률의 백분위(0~100)입니다.
      </p>
      {screener.isFetching && <Notice>새 결과를 불러오는 중입니다.</Notice>}
    </div>
  );
}

function PlanCell({ row }: { row: ScreenerRow }) {
  if (!row.plan) return <span className="text-ink-muted">{row.also.length > 0 ? `함께 통과: ${row.also.join(", ")}` : ""}</span>;
  return (
    <>
      {planText(row.plan)}
      <span className="block text-label text-ink-muted">
        손절 {num(row.plan.stop)}원{row.plan.target ? ` · 목표 ${num(row.plan.target)}원` : ""}
      </span>
    </>
  );
}

function StockSearch() {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const search = useStockSearch(query);
  const results = search.data?.results ?? [];

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [text]);

  return (
    <div className="relative w-full sm:w-72" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted" />
      <TextInput
        type="search"
        aria-label="종목 이름이나 코드로 찾기"
        placeholder="종목 이름·코드"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && results[0]) navigate(`/stocks/${results[0].code}`);
          if (e.key === "Escape") setOpen(false);
        }}
        className="pl-9"
      />
      {open && query && (
        <div className="absolute inset-x-0 top-full z-(--z-dropdown) mt-1 max-h-80 overflow-y-auto rounded-lg bg-surface-raised p-1 shadow-2">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-body-sm text-ink-secondary">{search.isFetching ? "찾는 중입니다" : `'${query}'에 맞는 종목이 없습니다`}</p>
          ) : (
            <ul>
              {results.map((r) => (
                <li key={r.code}>
                  <Link to={`/stocks/${r.code}`} className="flex min-h-11 items-center justify-between gap-3 rounded-md px-3 text-body-sm no-underline hover:bg-secondary focus-visible:bg-secondary">
                    <span className="font-semibold text-ink">{r.name}</span>
                    <span className="num text-label text-ink-muted">
                      {r.code} · {r.sector}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
