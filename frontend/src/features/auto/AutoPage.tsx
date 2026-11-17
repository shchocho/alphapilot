/** 자동매매: 승인 대기 → 얼마나 맡길지(자동화 단계) → 누가 판단할지 → 어떤 기법을 쓸지 → 시뮬레이션 진행. */

import { FastForward, RotateCcw, StepForward } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button, Check, cx, Empty, ErrorState, Field, Modal, Notice, PageHeader, Panel, RadioRow, SkeletonRows, TD, TDR, TextInput, TH, THR } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dayDots, dayLabel, num, won, wonShort } from "@/lib/format";
import { notifyError, refreshAll, usePending, useSettings, useStatus } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";
import type { EngineSettings, IntentCard, SettingsView } from "@/lib/types";
import { ApprovalCard, useStableCards } from "./ApprovalCard";

const LEVEL_TEXT: Record<number, string> = {
  0: "주문 계획을 알려 주기만 하고 주문은 내지 않습니다. 이미 보유한 종목의 손절·익절은 그대로 실행합니다.",
  1: "새 주문 계획은 모두 내가 승인해야 나갑니다. 처음에는 이 단계로 시작하기를 권합니다.",
  2: "한 건 금액이 아래 한도 이하면 자동으로 나가고, 넘으면 승인을 기다립니다.",
  3: "리스크 점검을 통과한 계획은 모두 자동으로 나갑니다. 충분히 지켜본 뒤에만 쓰세요.",
};

interface DayResult {
  day: string;
  fills: number;
  equity: number;
  halted: boolean;
  candidates?: number;
  buys?: number;
  sells?: number;
  regime?: string;
}

export default function AutoPage() {
  const settings = useSettings();
  const pending = usePending();

  if (settings.isPending) return <SkeletonRows rows={8} label="자동매매 설정을 불러오는 중" />;
  if (settings.isError) return <ErrorState message={errorMessage(settings.error)} onRetry={() => void settings.refetch()} />;
  return <AutoView view={settings.data} cards={pending.data?.cards ?? EMPTY_CARDS} />;
}

const EMPTY_CARDS: IntentCard[] = [];

function AutoView({ view, cards }: { view: SettingsView; cards: IntentCard[] }) {
  const { kept, outcomes, onDecided } = useStableCards(cards);

  return (
    <div>
      <PageHeader title="자동매매" lead="엔진에 얼마나 맡길지 정하는 곳입니다. 어떤 단계에서도 리스크 점검과 손절은 꺼지지 않습니다." />
      <div className="space-y-4">
        <section aria-labelledby="pending-title">
          <h2 id="pending-title" className="mb-2 text-h6 font-bold text-ink">
            승인 대기 {cards.length}건
          </h2>
          {kept.length === 0 ? (
            <Panel>
              <Empty title="승인을 기다리는 주문 계획이 없습니다">장 마감 뒤 위원회가 매수를 결정하면 다음 거래일 주문 계획이 여기에 올라옵니다.</Empty>
            </Panel>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {kept.map((card) => (
                <ApprovalCard key={card.id} card={card} outcome={outcomes[card.id]} onDecided={onDecided} />
              ))}
            </div>
          )}
        </section>

        <div className="grid gap-4 xl:grid-cols-2">
          <AutomationPanel view={view} />
          <div className="space-y-4">
            <DeciderPanel view={view} />
            <TechniquePanel view={view} />
          </div>
        </div>

        {view.engine.env === "sim" && <SimulationPanel view={view} />}
      </div>
    </div>
  );
}

