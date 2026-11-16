import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { endSession } from "./session";

describe("로그아웃 뒤 정리", () => {
  it("화면이 보고 있던 로그인 상태가 '로그인 안 됨'으로 바뀐다(첫 화면으로 돌아간다)", async () => {
    const client = new QueryClient();
    let server = { authenticated: true };
    const observer = new QueryObserver(client, { queryKey: ["auth"], queryFn: async () => server, staleTime: 0 });
    const stop = observer.subscribe(() => {});
    await observer.refetch();
    expect(observer.getCurrentResult().data).toEqual({ authenticated: true });

    server = { authenticated: false }; // 서버에서는 로그아웃이 끝났다
    await endSession(client);

    expect(observer.getCurrentResult().data).toEqual({ authenticated: false });
    stop();
  });
  it("다른 사람이 볼 수 없게 계좌·장부 같은 나머지 데이터는 지운다", async () => {
    const client = new QueryClient();
    client.setQueryData(["dashboard"], { equity: 1 });
    client.setQueryData(["auth"], { authenticated: true });
    client.setQueryDefaults(["auth"], { queryFn: async () => ({ authenticated: false }) });
    await endSession(client);
    expect(client.getQueryData(["dashboard"])).toBeUndefined();
  });
});
