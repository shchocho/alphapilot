/** 앱 틀: 통장 표지색 레일(넓은 화면)·하단 탭(좁은 화면), 상단 상태 띠, 엔진 정지 단추. */

import * as RD from "@radix-ui/react-dialog";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Bot, ChevronDown, Ellipsis, FlaskConical, Gavel, LayoutDashboard, LogOut, Monitor, Moon, Pause, Play, Settings, Square, Sun, Telescope, TriangleAlert, Wallet, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Badge, Button, cx, Field, Modal, Notice, Spinner, TextInput, type Tone } from "@/components/ui";
import { api } from "@/lib/api";
import { dayLabel, duration, pct } from "@/lib/format";
import { notifyError, refreshAll, useLiveEvents, useStatus } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";
import { useTheme, type ThemeChoice } from "@/lib/theme";
import type { Status } from "@/lib/types";
import { useAuth } from "./AuthGate";

interface NavItem {
  to: string;
  label: string;
  short: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { to: "/", label: "관제", short: "관제", icon: LayoutDashboard },
  { to: "/discover", label: "종목 발굴", short: "발굴", icon: Telescope },
  { to: "/committee", label: "AI 위원회", short: "위원회", icon: Gavel },
  { to: "/auto", label: "자동매매", short: "자동매매", icon: Bot },
  { to: "/portfolio", label: "포트폴리오", short: "보유", icon: Wallet },
  { to: "/backtest", label: "백테스트", short: "백테스트", icon: FlaskConical },
  { to: "/settings", label: "설정", short: "설정", icon: Settings },
];
const TABS = ["/", "/discover", "/auto", "/portfolio"];

const PHASE_LABEL: Record<Status["session"]["phase"], string> = {
  closed: "휴장",
  pre_open: "장 시작 전",
  regular: "장중",
  closing_auction: "종가 동시호가",
  after_close: "장 마감",
};

export function Shell({ children }: { children: ReactNode }) {
  const status = useStatus();
  useLiveEvents(true);
  const s = status.data;

  return (
    <div className="min-h-dvh bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-(--z-modal) focus:rounded-md focus:bg-surface-raised focus:px-3 focus:py-2 focus:text-body-sm focus:font-semibold">
        본문으로 건너뛰기
      </a>
      <Rail status={s} />
      <div className="lg:pl-60">
        <StatusBar status={s} />
        <main id="main" tabIndex={-1} className="mx-auto max-w-wide px-4 pt-4 pb-24 outline-none lg:px-6 lg:pb-10">
          {s && <GlobalNotices status={s} />}
          {children}
        </main>
      </div>
      <TabBar pending={s?.pending_approvals ?? 0} />
    </div>
  );
}

// ── 내비게이션(넓은 화면) ───────────────────────────────────────────────
// 잉크와 종이 바탕 위의 240px 내비. 지금 있는 곳은 잉크 글자와 옅은 채움으로 표시한다.

function Rail({ status }: { status: Status | undefined }) {
  const { logout } = useAuth();
  return (
    <aside className="fixed inset-y-0 left-0 z-(--z-sticky) hidden w-60 flex-col border-r border-divider bg-canvas lg:flex">
      <div className="flex h-12 items-center border-b border-divider px-5">
        <p className="text-h6 font-semibold text-ink">AlphaPilot</p>
      </div>
      <nav aria-label="주 메뉴" className="flex-1 space-y-1 p-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cx(
                "flex h-10 items-center gap-3 rounded-md px-3 text-body-sm no-underline transition-colors duration-(--duration-fast)",
                isActive ? "bg-secondary font-semibold text-ink" : "font-medium text-ink-secondary hover:bg-secondary hover:text-ink",
              )
            }
          >
            <item.icon aria-hidden className="size-5 shrink-0" />
            <span className="flex-1">{item.label}</span>
            {item.to === "/auto" && (status?.pending_approvals ?? 0) > 0 && (
              <span className="num grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-caption font-semibold text-on-accent" aria-label={`승인 대기 ${status?.pending_approvals}건`}>
                {status?.pending_approvals}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-3 border-t border-divider p-3">
        {status && (
          <p className="num px-3 text-caption text-ink-muted">
            {status.broker.kind === "kiwoom" ? "키움증권 연결됨" : status.broker.mock_keys || status.broker.live_keys ? "키움 키 등록됨 · 지금은 가상 계좌" : "증권사 연결 전 · 가상 계좌"}
            {status.data_day && (
              <>
                <br />
                일봉 {dayLabel(status.data_day)}까지 · {status.data_source === "naver" ? "네이버 금융" : status.data_source === "sample" ? "견본 데이터" : status.data_source}
              </>
            )}
          </p>
        )}
        <ThemeSwitch />
        <button type="button" onClick={() => void logout()} className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-body-sm font-medium text-ink-secondary transition-colors duration-(--duration-fast) hover:bg-secondary hover:text-ink">
          <LogOut aria-hidden className="size-5" />
          로그아웃
        </button>
      </div>
    </aside>
  );
}

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const options: { value: ThemeChoice; label: string; icon: LucideIcon }[] = [
    { value: "system", label: "기기 설정", icon: Monitor },
    { value: "light", label: "밝게", icon: Sun },
    { value: "dark", label: "어둡게", icon: Moon },
  ];
  return (
    <div role="group" aria-label="화면 밝기" className="grid grid-cols-3 gap-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={theme === o.value}
          aria-label={o.label}
          title={o.label}
          onClick={() => setTheme(o.value)}
          className={cx(
            "tap grid h-8 place-items-center rounded-md border transition-colors duration-(--duration-fast)",
            theme === o.value ? "border-ink bg-secondary text-ink" : "border-divider text-ink-secondary hover:bg-secondary hover:text-ink",
          )}
        >
          <o.icon aria-hidden className="size-4" />
        </button>
      ))}
    </div>
  );
}

