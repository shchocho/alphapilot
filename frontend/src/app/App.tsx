import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Empty, SkeletonRows } from "@/components/ui";
import { queryClient } from "@/lib/queries";
import { StepUpProvider } from "@/lib/stepup";
import { useThemeVersion, getTheme } from "@/lib/theme";
import { AuthGate } from "./AuthGate";
import { Shell } from "./Shell";

const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const DiscoverPage = lazy(() => import("@/features/discover/DiscoverPage"));
const StockPage = lazy(() => import("@/features/stock/StockPage"));
const CommitteePage = lazy(() => import("@/features/committee/CommitteePage"));
const DecisionPage = lazy(() => import("@/features/committee/DecisionPage"));
const AutoPage = lazy(() => import("@/features/auto/AutoPage"));
const PortfolioPage = lazy(() => import("@/features/portfolio/PortfolioPage"));
const BacktestPage = lazy(() => import("@/features/backtest/BacktestPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));

function Toasts() {
  useThemeVersion();
  return (
    <Toaster
      position="bottom-right"
      mobileOffset={{ bottom: "5rem" }}
      theme={getTheme()}
      // 토스트는 반전 표면: 잠깐 뜨는 결과 알림이 본문과 섞이지 않게 한다
      toastOptions={{ style: { background: "var(--surface-inverse)", color: "var(--ink-inverse)", border: "none", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-2)", fontFamily: "inherit", fontSize: "14px" } }}
    />
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthGate>
          <StepUpProvider>
            <Shell>
              <Suspense fallback={<SkeletonRows rows={6} />}>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/discover" element={<DiscoverPage />} />
                  <Route path="/stocks/:code" element={<StockPage />} />
                  <Route path="/committee" element={<CommitteePage />} />
                  <Route path="/committee/:id" element={<DecisionPage />} />
                  <Route path="/auto" element={<AutoPage />} />
                  <Route path="/portfolio" element={<PortfolioPage />} />
                  <Route path="/backtest" element={<BacktestPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="*" element={<Empty title="없는 화면입니다">주소를 다시 확인하거나 왼쪽 메뉴에서 화면을 고르세요.</Empty>} />
                </Routes>
              </Suspense>
            </Shell>
          </StepUpProvider>
        </AuthGate>
      </BrowserRouter>
      <Toasts />
    </QueryClientProvider>
  );
}
