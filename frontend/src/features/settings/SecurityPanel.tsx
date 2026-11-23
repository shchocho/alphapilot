/** 설정 › 보안: 로그인된 기기와 최근 조작 기록. 공개 데모 빌드에서는 SecurityPanel.demo.tsx가 대신 묶인다(vite.config.ts). */

import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/app/AuthGate";
import { Button, cx, ErrorState, Panel, SkeletonRows, TD, TH } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { notifyError, useSessions } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";
import type { SettingsView } from "@/lib/types";

const AUDIT: Record<string, string> = {
  login: "로그인",
  login_failed: "로그인 실패",
  login_recovery: "복구 코드로 로그인",
  password_changed: "비밀번호 변경",
  password_change_failed: "비밀번호 변경 실패",
  recovery_codes_issued: "복구 코드 새로 만듦",
  totp_reset: "인증 앱 다시 연결",
  broker_keys_saved: "증권사 키 저장",
  broker_keys_deleted: "증권사 키 지움",
  setup_completed: "처음 등록 완료",
  stepup: "재인증",
  stepup_failed: "재인증 실패",
  logout_all: "모든 기기 로그아웃",
  engine_start: "엔진 켬",
  engine_pause: "일시정지",
  engine_stop: "정지",
  engine_liquidate: "전량 매도 후 정지",
  engine_confirm_resume: "재시작 확인",
  env_switch: "거래 환경 전환",
  intent_approved: "주문 계획 승인",
  intent_rejected: "주문 계획 거절",
  settings_engine: "엔진 설정 변경",
  settings_limits: "리스크 한도 변경",
  sim_reset: "시뮬레이션 초기화",
  broker_test_ok: "증권사 연결 확인 성공",
  broker_test_failed: "증권사 연결 확인 실패",
};

export function SecurityPanel({ view }: { view: SettingsView }) {
  const sessions = useSessions();
  const elevated = useElevated();
  const { logout } = useAuth();
  const [busy, setBusy] = useState(false);

  const logoutAll = async () => {
    setBusy(true);
    try {
      await elevated(() => api.post("/api/auth/logout-all"));
      toast.success("모든 기기에서 로그아웃했습니다");
      await logout().catch(() => undefined);
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="보안"
      actions={
        <Button size="sm" busy={busy} onClick={() => void logoutAll()}>
          모든 기기에서 로그아웃
        </Button>
      }
    >
      <p className="num text-body-sm text-ink-secondary">
        서버 모드 {view.server.env === "prod" ? "운영" : "개발"} · 접속을 허용한 주소 {view.server.allowed_hosts.join(", ")}
      </p>
      {sessions.isPending ? (
        <SkeletonRows rows={3} />
      ) : sessions.isError ? (
        <div className="mt-3">
          <ErrorState message={errorMessage(sessions.error)} onRetry={() => void sessions.refetch()} />
        </div>
      ) : (
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div>
            <h3 className="mb-1 text-body-sm font-semibold text-ink">로그인된 기기 {sessions.data.sessions.length}대</h3>
            <ul className="divide-y divide-divider rounded-md border border-divider">
              {sessions.data.sessions.map((s, i) => (
                <li key={`${s.created_at}-${i}`} className="px-3 py-2 text-body-sm">
                  <span className="num font-semibold text-ink">{s.ip || "주소 모름"}</span>{" "}
                  <span className="num text-label text-ink-muted">
                    마지막 사용 {s.last_seen.slice(0, 16).replace("T", " ")} · 로그인 {s.created_at.slice(0, 16).replace("T", " ")}
                  </span>
                  <span className="block truncate text-label text-ink-muted">{s.user_agent}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-1 text-body-sm font-semibold text-ink">최근 조작 기록</h3>
            <div className="max-h-72 overflow-auto rounded-md border border-divider">
              <table className="w-full">
                <caption className="sr-only">최근 로그인과 설정 변경 기록</caption>
                <thead className="sticky top-0 bg-surface">
                  <tr>
                    <th scope="col" className={TH}>
                      시각
                    </th>
                    <th scope="col" className={TH}>
                      한 일
                    </th>
                    <th scope="col" className={TH}>
                      접속 주소
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.data.audit.map((a, i) => (
                    <tr key={`${a.ts}-${i}`}>
                      <td className={cx(TD, "num whitespace-nowrap")}>{a.ts.slice(5, 16).replace("T", " ")}</td>
                      <td className={cx(TD, a.action.endsWith("failed") && "font-semibold text-danger")}>{AUDIT[a.action] ?? a.action}</td>
                      <td className={cx(TD, "num")}>{a.ip}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
