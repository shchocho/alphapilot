/** 공개 데모용 재인증. 데모에는 로그인이 없어서 인증 코드 입력창 없이 요청을 그대로 보낸다. */

import { useCallback, type ReactNode } from "react";

export function StepUpProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function useElevated(): <T>(fn: () => Promise<T>) => Promise<T> {
  return useCallback(<T,>(fn: () => Promise<T>) => fn(), []);
}
