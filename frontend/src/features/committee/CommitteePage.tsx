/** AI 위원회: 날짜별 심의 결과. 무엇을 사기로 했고 무엇을 왜 보류했는지 한 줄씩 보여준다. */

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button, cx, Empty, ErrorState, PageHeader, Panel, Select, SkeletonRows, TH } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { dayLabel, labelOf, num, pct } from "@/lib/format";
import { CONVICTION } from "@/lib/labels";
import { useCommittee } from "@/lib/queries";
import type { Committee, DecisionBrief } from "@/lib/types";
import { votesText } from "../auto/ApprovalCard";
import { ActionBadge, sourceLabel } from "./parts";

export default function CommitteePage() {
  const [params, setParams] = useSearchParams();
  const committee = useCommittee(params.get("day"));

  if (committee.isPending) return <SkeletonRows rows={8} label="위원회 기록을 불러오는 중" />;
  if (committee.isError) return <ErrorState message={errorMessage(committee.error)} onRetry={() => void committee.refetch()} />;
  const c = committee.data;
  const index = c.day ? c.days.indexOf(c.day) : -1;
  const go = (day: string | undefined) => day && setParams({ day }, { replace: true });

  return (
    <div>
      <PageHeader
        title="AI 위원회"
        lead={
          <>
            장이 끝나면 기법 조건을 통과한 후보와 보유 종목을 심의합니다. 지금은 {sourceLabel(c.decider)}가 최종 판단을 내리고, 그 뒤 리스크 점검이 수량을 줄이거나 막습니다.
          </>
        }
        actions={
          c.days.length > 0 && (
            <div className="flex items-center gap-1">
              <Button size="icon" aria-label="이전 심의일" disabled={index < 0 || index >= c.days.length - 1} onClick={() => go(c.days[index + 1])} icon={<ChevronLeft aria-hidden className="size-4" />} />
              <Select aria-label="심의일 고르기" value={c.day ?? ""} onChange={(e) => go(e.target.value)} className="num w-44">
                {c.days.map((day) => (
                  <option key={day} value={day}>
                    {dayLabel(day)} ({day.slice(0, 4)})
                  </option>
                ))}
              </Select>
              <Button size="icon" aria-label="다음 심의일" disabled={index <= 0} onClick={() => go(c.days[index - 1])} icon={<ChevronRight aria-hidden className="size-4" />} />
            </div>
          )
        }
      />

      {c.day === null ? (
        <Panel>
          <Empty title="아직 심의한 기록이 없습니다" action={<Link to="/auto">자동매매에서 거래일 진행하기</Link>}>
            엔진을 켜고 거래일을 진행하면 그날 장 마감 뒤의 심의 결과가 여기에 쌓입니다.
          </Empty>
        </Panel>
      ) : (
        <div className="space-y-4">
          <Summary c={c} />
          <Panel bodyClassName="" title={<span className="num">{dayLabel(c.day)} 심의 {c.decisions.length}건</span>}>
            <DecisionList decisions={c.decisions} />
          </Panel>
          <Scorecard c={c} />
        </div>
      )}
    </div>
  );
}

function Summary({ c }: { c: Committee }) {
  const t = c.tally;
  const parts = [`매수 ${t.BUY ?? 0}건`, `보류 ${t.HOLD ?? 0}건`, `매도 ${t.SELL ?? 0}건`];
  return (
    <p className="num text-body-sm text-ink-secondary">
      {parts.join(" · ")}
      {(t.review ?? 0) > 0 && <span className="font-semibold text-warning"> · 확인 필요 {t.review}건</span>}
      {c.decider !== "rules" && (
        <>
          {" "}
          · {c.decider === "ai" ? `심의 깊이 ${c.depth_label} · ` : ""}이날 AI 비용 ${c.cost_usd.toFixed(2)}
        </>
      )}
    </p>
  );
}

