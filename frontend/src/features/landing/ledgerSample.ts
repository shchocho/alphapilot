/**
 * 첫 화면에 보이는 장부 표본. 2026-10-02~06 시뮬레이션 장부의 8734~8742번을 그대로 옮긴 것이다(지어낸 줄 없음).
 * 3D 장면의 수(신호 38 → 심의 6 → 매수안 3)가 이 가운데 8737번 줄이다.
 * 종목코드는 뺐다: 로그인 전 화면에서는 종목 화면으로 가는 링크를 만들지 않는다.
 */

import type { LedgerRow } from "@/lib/types";

export const LEDGER_SAMPLE: LedgerRow[] = [
  {"seq": 8742, "ts": "2026-10-06T15:30:00+09:00", "env": "sim", "day": "2026-10-06", "kind": "fill_buy", "kind_label": "매수 체결", "chain_id": "261002-067310", "code": null, "name": "하나마이크론", "summary": "변동성 돌파 매수 · 54,200원", "qty": 40, "amount": 2168000, "cash_after": 23962430, "payload": {}},
  {"seq": 8741, "ts": "2026-10-06T15:30:00+09:00", "env": "sim", "day": "2026-10-06", "kind": "fill_buy", "kind_label": "매수 체결", "chain_id": "261002-066570", "code": null, "name": "LG전자", "summary": "변동성 돌파 매수 · 231,500원", "qty": 13, "amount": 3009500, "cash_after": 26130755, "payload": {}},
  {"seq": 8740, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "reject", "kind_label": "거절", "chain_id": "261002-403870", "code": null, "name": "HPSP", "summary": "매수 28주 거절", "qty": 28, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8739, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "approve", "kind_label": "승인", "chain_id": "261002-067310", "code": null, "name": "하나마이크론", "summary": "매수 40주 승인", "qty": 40, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8738, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "approve", "kind_label": "승인", "chain_id": "261002-066570", "code": null, "name": "LG전자", "summary": "매수 13주 승인", "qty": 13, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8737, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "cycle", "kind_label": "장후 심의", "chain_id": "", "code": null, "name": null, "summary": "장후 심의 · 신호 38종목 → 심의 6 → 매수안 3 · 매도안 0 · 국면 중립", "qty": null, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8736, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "intent", "kind_label": "주문 계획", "chain_id": "261002-066570", "code": null, "name": "LG전자", "summary": "매수 13주 승인 대기 · 10월 6일 15:20까지", "qty": 13, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8735, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "intent", "kind_label": "주문 계획", "chain_id": "261002-403870", "code": null, "name": "HPSP", "summary": "매수 28주 승인 대기 · 10월 6일 15:20까지", "qty": 28, "amount": null, "cash_after": null, "payload": {}},
  {"seq": 8734, "ts": "2026-10-02T15:30:00+09:00", "env": "sim", "day": "2026-10-02", "kind": "intent", "kind_label": "주문 계획", "chain_id": "261002-067310", "code": null, "name": "하나마이크론", "summary": "매수 40주 승인 대기 · 10월 6일 15:20까지", "qty": 40, "amount": null, "cash_after": null, "payload": {}},
];
