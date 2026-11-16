/** 위험한 동작 앞의 재인증. 서버가 stepup_required를 돌려주면 인증 코드를 다시 받고 같은 요청을 한 번 더 보낸다. */

import { createContext, useCallback, useContext, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Button, Field, Modal, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage } from "./api";

type Ask = (reason: string) => Promise<void>;
const StepUpContext = createContext<Ask>(() => Promise.reject(new ApiError(0, "cancelled", "취소했습니다")));

interface Pending {
  reason: string;
  resolve: () => void;
  reject: (error: Error) => void;
}

export function StepUpProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pendingRef = useRef<Pending | null>(null);
  pendingRef.current = pending;

  const ask = useCallback<Ask>(
    (reason) =>
      new Promise<void>((resolve, reject) => {
        setCode("");
        setError(null);
        setPending({ reason, resolve, reject });
      }),
    [],
  );

  const close = (open: boolean) => {
    if (open || busy) return;
    pendingRef.current?.reject(new ApiError(0, "cancelled", "취소했습니다"));
    setPending(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/stepup", { code: code.trim() });
      pending.resolve();
      setPending(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <StepUpContext.Provider value={ask}>
      {children}
      <Modal open={pending !== null} onOpenChange={close} title="인증 코드 다시 입력" description={pending?.reason}>
        <form onSubmit={submit} className="space-y-4">
          <Field label="인증 앱의 6자리 코드" hint="확인하면 5분 동안 다시 묻지 않습니다" error={error}>
            {(props) => (
              <TextInput
                {...props}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                className="num tracking-widest"
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => close(false)} disabled={busy}>
              취소
            </Button>
            <Button type="submit" variant="primary" busy={busy} disabled={code.length !== 6}>
              확인
            </Button>
          </div>
        </form>
      </Modal>
    </StepUpContext.Provider>
  );
}

/** fn을 실행하고, 재인증이 필요하다는 답이 오면 코드를 받은 뒤 한 번 더 실행한다. */
export function useElevated(): <T>(fn: () => Promise<T>) => Promise<T> {
  const ask = useContext(StepUpContext);
  return useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      try {
        return await fn();
      } catch (error) {
        if (error instanceof ApiError && error.needsStepUp) {
          await ask(error.message);
          return await fn();
        }
        throw error;
      }
    },
    [ask],
  );
}
