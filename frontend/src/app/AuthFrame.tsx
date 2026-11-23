/** 로그인 관문의 틀. 첫 화면(Landing) 안에서는 틀 없이 내용만 그린다. */

import { createContext, useContext, type ReactNode } from "react";

/** 첫 화면(Landing) 안에 놓인 양식인지. 그 안에서는 틀 없이 내용만 그리고, 열자마자 포커스를 가져가지 않는다. */
export const EmbeddedContext = createContext(false);

export function AuthFrame({ title, lead, children }: { title: string; lead?: ReactNode; children: ReactNode }) {
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