// ── 상태 띠 ─────────────────────────────────────────────────────────────

// 거래 환경 표시: 시뮬레이션은 잉크 배지, 모의투자는 외곽선, 실전은 경고색 + 아이콘
const MODE_TONE: Record<Status["env"], Tone> = { sim: "neutral", mock: "outline", live: "warning" };
const STATE_DOT: Record<Status["state"], string> = { running: "bg-success", paused: "bg-warning", stopped: "bg-ink-muted" };

function StatusBar({ status }: { status: Status | undefined }) {
  if (!status) {
    return (
      <div className="sticky top-0 z-(--z-sticky) flex h-12 items-center border-b border-divider bg-canvas px-4">
        <div className="skeleton h-5 w-56" />
      </div>
    );
  }
  const used = Math.max(0, Math.min(1, status.risk.daily_used));
  return (
    <div className="sticky top-0 z-(--z-sticky) flex h-12 items-center gap-x-3 border-b border-divider bg-canvas px-4 text-body-sm lg:gap-x-5 lg:px-6">
      <Badge tone={MODE_TONE[status.env]} className="shrink-0 font-semibold">
        {status.env === "live" && <TriangleAlert aria-hidden className="size-4 text-warning" />}
        {status.env_label}
      </Badge>

      <span className="flex min-w-0 items-center gap-2 font-semibold text-ink" aria-live="polite">
        {status.busy ? <Spinner className="shrink-0 text-ink-secondary" /> : <span aria-hidden className={cx("size-2 shrink-0 rounded-full", STATE_DOT[status.state])} />}
        <span className="truncate">{status.busy || status.state_label}</span>
      </span>

      <span className="num hidden shrink-0 text-ink-secondary md:inline">
        {status.env === "sim" ? (
          status.sim_day ? <>기준일 {dayLabel(status.sim_day)}</> : <>아직 시작 전</>
        ) : (
          <>
            {PHASE_LABEL[status.session.phase]}
            {status.session.seconds_to_close !== null && <> · 마감까지 {duration(status.session.seconds_to_close)}</>}
          </>
        )}
      </span>

      {status.regime && (
        <span className="hidden shrink-0 text-ink-secondary xl:inline">
          시장 {status.regime.label} · {status.regime.allow_new_buys ? <>투자 비중 상한 {pct(status.regime.exposure_cap, 0, false)}</> : "새 매수 중단"}
        </span>
      )}

      <span className="flex-1" />

      <span className="hidden shrink-0 items-center gap-2 text-ink-secondary lg:flex" title="오늘 손실이 한도에 닿으면 새 매수를 멈춥니다">
        일 손실 한도
        <span aria-hidden className="block h-1 w-16 overflow-hidden rounded-full bg-surface-sunken">
          <span className={cx("block h-full rounded-full", used >= 0.8 ? "bg-danger" : used >= 0.5 ? "bg-warning" : "bg-success")} style={{ width: `${Math.max(used * 100, used > 0 ? 6 : 0)}%` }} />
        </span>
        <span className="num font-semibold text-ink">{pct(used, 0, false)} 사용</span>
      </span>

      {status.pending_approvals > 0 && (
        <Link to="/auto" className="num hidden h-8 shrink-0 items-center rounded-md bg-accent-subtle px-3 text-label font-semibold text-ink no-underline transition-colors duration-(--duration-fast) hover:text-accent sm:flex">
          승인 대기 {status.pending_approvals}건
        </Link>
      )}

      <EngineControl status={status} />
    </div>
  );
}

