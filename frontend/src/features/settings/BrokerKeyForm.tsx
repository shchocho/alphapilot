/** 증권사 키 넣기·바꾸기·지우기. 공개 데모 빌드에서는 이 파일 대신 BrokerKeyForm.demo.tsx가 묶인다(vite.config.ts). */

import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button, DisclosureIcon, Field, SUMMARY, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import { notifyError, queryClient } from "@/lib/queries";
import { useElevated } from "@/lib/stepup";

export function BrokerKeyForm({ env, stored, onSaved }: { env: "mock" | "live"; stored: boolean; onSaved: () => void }) {
  const elevated = useElevated();
  const [appKey, setAppKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [busy, setBusy] = useState(false);

  const done = (message: string) => {
    toast.success(message);
    setAppKey("");
    setSecretKey("");
    onSaved();
    void queryClient.invalidateQueries({ queryKey: ["broker-keys"] });
    void queryClient.invalidateQueries({ queryKey: ["settings"] });
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await elevated(() => api.put("/api/settings/broker/keys", { env, app_key: appKey.trim(), secret_key: secretKey.trim() }));
      done("키를 암호화해 저장했습니다. 연결 확인을 눌러 보세요");
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await elevated(() => api.delete(`/api/settings/broker/keys/${env}`));
      done("화면에서 넣은 키를 지웠습니다. .env에 키가 있으면 그것을 씁니다");
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="group">
      <summary className={SUMMARY}>
        <DisclosureIcon />
        {stored ? "키 바꾸기" : "키 넣기"}
      </summary>
      <form onSubmit={save} className="mt-2 space-y-2">
        <Field label="앱키">{(p) => <TextInput {...p} type="password" autoComplete="off" spellCheck={false} value={appKey} onChange={(e) => setAppKey(e.target.value)} required />}</Field>
        <Field label="시크릿키">{(p) => <TextInput {...p} type="password" autoComplete="off" spellCheck={false} value={secretKey} onChange={(e) => setSecretKey(e.target.value)} required />}</Field>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" variant="primary" busy={busy} disabled={appKey.trim().length < 8 || secretKey.trim().length < 8}>
            저장
          </Button>
          {stored && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void remove()}>
              화면에서 넣은 키 지우기
            </Button>
          )}
        </div>
        <p className="text-label text-ink-muted">저장하거나 지울 때 인증 코드를 다시 묻습니다.</p>
      </form>
    </details>
  );
}

/** 거래 환경 패널 아래의 키 안내. */
export function BrokerKeyNote() {
  return (
    <p className="mt-3 text-label text-ink-muted">
      키움 앱키와 시크릿키는 여기서 넣거나 서버의 .env 파일에 둡니다. 여기서 넣은 키는 서버 비밀키로 암호화해 DB에 저장하고 .env 값보다 먼저 쓰며, 화면으로 다시 보여 주지 않습니다. 키움 개발자 사이트에 이 서버의 고정 IP를 등록해야 합니다. 자세한 순서는 docs/kiwoom-setup.md에 있습니다.
    </p>
  );
}
