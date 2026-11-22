/** 설정: 거래 환경(시뮬레이션·모의투자·실전)과 증권사 키, AI 위원회, 리스크 한도, 비용 가정, 데이터, 계정, 보안. */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge, Button, cx, ErrorState, Field, Notice, PageHeader, Panel, Select, SkeletonRows, TD, TDR, TextInput, TH, THR, type Tone } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dayDots, num, pct, won } from "@/lib/format";
import { CONVICTION, DATA_SOURCE } from "@/lib/labels";
import { notifyError, refreshAll, useBrokerKeys, useSettings, useStatus } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";
import type { EngineSettings, RiskLimits, SettingsView } from "@/lib/types";
import { AccountPanel } from "@/features/settings/AccountPanel";
import { BrokerKeyForm, BrokerKeyNote } from "@/features/settings/BrokerKeyForm";
import { SecurityPanel } from "@/features/settings/SecurityPanel";

export default function SettingsPage() {
  const settings = useSettings();
  if (settings.isPending) return <SkeletonRows rows={8} label="설정을 불러오는 중" />;
  if (settings.isError) return <ErrorState message={errorMessage(settings.error)} onRetry={() => void settings.refetch()} />;
  const view = settings.data;
  return (
    <div>
      <PageHeader title="설정" lead="위험을 키우는 변경(한도 완화, 모의투자·실전 전환)은 인증 코드를 한 번 더 묻습니다." />
      <div className="space-y-4">
        <EnvPanel view={view} />
        <div className="grid gap-4 xl:grid-cols-2">
          <AiPanel view={view} />
          <div className="space-y-4">
            <CostPanel view={view} />
            <DataPanel view={view} />
          </div>
        </div>
        <LimitsPanel limits={view.limits} />
        {/* 계정·보안·키 입력은 공개 데모 빌드에서 빈 부품으로 바뀐다(vite.config.ts, CLAUDE.md 배포 안전 기준) */}
        <AccountPanel />
        <SecurityPanel view={view} />
      </div>
    </div>
  );
}

// ── 거래 환경 ───────────────────────────────────────────────────────────

interface TestResult {
  ok: boolean;
  message?: string;
  hint?: string;
  code?: number | string;
  cash?: number;
  total_equity?: number;
  positions?: number;
  token_expires_at?: string;
}

