import { describe, expect, it } from "vitest";
import { demoKey } from "./api";

describe("demoKey", () => {
  // backend/scripts/export_demo.py의 key()가 같은 파일 이름을 만들어야 데모가 응답을 찾는다
  it("API 주소를 파일 이름으로 바꾼다", () => {
    expect(demoKey("/api/ledger?limit=100&kind=fill_buy,fill_sell")).toBe("ledger_limit_100_kind_fill_buy_fill_sell");
    expect(demoKey("/api/stocks/005930")).toBe("stocks_005930");
    expect(demoKey("/api/stocks/_all")).toBe("stocks__all");
  });
});