function DecisionList({ decisions }: { decisions: DecisionBrief[] }) {
  const navigate = useNavigate();
  if (decisions.length === 0) return <Empty title="이날은 심의할 후보가 없었습니다">기법 조건을 통과한 종목도, 다시 볼 보유 종목도 없었습니다.</Empty>;
  return (
    <>
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full">
          <thead>
            <tr>
              {["종목", "판단", "요지", "위원 의견", "리스크 점검"].map((h) => (
                <th key={h} scope="col" className={TH}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {decisions.map((d) => (
              <tr key={d.id} onClick={() => navigate(`/committee/${d.id}`)} className="cursor-pointer align-top transition-colors duration-(--duration-fast) hover:bg-surface-sunken">
                <td className="border-b border-divider px-3 py-2">
                  <Link to={`/committee/${d.id}`} onClick={(e) => e.stopPropagation()} className="text-h6 font-semibold text-ink no-underline hover:underline">
                    {d.name}
                  </Link>
                  <span className="num block text-label text-ink-muted">
                    {d.kind === "entry" ? "새로 살지 심의" : "보유 다시 심의"}
                    {d.technique_name && <> · {d.technique_name}</>}
                  </span>
                </td>
                <td className="border-b border-divider px-3 py-2 whitespace-nowrap">
                  <ActionBadge action={d.action} review={d.status !== "ok"} />
                  <span className="block text-label text-ink-muted">
                    확신 {d.conviction_label || labelOf(CONVICTION, d.conviction)} · {sourceLabel(d.source)}
                  </span>
                </td>
                <td className="max-w-md border-b border-divider px-3 py-2 text-body-sm text-ink-secondary">
                  <span className="line-clamp-2">{d.status !== "ok" && d.status_detail ? d.status_detail : d.thesis}</span>
                </td>
                <td className="num border-b border-divider px-3 py-2 text-body-sm whitespace-nowrap text-ink-secondary">{votesText(d.votes)}</td>
                <td className="num border-b border-divider px-3 py-2 text-body-sm text-ink-secondary">
                  {d.gate_summary ? (
                    <>
                      <span className={cx("font-semibold", (d.gate_qty ?? 0) > 0 ? "text-success" : "text-danger")}>{(d.gate_qty ?? 0) > 0 ? `${num(d.gate_qty)}주 통과` : "거부"}</span>
                      <span className="line-clamp-2 block text-label text-ink-muted">{d.gate_summary}</span>
                    </>
                  ) : (
                    <span className="text-label text-ink-muted">매수 판단이 아니라 점검하지 않음</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="lg:hidden">
        {decisions.map((d) => (
          <li key={d.id} className="border-b border-divider last:border-b-0">
            <Link to={`/committee/${d.id}`} className="block px-4 py-3 no-underline">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-h6 font-semibold text-ink">{d.name}</span>
                <ActionBadge action={d.action} review={d.status !== "ok"} />
              </div>
              <p className="num text-label text-ink-muted">
                {d.kind === "entry" ? "새로 살지 심의" : "보유 다시 심의"} · 확신 {d.conviction_label || labelOf(CONVICTION, d.conviction)} · {votesText(d.votes)}
              </p>
              <p className="mt-1 line-clamp-2 text-body-sm text-ink-secondary">{d.status !== "ok" && d.status_detail ? d.status_detail : d.thesis}</p>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function Scorecard({ c }: { c: Committee }) {
  const rows = (["ai", "rules"] as const).map((key) => ({ key, ...c.scorecard[key] }));
  return (
    <Panel title="위원회 성적">
      <p className="mb-3 text-body-sm text-ink-secondary">매수 판단이 실제 거래로 이어져 매도까지 끝난 건만 셉니다. 20건이 쌓이기 전에는 우연과 실력을 가르기 어렵습니다.</p>
      <dl className="grid gap-4 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.key} className="border-t border-ink pt-2">
            <dt className="text-body-sm font-semibold text-ink">{sourceLabel(r.key)}</dt>
            {r.closed === 0 ? (
              <dd className="mt-1 text-body-sm text-ink-muted">끝난 거래가 아직 없습니다</dd>
            ) : (
              <dd className="num mt-1 text-body-sm text-ink-secondary">
                끝난 거래 <span className="font-semibold text-ink">{r.closed}건</span> · 이익 {r.wins}건({r.win_rate !== null ? pct(r.win_rate, 0, false) : "–"}) · 평균{" "}
                <span className="font-semibold text-ink">{r.avg_pct !== null ? pct(r.avg_pct, 1) : "–"}</span>
                {!r.enough && <span className="block text-label text-ink-muted">표본이 20건에 못 미쳐 참고만 하세요</span>}
              </dd>
            )}
          </div>
        ))}
      </dl>
    </Panel>
  );
}