/** 설정 한 묶음을 저장한다. 위험해지는 변경이면 서버가 재인증을 요구하고, 그때 코드 입력 창이 뜬다. */
function useSaveEngine() {
  const elevated = useElevated();
  const [busy, setBusy] = useState(false);
  const save = async (patch: Partial<EngineSettings>, done: string) => {
    setBusy(true);
    try {
      await elevated(() => api.put("/api/settings/engine", patch));
      toast.success(done);
      refreshAll();
      return true;
    } catch (e) {
      notifyError(e);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { save, busy };
}

function AutomationPanel({ view }: { view: SettingsView }) {
  const { save, busy } = useSaveEngine();
  const engine = view.engine;
  const [limit, setLimit] = useState(String(engine.auto_max_order_value));
  useEffect(() => setLimit(String(engine.auto_max_order_value)), [engine.auto_max_order_value]);
  const limitValue = Number(limit.replace(/\D/g, ""));

  return (
    <Panel title="자동화 단계">
      <fieldset disabled={busy} className="space-y-2">
        <legend className="sr-only">자동화 단계 고르기</legend>
        {view.options.automation.map((option) => {
          const on = engine.automation_level === option.value;
          return (
            <label key={option.value} className={cx("flex cursor-pointer gap-3 rounded-md border p-3 transition-colors duration-(--duration-fast)", on ? "border-ink bg-surface-sunken" : "border-divider hover:border-border")}>
              <input
                type="radio"
                name="automation"
                className="mt-1 size-5 shrink-0 accent-accent"
                checked={on}
                onChange={() => void save({ automation_level: option.value }, `자동화 단계를 '${option.label}'으로 바꿨습니다`)}
              />
              <span className="min-w-0">
                <span className="block text-h6 font-semibold text-ink">
                  {option.value}단계 · {option.label}
                </span>
                <span className="block text-body-sm text-ink-secondary">{LEVEL_TEXT[option.value]}</span>
              </span>
            </label>
          );
        })}
      </fieldset>
      <form
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void save({ auto_max_order_value: limitValue }, `자동 주문 한도를 ${won(limitValue)}으로 바꿨습니다`);
        }}
      >
        <Field label="한 건 자동 주문 한도(원)" hint={`2단계에서 씁니다 · 지금 ${wonShort(engine.auto_max_order_value)}`} className="min-w-0 flex-1">
          {(p) => <TextInput {...p} inputMode="numeric" value={num(limitValue)} onChange={(e) => setLimit(e.target.value)} className="num" />}
        </Field>
        <Button type="submit" busy={busy} disabled={limitValue <= 0 || limitValue === engine.auto_max_order_value} className="mb-5">
          한도 저장
        </Button>
      </form>
      {engine.resume_check_required && <Notice tone="warning">서버가 다시 시작돼, 확인하기 전까지는 고른 단계와 상관없이 모든 계획이 승인을 기다립니다.</Notice>}
    </Panel>
  );
}

function DeciderPanel({ view }: { view: SettingsView }) {
  const { save, busy } = useSaveEngine();
  const engine = view.engine;
  return (
    <Panel title="누가 최종 판단을 내리나">
      <RadioRow
        legend="판단 주체"
        name="decider"
        disabled={busy}
        value={engine.decider}
        onChange={(value) => void save({ decider: value }, value === "ai" ? "AI 위원회가 판단합니다" : value === "hybrid" ? "규칙이 판단하고 애매한 분기만 AI에게 묻습니다" : "규칙 위원회가 판단합니다")}
        options={[
          { value: "ai", label: "AI 위원회" },
          { value: "rules", label: "규칙 위원회" },
          { value: "hybrid", label: "규칙 + AI 분기" },
        ]}
      />
      <p className="mt-3 text-body-sm text-ink-secondary">
        {engine.decider === "ai"
          ? "강세·약세 연구원이 토론하고 리스크 검토자가 점검한 뒤 의장이 결론을 냅니다. AI가 답하지 못하거나 예산을 넘으면 그 건은 사지 않고 보류합니다."
          : engine.decider === "hybrid"
            ? "규칙 위원회가 결론을 내고, 규칙만으로 가르기 애매할 때만 AI에게 한 번 묻습니다. 애매한 경우는 문턱 근처 점수, 위원 의견 충돌, 리스크 경고, 손실 중인 보유 종목입니다. 위험을 줄이는 답은 그대로 따르고, 위험을 늘리는 답은 AI 확신이 보통 이상일 때만 따릅니다. AI가 답하지 못하면 규칙 결론을 씁니다."
            : "위원 의견을 가중 평균해 정해진 문턱을 넘으면 매수합니다. AI 비용이 들지 않고 결과가 항상 같습니다."}
      </p>
      {engine.decider === "hybrid" && !view.ai.configured && (
        <div className="mt-3">
          <Notice tone="warning">서버에 AI 키(ANTHROPIC_API_KEY)가 없어 분기에서도 AI에게 묻지 못합니다. 키를 넣기 전에는 규칙 위원회와 똑같이 움직입니다.</Notice>
        </div>
      )}
      {engine.decider === "ai" && !view.ai.configured && (
        <div className="mt-3">
          <Notice tone="warning">서버에 AI 키(ANTHROPIC_API_KEY)가 없습니다. 이대로 두면 AI 위원회가 판단하지 못해 새 매수를 모두 보류합니다. 키를 넣기 전에는 규칙 위원회를 고르세요.</Notice>
        </div>
      )}
    </Panel>
  );
}

