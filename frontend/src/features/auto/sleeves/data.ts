/** 바구니 화면의 서버 조회와 계산 도우미. */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/queries";
import type { Tone } from "@/components/ui";
import type { Comparison, PlanConfig, Revision, SignalDetail, SleeveAction, SleeveConfig, SleevesOverview } from "./types";

export const useSleeves = (enabled = true) =>
  useQuery({ queryKey: ["sleeves"], queryFn: () => api.get<SleevesOverview>("/api/sleeves"), enabled });

export const useRevisions = () =>
  useQuery({ queryKey: ["sleeve-revisions"], queryFn: () => api.get<{ revisions: Revision[] }>("/api/sleeves/revisions") });

export const usePerformance = (id: string | null) =>
  useQuery({ queryKey: ["sleeve-perf", id], queryFn: () => api.get<Comparison>(`/api/sleeves/${id}/performance`), enabled: Boolean(id) });

export const useSignal = (id: string | null) =>
  useQuery({ queryKey: ["sleeve-signal", id], queryFn: () => api.get<SignalDetail>(`/api/sleeves/signals/${id}`), enabled: Boolean(id), staleTime: Infinity });

/** 계획·심의·체결이 바뀐 뒤 바구니 화면을 모두 다시 읽는다. */
export function refreshSleeves(): void {
  for (const key of ["sleeves", "sleeve-revisions", "sleeve-perf"]) void queryClient.invalidateQueries({ queryKey: [key] });
}

// 매수 쪽은 상승 빨강, 매도 쪽은 하락 파랑(DESIGN.md: 매수·매도 배지는 가격 색). 쉬기는 색이 없다.
export const ACTION_TONE: Record<SleeveAction, Tone> = { BUY_MORE: "up", BUY: "up", WAIT: "outline", TRIM: "down", SELL: "down" };

export const DEPTH_LABEL: Record<string, string> = { light: "간단(종목당 1회 호출)", standard: "표준(4회)", deep: "심층(6회)" };
export const ACTION_WORD: Record<string, string> = { BUY_MORE: "더 모으기", BUY: "모으기", WAIT: "쉬기", TRIM: "줄이기", SELL: "팔기" };

/** 한 회차에 이 종목에 쓰는 기본 금액(백엔드 SleeveConfig.base_amount와 같은 계산). */
export function baseAmount(sleeve: Pick<SleeveConfig, "amount" | "installments" | "items">, code: string): number {
  const total = sleeve.items.reduce((sum, item) => sum + item.weight, 0);
  const item = sleeve.items.find((i) => i.code === code);
  if (!item || total <= 0 || sleeve.installments <= 0) return 0;
  return (sleeve.amount / sleeve.installments) * (item.weight / total);
}

/** 1주 값이 회차 금액보다 크면 몇 회차마다 1주를 살 수 있는지. 회차 금액으로 1주 이상 사면 null. */
export function roundsPerShare(base: number, price: number | undefined): number | null {
  if (!price || base <= 0 || price <= base) return null;
  return Math.ceil(price / base);
}

export function emptyPlan(total = 1_000_000): PlanConfig {
  return { total, sleeves: [] };
}

export function newSleeve(name: string, amount: number): SleeveConfig {
  return { id: "", name, amount, items: [], mandate: "", decider: "rules", depth: "standard", cadence: "weekly", installments: 12, mode: "paper" };
}

/** 저장 전 검사(서버도 같은 것을 다시 검사한다). 문제마다 한 문장. */
export function planProblems(plan: PlanConfig): string[] {
  const out: string[] = [];
  const allocated = plan.sleeves.reduce((sum, s) => sum + s.amount, 0);
  if (plan.total < 100_000) out.push("총 투입 금액은 10만 원 이상이어야 합니다");
  if (allocated > plan.total) out.push(`바구니 금액의 합(${allocated.toLocaleString("ko-KR")}원)이 총 투입 금액보다 큽니다`);
  const names = plan.sleeves.map((s) => s.name.trim());
  if (new Set(names).size !== names.length) out.push("바구니 이름이 겹칩니다");
  plan.sleeves.forEach((s) => {
    const label = s.name.trim() || "이름 없는 바구니";
    if (!s.name.trim()) out.push("바구니 이름을 적어 주세요");
    if (s.amount < 10_000) out.push(`'${label}' 금액은 1만 원 이상이어야 합니다`);
    if (s.items.length === 0) out.push(`'${label}'에 종목을 하나 이상 넣어 주세요`);
    if (s.installments < 1 || s.installments > 120) out.push(`'${label}' 나눠 살 횟수는 1~120회입니다`);
  });
  return out;
}
