/** 공개 데모 빌드에서 BrokerKeyForm.tsx 대신 묶이는 빈 부품(vite.config.ts). 키 입력칸을 공개 사이트에 싣지 않는다. */

import type * as Real from "./BrokerKeyForm";

export const BrokerKeyForm = (_props: Parameters<typeof Real.BrokerKeyForm>[0]) => null;
export const BrokerKeyNote = () => (
  <p className="mt-3 text-label text-ink-muted">공개 데모라 증권사에 연결하지 않습니다. 직접 띄운 서버에서는 여기서 키움 연결을 설정합니다.</p>
);