function TechniquePanel({ view }: { view: SettingsView }) {
  const { save, busy } = useSaveEngine();
  const enabled = new Set(view.engine.enabled_techniques);
  const toggle = (key: string, name: string) => {
    const next = new Set(enabled);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    if (next.size === 0) {
      toast.error("기법을 하나는 켜 두어야 합니다");
      return;
    }
    void save({ enabled_techniques: view.options.techniques.map((t) => t.key).filter((k) => next.has(k)) }, `${name} 기법을 ${next.has(key) ? "켰습니다" : "껐습니다"}`);
  };
  return (
    <Panel title="쓸 진입 기법">
      <fieldset disabled={busy}>
        <legend className="sr-only">자동매매에 쓸 진입 기법</legend>
        {view.options.techniques.map((t) => (
          <Check key={t.key} checked={enabled.has(t.key)} onChange={() => toggle(t.key, t.name)} label={t.name} hint={`${t.summary} · 보유 ${t.holding}`} />
        ))}
      </fieldset>
      <p className="mt-2 text-label text-ink-muted">트렌드 템플릿은 항상 관문으로 쓰이고, 하루에 심의하는 후보는 점수 순으로 최대 {view.engine.max_candidates}개입니다.</p>
    </Panel>
  );
}

function SimulationPanel({ view }: { view: SettingsView }) {
  const status = useStatus().data;
  const [days, setDays] = useState("20");
  const [autoApprove, setAutoApprove] = useState(true);
  const [busy, setBusy] = useState<"one" | "many" | null>(null);
  const [results, setResults] = useState<DayResult[]>([]);
  const [resetOpen, setResetOpen] = useState(false);
  const dayCount = Math.max(1, Math.min(250, Number(days) || 1));
  const pendingNow = status?.pending_approvals ?? 0;

  const advance = async (count: number, auto: boolean, mode: "one" | "many") => {
    setBusy(mode);
    try {
      const out = await api.post<{ days: DayResult[] }>("/api/engine/advance", { days: count, auto_approve: auto });
      setResults(out.days);
      const last = out.days[out.days.length - 1];
      toast.success(out.days.length === 1 ? `${dayLabel(last.day)}을 처리했습니다` : `${out.days.length}거래일을 처리했습니다(${dayLabel(last.day)}까지)`);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
      refreshAll();
    }
  };

  return (
    <Panel
      title="시뮬레이션 진행"
      actions={
        <Button size="sm" icon={<RotateCcw aria-hidden className="size-4" />} onClick={() => setResetOpen(true)} disabled={busy !== null}>
          처음부터 다시
        </Button>
      }
    >
      <p className="text-body-sm text-ink-secondary">
        과거 일봉으로 하루씩 진행합니다. 그날 종가로 판단하고 다음 거래일에 주문하므로, 미래의 가격은 판단에 쓰이지 않습니다. 수수료·세금·체결 오차도 뺍니다.
      </p>
      <p className="num mt-2 text-body-sm text-ink">
        {status?.sim_day ? <>지금까지 {dayLabel(status.sim_day)}까지 처리했습니다.</> : <>아직 시작하지 않았습니다{view.sim_start ? ` (시작일 ${dayDots(view.sim_start)})` : ""}.</>}
        {status && status.behind_days > 0 ? <> 일봉이 있는 거래일이 {num(status.behind_days)}일 더 남았습니다.</> : status?.sim_day ? <> 최신 일봉까지 모두 처리했습니다.</> : null}
      </p>
      {status && status.state !== "running" && (
        <div className="mt-3">
          <Notice tone="warning">엔진이 {status.state_label} 상태라 새 매수 계획은 만들지 않습니다. 위쪽에서 엔진을 켠 뒤 진행하세요.</Notice>
        </div>
      )}

      {/* 두 방법을 패널 안의 상자로 다시 감싸지 않고, 구분선 하나로 나눈다(카드 안 카드 없음) */}
      <div className="mt-4 grid gap-4 border-t border-divider pt-4 lg:grid-cols-2 lg:gap-6">
        <div>
          <h3 className="text-body-sm font-bold text-ink">하루씩</h3>
          <p className="mt-1 text-body-sm text-ink-secondary">다음 거래일 하루를 처리합니다. 승인 대기 계획은 그대로 남아 내 결정을 기다립니다.</p>
          {/* 이 화면의 primary는 승인 카드의 승인 단추다. 시뮬레이션 진행은 보조 행동으로 둔다. */}
          <Button className="mt-3" busy={busy === "one"} disabled={busy !== null} icon={<StepForward aria-hidden className="size-4" />} onClick={() => void advance(1, false, "one")}>
            다음 거래일 처리
          </Button>
        </div>
        <form
          className="border-t border-divider pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
          onSubmit={(event) => {
            event.preventDefault();
            void advance(dayCount, autoApprove, "many");
          }}
        >
          <h3 className="text-body-sm font-bold text-ink">여러 날 이어서</h3>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <Field label="거래일 수" hint="1~250" className="w-28">
              {(p) => <TextInput {...p} inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, "").slice(0, 3))} className="num" />}
            </Field>
            <Button type="submit" busy={busy === "many"} disabled={busy !== null} icon={<FastForward aria-hidden className="size-4" />} className="mb-5">
              {dayCount}거래일 이어서 처리
            </Button>
          </div>
          <Check checked={autoApprove} onChange={(e) => setAutoApprove(e.target.checked)} label="승인 대기 계획을 자동으로 승인" hint="지난 구간을 한 번에 돌려 볼 때 씁니다. 끄면 승인하지 않은 계획은 기한이 지나 사라집니다." />
          {/* 위쪽에 아직 보지 않은 승인 카드가 있으면, 이어서 처리가 그 카드까지 승인한다는 것을 단추 옆에 바로 적는다 */}
          {autoApprove && pendingNow > 0 && (
            <p className="num text-label text-ink-secondary">
              지금 승인을 기다리는 {pendingNow}건도 자동으로 승인됩니다. 직접 보고 고르려면 위의 카드에서 먼저 결정하세요.
            </p>
          )}
        </form>
      </div>

      {busy !== null && (
        <p role="status" className="num mt-3 text-body-sm text-ink-secondary">
          {status?.busy || "처리하고 있습니다"}. AI 위원회를 쓰면 하루에 수십 초가 걸릴 수 있습니다.
        </p>
      )}

      {results.length > 0 && (
        <div className="mt-4 max-h-80 overflow-auto rounded-md border border-divider">
          <table className="w-full">
            <caption className="sr-only">방금 처리한 거래일별 결과</caption>
            <thead>
              <tr>
                <th scope="col" className={TH}>
                  거래일
                </th>
                <th scope="col" className={TH}>
                  시장 국면
                </th>
                <th scope="col" className={THR}>
                  후보
                </th>
                <th scope="col" className={THR}>
                  매수 결정
                </th>
                <th scope="col" className={THR}>
                  매도 결정
                </th>
                <th scope="col" className={THR}>
                  체결
                </th>
                <th scope="col" className={THR}>
                  평가 금액
                </th>
              </tr>
            </thead>
            <tbody>
              {[...results].reverse().map((r) => (
                <tr key={r.day}>
                  <td className={cx(TD, "num")}>
                    {dayDots(r.day)}
                    {r.halted && <span className="ml-2 font-semibold text-danger">엔진 정지</span>}
                  </td>
                  <td className={TD}>{r.regime ?? ""}</td>
                  <td className={TDR}>{r.candidates ?? 0}</td>
                  <td className={TDR}>{r.buys ?? 0}</td>
                  <td className={TDR}>{r.sells ?? 0}</td>
                  <td className={TDR}>{r.fills}</td>
                  <td className={TDR}>{won(r.equity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ResetDialog open={resetOpen} onOpenChange={setResetOpen} view={view} onDone={() => setResults([])} />
    </Panel>
  );
}

function ResetDialog({ open, onOpenChange, view, onDone }: { open: boolean; onOpenChange: (open: boolean) => void; view: SettingsView; onDone: () => void }) {
  const [start, setStart] = useState(view.sim_start ?? "");
  const [cash, setCash] = useState(String(view.engine.sim_initial_cash));
  const [busy, setBusy] = useState(false);
  const cashValue = Number(cash.replace(/\D/g, ""));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.post("/api/settings/sim-reset", { start: start || null, initial_cash: cashValue });
      toast.success("시뮬레이션을 처음으로 되돌렸습니다. 엔진은 정지 상태입니다");
      onDone();
      onOpenChange(false);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
      refreshAll();
    }
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="시뮬레이션 처음부터 다시"
      description="시뮬레이션의 보유 종목·주문 계획·체결 내역·위원회 기록·자산 추이를 지우고 시작 자금으로 돌아갑니다. 지운 기록은 되살릴 수 없습니다. 장부에는 지난 실행의 줄이 그대로 남고, 백테스트 결과와 설정도 그대로 둡니다."
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="시작일" hint={`비워 두면 가장 최근 거래일부터 시작합니다${view.data.day ? ` · 일봉은 ${dayDots(view.data.day)}까지 있습니다` : ""}`}>
          {(p) => <TextInput {...p} type="date" value={start} max={view.data.day ?? undefined} onChange={(e) => setStart(e.target.value)} className="num" />}
        </Field>
        <Field label="시작 자금(원)" hint="100만 원 이상" error={cashValue < 1_000_000 ? "100만 원 이상이어야 합니다" : null}>
          {(p) => <TextInput {...p} inputMode="numeric" value={num(cashValue)} onChange={(e) => setCash(e.target.value)} className="num" />}
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)} disabled={busy}>
            취소
          </Button>
          <Button type="submit" variant="danger" busy={busy} disabled={cashValue < 1_000_000}>
            기록을 지우고 다시 시작
          </Button>
        </div>
      </form>
    </Modal>
  );
}