function EngineControl({ status }: { status: Status }) {
  const elevated = useElevated();
  const [busy, setBusy] = useState(false);
  const [liquidateOpen, setLiquidateOpen] = useState(false);

  const act = async (path: string, done: string, body: unknown = {}) => {
    setBusy(true);
    try {
      await elevated(() => api.post(path, body));
      toast.success(done);
      refreshAll();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const item = "flex min-h-11 cursor-pointer flex-col justify-center rounded-md px-3 py-2 outline-none data-[highlighted]:bg-secondary";

  return (
    <div className="flex shrink-0 items-center gap-2">
      {status.state !== "running" && (
        <Button variant="primary" size="sm" busy={busy} icon={<Play aria-hidden className="size-4" />} onClick={() => void act("/api/engine/start", "엔진을 켰습니다")}>
          {status.state === "paused" ? "다시 가동" : "엔진 켜기"}
        </Button>
      )}
      {status.state !== "stopped" && (
        <Menu.Root>
          <Menu.Trigger asChild>
            <Button size="sm" disabled={busy} icon={<Square aria-hidden className="size-4" />}>
              멈추기
              <ChevronDown aria-hidden className="size-4" />
            </Button>
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Content align="end" sideOffset={8} className="z-(--z-dropdown) w-72 rounded-lg bg-surface-raised p-1 text-body-sm shadow-2 data-[state=open]:enter-fade">
              {status.state === "running" && (
                <Menu.Item className={item} onSelect={() => void act("/api/engine/pause", "일시정지했습니다. 새 매수만 멈춥니다")}>
                  <span className="flex items-center gap-2 font-semibold text-ink">
                    <Pause aria-hidden className="size-4" />
                    일시정지
                  </span>
                  <span className="text-label text-ink-muted">새 매수만 멈춥니다. 보유와 손절·익절은 그대로 둡니다.</span>
                </Menu.Item>
              )}
              <Menu.Item className={item} onSelect={() => void act("/api/engine/stop", "정지했습니다. 실행 전 주문 계획을 취소했습니다")}>
                <span className="flex items-center gap-2 font-semibold text-ink">
                  <Square aria-hidden className="size-4" />
                  정지
                </span>
                <span className="text-label text-ink-muted">새 주문을 멈추고 실행 전 계획을 취소합니다. 보유와 손절·익절은 유지합니다.</span>
              </Menu.Item>
              <Menu.Separator className="my-1 h-px bg-surface-sunken" />
              <Menu.Item className={item} onSelect={() => setLiquidateOpen(true)}>
                <span className="flex items-center gap-2 font-semibold text-danger">
                  <TriangleAlert aria-hidden className="size-4" />
                  전량 매도 후 정지
                </span>
                <span className="text-label text-ink-muted">보유 종목을 모두 다음 거래일 시가에 파는 계획을 만들고 정지합니다.</span>
              </Menu.Item>
            </Menu.Content>
          </Menu.Portal>
        </Menu.Root>
      )}
      <LiquidateDialog open={liquidateOpen} onOpenChange={setLiquidateOpen} onConfirm={(text) => act("/api/engine/liquidate", "전량 매도 계획을 만들고 정지했습니다", { confirm: text })} />
    </div>
  );
}

function LiquidateDialog({ open, onOpenChange, onConfirm }: { open: boolean; onOpenChange: (open: boolean) => void; onConfirm: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const phrase = "전량 매도";
  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) setText("");
        onOpenChange(next);
      }}
      title="전량 매도 후 정지"
      description="보유한 모든 종목을 다음 거래일 시가에 파는 계획을 만들고 엔진을 정지합니다. 만든 계획은 되돌릴 수 없고, 다시 사려면 엔진을 켜야 합니다."
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim() !== phrase) return;
          void onConfirm(text.trim()).then(() => {
            setText("");
            onOpenChange(false);
          });
        }}
      >
        <Field label={`확인하려면 '${phrase}'라고 입력하세요`}>{(p) => <TextInput {...p} value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" autoFocus />}</Field>
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)}>취소</Button>
          <Button type="submit" variant="danger" disabled={text.trim() !== phrase}>
            전량 매도하고 정지
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── 전체 안내 ───────────────────────────────────────────────────────────