function EnvPanel({ view }: { view: SettingsView }) {
  const elevated = useElevated();
  const [busy, setBusy] = useState(false);
  const env = view.engine.env;

  const toSim = async () => {
    setBusy(true);
    try {
      await elevated(() => api.post("/api/settings/env", { env: "sim", confirm: "" }));
      toast.success("시뮬레이션으로 바꿨습니다. 엔진은 정지 상태입니다");
      refreshAll();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="거래 환경">
      <div className="grid gap-3 lg:grid-cols-3">
        <EnvCard title="시뮬레이션" active={env === "sim"} tone="neutral" lines={["지난 일봉으로 가상 계좌를 굴립니다.", "증권사에 주문이 나가지 않습니다."]}>
          {env !== "sim" && (
            <Button size="sm" busy={busy} onClick={() => void toSim()}>
              시뮬레이션으로 바꾸기
            </Button>
          )}
        </EnvCard>
        <BrokerCard title="모의투자" env="mock" active={env === "mock"} tone="outline" configured={view.broker.mock.configured} baseUrl={view.broker.mock.base_url} keyPrefix="KIWOOM_MOCK" lines={["키움 모의투자 서버에 가상 주문을 냅니다.", "실제 돈은 움직이지 않습니다."]} />
        <BrokerCard
          title="실전"
          env="live"
          active={env === "live"}
          tone="warning"
          configured={view.broker.live.configured}
          baseUrl={view.broker.live.base_url}
          keyPrefix="KIWOOM_LIVE"
          lines={["내 키움 계좌에 실제 주문을 냅니다.", view.broker.live.allowed_by_server ? "서버에서 실전 전환을 허용해 둔 상태입니다." : "서버 환경변수 ALLOW_LIVE_TRADING=true가 있어야 전환할 수 있습니다."]}
        />
      </div>
      {!view.broker.runner_available && (
        <div className="mt-3">
          <Notice tone="warning">
            모의투자·실전으로 주문을 내는 기능은 아직 열려 있지 않습니다. 지금은 키를 넣고 연결 확인(잔고 읽기)까지만 할 수 있습니다. 키움 모의투자 서버에서 주문·체결 응답을 실제로 검증한 뒤에 엽니다.
          </Notice>
        </div>
      )}
      {/* 키 넣는 안내는 키 입력칸과 함께 다닌다. 공개 데모 빌드에서는 둘 다 빠진다(BrokerKeyForm.demo.tsx) */}
      <BrokerKeyNote />
    </Panel>
  );
}

function EnvCard({ title, active, tone, lines, children }: { title: string; active: boolean; tone: Tone; lines: string[]; children?: React.ReactNode }) {
  return (
    <div className={cx("flex flex-col gap-2 rounded-md border p-3", active ? "border-ink bg-surface-sunken" : "border-divider")}>
      <div className="flex items-center gap-2">
        <Badge tone={tone} className="font-semibold">{title}</Badge>
        {active && <Badge tone="success">지금 쓰는 환경</Badge>}
      </div>
      <ul className="space-y-1 text-body-sm text-ink-secondary">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {children && <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">{children}</div>}
    </div>
  );
}

function BrokerCard({ title, env, active, tone, configured, baseUrl, keyPrefix, lines }: { title: string; env: "mock" | "live"; active: boolean; tone: Tone; configured: boolean; baseUrl: string; keyPrefix: string; lines: string[] }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const source = useBrokerKeys().data?.[env] ?? null;

  const test = async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult(await api.post<TestResult>("/api/settings/broker/test", { env }));
    } catch (e) {
      setResult({ ok: false, message: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <EnvCard title={title} active={active} tone={tone} lines={lines}>
      <div className="w-full space-y-2">
        <p className="num text-label text-ink-muted">
          {configured ? <Badge tone="success">{source === "db" ? "키 등록됨(화면에서 넣음)" : "키 등록됨(.env)"}</Badge> : <Badge tone="neutral">키 없음</Badge>} <span className="break-all">{baseUrl}</span>
        </p>
        {!configured && (
          <p className="text-label text-ink-muted">
            아래에서 키를 넣거나, 서버 .env에 {keyPrefix}_APP_KEY와 {keyPrefix}_SECRET_KEY를 넣고 서버를 다시 시작하세요.
          </p>
        )}
        <BrokerKeyForm env={env} stored={source === "db"} onSaved={() => setResult(null)} />
        <Button size="sm" busy={busy} disabled={!configured} onClick={() => void test()}>
          연결 확인
        </Button>
        {result && (
          <p role="status" className={cx("num text-body-sm", result.ok ? "text-success" : "text-danger")}>
            {result.ok ? (
              <>
                연결됐습니다. 예수금 {won(result.cash)}, 평가 금액 {won(result.total_equity)}, 보유 {result.positions ?? 0}종목.
              </>
            ) : (
              <>
                연결하지 못했습니다. {result.message}
                {result.hint && <span className="block text-ink-secondary">{result.hint}</span>}
              </>
            )}
          </p>
        )}
      </div>
    </EnvCard>
  );
}

// ── AI 위원회 ───────────────────────────────────────────────────────────

function useSaveEngine() {
  const elevated = useElevated();
  const [busy, setBusy] = useState(false);
  const save = async (patch: Partial<EngineSettings>, done: string) => {
    setBusy(true);
    try {
      await elevated(() => api.put("/api/settings/engine", patch));
      toast.success(done);
      refreshAll();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  return { save, busy };
}

function AiPanel({ view }: { view: SettingsView }) {
  const { save, busy } = useSaveEngine();
  const engine = view.engine;
  const [model, setModel] = useState(engine.ai_model);
  const [depth, setDepth] = useState(engine.ai_depth);
  const [effort, setEffort] = useState(engine.ai_effort);
  const [budget, setBudget] = useState(String(engine.ai_daily_budget_usd));
  useEffect(() => {
    setModel(engine.ai_model);
    setDepth(engine.ai_depth);
    setEffort(engine.ai_effort);
    setBudget(String(engine.ai_daily_budget_usd));
  }, [engine.ai_model, engine.ai_depth, engine.ai_effort, engine.ai_daily_budget_usd]);
  const budgetValue = Number(budget);
  const dirty = model !== engine.ai_model || depth !== engine.ai_depth || effort !== engine.ai_effort || budgetValue !== engine.ai_daily_budget_usd;
  const valid = Number.isFinite(budgetValue) && budgetValue >= 0 && budgetValue <= 500;

  return (
    <Panel title="AI 위원회">
      {view.ai.configured ? (
        <Notice tone="success">서버에 AI 키가 등록돼 있습니다.</Notice>
      ) : (
        <Notice tone="warning">서버 .env에 ANTHROPIC_API_KEY가 없습니다. 키가 없으면 AI 위원회는 판단하지 못하고 새 매수를 모두 보류합니다. 그동안은 자동매매에서 규칙 위원회를 고르세요.</Notice>
      )}
      <form
        className="mt-4 grid gap-x-4 gap-y-3 sm:grid-cols-2"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void save({ ai_model: model, ai_depth: depth, ai_effort: effort, ai_daily_budget_usd: budgetValue }, "AI 위원회 설정을 저장했습니다");
        }}
      >
        <Field label="모델" className="sm:col-span-2">
          {(p) => (
            <Select {...p} value={model} onChange={(e) => setModel(e.target.value)}>
              {view.options.models.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="심의 깊이" hint="깊을수록 한 종목에 호출이 늘어 비용이 듭니다">
          {(p) => (
            <Select {...p} value={depth} onChange={(e) => setDepth(e.target.value as EngineSettings["ai_depth"])}>
              {view.options.depths.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="생각하는 정도" hint="높을수록 느리고 비쌉니다">
          {(p) => (
            <Select {...p} value={effort} onChange={(e) => setEffort(e.target.value)}>
              <option value="low">낮게</option>
              <option value="medium">보통</option>
              <option value="high">높게</option>
            </Select>
          )}
        </Field>
        <Field label="하루 예산(달러)" hint="넘으면 그날 남은 후보는 사지 않고 보류합니다" error={valid ? null : "0에서 500 사이로 넣으세요"}>
          {(p) => <TextInput {...p} inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value.replace(/[^\d.]/g, ""))} className="num" />}
        </Field>
        <div className="flex items-end pb-5">
          {/* 설정 화면에는 저장 단추가 여럿이다. 바꾼 값이 있는 묶음의 저장만 잉크(primary)로 올라와, 지금 누를 단추가 하나로 보인다. */}
          <Button type="submit" variant={dirty ? "primary" : "secondary"} busy={busy} disabled={!dirty || !valid}>
            저장
          </Button>
        </div>
      </form>
      <h3 className="mt-2 mb-1 text-body-sm font-semibold text-ink">최근 쓴 비용</h3>
      {view.ai.usage.length === 0 ? (
        <p className="text-body-sm text-ink-secondary">아직 AI를 호출한 적이 없습니다.</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr>
              <th scope="col" className={TH}>
                날짜
              </th>
              <th scope="col" className={THR}>
                호출
              </th>
              <th scope="col" className={THR}>
                비용
              </th>
            </tr>
          </thead>
          <tbody>
            {view.ai.usage.map((u) => (
              <tr key={u.day}>
                <td className={cx(TD, "num")}>{dayDots(u.day)}</td>
                <td className={TDR}>{num(u.calls)}회</td>
                <td className={TDR}>${u.cost_usd.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

// ── 비용 가정 · 데이터 ──────────────────────────────────────────────────

function CostPanel({ view }: { view: SettingsView }) {
  const { save, busy } = useSaveEngine();
  const engine = view.engine;
  const initial = useMemo(
    () => ({ commission_rate: (engine.commission_rate * 100).toFixed(3), sell_tax_rate: (engine.sell_tax_rate * 100).toFixed(2), slippage_rate: (engine.slippage_rate * 100).toFixed(2) }),
    [engine.commission_rate, engine.sell_tax_rate, engine.slippage_rate],
  );
  const [form, setForm] = useState(initial);
  useEffect(() => setForm(initial), [initial]);
  const dirty = (Object.keys(initial) as (keyof typeof initial)[]).some((k) => form[k] !== initial[k]);
  const fields: { key: keyof typeof initial; label: string; hint: string }[] = [
    { key: "commission_rate", label: "수수료(%)", hint: "살 때와 팔 때 모두" },
    { key: "sell_tax_rate", label: "매도세(%)", hint: "팔 때만" },
    { key: "slippage_rate", label: "체결 오차(%)", hint: "불리한 쪽으로 계산" },
  ];
  return (
    <Panel title="비용 가정">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save({ commission_rate: Number(form.commission_rate) / 100, sell_tax_rate: Number(form.sell_tax_rate) / 100, slippage_rate: Number(form.slippage_rate) / 100 }, "비용 가정을 저장했습니다");
        }}
      >
        <div className="grid gap-x-4 gap-y-3 sm:grid-cols-3">
          {fields.map((f) => (
            <Field key={f.key} label={f.label} hint={f.hint}>
              {(p) => <TextInput {...p} inputMode="decimal" value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value.replace(/[^\d.]/g, "") })} className="num" />}
            </Field>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button type="submit" variant={dirty ? "primary" : "secondary"} busy={busy} disabled={!dirty}>
            저장
          </Button>
          <p className="text-label text-ink-muted">시뮬레이션과 백테스트에 쓰는 값입니다. 실제 수수료는 증권사 약정에 따라 다릅니다.</p>
        </div>
      </form>
    </Panel>
  );
}

function DataPanel({ view }: { view: SettingsView }) {
  const status = useStatus().data;
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    setBusy(true);
    try {
      const out = await api.post<{ updated: number; unchanged: number; failed: string[]; refetched: number }>("/api/engine/refresh-data");
      if (out.failed.length > 0) toast.warning(`일봉을 갱신했지만 ${out.failed.length}종목은 받지 못했습니다`);
      else toast.success(`일봉을 갱신했습니다. 새 봉 ${out.updated}종목, 변동 없음 ${out.unchanged}종목`);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
      refreshAll();
    }
  };
  return (
    <Panel
      title="시세 데이터"
      actions={
        <Button size="sm" busy={busy || Boolean(status?.busy)} onClick={() => void refresh()}>
          일봉 갱신
        </Button>
      }
    >
      <p className="num text-body-sm text-ink-secondary">
        {DATA_SOURCE[view.data.source] ?? view.data.source} · {num(view.data.stocks)}종목 · {view.data.day ? `${dayDots(view.data.day)}까지` : "아직 없음"}
        {view.data.refreshed_at && <> · 마지막 갱신 {view.data.refreshed_at.slice(0, 16).replace("T", " ")}</>}
      </p>
      <p className="mt-2 text-label text-ink-muted">
        {view.data.source === "naver"
          ? "네이버 금융의 공개 일봉을 씁니다. 공식 제공 통로가 아니라 언제든 막히거나 형식이 바뀔 수 있습니다. 실전에서는 키움 시세로 바꿔야 합니다."
          : view.data.source === "sample"
            ? "가짜로 만든 견본 데이터입니다. 화면 확인용이며 실제 시세가 아닙니다."
            : "증권사에서 받은 시세입니다."}
      </p>
    </Panel>
  );
}

// ── 리스크 한도 ─────────────────────────────────────────────────────────

type LimitKind = "pct" | "int" | "num" | "won" | "conviction";
interface LimitField {
  key: string;
  label: string;
  kind: LimitKind;
  hint?: string;
}
const LIMIT_GROUPS: { title: string; fields: LimitField[] }[] = [
  {
    title: "계좌",
    fields: [
      { key: "max_positions", label: "최대 보유 종목 수", kind: "int" },
      { key: "max_position_pct", label: "한 종목 최대 비중(%)", kind: "pct" },
      { key: "max_sector_pct", label: "한 업종 최대 비중(%)", kind: "pct" },
      { key: "max_heat_pct", label: "손절 시 총손실 상한(%)", kind: "pct", hint: "모든 손절이 한꺼번에 걸릴 때" },
      { key: "min_cash_pct", label: "남겨 둘 현금(%)", kind: "pct" },
      { key: "max_order_value_pct", label: "주문 한 건 최대 금액(%)", kind: "pct", hint: "계좌 평가 금액 대비" },
      { key: "max_orders_per_day", label: "하루 최대 주문 수", kind: "int" },
    ],
  },
  {
    title: "손실이 커질 때",
    fields: [
      { key: "daily_loss_limit_pct", label: "하루 손실 한도(%)", kind: "pct", hint: "닿으면 그날 새 매수 중단" },
      { key: "weekly_loss_limit_pct", label: "한 주 손실 한도(%)", kind: "pct" },
      { key: "monthly_loss_limit_pct", label: "한 달 손실 한도(%)", kind: "pct" },
      { key: "drawdown_reduce_pct", label: "낙폭 1단계(%)", kind: "pct", hint: "수량을 75%로" },
      { key: "drawdown_half_pct", label: "낙폭 2단계(%)", kind: "pct", hint: "수량을 절반으로" },
      { key: "drawdown_block_pct", label: "낙폭 3단계(%)", kind: "pct", hint: "새 매수 중단" },
      { key: "drawdown_halt_pct", label: "낙폭 4단계(%)", kind: "pct", hint: "엔진 정지" },
      { key: "consecutive_stops_pause", label: "연속 손절 횟수", kind: "int", hint: "이만큼 이어지면 하루 쉼" },
    ],
  },
  {
    title: "거래 한 건",
    fields: [
      { key: "risk_per_trade_pct", label: "한 건에 거는 위험(%)", kind: "pct", hint: "손절 시 잃는 금액 ÷ 계좌" },
      { key: "min_buy_conviction", label: "매수에 필요한 최소 확신", kind: "conviction" },
      { key: "max_stop_pct", label: "손절 폭 상한(%)", kind: "pct" },
      { key: "max_cost_to_risk", label: "비용 ÷ 위험 상한", kind: "num", hint: "수수료·세금이 위험의 이 비율을 넘으면 거부" },
      { key: "min_reward_to_risk", label: "최소 손익비", kind: "num", hint: "목표가가 있을 때, 비용을 뺀 뒤" },
    ],
  },
  {
    title: "유동성과 가격 확인",
    fields: [
      { key: "min_avg_value", label: "하루 평균 거래대금 하한(원)", kind: "won" },
      { key: "max_adv_pct", label: "주문 ÷ 하루 거래대금 상한(%)", kind: "pct" },
      { key: "price_recheck_pct", label: "승인 때 가격 허용 폭(%)", kind: "pct", hint: "이보다 많이 움직였으면 승인을 막음" },
    ],
  },
];

const toText = (kind: LimitKind, value: number | string): string => {
  if (kind === "pct") return String(Number((Number(value) * 100).toFixed(4)));
  if (kind === "won") return num(Number(value));
  return String(value);
};
const toValue = (kind: LimitKind, text: string): number | string => {
  if (kind === "conviction") return text;
  if (kind === "pct") return Number((Number(text) / 100).toFixed(6));
  if (kind === "won" || kind === "int") return Number(text.replace(/\D/g, ""));
  return Number(text);
};

function LimitsPanel({ limits }: { limits: RiskLimits }) {
  const elevated = useElevated();
  const all = useMemo(() => LIMIT_GROUPS.flatMap((g) => g.fields), []);
  const initial = useMemo(() => Object.fromEntries(all.map((f) => [f.key, toText(f.kind, limits[f.key])])), [all, limits]);
  const [form, setForm] = useState<Record<string, string>>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setForm(initial), [initial]);

  const changed = all.filter((f) => form[f.key] !== initial[f.key]);
  const invalid = changed.filter((f) => f.kind !== "conviction" && !Number.isFinite(toValue(f.kind, form[f.key]) as number));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const patch = Object.fromEntries(changed.map((f) => [f.key, toValue(f.kind, form[f.key])]));
    try {
      const out = await elevated(() => api.put<{ loosened: string[] }>("/api/settings/limits", patch));
      toast.success(out.loosened.length > 0 ? `한도를 저장했습니다. 느슨해진 항목 ${out.loosened.length}개` : "한도를 저장했습니다");
      refreshAll();
    } catch (e) {
      if (!(e instanceof Error && "code" in e && (e as { code: string }).code === "cancelled")) setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="리스크 한도">
      <p className="mb-4 max-w-reading text-body-sm text-ink-secondary">
        엔진이 넘지 못하는 선입니다. AI 위원회가 매수를 정해도 리스크 점검이 이 한도 안으로 수량을 줄이거나 막습니다. 한도를 느슨하게 바꾸면 인증 코드를 다시 묻습니다.
      </p>
      <form onSubmit={submit}>
        <div className="space-y-5">
          {LIMIT_GROUPS.map((group) => (
            <fieldset key={group.title}>
              <legend className="mb-2 text-body-sm font-bold text-ink">{group.title}</legend>
              <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                {group.fields.map((f) => (
                  <Field key={f.key} label={f.label} hint={f.hint}>
                    {(p) =>
                      f.kind === "conviction" ? (
                        <Select {...p} value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                          {Object.entries(CONVICTION).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label} 이상
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <TextInput
                          {...p}
                          inputMode={f.kind === "int" || f.kind === "won" ? "numeric" : "decimal"}
                          value={f.kind === "won" ? num(Number(form[f.key].replace(/\D/g, ""))) : form[f.key]}
                          onChange={(e) => setForm({ ...form, [f.key]: f.kind === "int" || f.kind === "won" ? e.target.value.replace(/\D/g, "") : e.target.value.replace(/[^\d.]/g, "") })}
                          className="num"
                        />
                      )
                    }
                  </Field>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
        {error && (
          <div className="mt-2">
            <ErrorState message={error} />
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button type="submit" variant={changed.length > 0 ? "primary" : "secondary"} busy={busy} disabled={changed.length === 0 || invalid.length > 0}>
            한도 저장
          </Button>
          <Button onClick={() => setForm(initial)} disabled={changed.length === 0 || busy}>
            되돌리기
          </Button>
          <p role="status" className="num text-body-sm text-ink-secondary">
            {changed.length > 0 ? `바꾼 항목 ${changed.length}개: ${changed.map((f) => f.label.replace(/\(.*\)/, "")).join(", ")}` : `지금 값: 하루 손실 한도 ${pct(Number(limits.daily_loss_limit_pct), 1, false)}, 한 건 위험 ${pct(Number(limits.risk_per_trade_pct), 2, false)}`}
          </p>
        </div>
      </form>
    </Panel>
  );
}
