/** 공개 데모 빌드에서 SecurityPanel.tsx 대신 묶이는 빈 부품(vite.config.ts). 접속 기록은 공개 사이트에 싣지 않는다. */

import type * as Real from "./SecurityPanel";

export const SecurityPanel = (_props: Parameters<typeof Real.SecurityPanel>[0]) => null;
