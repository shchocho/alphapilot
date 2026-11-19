/** 로그인 관문. 처음에는 비밀번호와 인증 앱(TOTP)을 등록하고, 그 뒤로는 둘 다 넣어야 들어온다. */

import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Button, ErrorState, Field, Notice, SkeletonRows, TextInput } from "@/components/ui";
import { api, DEMO, errorMessage, setCsrf, setUnauthenticatedHandler } from "@/lib/api";
import { queryClient, useAuthState } from "@/lib/queries";
import { endSession } from "@/lib/session";
import { Landing } from "@/features/landing/Landing";

const AuthContext = createContext<{ logout: () => Promise<void> }>({ logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

/** 첫 화면(Landing) 안에 놓인 양식인지. 그 안에서는 틀 없이 내용만 그리고, 열자마자 포커스를 가져가지 않는다. */
const EmbeddedContext = createContext(false);

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuthState();

  useEffect(() => {
    setUnauthenticatedHandler(() => void queryClient.invalidateQueries({ queryKey: ["auth"] }));
  }, []);

  if (auth.data?.authenticated) setCsrf(auth.data.csrf);

  const logout = async () => {
    try {
      await api.post("/api/auth/logout");
    } finally {
      setCsrf(null);
      await endSession(queryClient);
    }
  };

  if (auth.isPending) {
    return (
      <AuthFrame title="불러오는 중">
        <SkeletonRows rows={3} />
      </AuthFrame>
    );
  }
  if (auth.isError) {
    return (
      <AuthFrame title="서버에 연결하지 못했습니다">
        <ErrorState message={errorMessage(auth.error)} onRetry={() => void auth.refetch()} />
      </AuthFrame>
    );
  }
  if (auth.data.authenticated) return <AuthContext.Provider value={{ logout }}>{children}</AuthContext.Provider>;
  // 공개 데모(GitHub Pages)에는 비밀번호·인증 코드 입력칸을 두지 않는다. 공개 페이지의 로그인 양식은 피싱 오판의 가장 큰 원인이다.
  if (DEMO) {
    return (
      <EmbeddedContext.Provider value={true}>
        <Landing action="demo">
          <DemoEnter onDone={() => void auth.refetch()} />
        </Landing>
      </EmbeddedContext.Provider>
    );
  }
  const setup = auth.data.setup !== "done";
  return (
    <EmbeddedContext.Provider value={true}>
      <Landing action={setup ? "setup" : "login"}>
        {setup ? <SetupFlow tokenRequired={auth.data.setup_token_required} resumed={auth.data.setup === "pending"} onDone={() => void auth.refetch()} /> : <LoginForm onDone={() => void auth.refetch()} />}
      </Landing>
    </EmbeddedContext.Provider>
  );
}

function AuthFrame({ title, lead, children }: { title: string; lead?: ReactNode; children: ReactNode }) {
  const embedded = useContext(EmbeddedContext);
  if (embedded) {
    return (
      <>
        <h3 className="text-h4 font-bold text-ink">{title}</h3>
        {lead && <p className="mt-1 mb-5 text-body-sm text-ink-secondary">{lead}</p>}
        <div className={lead ? "" : "mt-5"}>{children}</div>
      </>
    );
  }
  return (
    <main className="grid min-h-dvh place-items-center bg-canvas px-4 py-8">
      <div className="w-full max-w-md overflow-hidden rounded-lg border border-divider bg-surface">
        <div className="border-b border-divider px-6 py-4">
          <p className="text-h5 font-bold">AlphaPilot</p>
          <p className="text-caption text-ink-muted">국내 주식 자동매매 관제</p>
        </div>
        <div className="p-6">
          <h1 className="text-h4 font-bold text-ink">{title}</h1>
          {lead && <p className="mt-1 mb-5 text-body-sm text-ink-secondary">{lead}</p>}
          <div className={lead ? "" : "mt-5"}>{children}</div>
        </div>
      </div>
    </main>
  );
}

function CodeInput(props: React.InputHTMLAttributes<HTMLInputElement> & { onCode: (code: string) => void }) {
  const { onCode, ...rest } = props;
  return (
    <TextInput
      {...rest}
      onChange={(e) => onCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
      inputMode="numeric"
      autoComplete="one-time-code"
      className="num tracking-widest"
    />
  );
}

function DemoEnter({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const enter = async () => {
    setBusy(true);
    try {
      const result = await api.post<{ csrf: string }>("/api/auth/login");
      setCsrf(result.csrf);
      onDone();
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthFrame title="데모 보기" lead="예시 데이터로 대시보드·종목·백테스트 화면을 둘러봅니다. 아무것도 입력하지 않습니다.">
      <Button type="button" variant="primary" busy={busy} onClick={() => void enter()} className="w-full">
        데모 둘러보기
      </Button>
    </AuthFrame>
  );
}

function LoginForm({ onDone }: { onDone: () => void }) {
  const embedded = useContext(EmbeddedContext);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ csrf: string }>("/api/auth/login", { password, code });
      setCsrf(result.csrf);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame title="로그인" lead="비밀번호와 인증 앱의 6자리 코드를 함께 입력합니다.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="비밀번호">{(p) => <TextInput {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus={!embedded} required />}</Field>
        <Field label="인증 코드" hint="인증 앱에 보이는 6자리 숫자">
          {(p) => <CodeInput {...p} value={code} onCode={setCode} required />}
        </Field>
        {error && <ErrorState message={error} />}
        <Button type="submit" variant="primary" busy={busy} disabled={!password || code.length !== 6} className="w-full">
          로그인
        </Button>
      </form>
    </AuthFrame>
  );
}

function SetupFlow({ tokenRequired, resumed, onDone }: { tokenRequired: boolean; resumed: boolean; onDone: () => void }) {
  const embedded = useContext(EmbeddedContext);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mismatch = again.length > 0 && password !== again;

  useEffect(() => {
    if (!secret) return;
    let alive = true;
    import("qrcode")
      .then((QRCode) => QRCode.toDataURL(secret.otpauth_uri, { margin: 1, width: 220, errorCorrectionLevel: "M" }))
      .then((url) => alive && setQr(url))
      .catch(() => alive && setQr(""));
    return () => {
      alive = false;
    };
  }, [secret]);

  const begin = async (event: FormEvent) => {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      setSecret(await api.post<{ secret: string; otpauth_uri: string }>("/api/auth/setup", { password, setup_token: token }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/setup/confirm", { code });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  if (secret) {
    return (
      <AuthFrame title="인증 앱 연결" lead="Google Authenticator 같은 인증 앱으로 아래 QR을 찍고, 앱에 뜬 6자리 코드를 입력하세요.">
        <form onSubmit={confirm} className="space-y-4">
          <div className="flex flex-col items-center gap-3 rounded-lg bg-surface-sunken p-4">
            {qr ? <img src={qr} alt="인증 앱 등록용 QR 코드" width={220} height={220} className="rounded-xs" /> : <div className="skeleton size-55" />}
            <p className="text-center text-label text-ink-muted">
              QR을 찍을 수 없으면 이 키를 앱에 직접 입력하세요
              <br />
              <code className="num mt-1 inline-block text-body-sm break-all text-ink select-all">{secret.secret}</code>
            </p>
          </div>
          <Field label="인증 코드">{(p) => <CodeInput {...p} value={code} onCode={setCode} autoFocus required />}</Field>
          {error && <ErrorState message={error} />}
          <Button type="submit" variant="primary" busy={busy} disabled={code.length !== 6} className="w-full">
            등록 마치기
          </Button>
        </form>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="처음 등록" lead="이 서버를 쓸 한 사람의 비밀번호를 정합니다. 다음 단계에서 인증 앱을 연결합니다.">
      <form onSubmit={begin} className="space-y-4">
        {resumed && <Notice tone="warning">이전 등록이 끝나지 않았습니다. 비밀번호를 다시 정하면 새 QR이 나옵니다.</Notice>}
        <Field label="비밀번호" hint="12자 이상">
          {(p) => <TextInput {...p} type="password" autoComplete="new-password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} autoFocus={!embedded} required />}
        </Field>
        <Field label="비밀번호 확인" error={mismatch ? "두 비밀번호가 다릅니다" : null}>
          {(p) => <TextInput {...p} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />}
        </Field>
        {tokenRequired && (
          <Field label="설치 토큰" hint="서버 환경변수 AP_SETUP_TOKEN에 넣은 값">
            {(p) => <TextInput {...p} type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} required />}
          </Field>
        )}
        {error && <ErrorState message={error} />}
        <Button type="submit" variant="primary" busy={busy} disabled={password.length < 12 || password !== again} className="w-full">
          다음: 인증 앱 연결
        </Button>
      </form>
    </AuthFrame>
  );
}
