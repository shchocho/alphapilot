/** 서버 상태 조회(React Query)와 실시간 알림(SSE). */

import { QueryClient, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import { api, ApiError, DEMO, errorMessage } from "./api";
import type {
  Account,
  BrokerKeySources,
  AuthState, BacktestResult, BacktestRun, Committee, Dashboard, DecisionDetail, IntentCard, Portfolio, Screener, SettingsView,
  Status, StockDetail,
} from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      // 4xx는 다시 시도해도 같은 답이므로 재시도하지 않는다.
      retry: (count, error) => (error instanceof ApiError && error.status >= 400 && error.status < 500 ? false : count < 2),
    },
  },
});

export const useAuthState = () => useQuery({ queryKey: ["auth"], queryFn: () => api.get<AuthState>("/api/auth/state"), staleTime: 0 });

export const useStatus = (enabled = true) =>
  useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/api/status"), refetchInterval: 20_000, enabled });

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard") });

export const useScreener = (technique: string | null) =>
  useQuery({
    queryKey: ["screener", technique],
    queryFn: () => api.get<Screener>(`/api/screener${technique ? `?technique=${encodeURIComponent(technique)}` : ""}`),
    placeholderData: (prev) => prev,
  });

export const useStock = (code: string) =>
  useQuery({ queryKey: ["stock", code], queryFn: () => api.get<StockDetail>(`/api/stocks/${code}`), enabled: /^\d{6}$/.test(code) });

export const useStockSearch = (q: string) =>
  useQuery({
    queryKey: ["stock-search", q],
    queryFn: () => api.get<{ results: { code: string; name: string; market: string; sector: string }[] }>(`/api/stocks/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length > 0,
    staleTime: 60_000,
  });

export const useCommittee = (day: string | null) =>
  useQuery({
    queryKey: ["committee", day],
    queryFn: () => api.get<Committee>(`/api/committee${day ? `?day=${day}` : ""}`),
    placeholderData: (prev) => prev,
  });

export const useDecision = (id: string | undefined) =>
  useQuery({ queryKey: ["decision", id], queryFn: () => api.get<DecisionDetail>(`/api/committee/${id}`), enabled: Boolean(id) });

export const usePending = () =>
  useQuery({ queryKey: ["pending"], queryFn: () => api.get<{ cards: IntentCard[] }>("/api/intents/pending") });

export const usePortfolio = () => useQuery({ queryKey: ["portfolio"], queryFn: () => api.get<Portfolio>("/api/portfolio") });

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsView>("/api/settings") });

export const useBacktests = () =>
  useQuery({ queryKey: ["backtests"], queryFn: () => api.get<{ runs: BacktestRun[] }>("/api/backtests") });

export const useBacktest = (id: string | null) =>
  useQuery({ queryKey: ["backtest", id], queryFn: () => api.get<BacktestResult>(`/api/backtests/${id}`), enabled: Boolean(id), staleTime: Infinity });

export interface SessionsView {
  sessions: { created_at: string; last_seen: string; ip: string; user_agent: string }[];
  audit: { ts: string; actor: string; action: string; detail: Record<string, unknown>; ip: string }[];
}
export const useAccount = () => useQuery({ queryKey: ["account"], queryFn: () => api.get<Account>("/api/auth/account") });

export const useBrokerKeys = () => useQuery({ queryKey: ["broker-keys"], queryFn: () => api.get<BrokerKeySources>("/api/settings/broker/keys") });

export const useSessions = () => useQuery({ queryKey: ["sessions"], queryFn: () => api.get<SessionsView>("/api/auth/sessions") });

/** 계좌·장부에 영향을 주는 동작 뒤에 관련 화면을 모두 새로 읽는다. */
export function refreshAll(): void {
  for (const key of ["status", "dashboard", "pending", "portfolio", "committee", "decision", "stock", "settings", "screener"]) {
    void queryClient.invalidateQueries({ queryKey: [key] });
  }
}

/** 오류를 알림으로 보여준다. 사용자가 직접 취소한 경우는 조용히 넘어간다. */
export function notifyError(error: unknown): void {
  if (error instanceof ApiError && error.code === "cancelled") return;
  toast.error(errorMessage(error));
}

/** 서버가 보내는 실시간 알림. 상태는 바로, 장부 변화는 잠깐 모아서 다시 읽는다. */
export function useLiveEvents(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || DEMO || typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events");
    let timer: number | undefined;
    source.onmessage = (event) => {
      let kind = "";
      try {
        kind = (JSON.parse(event.data) as { kind?: string }).kind ?? "";
      } catch {
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["status"] });
      if (kind === "sleeves") void queryClient.invalidateQueries({ queryKey: ["sleeves"] });
      if (kind === "ledger" && timer === undefined) {
        timer = window.setTimeout(() => {
          timer = undefined;
          for (const key of ["dashboard", "pending", "portfolio", "committee"]) void queryClient.invalidateQueries({ queryKey: [key] });
        }, 1200);
      }
    };
    return () => {
      source.close();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled]);
}