function GlobalNotices({ status }: { status: Status }) {
  const [busy, setBusy] = useState(false);
  const run = async (path: string, done: string) => {
    setBusy(true);
    try {
      await api.post(path);
      toast.success(done);
      refreshAll();
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };
  const notices: ReactNode[] = [];
  if (status.last_error) {
    notices.push(
      <Notice key="error" tone="danger">
        <strong className="font-semibold">엔진 오류</strong> · {status.last_error}
      </Notice>,
    );
  }
  if (status.resume_check_required) {
    notices.push(
      <Notice
        key="resume"
        tone="warning"
        action={
          <Button size="sm" busy={busy} onClick={() => void run("/api/engine/confirm-resume", "확인했습니다. 설정한 자동화 단계로 돌아갑니다")}>
            확인하고 자동 주문 재개
          </Button>
        }
      >
        서버가 다시 시작됐습니다. 확인하기 전까지 모든 주문 계획은 자동으로 나가지 않고 승인을 기다립니다.
      </Notice>,
    );
  }
  if (!status.has_data) {
    notices.push(
      <Notice
        key="data"
        tone="warning"
        action={
          <Button size="sm" busy={busy || Boolean(status.busy)} onClick={() => void run("/api/engine/refresh-data", "일봉을 갱신했습니다")}>
            일봉 받아오기
          </Button>
        }
      >
        일봉 데이터가 아직 없습니다. 받아오면 종목 발굴과 시뮬레이션을 시작할 수 있습니다.
      </Notice>,
    );
  }
  if (!status.ai.configured && status.decider === "ai") {
    notices.push(
      <Notice key="ai" tone="warning">
        서버에 AI 키가 없어 AI 위원회가 판단하지 못합니다. 이 상태에서는 새 매수를 모두 보류합니다. 서버에 키를 넣거나 <Link to="/auto">자동매매에서 규칙 위원회로 바꾸세요</Link>.
      </Notice>,
    );
  }
  if (notices.length === 0) return null;
  return <div className="mb-4 space-y-2">{notices}</div>;
}

// ── 하단 탭(좁은 화면) ──────────────────────────────────────────────────

function TabBar({ pending }: { pending: number }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { logout } = useAuth();
  const tabs = NAV.filter((n) => TABS.includes(n.to));
  const more = NAV.filter((n) => !TABS.includes(n.to));
  const moreActive = more.some((n) => location.pathname.startsWith(n.to));
  const tab = "relative flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-caption transition-colors duration-(--duration-fast)";

  return (
    <>
      <nav aria-label="주 메뉴" className="fixed inset-x-0 bottom-0 z-(--z-sticky) flex border-t border-divider bg-canvas pb-[env(safe-area-inset-bottom)] lg:hidden">
        {tabs.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => cx(tab, "no-underline", isActive ? "font-semibold text-ink" : "font-medium text-ink-muted")}>
            <item.icon aria-hidden className="size-5" />
            {item.short}
            {item.to === "/auto" && pending > 0 && (
              <span className="num absolute top-1 left-1/2 ml-2 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-caption font-semibold text-on-accent" aria-label={`승인 대기 ${pending}건`}>
                {pending}
              </span>
            )}
          </NavLink>
        ))}
        <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" className={cx(tab, moreActive ? "font-semibold text-ink" : "font-medium text-ink-muted")}>
          <Ellipsis aria-hidden className="size-5" />
          더보기
        </button>
      </nav>
      <RD.Root open={open} onOpenChange={setOpen}>
        <RD.Portal>
          <RD.Overlay className="fixed inset-0 z-(--z-overlay) bg-scrim data-[state=open]:enter-fade" />
          <RD.Content className="fixed inset-x-0 bottom-0 z-(--z-modal) rounded-t-xl bg-surface-raised p-3 pb-[calc(env(safe-area-inset-bottom)+var(--space-3))] shadow-3 data-[state=open]:enter-sheet">
            <RD.Title className="px-2 pb-2 text-body-sm font-semibold text-ink-secondary">더보기</RD.Title>
            <RD.Description className="sr-only">나머지 화면과 화면 밝기, 로그아웃</RD.Description>
            {more.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={() => setOpen(false)} className={({ isActive }) => cx("flex h-12 items-center gap-3 rounded-md px-3 text-body-sm no-underline", isActive ? "bg-secondary font-semibold text-ink" : "font-medium text-ink")}>
                <item.icon aria-hidden className="size-5 text-ink-secondary" />
                {item.label}
              </NavLink>
            ))}
            <div className="mt-2 border-t border-divider px-1 pt-3">
              <ThemeSwitch />
              <button type="button" onClick={() => void logout()} className="mt-2 flex h-12 w-full items-center gap-3 rounded-md px-3 text-body-sm font-medium text-ink">
                <LogOut aria-hidden className="size-5 text-ink-secondary" />
                로그아웃
              </button>
            </div>
          </RD.Content>
        </RD.Portal>
      </RD.Root>
    </>
  );
}
