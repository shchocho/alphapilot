/** 로그아웃 뒤 화면이 가진 서버 상태를 정리한다. */

import type { QueryClient } from "@tanstack/react-query";

/**
 * 로그인 상태를 먼저 다시 받아 화면을 첫 화면으로 돌려보내고, 그다음 계좌·장부 같은 나머지 데이터를 지운다.
 * 전부 지우고(clear) 나서 다시 받으면 화면이 보고 있던 항목이 캐시에서 떨어져 나가 새 상태를 받지 못한다(로그아웃해도 화면이 그대로 남는다).
 */
export async function endSession(client: QueryClient): Promise<void> {
  await client.invalidateQueries({ queryKey: ["auth"] });
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
}
