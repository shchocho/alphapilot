/** 설정 › 계정: 비밀번호 바꾸기, 복구 코드, 인증 앱 다시 연결. 공개 데모 빌드에서는 AccountPanel.demo.tsx가 대신 묶인다(vite.config.ts). */

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { RecoveryCodes, TotpQr } from "@/app/authForms";
import { Button, cx, ErrorState, Field, Notice, Panel, SkeletonRows, TextInput } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { notifyError, queryClient, useAccount } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";

export function AccountPanel() {
  const account = useAccount();
  return (
    <Panel title="계정">
      {account.isPending ? (
        <SkeletonRows rows={2} />
      ) : account.isError ? (
        <ErrorState message={errorMessage(account.error)} onRetry={() => void account.refetch()} />
      ) : (
        <>
          <p className="text-body-sm text-ink-secondary">
            아이디 <span className="num font-semibold text-ink">{account.data.username}</span> · 남은 복구 코드{" "}
            <span className={cx("num font-semibold", account.data.recovery_codes_left <= 2 ? "text-danger" : "text-ink")}>{account.data.recovery_codes_left}개</span>
          </p>
          {account.data.recovery_codes_left === 0 && (
            <div className="mt-3">
              <Notice tone="warning">복구 코드가 없습니다. 인증 앱을 잃어버리면 들어올 수 없으니 새로 만들어 두세요.</Notice>
            </div>
          )}
          <div className="mt-4 grid gap-6 xl:grid-cols-3">
            <PasswordForm />
            <RecoveryCodesBlock />
            <TotpResetBlock />
          </div>
        </>
      )}
    </Panel>
  );
}

function PasswordForm() {
  const elevated = useElevated();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const mismatch = again.length > 0 && next !== again;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const { closed } = await elevated(() => api.post<{ closed: number }>("/api/auth/password", { current, new: next }));
      toast.success(closed ? `비밀번호를 바꿨습니다. 다른 기기 ${closed}대는 로그아웃했습니다` : "비밀번호를 바꿨습니다");
      setCurrent("");
      setNext("");
      setAgain("");
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <h3 className="text-body-sm font-semibold text-ink">비밀번호 바꾸기</h3>
      <Field label="지금 비밀번호">{(p) => <TextInput {...p} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />}</Field>
      <Field label="새 비밀번호" hint="12자 이상">{(p) => <TextInput {...p} type="password" autoComplete="new-password" minLength={12} value={next} onChange={(e) => setNext(e.target.value)} required />}</Field>
      <Field label="새 비밀번호 확인" error={mismatch ? "두 비밀번호가 다릅니다" : null}>
        {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />}
      </Field>
      <Button type="submit" size="sm" variant="primary" busy={busy} disabled={!current || next.length < 12 || next !== again}>
        비밀번호 바꾸기
      </Button>
      <p className="text-label text-ink-muted">바꾸면 이 기기를 뺀 다른 기기는 모두 로그아웃됩니다.</p>
    </form>
  );
}

function RecoveryCodesBlock() {
  const elevated = useElevated();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  const issue = async () => {
    setBusy(true);
    try {
      setCodes((await elevated(() => api.post<{ recovery_codes: string[] }>("/api/auth/recovery-codes"))).recovery_codes);
      void queryClient.invalidateQueries({ queryKey: ["account"] });
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-body-sm font-semibold text-ink">복구 코드</h3>
      <p className="text-body-sm text-ink-secondary">인증 앱을 잃어버렸을 때 6자리 코드 대신 넣습니다. 새로 만들면 이전 코드는 모두 못 씁니다.</p>
      {codes ? (
        <RecoveryCodes codes={codes} />
      ) : (
        <Button size="sm" busy={busy} onClick={() => void issue()}>
          복구 코드 새로 만들기
        </Button>
      )}
    </div>
  );
}

function TotpResetBlock() {
  const elevated = useElevated();
  const [secret, setSecret] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const begin = async () => {
    setBusy(true);
    setError(null);
    try {
      setSecret(await elevated(() => api.post<{ secret: string; otpauth_uri: string }>("/api/auth/totp/reset")));
      setCode("");
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await elevated(() => api.post("/api/auth/totp/confirm", { code }));
      toast.success("새 인증 앱을 연결했습니다. 이전 앱의 코드는 더 이상 받지 않습니다");
      setSecret(null);
    } catch (e) {
      setError(errorMessage(e));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-body-sm font-semibold text-ink">인증 앱 다시 연결</h3>
      {secret ? (
        <form onSubmit={confirm} className="space-y-3">
          <TotpQr secret={secret.secret} uri={secret.otpauth_uri} />
          <Field label="새 앱의 6자리 코드" error={error}>
            {(p) => (
              <TextInput {...p} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" className="num tracking-widest" autoFocus required />
            )}
          </Field>
          <div className="flex gap-2">
            <Button type="submit" size="sm" variant="primary" busy={busy} disabled={code.length !== 6}>
              연결 마치기
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setSecret(null)}>
              취소
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="text-body-sm text-ink-secondary">휴대폰을 바꿨거나 잃어버렸을 때 새 인증 앱을 연결합니다. 새 코드를 확인하기 전까지는 이전 앱이 그대로 쓰입니다.</p>
          <Button size="sm" busy={busy} onClick={() => void begin()}>
            새 인증 앱 연결하기
          </Button>
        </>
      )}
    </div>
  );
}
