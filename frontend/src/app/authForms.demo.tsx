/** 공개 데모 빌드에서 authForms.tsx 대신 묶이는 빈 부품(vite.config.ts). 로그인·등록 양식과 그 문구를 공개 사이트에 싣지 않는다. */

import type * as Real from "./authForms";

export const LoginForm = (_props: Parameters<typeof Real.LoginForm>[0]) => null;
export const SetupFlow = (_props: Parameters<typeof Real.SetupFlow>[0]) => null;
export const TotpQr = (_props: Parameters<typeof Real.TotpQr>[0]) => null;
export const RecoveryCodes = (_props: Parameters<typeof Real.RecoveryCodes>[0]) => null;
