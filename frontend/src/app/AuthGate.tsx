/** 로그인 관문. 처음에는 아이디·비밀번호와 인증 앱(TOTP)을 등록하고, 그 뒤로는 셋 다 넣어야 들어온다. 인증 앱을 잃어버리면 복구 코드로 들어온다. */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { AuthFrame, EmbeddedContext } from "@/app/AuthFrame";
import { LoginForm, SetupFlow } from "@/app/authForms";
import { Button, ErrorState, SkeletonRows } from "@/components/ui";
import { api, DEMO, errorMessage, setCsrf, setUnauthenticatedHandler } from "@/lib/api";
import { queryClient, useAuthState } from "@/lib/queries";
import { endSession } from "@/lib/session";
import { Landing } from "@/features/landing/Landing";

const AuthContext = createContext<{ logout: () => Promise<void> }>({ logout: async () => {} });
export const useAuth = () => useContext(AuthContext);

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
  // 데모 빌드에서는 authForms 자체가 빈 부품(authForms.demo.tsx)으로 바뀌어 묶음에도 들어가지 않는다.
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
