/** 운용 계획 고치기: 총액 → 바구니(금액·방식·판단 주체·주기·횟수·지침·종목). 저장하면 새 판이 된다. */

import { Plus, Search, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button, Field, Notice, Panel, RadioRow, Select, TextArea, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import { num, won, wonShort } from "@/lib/format";
import { notifyError, useStockSearch } from "@/lib/queries";
import { baseAmount, DEPTH_LABEL, newSleeve, planProblems, refreshSleeves, roundsPerShare } from "./data";
import { PreviewResult } from "./Validation";
import type { Cadence, Decider, Depth, Kind, Lookup, Mode, PlanConfig, Preview, SleeveConfig, SleevesOverview } from "./types";

const MAX_SLEEVES = 6;
const MAX_ITEMS = 15;
const MANDATE_MAX = 1500;
const WEIGHTS = [0.5, 1, 1.5, 2, 3, 4, 5]; // 같은 바구니 안 종목끼리의 상대 비중

const MODE_HINT: Record<Mode, string> = {
  paper: "판단을 다음 거래일 시가에 가상으로 체결해 바구니 장부에 쌓습니다. 성과를 기준선과 비교할 수 있습니다.",
  alert: "판단과 권장 수량만 알려 줍니다. 실제 매매는 키움 앱에서 직접 합니다.",
};
const DECIDER_HINT: Record<Decider, string> = {
  rules: "좌석 점수로 정합니다. 비용이 없고 결과가 항상 같습니다. 운용 지침은 쓰지 않습니다.",
  ai: "강세·약세 연구원과 리스크 검토를 거쳐 위원장이 운용 지침을 참고해 고릅니다. 종목마다 Claude를 부릅니다.",
  hybrid: "규칙이 결론을 내고, 애매한 경우에만 AI에게 한 번 묻습니다.",
};

function parseMoney(text: string): number {
  return Number(text.replace(/\D/g, "")) || 0;
}

export function PlanEditor({ view, initial, onDone }: { view: SleevesOverview; initial: PlanConfig; onDone: () => void }) {
  const [plan, setPlan] = useState<PlanConfig>(() => structuredClone(initial));
  const [note, setNote] = useState("");
  const [prices, setPrices] = useState<Record<string, number>>(() => ({ ...(view.prices ?? {}) }));
  const [busy, setBusy] = useState<"save" | "preview" | null>(null);
  const [previewStart, setPreviewStart] = useState(() => yearAgo(view.data_day));
  const [preview, setPreview] = useState<Preview | null>(null);
  const nextRev = (view.plan?.rev ?? 0) + 1;
  const allocated = plan.sleeves.reduce((sum, s) => sum + s.amount, 0);
  const problems = planProblems(plan);

  const patchSleeve = (index: number, patch: Partial<SleeveConfig>) =>
    setPlan((p) => ({ ...p, sleeves: p.sleeves.map((s, i) => (i === index ? { ...s, ...patch } : s)) }));

  const addSleeve = () => {
    const left = Math.max(10_000, plan.total - allocated);
    setPlan((p) => ({ ...p, sleeves: [...p.sleeves, newSleeve(`바구니 ${p.sleeves.length + 1}`, left)] }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (problems.length) return;
    setBusy("save");
    try {
      const out = await api.put<{ rev: number; changes: string[] }>("/api/sleeves/plan", { config: plan, note });
      toast.success(`운용 계획 r${out.rev}을 저장했습니다`);
      refreshSleeves();
      onDone();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
    }
  };

  const runPreview = async () => {
    setBusy("preview");
    try {
      setPreview(await api.post<Preview>("/api/sleeves/preview", { config: plan, start: previewStart }));
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <form onSubmit={save} className="space-y-4" aria-label="운용 계획 고치기">
      <Panel title={`운용 계획 고치기 · 저장하면 r${nextRev}`}>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <Field label="총 투입 금액(원)" hint="10만 원 이상" className="w-56">
            {(p) => <TextInput {...p} inputMode="numeric" value={num(plan.total)} onChange={(e) => setPlan({ ...plan, total: parseMoney(e.target.value) })} className="num" />}
          </Field>
          <p className="num mb-5 text-body-sm text-ink-secondary" aria-live="polite">
            바구니에 {won(allocated)} 배정 · {allocated <= plan.total ? <>남은 금액 {won(plan.total - allocated)}</> : <span className="font-semibold text-danger">{won(allocated - plan.total)} 넘음</span>}
          </p>
        </div>

        {plan.sleeves.length === 0 && <p className="text-body-sm text-ink-secondary">바구니가 없습니다. 아래에서 첫 바구니를 더하세요. 예: 중장기 50만 원, ETF 적립 50만 원.</p>}

        {plan.sleeves.map((sleeve, index) => (
          <SleeveFields
            key={sleeve.id || `new-${index}`}
            index={index}
            sleeve={sleeve}
            total={plan.total}
            prices={prices}
            onChange={(patch) => patchSleeve(index, patch)}
            onRemove={() => setPlan((p) => ({ ...p, sleeves: p.sleeves.filter((_, i) => i !== index) }))}
            onPrice={(code, price) => setPrices((m) => ({ ...m, [code]: price }))}
          />
        ))}

        <div className="mt-4 border-t border-divider pt-4">
          <Button icon={<Plus aria-hidden className="size-4" />} onClick={addSleeve} disabled={plan.sleeves.length >= MAX_SLEEVES}>
            바구니 더하기
          </Button>
          <span className="ml-3 text-caption text-ink-muted">최대 {MAX_SLEEVES}개</span>
        </div>
      </Panel>

      <Panel title="저장 전에 과거로 돌려 보기">
        <p className="max-w-reading text-body-sm text-ink-secondary">
          고친 계획을 과거 시작일부터 규칙만·단순 적립 두 방식으로 돌려 봅니다. AI 판단은 그 기간의 주가를 이미 알 수 있어 넣지 않습니다.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Field label="시작일" className="w-48">
            {(p) => <TextInput {...p} type="date" value={previewStart} max={view.data_day ?? undefined} onChange={(e) => setPreviewStart(e.target.value)} className="num" />}
          </Field>
          <Button className="mb-5" busy={busy === "preview"} disabled={busy !== null || plan.sleeves.length === 0 || problems.length > 0 || !previewStart} onClick={() => void runPreview()}>
            과거로 돌려 보기
          </Button>
        </div>
        {preview && <PreviewResult preview={preview} />}
      </Panel>

      <Panel>
        <Field label="변경 메모" hint="이 판에서 무엇을 왜 바꿨는지. 리비전 기록에 남습니다">
          {(p) => <TextInput {...p} value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="예: ETF 바구니를 매월 적립으로 바꿈" />}
        </Field>
        {problems.length > 0 && (
          <div className="mt-2">
            <Notice tone="warning">
              <ul className="list-disc pl-4">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </Notice>
          </div>
        )}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button onClick={onDone} disabled={busy === "save"}>
            취소
          </Button>
          <Button type="submit" variant="primary" busy={busy === "save"} disabled={problems.length > 0 || busy !== null}>
            r{nextRev}으로 저장
          </Button>
        </div>
      </Panel>
    </form>
  );
}

function SleeveFields({ index, sleeve, total, prices, onChange, onRemove, onPrice }: {
  index: number;
  sleeve: SleeveConfig;
  total: number;
  prices: Record<string, number>;
  onChange: (patch: Partial<SleeveConfig>) => void;
  onRemove: () => void;
  onPrice: (code: string, price: number) => void;
}) {
  const share = total > 0 ? sleeve.amount / total : 0;
  const perRound = sleeve.installments > 0 ? sleeve.amount / sleeve.installments : 0;
  return (
    <fieldset className="mt-4 border-t border-divider pt-4">
      <legend className="sr-only">{`바구니 ${index + 1}: ${sleeve.name}`}</legend>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-h6 font-semibold text-ink">
          바구니 {index + 1}
          {!sleeve.id && <span className="ml-2 text-caption font-normal text-ink-muted">새로 더함</span>}
        </h3>
        <Button variant="ghost" size="sm" icon={<X aria-hidden className="size-4" />} onClick={onRemove}>
          이 바구니 빼기
        </Button>
      </div>

      <div className="mt-2 grid gap-x-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="이름" hint="20자 이내">
          {(p) => <TextInput {...p} value={sleeve.name} maxLength={20} onChange={(e) => onChange({ name: e.target.value })} />}
        </Field>
        <Field label="배정 금액(원)" hint={`총액의 ${Math.round(share * 100)}%`}>
          {(p) => <TextInput {...p} inputMode="numeric" value={num(sleeve.amount)} onChange={(e) => onChange({ amount: parseMoney(e.target.value) })} className="num" />}
        </Field>
        <Field label="심의 주기" hint="장 마감 뒤 그 주기의 첫 거래일에 심의">
          {(p) => (
            <Select {...p} value={sleeve.cadence} onChange={(e) => onChange({ cadence: e.target.value as Cadence })}>
              <option value="daily">매일</option>
              <option value="weekly">매주</option>
              <option value="monthly">매월</option>
            </Select>
          )}
        </Field>
        <Field label="나눠 살 횟수" hint={`회차 금액 ${wonShort(perRound)}`}>
          {(p) => (
            <TextInput {...p} inputMode="numeric" value={String(sleeve.installments)} onChange={(e) => onChange({ installments: Math.min(120, Number(e.target.value.replace(/\D/g, "")) || 0) })} className="num" />
          )}
        </Field>
      </div>

      <div className="mt-1 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-label font-medium text-ink">방식</p>
          <RadioRow legend={`바구니 ${index + 1} 방식`} name={`mode-${index}`} value={sleeve.mode} onChange={(mode: Mode) => onChange({ mode })}
            options={[{ value: "paper", label: "가상 운용" }, { value: "alert", label: "알림만" }]} />
          <p className="text-caption text-ink-muted">{MODE_HINT[sleeve.mode]}</p>
        </div>
        <div>
          <p className="mb-1 text-label font-medium text-ink">판단 주체</p>
          <RadioRow legend={`바구니 ${index + 1} 판단 주체`} name={`decider-${index}`} value={sleeve.decider} onChange={(decider: Decider) => onChange({ decider })}
            options={[{ value: "rules", label: "규칙" }, { value: "ai", label: "AI 위원회" }, { value: "hybrid", label: "규칙 + AI 분기" }]} />
          <p className="text-caption text-ink-muted">{DECIDER_HINT[sleeve.decider]}</p>
          {sleeve.decider === "ai" && (
            <Field label="AI 심의 깊이" className="mt-2 w-64">
              {(p) => (
                <Select {...p} value={sleeve.depth} onChange={(e) => onChange({ depth: e.target.value as Depth })}>
                  {Object.entries(DEPTH_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          )}
        </div>
      </div>

      <Field
        label="운용 지침(위원회에 주는 세부 프롬프트)"
        className="mt-3"
        hint={`${sleeve.mandate.length} / ${MANDATE_MAX}자 · ${sleeve.decider === "rules" ? "규칙 판단에서는 쓰지 않고 기록으로만 남습니다" : "판단 관점을 정하지만 허용 행동·금액 범위·리스크 거부권을 넘지 못합니다"}`}
      >
        {(p) => (
          <TextArea {...p} rows={3} maxLength={MANDATE_MAX} value={sleeve.mandate} onChange={(e) => onChange({ mandate: e.target.value })}
            placeholder="예: 3년 이상 들고 갈 대형주를 모은다. 급등한 주에는 덜 사고, 크게 빠진 주에는 더 모은다." />
        )}
      </Field>

      <ItemList sleeve={sleeve} prices={prices} onChange={onChange} onPrice={onPrice} />
    </fieldset>
  );
}

function ItemList({ sleeve, prices, onChange, onPrice }: { sleeve: SleeveConfig; prices: Record<string, number>; onChange: (patch: Partial<SleeveConfig>) => void; onPrice: (code: string, price: number) => void }) {
  const setItem = (code: string, patch: { kind?: Kind; weight?: number }) =>
    onChange({ items: sleeve.items.map((i) => (i.code === code ? { ...i, ...patch } : i)) });
  return (
    <div className="mt-3">
      <p className="text-label font-medium text-ink">
        종목 {sleeve.items.length} / {MAX_ITEMS}
      </p>
      {sleeve.items.length > 0 && (
        <ul className="mt-1 divide-y divide-divider border-y border-divider">
          {sleeve.items.map((item) => {
            const base = baseAmount(sleeve, item.code);
            const price = prices[item.code];
            const rounds = roundsPerShare(base, price);
            return (
              <li key={item.code} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                <span className="min-w-48 flex-1">
                  <span className="block text-body-sm font-medium text-ink">{item.name || item.code}</span>
                  <span className="num block text-caption text-ink-muted">
                    {item.code}
                    {price ? ` · 1주 ${won(price)}` : ""} · 회차 {won(base)}
                  </span>
                  {rounds && <span className="num block text-caption text-warning">1주 값이 회차 금액보다 커서 약 {rounds}회차마다 1주를 삽니다</span>}
                </span>
                <label className="flex items-center gap-2 text-label whitespace-nowrap text-ink-secondary">
                  종류
                  <Select value={item.kind} onChange={(e) => setItem(item.code, { kind: e.target.value as Kind })} className="h-8 w-24" aria-label={`${item.name} 종류`}>
                    <option value="stock">주식</option>
                    <option value="etf">ETF</option>
                  </Select>
                </label>
                <label className="flex items-center gap-2 text-label whitespace-nowrap text-ink-secondary">
                  비중
                  <Select value={String(item.weight)} onChange={(e) => setItem(item.code, { weight: Number(e.target.value) })} className="num h-8 w-20" aria-label={`${item.name} 비중`}>
                    {WEIGHTS.map((w) => (
                      <option key={w} value={String(w)}>
                        {w}
                      </option>
                    ))}
                  </Select>
                </label>
                <Button variant="ghost" size="sm" icon={<X aria-hidden className="size-4" />} onClick={() => onChange({ items: sleeve.items.filter((i) => i.code !== item.code) })} aria-label={`${item.name} 빼기`}>
                  빼기
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {sleeve.items.length < MAX_ITEMS && (
        <AddItem
          existing={sleeve.items.map((i) => i.code)}
          onAdd={(found) => {
            onPrice(found.code, found.close);
            onChange({ items: [...sleeve.items, { code: found.code, name: found.name, kind: found.kind, weight: 1 }] });
          }}
        />
      )}
    </div>
  );
}

/** 이름으로 찾거나(유니버스 안) 6자리 코드로 확인해서(ETF 등 유니버스 밖도) 더한다. 더할 때 일봉을 받아 둔다. */
function AddItem({ existing, onAdd }: { existing: string[]; onAdd: (found: Lookup) => void }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const isCode = /^[0-9A-Za-z]{6}$/.test(q.trim());
  const search = useStockSearch(isCode ? "" : q);
  const add = async (code: string) => {
    if (existing.includes(code.toUpperCase())) {
      toast.error("이미 넣은 종목입니다");
      return;
    }
    setBusy(true);
    try {
      const found = await api.get<Lookup>(`/api/sleeves/lookup?code=${encodeURIComponent(code.toUpperCase())}`);
      onAdd(found);
      setQ("");
      toast.success(`${found.name}(${found.kind_label})을 넣었습니다`);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  const results = (search.data?.results ?? []).filter((r) => !existing.includes(r.code)).slice(0, 6);
  return (
    <div className="mt-2">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="종목 더하기" hint="이름으로 찾거나 6자리 코드를 넣으세요. ETF는 코드로 넣습니다(예: 069500)" className="min-w-0 flex-1">
          {(p) => (
            <TextInput
              {...p}
              value={q}
              onChange={(e) => setQ(e.target.value.slice(0, 30))}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (isCode) void add(q.trim());
                }
              }}
              placeholder="삼성전자 또는 069500"
              autoComplete="off"
            />
          )}
        </Field>
        <Button className="mb-5" icon={<Search aria-hidden className="size-4" />} busy={busy} disabled={!isCode || busy} onClick={() => void add(q.trim())}>
          코드로 확인
        </Button>
      </div>
      {!isCode && q.trim() && (
        <ul className="-mt-3 mb-2 divide-y divide-divider rounded-md border border-divider" aria-label="찾은 종목">
          {results.length === 0 ? (
            <li className="px-3 py-2 text-body-sm text-ink-muted">{search.isFetching ? "찾는 중" : "찾은 종목이 없습니다. ETF·유니버스 밖 종목은 6자리 코드로 넣으세요"}</li>
          ) : (
            results.map((r) => (
              <li key={r.code}>
                <button type="button" disabled={busy} onClick={() => void add(r.code)} className="tap flex min-h-11 w-full items-center justify-between gap-3 px-3 text-left text-body-sm text-ink hover:bg-secondary">
                  <span>{r.name}</span>
                  <span className="num text-caption text-ink-muted">
                    {r.code} · {r.sector}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function yearAgo(day: string | null): string {
  const base = day ? new Date(`${day}T00:00:00`) : new Date();
  base.setFullYear(base.getFullYear() - 1);
  const y = base.getFullYear();
  const m = String(base.getMonth() + 1).padStart(2, "0");
  const d = String(base.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
