# 03. 키움 REST API 연동 명세 — `broker` 어댑터 구현용

- 조사일: 2026-11-15(KST). 범위: 국내주식 REST + WebSocket. 미국주식·금현물·ELW·신용주문은 필요한 곳에서만 언급한다.
- 조사 방식: 공개 자료만 읽었다. 로그인·회원가입·키 발급·주문·실제 API 호출은 하지 않았다. 그래서 "실제 응답의 특성"은 키움증권 공식 저장소에 **실측**으로 기록된 주석과 문서 예시로만 확인했다.
- 근거 우선순위: ① 포털 라이브 API 가이드(2026-11-15 조회) ② 포털 공지·자주묻는질문(FAQ) ③ 키움증권 공식 GitHub(스펙 JSON 원본 2026-09-04, 커밋 2026-09-15) ④ 공식 플러그인·CLI의 실측 주석 ⑤ 커뮤니티 래퍼·블로그(교차 확인용).
- **주의:** 공식 GitHub의 스펙 JSON(2026-09-04)은 2026-09-12 제도 변경(시간외단일가 폐지, GTP 주문유형 추가)과 2026-11-12 계좌 TR 유량 변경을 반영하지 못했다. 둘이 다르면 이 문서는 라이브 가이드·공지를 따른다.

### 표기

| 표시 | 뜻 |
|---|---|
| **[확인됨]** | 공식 출처(포털 가이드·공지·FAQ·키움증권 GitHub)에서 직접 확인 |
| **[확인됨·실측]** | 키움증권 공식 저장소(플러그인·CLI)에 "실측"으로 기록된 응답 특성. 문서 표와 다를 수 있다 |
| **[불확실]** | 공식 출처끼리 어긋나거나, 커뮤니티 관찰뿐이거나, 추론이다. 키를 받은 뒤 모의 도메인에서 검증해야 한다 |
| **[권고]** | 사실이 아니라 이 문서의 설계 권고 |

- "가이드 XXX" 링크는 `https://openapi.kiwoom.com/guide/apiGuideContents/<분류>/<api-id>` 형식이다. 포털의 [API 가이드 화면](https://openapi.kiwoom.com/guide/apiguide)이 불러오는 TR별 상세 내용이며, 화면에 표시되는 "TR 호출 한도"도 여기서 읽었다.
- 모든 시각은 KST다.

---

## 0. 한눈에 보기

### 0.1 도메인

| 구분 | 운영(실전) | 모의투자 | 근거 |
|---|---|---|---|
| REST | `https://api.kiwoom.com` | `https://mockapi.kiwoom.com` | [확인됨] [가이드 au10001](https://openapi.kiwoom.com/guide/apiGuideContents/a1/au10001), [.env.example](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/.env.example) |
| WebSocket 호스트 | `wss://api.kiwoom.com:10000` | `wss://mockapi.kiwoom.com:10000` | [확인됨] [auth.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py), [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B) |
| WebSocket 경로 | `/api/dostk/websocket` | 같음 | [확인됨] 공식 런타임 [ws_client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/ws_client.py)·[테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample)·[FAQ#43](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=43)이 이 경로를 쓴다 |
| (대안 경로) | `/api/websocket` | 같음 | 라이브 가이드의 실시간·조건검색 TR 표와 [튜토리얼](https://openapi.kiwoom.com/guide/index)은 이 경로로 적혀 있다. **[불확실]** 어느 쪽이 정식인지. FAQ#43은 국내(`/api/dostk/websocket`)·미국(`/api/us/websocket`) 경로가 같은 IP로 접속되어 어느 쪽으로 붙어도 수신된다고 설명한다. [권고] 경로를 설정값으로 두고 기본값은 `/api/dostk/websocket` |

### 0.2 핵심 엔드포인트 (모두 `POST`, JSON 본문)

유량 열은 라이브 가이드의 "TR 호출 한도"(계좌·토큰별)다. 모의투자는 TR당 초당 1회다(§5).

| 기능 | api-id | URL | 유량(실전) | 근거 |
|---|---|---|---|---|
| 접근토큰 발급 | au10001 | `/oauth2/token` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/a1/au10001) [확인됨] |
| 접근토큰 폐기 | au10002 | `/oauth2/revoke` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/a2/au10002) [확인됨] |
| 주식기본정보 | ka10001 | `/api/dostk/stkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10001) [확인됨] |
| 종목정보 리스트 | ka10099 | `/api/dostk/stkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10099) [확인됨] |
| 종목정보 조회 | ka10100 | `/api/dostk/stkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10100) [확인됨] |
| 체결정보 | ka10003 | `/api/dostk/stkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10003) [확인됨] |
| 주식호가 | ka10004 | `/api/dostk/mrkcond` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/02/ka10004) [확인됨] |
| 시세표성정보 | ka10007 | `/api/dostk/mrkcond` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/02/ka10007) [확인됨] |
| 틱·분·일·주·월·년봉 | ka10079 / ka10080 / ka10081 / ka10082 / ka10083 / ka10094 | `/api/dostk/chart` | 초당 5회 | [가이드 ka10081](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10081) [확인됨] |
| 정규장 전용 봉 | ka11079 / ka11080 / ka11081 / ka11082 / ka11083 / ka11094 | `/api/dostk/chart` | 초당 5회 | [가이드 ka11081](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka11081) [확인됨] (스펙 JSON에는 없음) |
| 당일거래량상위 | ka10030 | `/api/dostk/rkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10030) [확인됨] |
| 전일대비등락률상위 | ka10027 | `/api/dostk/rkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10027) [확인됨] |
| 거래대금상위 | ka10032 | `/api/dostk/rkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10032) [확인됨] |
| 거래량급증 | ka10023 | `/api/dostk/rkinfo` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10023) [확인됨] |
| 계좌번호조회 | ka00001 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka00001) [확인됨] |
| 계좌평가잔고내역 | kt00018 | `/api/dostk/acnt` | **초당 1회** | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00018), [공지#68](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=68) [확인됨] |
| 예수금상세현황 | kt00001 | `/api/dostk/acnt` | **초당 1회** | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00001) [확인됨] |
| 계좌평가현황 | kt00004 | `/api/dostk/acnt` | **초당 1회** | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00004) [확인됨] |
| 미체결 | ka10075 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10075) [확인됨] |
| 체결 | ka10076 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10076) [확인됨] |
| 당일실현손익상세 | ka10077 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10077) [확인됨] |
| 일자별실현손익 | ka10074 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10074) [확인됨] |
| 당일매매일지 | ka10170 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10170) [확인됨] |
| 계좌별주문체결내역상세 | kt00007 | `/api/dostk/acnt` | **초당 1회** | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00007) [확인됨] |
| 주문인출가능금액 | kt00010 | `/api/dostk/acnt` | 초당 5회 | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00010) [확인됨] |
| 매수·매도·정정·취소 | kt10000 / kt10001 / kt10002 / kt10003 | `/api/dostk/ordr` | 초당 5회 | [가이드 kt10000](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10000) [확인됨] |
| 실시간 시세·주문체결·잔고 | 00, 04, 0B, 0D, 0s, 1h 등 | WebSocket | 세션당 200종목(국내·미국 합산) | [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B) [확인됨] |
| 조건검색 | ka10171~ka10174 | WebSocket | 실시간 조건 10건, 결과 최대 100종목 | [가이드 ka10173](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10173) [확인됨] |

---

## 1. 계정·앱키 준비 (사용자가 직접 할 일)

| # | 사실 | 근거 |
|---|---|---|
| 1 | 키움증권 계좌가 있고 HTS ID를 연결한 고객이면 이용할 수 있다. 수수료율은 HTS와 같다. | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro) |
| 2 | 포털 우측 상단 "API 사용신청" → 로그인 → 이용약관·개인(신용)정보 동의 → 신청. 완료 시 카카오톡 알림톡이 온다. | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo) |
| 3 | 실전 키와 모의투자 키는 별도다. 신청 화면의 "계좌 App Key 관리"와 "모의투자 App Key 관리" 탭이 따로 있다. | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo), [공식 README](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/README.md) |
| 4 | **IP 등록이 필수다.** 허용된 IP에서만 인증되며 최대 10개까지 등록한다. 미등록 IP는 오류 8050("IP가 등록되지 않았습니다") | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo), [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) |
| 5 | 토큰은 발급받은 IP에 묶인다. 다른 IP에서 쓰면 오류 8010. → 서버의 고정 출구 IP에서 발급하고 호출해야 한다(NAT 출구가 여러 개면 위험). | [확인됨] [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) |
| 6 | 계좌 등록: 계좌 비밀번호 + SMS 인증. 실전·모의 각각 20개까지 추가 등록 가능. | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo) |
| 7 | App Key·App Secret은 **각 1회만** 내려받을 수 있다(`계좌번호_appkey.txt`, `계좌번호_appsecret.txt`). 분실하면 기존 키를 해지하고 재발급. | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo), [FAQ#12](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=12) |
| 8 | 계좌는 앱키에 묶인다. REST 요청 본문에 계좌번호 필드가 없다. ka00001로 계좌번호(10자리, 뒤 2자리는 키움 분류값)를 확인한다. 다른 계좌의 토큰을 쓰면 8001. | [확인됨] [가이드 ka00001](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka00001), [FAQ#21](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=21) |
| 9 | 모의투자는 별도 신청: 키움 홈페이지 > 모의투자 > 상시모의투자 > 주식/선물옵션 > 안내. 모의 앱키 만료일은 모의투자 신청 정보를 따른다. | [확인됨] [모의투자 안내](https://openapi.kiwoom.com/intro/mockInvestInfo), [FAQ#11](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=11) |
| 10 | 신청·해지 가능 시간: 00:10~23:50(2026-07-09부터). FAQ#22의 "7~22시"는 이전 안내다. | [확인됨] [공지#50](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=50) |
| 11 | 신청·계좌 등록은 Windows·macOS PC에서 해야 한다. 이후 API 호출은 리눅스 서버에서 가능. 모바일(유동 IP)은 제한. | [확인됨] [FAQ#26](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=26), [FAQ#2](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=2) |
| 12 | **자동 해지:** 3개월 동안 운영(실전) 도메인에 접속하지 않으면 매월 첫 영업일에 해지된다. 모의 도메인만 쓰면 미접속으로 본다. | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro), [FAQ#19](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=19) |
| 13 | OpenAPI+와 REST API는 한쪽만 신청해도 둘 다 쓸 수 있다. | [확인됨] [FAQ#20](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=20) |
| 14 | **시세 이용 제한:** 개인은 본인 자산 투자 목적에만 쓸 수 있고, 제3자 제공·재배포(웹사이트·앱 제공 포함)는 금지된다. 법인은 코스콤·넥스트레이드와 별도 계약이 필요하다. → AlphaPilot은 본인 전용으로 운영하고, 키움 시세를 다른 사용자에게 보여주지 않는다. | [확인됨] [FAQ#39](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=39), [FAQ#28](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=28) |
| 15 | 2026-09-14부터 "최선집행기준 설명서"를 받지 않은 고객은 주문이 거부된다. HTS·MTS 접속 시 뜨는 교부 팝업이나 고객센터(1544-9000)로 해소. | [확인됨] [공지#61](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=61) |
| 16 | 제3자가 만든 프로그램 사용 결과는 고객 책임이며, 키움은 답변하지 않는다. 실전 전에 모의투자로 충분히 시험할 것을 권한다. | [확인됨] [공지#22](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=22) |

---

## 2. 인증

### 2.1 접근토큰 발급 — au10001

`POST {REST}/oauth2/token` — [확인됨] [가이드 au10001](https://openapi.kiwoom.com/guide/apiGuideContents/a1/au10001)

**요청 헤더:** `Content-Type: application/json;charset=UTF-8`만 보낸다.
- 라이브 가이드의 au10001에는 요청 헤더 표가 없고, 공식 런타임([auth.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py))·[테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample)·[TradingView 연동 샘플](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server/blob/main/api-caller.js)이 모두 Content-Type만 보낸다. [확인됨]
- 공식 스펙 JSON(2026-09-04)에는 `api-id`·`authorization`이 필수 헤더로 적혀 있다. 이 둘을 같이 보내도 되는지는 **[불확실]**. 공식 런타임처럼 보내지 않는다.

| 요청 본문 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `grant_type` | String | Y | `client_credentials` 고정 |
| `appkey` | String | Y | 앱키 |
| `secretkey` | String | Y | 시크릿키 |

| 응답 본문 | 설명 |
|---|---|
| `expires_dt` | 만료 **시각** `YYYYMMDDHHmmss`. 공식 런타임은 KST로 해석한다([auth.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py) `_parse_kiwoom_expiry`) [확인됨] |
| `token_type` | `bearer` (소문자) |
| `token` | 접근토큰 |
| `return_code` / `return_msg` | 0이면 정상 |

```http
POST https://mockapi.kiwoom.com/oauth2/token
Content-Type: application/json;charset=UTF-8

{"grant_type": "client_credentials", "appkey": "<APP_KEY>", "secretkey": "<APP_SECRET>"}
```

```json
{
  "expires_dt": "20261116083713",
  "token_type": "bearer",
  "token": "WQJCwyqInphKnR3bSRtB9NE1lv...",
  "return_code": 0,
  "return_msg": "정상적으로 처리되었습니다"
}
```

**토큰 수명 규칙**

| 사실 | 근거 |
|---|---|
| 유효기간 24시간. 24시간마다 재발급 필요. | [확인됨] [이용안내](https://openapi.kiwoom.com/intro/serviceInfo), [FAQ#25](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=25) |
| 발급 후 **6시간 안에** 다시 요청하면 기존 토큰을 그대로 돌려준다. **6시간이 지나** 다시 요청하면 새 토큰을 발급하고 **기존 토큰은 폐기**된다. | [확인됨] [FAQ#25](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=25) (2025-04-07). 더 오래된 [FAQ#10](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=10)은 "갱신 전에는 같은 토큰"이라고만 적었다. 실제 동작은 **[불확실]** — 모의 도메인에서 검증 |
| FAQ#10은 만료 필드를 `expired_at`이라고 적었지만 실제 필드명은 `expires_dt`다. | [확인됨] 가이드 au10001과 대조 |
| 공식 런타임은 만료 600초 전부터 재발급한다(`refresh_buffer_seconds=600`). | [확인됨] [auth.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py) |

**[권고]** 같은 앱키로 토큰을 발급하는 주체를 **엔진 프로세스 하나**로 제한한다. 개발자가 같은 키로 스크립트·CLI를 돌려 6시간 뒤 토큰을 새로 받으면, 엔진이 쓰던 토큰이 폐기되어 8005가 난다. 토큰은 DB(또는 파일)에 `expires_dt`와 함께 저장하고, 8005를 받으면 먼저 저장소의 최신 토큰을 다시 읽고 그래도 실패할 때만 재발급한다.

### 2.2 접근토큰 폐기 — au10002

`POST {REST}/oauth2/revoke`, 헤더는 Content-Type만 — [확인됨] [가이드 au10002](https://openapi.kiwoom.com/guide/apiGuideContents/a2/au10002), [auth.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py)

```json
{"appkey": "<APP_KEY>", "secretkey": "<APP_SECRET>", "token": "<ACCESS_TOKEN>"}
```

응답은 `{"return_code": 0, "return_msg": "정상적으로 처리되었습니다"}`뿐이다. [확인됨]

### 2.3 토큰 사용

| 대상 | 형식 | 근거 |
|---|---|---|
| REST | 헤더 `authorization: Bearer <token>` | [확인됨] 가이드 공통 헤더 설명, [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py) |
| WebSocket | 접속 직후 `{"trnm": "LOGIN", "token": "<token>"}` — `Bearer` 접두어 없음 | [확인됨] [ws_client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/ws_client.py), [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample) |

### 2.4 인증 실패의 모양

| 상황 | 응답 | 근거 |
|---|---|---|
| 만료·무효 토큰 | HTTP 200 + `return_code: 3` + `return_msg: "인증에 실패했습니다[8005:Token이 유효하지 않습니다]"`, 또는 최상위 `return_code: 8005` | [확인됨] [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py)·[errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py) 주석. 커뮤니티 래퍼도 2026-08-15 실서버에서 같은 형태를 확인([base.py](https://github.com/younghwan91/kiwoom-rest-api/blob/main/src/kiwoom_client/base.py)) |
| WebSocket LOGIN 실패 | LOGIN 응답의 `return_code≠0`, `return_msg`에 `CODE=8005` 형태로 세부 코드가 들어갈 수 있다 | [확인됨] [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py) 주석 |
| HTTP 401 | 공식 클라이언트는 401이면 토큰을 다시 받고 1회 재시도한다 | [확인됨] [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py) |
| 재발급 후 1회 재시도 대상 코드 | 8005, 8031, 8103 (최상위 코드 또는 `[NNNN:` 형태로 메시지에 박힌 코드) | [확인됨] [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py) `AUTH_RETRY_RETURN_CODES` |
| 실전 키·토큰을 모의 도메인에(또는 반대로) | 8030(앱키), 8031(토큰) | [확인됨] [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) |

---

## 3. REST 공통 규약

### 3.1 요청

모든 TR이 `POST` + JSON 본문이다. 조회도 POST다. [확인됨] 가이드 각 TR의 Method

| 요청 헤더 | 필수 | 설명 | 근거 |
|---|---|---|---|
| `Content-Type` | Y | `application/json;charset=UTF-8` | [확인됨] 가이드 공통 |
| `api-id` | Y | TR 코드(최대 10자). 라이브 가이드 설명은 "8자리 TR코드, ex) ka00001, usa10099" | [확인됨] [가이드 kt10000](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10000) |
| `authorization` | Y | `Bearer <token>` (최대 1000자) | [확인됨] |
| `cont-yn` | N | 연속조회 시 직전 응답 헤더의 `cont-yn` 값(`Y`) | [확인됨] |
| `next-key` | N | 연속조회 시 직전 응답 헤더의 `next-key` 값(최대 50자) | [확인됨] |

- 첫 조회에서 `cont-yn`·`next-key`를 빼도 되고(공식 런타임 [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py)), `N`·빈 문자열로 보내도 된다(공식 [TradingView 샘플 common.js](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server/blob/main/common.js)). [확인됨]
- 본문의 값은 **숫자도 문자열**로 보낸다(예: `"ord_qty": "1"`). 모든 가이드 예시가 문자열이다. [확인됨]

### 3.2 응답

| 위치 | 필드 | 설명 | 근거 |
|---|---|---|---|
| 헤더 | `api-id` | 요청한 TR | [확인됨] |
| 헤더 | `cont-yn` | `Y`면 다음 데이터가 있음 | [확인됨] |
| 헤더 | `next-key` | 다음 요청에 넣을 키(불투명 문자열) | [확인됨] |
| 본문 | TR별 필드 | **모든 값이 문자열**이다. 가격·수량도 `"+70100"`, `"000000017598258"` 같은 문자열 | [확인됨] 가이드 예시, [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) |
| 본문 | `return_code` | 0 = 정상. 정수 또는 숫자 문자열(`"0"`)로 올 수 있다 | [확인됨] [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py) `normalize_return_code` |
| 본문 | `return_msg` | 메시지. 세부 코드가 `[8005:...]`, `[2000](RC4058:...)`처럼 박혀 올 수 있다 | [확인됨] [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py), [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) |

- **업무 오류도 HTTP 200**으로 온다. 성공 여부는 본문 `return_code`로만 판단한다. [확인됨] [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py) 주석
- 유량 초과는 HTTP 429로 온다(§5). [확인됨·실측] [kw_market.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_market.py) 주석
- 요청 본문 값이 무효(예: 없는 종목코드)일 때 `Method Not Allowed`(HTTP 405)가 날 수 있다. [확인됨] [FAQ#16](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=16)
- 응답 예시의 성공 키가 `returnCode`/`returnMsg`로 적힌 TR(ka10030)이 있다. 실제 응답도 그런지 **[불확실]** — 두 이름을 모두 읽도록 방어한다. [가이드 ka10030](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10030)

### 3.3 연속조회(페이지네이션)

[확인됨] [FAQ#23](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=23), [client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py) `iterate_pages`

1. 첫 요청을 보낸다.
2. 응답 **헤더** `cont-yn == "Y"`이면, **같은 본문**에 요청 헤더 `cont-yn: Y`, `next-key: <응답의 next-key>`를 붙여 다시 요청한다.
3. `cont-yn`이 `Y`가 아니면 끝.
- `next-key`는 해석하지 말고 그대로 돌려보낸다. 형식이 틀리면 오류 1518. [확인됨] [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView)
- 공식 런타임은 페이지 사이 0.2초 쉰다. 초당 1회 TR(kt00018 등)은 1초 이상 쉰다. [확인됨] / [권고]
- 커뮤니티 래퍼가 연속조회 키를 본문에서 찾다가 1페이지에서 멈춘 사례가 있다(2026-09-12 수정 기록). **헤더**에서 읽어야 한다. [확인됨] [base.py](https://github.com/younghwan91/kiwoom-rest-api/blob/main/src/kiwoom_client/base.py) 주석
- 조건검색(WebSocket ka10172)의 연속조회는 헤더가 아니라 **본문** `cont_yn`/`next_key`다(§12). [확인됨]

```http
POST https://api.kiwoom.com/api/dostk/rkinfo
Content-Type: application/json;charset=UTF-8
api-id: ka10032
authorization: Bearer <token>
cont-yn: Y
next-key: 00110001

{"mrkt_tp": "001", "mang_stk_incls": "1", "stex_tp": "3"}
```

### 3.4 httpx 호출 골격 [권고]

```python
r = await client.post(
    "/api/dostk/acnt",
    headers={
        "Content-Type": "application/json;charset=UTF-8",
        "api-id": "kt00018",
        "authorization": f"Bearer {token}",
        # 연속조회일 때만: "cont-yn": "Y", "next-key": next_key,
    },
    json={"qry_tp": "1", "dmst_stex_tp": "KRX"},
)
body = r.json()                      # 업무 오류도 200
code = int(str(body.get("return_code", body.get("returnCode", 0))).strip() or 0)
has_next = r.headers.get("cont-yn") == "Y"
next_key = r.headers.get("next-key", "")
```

---

## 4. 거래소 구분: KRX · NXT · SOR

| 항목 | 값 | 근거 |
|---|---|---|
| 시세·차트·실시간의 종목코드 | KRX `005930`, NXT `005930_NX`, 통합(SOR) `005930_AL` | [확인됨] 가이드 ka10001·ka10081·0B의 `stk_cd`/`item` 설명 |
| 주문(kt10000~kt10003) `dmst_stex_tp` | `KRX`, `NXT`, `SOR`. 주문의 `stk_cd`는 접미사 없는 6자리 | [확인됨] [가이드 kt10001](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10001) ("종목코드 6자리") |
| SOR 뜻 | 최선주문집행(Smart Order Routing). 두 시장 중 유리한 곳으로 집행 | [확인됨] [가이드 kt00007](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00007) "SOR:최선주문집행", [공지#26](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=26) |
| SOR + FOK | 2025-10-27부터 중단(보통·시장가·최유리 FOK 모두) | [확인됨] [공지#26](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=26) |
| kt00018·kt00004·kt00005 `dmst_stex_tp` | `KRX`, `NXT`만(SOR 없음). 공식 테스트샘플은 SOR 화면에서 `KRX`로 조회 | [확인됨] 가이드, [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample) |
| kt00007·kt00009 `dmst_stex_tp` | `%`(전체), `KRX`, `NXT`, `SOR` | [확인됨] [가이드 kt00007](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00007) |
| ka10075·ka10076·ka10085 `stex_tp` | `0` 통합, `1` KRX, `2` NXT | [확인됨] 가이드 |
| 순위 TR `stex_tp` | `1` KRX, `2` NXT, `3` 통합 | [확인됨] 가이드 ka10030 등 |
| 조건검색 `stex_tp` | `K` KRX, `A` 통합. 하나만 사용 | [확인됨] [가이드 ka10173](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10173), [공지#52](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=52) |
| NXT 거래 가능 여부 | ka10099·ka10100 응답의 `nxtEnable == "Y"`. NXT 불가 종목에 NXT 주문 → 오류 1904 | [확인됨] 가이드, [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) |
| NXT 프리·애프터마켓 | 지정가만 허용(시장가 불가) | [확인됨] [공지#55](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=55) |
| GTP 주문유형(40·46·47) | NXT 프리마켓 한정 | [확인됨] [공지#60](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=60) |
| 실시간 주문체결(00) | FID 2134 거래소구분(0 통합, 1 KRX, 2 NXT), 2135 거래소구분명, 2136 SOR여부(Y/N) | [확인됨] [가이드 00](https://openapi.kiwoom.com/guide/apiGuideContents/14/00) |
| 모의투자 | NXT 미지원. 매매·계좌조회는 KRX만, KRX에서 매매한 종목만 조회됨. 시세는 NXT까지 제공 | [확인됨] [모의투자 안내](https://openapi.kiwoom.com/intro/mockInvestInfo), [FAQ#27](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=27) |

**[권고]** AlphaPilot 1차 범위는 `dmst_stex_tp="KRX"`, 시세 종목코드는 접미사 없이 쓴다. 모의투자와 동작이 같아 검증이 쉽다. NXT·SOR은 실전 전환 뒤 별도 단계로 연다.

---

## 5. 호출 제한(유량)

| 항목 | 값 | 근거 |
|---|---|---|
| 국내주식 기본(계좌·토큰별) | 주문 TR 초당 5회, 조회 TR 초당 5회. TR별 한도는 각 API 상세에 표시 | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro), [공지#49](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=49) |
| 단위 | "TR당 토큰별"로 센다. 토큰(계좌)을 여러 개 쓰면 각각 따로 | [확인됨] [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41), [FAQ#7](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=7) |
| **계좌 TR 1회/초** (2026-11-12 18시~) | kt00001, kt00002, kt00003, kt00004, kt00005, kt00007, kt00008, kt00009, kt00013, kt00015, kt00016, kt00017, kt00018, kt50020, kt50021, kt50030, kt50031, kt50032, kt50075 | [확인됨] [공지#68](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=68)(대상 표는 이미지), 라이브 가이드 kt00001·kt00004·kt00005·kt00007·kt00009·kt00018 "초당 1회" |
| kt00018 이력 | 5회 → 3회(2026-10-29) → 1회(2026-11-12) | [확인됨] [공지#66](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=66), [공지#68](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=68) |
| 모의투자 | 계좌(토큰)별 TR 1개당 초당 1회 | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro), [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41) |
| WebSocket 세션 | 계좌(토큰)별 1개. 같은 토큰으로 중복 연결 불가 | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro), [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41) |
| 실시간 시세 종목 수 | 세션당 200종목(국내·미국 합산, 그룹·TR 종류 무관 합산). 2025-03 FAQ#8의 "100개"는 이전 값 | [확인됨] [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B), [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41) |
| WebSocket 실시간 TR(타입) 수 | 토큰(계좌)별 10개 | [확인됨] [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41) |
| 실시간 조건검색 | 세션당 국내 10건, 조건당 결과 최대 100종목 | [확인됨] [가이드 ka10173](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10173), [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41) |
| 초과 오류 | 1700 API별 한도 초과("유량={?}, API ID={?}"), 1701 전체 한도, 1702 그룹 한도 | [확인됨] [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) |
| 초과 시 HTTP | 429. 같은 API를 바로 다시 부르면 "1700 허용된 API 요청 개수를 초과" (ka20003은 `유량=1`) | [확인됨·실측] [kw_market.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_market.py) |
| 초과 시 본문(커뮤니티) | HTTP 429 + `{"return_code": 5, "return_msg": "허용된 요청 개수를 초과하였습니다"}` | **[불확실]** 커뮤니티 래퍼 [README](https://github.com/younghwan91/kiwoom-rest-api/blob/main/README.md) |
| 커뮤니티 실측 한도 | TR당 지속 약 1회/초, 버스트 약 2회가 안전 — 공식 5회와 다르다 | **[불확실]** [README](https://github.com/younghwan91/kiwoom-rest-api/blob/main/README.md), [AlgoLab 429 글](https://algolab.co.kr/blog/kiwoom-rest-api-429-rate-limit-2026) |

**[권고] 어댑터 설정**
- `(토큰, api-id)`별 토큰 버킷. 기본 실전 4회/초(공식 5회의 80%), 모의 0.9회/초, 계좌 1회/초 TR 목록은 0.9회/초. 표는 설정 파일로 뺀다(공지로 자주 바뀐다).
- 429·1700·1701·1702는 지수 백오프+지터 후 재시도하되, **주문 TR은 자동 재시도하지 않는다**(§10.5).
- `return_msg`의 `유량=N`을 파싱해 그 TR의 버킷을 자동으로 낮추고 경고를 남긴다.
- 엔진이 단일 프로세스(Uvicorn 워커 1개)라는 SPEC 전제와 맞는다. 다른 프로세스가 같은 키로 호출하면 버킷이 무의미해진다.

---

## 6. 시세·종목 TR

### 6.1 주식기본정보 — ka10001 (`/api/dostk/stkinfo`)

출처: [가이드 ka10001](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10001) [확인됨]. 초당 5회.

요청: `{"stk_cd": "005930"}` — `stk_cd`(필수, 최대 20자, KRX `005930` / NXT `005930_NX` / SOR `005930_AL`).

| 응답 필드 | 의미 | 단위·형식 |
|---|---|---|
| `stk_cd`, `stk_nm` | 종목코드, 종목명 | |
| `setl_mm` | 결산월 | 숫자 |
| `fav`, `fav_unit` | 액면가, 액면가단위 | 원 |
| `cap` | 자본금 | 억원 |
| `flo_stk` | 상장주식 | **천주** (라이브 가이드. 스펙 JSON의 "천원"은 오기) [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py): 005930 실측 5,846,279 = 58.46억 주 |
| `dstr_stk`, `dstr_rt` | 유통주식, 유통비율 | 1주, % |
| `mac` | 시가총액 | **억원** |
| `mac_wght` | 시가총액비중 | "데이터 제공 검토중" — 빈 값 예상 |
| `crd_rt` | 신용비율 | %, 부호 포함 |
| `for_exh_rt` | 외인소진률 | % |
| `repl_pric` | 대용가 | 원 |
| `per` | PER(주가수익비율) | 외부 벤더 제공. **주 1회 또는 실적 시즌에 갱신** |
| `eps` | EPS(주당순이익) | |
| `roe` | ROE(자기자본이익률) | 외부 벤더 제공, 갱신 주기는 PER과 같음 |
| `pbr` | PBR(주가순자산비율) | |
| `ev` | EV(기업가치) | |
| `bps` | BPS(주당순자산가치) | |
| `sale_amt` | 매출액 | 억원 |
| `bus_pro` | 영업이익 | 억원 |
| `cup_nga` | 당기순이익 | 억원 |
| `oyr_hgst`, `oyr_lwst` | 연중 최고·최저 | 원, 부호 포함 |
| `250hgst`, `250lwst` | 250일 최고·최저 | 원, 부호 포함 |
| `250hgst_pric_dt`, `250lwst_pric_dt` | 250일 최고·최저가 일자 | YYYYMMDD |
| `250hgst_pric_pre_rt`, `250lwst_pric_pre_rt` | 250일 최고·최저가 대비율 | % |
| `open_pric`, `high_pric`, `low_pric` | 시가·고가·저가 | 원, 부호 포함 |
| `upl_pric`, `lst_pric` | 상한가·하한가 | 원, 부호 포함 |
| `base_pric` | 기준가 | 원 |
| `exp_cntr_pric`, `exp_cntr_qty` | 예상체결가, 예상체결수량 | 원, 1주 |
| `cur_prc` | 현재가 | 원, 부호 포함 |
| `pre_sig` | 대비기호 | 1 상한가, 2 상승, 3 보합, 4 하한가, 5 하락 |
| `pred_pre`, `flu_rt` | 전일대비, 등락율 | 원, % (부호 포함) |
| `trde_qty`, `trde_pre` | 거래량, 거래대비 | 1주, % |

주의
- 필드명이 숫자로 시작한다(`250hgst`). Pydantic에서는 alias로 받는다. [확인됨]
- **공식 응답 예시의 값이 필드와 어긋나 있다**(예: `upl_pric: "20241016"`, `base_pric: "20231024"`). 계약 테스트 픽스처로 쓰면 안 된다. [확인됨] 라이브 가이드·스펙 JSON 예시 모두 같음
- 공식 예시에서 `per`·`eps`·`roe`·`pbr`·`ev`가 빈 문자열이다. 빈 값을 "데이터 없음"으로 처리해야 한다. [확인됨]
- 부채비율·배당수익률·영업이익률 같은 필드는 없다. 매출·영업이익·당기순이익이 어느 기간(연간·최근 4분기 등) 기준인지 문서에 없다. **[불확실]**
- [권고] SPEC §3.1의 "가치 점검(PER·PBR·ROE·EPS)"은 이 TR로 가능하나, 갱신이 주 1회 수준이므로 일 1회 캐시로 충분하다.

형식 예시(값은 설명용):

```json
{
  "stk_cd": "005930", "stk_nm": "삼성전자", "setl_mm": "12",
  "fav": "100", "cap": "8975", "flo_stk": "5846279", "mac": "4120000",
  "per": "13.52", "eps": "5212", "roe": "9.03", "pbr": "1.21", "bps": "58120",
  "sale_amt": "3008709", "bus_pro": "327260", "cup_nga": "344514",
  "cur_prc": "+70500", "pre_sig": "2", "pred_pre": "+600", "flu_rt": "+0.86",
  "trde_qty": "12345678",
  "return_code": 0, "return_msg": "정상적으로 처리되었습니다"
}
```

### 6.2 종목 목록 — ka10099 / 종목 조회 — ka10100 (`/api/dostk/stkinfo`)

출처: [가이드 ka10099](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10099), [가이드 ka10100](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10100) [확인됨]

| TR | 요청 | 비고 |
|---|---|---|
| ka10099 | `mrkt_tp`(필수): `0` 코스피, `10` 코스닥, `30` K-OTC, `50` 코넥스, `60` ETN, `70` 손실제한 ETN, `80` 금현물, `90` 변동성 ETN, `2` 인프라투융자, `3` ELW, `4` 뮤추얼펀드, `5` 신주인수권, `6` 리츠, `7` 신주인수권증서, `8` ETF, `9` 하이일드펀드 | 응답 `list[]` |
| ka10100 | `stk_cd`(필수, 6자리) | 단건 객체 |

| 응답 필드 | 의미 |
|---|---|
| `code`, `name` | 종목코드(6자리), 종목명 |
| `listCount` | 상장주식수(1주, 0-padding 16자리) |
| `auditInfo` | 감리구분: 정상, 관리종목, 거래정지, 단기과열, 투자주의, 투자경고 등 |
| `regDay` | 상장일 YYYYMMDD |
| `lastPrice` | 전일종가(원, 0-padding 8자리) |
| `state` | 증거금율·담보·신용 가능 여부(예: `증거금20%|담보대출|신용가능`) |
| `marketCode`, `marketName` | 시장 구분 코드·이름 |
| `upName`, `upSizeName` | 업종명, 회사 크기(대형주·중형주·소형주. 우선주·ETF는 빈 값) |
| `companyClassName` | 회사분류(코스닥만) |
| `orderWarning` | 투자유의: 0 해당없음, 1 ETF투자주의요망(ETF만), 2 정리매매, 3 단기과열, 4 투자위험, 5 투자경고(가이드 표기 "투자경과") |
| `nxtEnable` | NXT 거래 가능이면 `Y` |

- 공식 테스트샘플은 시작 시 ka10099(`mrkt_tp` 0, 10)으로 종목 마스터를 만든다. [확인됨] [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample)
- [권고] 하루 1회(장 전) 마스터 갱신. `orderWarning`·`auditInfo`로 관리종목·정리매매·투자위험 종목을 유니버스에서 제외.

### 6.3 현재가·호가 최소 세트

**ka10004 주식호가요청** (`/api/dostk/mrkcond`) — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/02/ka10004) [확인됨]. 요청 `{"stk_cd": "005930"}`.

| 응답 필드 패턴 | 의미 |
|---|---|
| `bid_req_base_tm` | 호가잔량 기준시간 **HHmmss** (스펙 JSON의 "YYYYMMDD"는 오기, 라이브 가이드 기준) |
| `sel_fpr_bid` / `sel_fpr_req` | 매도 최우선(1호가) 가격 / 잔량 |
| `buy_fpr_bid` / `buy_fpr_req` | 매수 최우선(1호가) 가격 / 잔량 |
| `sel_{n}th_pre_bid` / `sel_{n}th_pre_req` / `sel_{n}th_pre_req_pre` | 매도 n차선(n=2~10) 호가 / 잔량 / 잔량대비. 철자가 `2th`, `3th`임에 주의 |
| `buy_{n}th_pre_bid` / `buy_{n}th_pre_req` / `buy_{n}th_pre_req_pre` | 매수 n차선 |
| `sel_1th_pre_req_pre`, `buy_1th_pre_req_pre` | 1차선 잔량대비 |
| `tot_sel_req`, `tot_buy_req` | 총 매도·매수 잔량 |
| `tot_sel_req_jub_pre`, `tot_buy_req_jub_pre` | 총잔량 직전대비 |
| `ovt_sel_req`, `ovt_buy_req` (+ `_pre`) | 시간외 매도·매수 잔량 |

- 1호가만 `*_fpr_*`, 2~10호가는 `*_{n}th_pre_*` 이름이다. [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py)
- 호가 가격에 부호가 붙는다(전일 대비 방향). 일부 음수 필드는 `--N` 이중부호로 온다. [확인됨·실측] [kwcli 1.0.3 maps/api_commands.csv](https://pypi.org/project/kwcli/1.0.3/)

**ka10007 시세표성정보요청** (`/api/dostk/mrkcond`) — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/02/ka10007) [확인됨]. 현재가·전일종가·시고저·거래량과 10호가를 한 번에 준다.
- 주요 필드: `cur_prc`, `pred_close_pric`, `open_pric`/`high_pric`/`low_pric`, `upl_pric`/`lst_pric`, `trde_qty`, `trde_prica`(백만원 [확인됨·실측] normalize.py), `flu_rt`, `exp_cntr_pric`/`exp_cntr_qty`, `sel_{1..10}bid`, `buy_{1..10}bid`, `sel_{n}bid_req`, `buy_{n}bid_req`, `tot_sel_req`, `tot_buy_req`.
- `pred_rt`는 가격이 아니라 **전일 거래량 대비 비율**이다. [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py)
- 호가 건수(`sel_1bid_cnt` 등)는 "데이터 제공 검토중". [확인됨] 가이드

**ka10003 체결정보요청** (`/api/dostk/stkinfo`) — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/01/ka10003) [확인됨]. 응답 `cntr_infr[]`: `tm`, `cur_prc`, `pred_pre`, `pre_rt`, `pri_sel_bid_unit`, `pri_buy_bid_unit`, `cntr_trde_qty`, `sign`, `acc_trde_qty`, `acc_trde_prica`, `cntr_str`, `stex_tp`.

[권고] 장중 현재가는 REST 폴링보다 실시간 0B(체결)·0D(호가)를 쓴다. 키움도 실시간 시세는 0B·0D를 정제해 쓰라고 안내한다. [확인됨] [FAQ#14](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=14)

---

## 7. 차트 TR (`/api/dostk/chart`, 초당 5회)

출처: [가이드 ka10081](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10081), [ka10082](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10082), [ka10080](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10080), [ka10079](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10079), [ka10083](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10083), [ka10094](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka10094), [ka11081](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka11081), [ka11080](https://openapi.kiwoom.com/guide/apiGuideContents/07/ka11080) [확인됨]

### 7.1 요청

| TR | 봉 | 요청 필드 | 응답 리스트 키 |
|---|---|---|---|
| ka10079 | 틱 | `stk_cd`(Y), `tic_scope`(Y: 1·3·5·10·30틱), `upd_stkpc_tp`(Y) | `stk_tic_chart_qry` (+ `last_tic_cnt`) |
| ka10080 | 분 | `stk_cd`(Y), `tic_scope`(Y: 1·3·5·10·15·30·45·60분), `upd_stkpc_tp`(Y), `base_dt`(N, YYYYMMDD) | `stk_min_pole_chart_qry` |
| ka10081 | 일 | `stk_cd`(Y), `base_dt`(Y), `upd_stkpc_tp`(Y) | `stk_dt_pole_chart_qry` |
| ka10082 | 주 | 위와 같음 | `stk_stk_pole_chart_qry` |
| ka10083 | 월 | 위와 같음 | `stk_mth_pole_chart_qry` |
| ka10094 | 년 | 위와 같음 | `stk_yr_pole_chart_qry` |
| ka11079~ka11094 | 정규장 전용 틱·분·일·주·월·년 | 각 대응 TR과 같음 | **`result_list`** |

- `upd_stkpc_tp`: `0` 원주가, `1` 수정주가. 수정주가로 과거를 보려면 `base_dt`를 권리발생일 **이후** 날짜로 두고 조회·연속조회해야 한다(예: 삼성전자 2018-05-04 액면분할). [확인됨] 가이드 ka10081
- 정규장 전용 TR(ka11079~ka11094)은 라이브 가이드에만 있다(스펙 JSON 2026-09-04에는 없음). 2026-09-14 KRX 애프터마켓 신설과 함께 생긴 것으로 보인다. 기존 TR(ka10081 등)의 봉에 애프터마켓·NXT 체결이 섞이는지는 **[불확실]**. [권고] 지표 계산은 정규장 전용 TR로 통일하고, 키를 받은 뒤 두 TR의 같은 날 봉을 비교한다.

### 7.2 응답 행 필드

| 필드 | 의미 | 단위·형식 | 비고 |
|---|---|---|---|
| `dt` | 일자 | YYYYMMDD | 일·주·월·년 |
| `cntr_tm` | 체결시간 | YYYYMMDDHHmmss, **봉의 시작시간** | 틱·분 [확인됨] 라이브 가이드 ka10080 |
| `cur_prc` | 현재가(=종가) | 원. 분·틱은 **부호 포함**(예 `"-78800"`) | |
| `open_pric`, `high_pric`, `low_pric` | 시·고·저 | 원. 분·틱은 부호 포함 | |
| `trde_qty` | 거래량 | 1주 | |
| `acc_trde_qty` | 누적거래량 | 1주 | 분봉 |
| `trde_prica` | 거래대금 | **일봉 백만원**, 주·월·년봉은 문서상 **원** | 문서 단위가 다르다. 주봉 예시값(3,922,030,535,087)도 원 단위로 보인다. 실제는 **[불확실]** |
| `pred_pre`, `pred_pre_sig` | 전일대비(현재가−전일종가), 기호(1~5) | | 년봉에는 없음 |
| `trde_tern_rt` | 거래회전율 | % | 일·주·월 |
| `upd_stkpc_tp` | 수정구분자 | 쉼표로 여러 개: 1 유상증자, 2 무상증자, 4 배당락, 8 액면분할, 16 액면병합, 32 기업합병, 64 감자, 256 권리락 | 라이브에서 추가 |
| `upd_rt` | 수정비율 | `""` 권리 이벤트 없음, `"0.00"` 가격조정 없는 이벤트. 수정주가 = round_half_up(원본 × R), R = round(1 + upd_rt/100, 4자리); 수정거래량 = round_half_even(원본 × 1/R) | 라이브에서 추가 |

- 공지 이력: 2025-09-18 차트 응답 필드 정리(대업종구분·수정주가구분 등 삭제, 전일대비·누적거래량 추가), 2025-10-23 ka10079·ka10080·ka20004의 `cntr_dt` 삭제. [확인됨] [공지#18](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=18), [공지#25](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=25)
- 분봉 예시에는 표에 없던 `acc_trde_qty`가 있었고 라이브 표에 반영됐다. 문서에 없는 필드가 더 올 수 있으니 모델은 추가 필드를 허용한다(`extra="ignore"`). [확인됨] / [권고]
- 행 순서: 예시는 최신 → 과거 순이다. [확인됨] 예시. 정렬을 가정하지 말고 `dt`/`cntr_tm`으로 오름차순 정렬·중복 제거한다. [권고]
- 한 페이지 행 수는 문서에 없다. 공식 플러그인 주석은 일봉 1회 조회를 "600봉≈2년"으로 적었다. **[불확실]** [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py)
- 거래량이 `4294967295`(2³²−1)로 포화될 수 있다(초대량 종목, 곱버스 252670 실측). `trde_tern_rt`가 `"-0.00"`일 수 있다. [확인됨·실측] [kwcli maps/api_commands.csv](https://pypi.org/project/kwcli/1.0.3/)

```json
{"stk_cd": "005930", "base_dt": "20261113", "upd_stkpc_tp": "1"}
```

```json
{
  "stk_cd": "005930",
  "stk_dt_pole_chart_qry": [
    {"cur_prc": "70100", "trde_qty": "9263135", "trde_prica": "648525", "dt": "20261113",
     "open_pric": "69800", "high_pric": "70500", "low_pric": "69600",
     "pred_pre": "+600", "pred_pre_sig": "2", "trde_tern_rt": "+0.16",
     "upd_stkpc_tp": "", "upd_rt": ""}
  ],
  "return_code": 0, "return_msg": "정상적으로 처리되었습니다"
}
```

---

## 8. 종목 발굴용 순위 TR (`/api/dostk/rkinfo`, 초당 5회)

### 8.1 당일거래량상위 — ka10030 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10030) [확인됨]

| 요청 필드(모두 필수) | 값 |
|---|---|
| `mrkt_tp` | `000` 전체, `001` 코스피, `101` 코스닥 |
| `sort_tp` | `1` 거래량, `2` 거래회전율, `3` 거래대금 |
| `mang_stk_incls` | `0` 관리종목 포함, `1` 미포함, `3` 우선주제외, `11` 정리매매제외, `4` 관리·우선주제외, `5` 증100제외, `6` 증100만보기, `13` 증60만, `12` 증50만, `7` 증40만, `8` 증30만, `9` 증20만, `14` ETF제외, `15` 스팩제외, `16` ETF+ETN제외 |
| `crd_tp` | `0` 전체, `9` 신용융자전체, `1`~`4` 신용융자 A~D군, `8` 신용대주 |
| `trde_qty_tp` | `0` 전체, `5` 5천주↑, `10` 1만주↑, `50` 5만주↑, `100` 10만주↑, `200`, `300`, `500`, `1000` |
| `pric_tp` | `0` 전체, `1` 1천원 미만, `2` 1천원↑, `3` 1천~2천, `4` 2천~5천, `5` 5천↑, `6` 5천~1만, `10` 1만 미만, `7` 1만↑, `8` 5만↑, `9` 10만↑ |
| `trde_prica_tp` | `0` 전체, `1` 1천만↑, `3` 3천만↑, `4` 5천만↑, `10` 1억↑, `30`, `50`, `100` 10억↑, `300`, `500`, `1000` 100억↑, `3000`, `5000` 500억↑ |
| `mrkt_open_tp` | `0` 전체, `1` 장중, `2` 장전시간외, `3` 장후시간외 |
| `stex_tp` | `1` KRX, `2` NXT, `3` 통합 |

응답 `tdy_trde_qty_upper[]`: `stk_cd`, `stk_nm`, `cur_prc`, `pred_pre_sig`, `pred_pre`, `flu_rt`, `trde_qty`, `pred_rt`(전일비 %), `trde_tern_rt`, `trde_amt`(거래금액, **백만원**), `opmr_*`(장중), `af_mkrt_*`(장후), `bf_mkrt_*`(장전).

### 8.2 전일대비등락률상위 — ka10027 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10027) [확인됨]

| 요청 필드(모두 필수) | 값 |
|---|---|
| `mrkt_tp` | `000`, `001`, `101` |
| `sort_tp` | `1` 상승률, `2` 상승폭, `3` 하락률, `4` 하락폭, `5` 보합 |
| `trde_qty_cnd` | `0000` 전체, `0010` 만주↑, `0050`, `0100`, `0150`, `0200`, `0300`, `0500`, `1000` 백만주↑ |
| `stk_cnd` | `0` 전체, `1` 관리종목제외, `4` 우선주+관리주제외, `3` 우선주제외, `5`~`9`·`12`·`13` 증거금 조건, `11` 정리매매제외, `14` ETF제외, `15` 스팩제외, `16` ETF+ETN제외 |
| `crd_cnd` | `0` 전체, `1`~`4` A~D군, `7` E군, `9` 신용융자전체 |
| `updown_incls` | `0` 불포함, `1` 포함(상·하한가) |
| `pric_cnd` | `0` 전체, `1` 1천원 미만, `2` 1천~2천, `3` 2천~5천, `4` 5천~1만, `5` 1만↑, `8` 1천↑, `10` 1만 미만 |
| `trde_prica_cnd` | `0` 전체, `3` 3천만↑, `5`, `10` 1억↑, `30`, `50`, `100`, `300`, `500`, `1000`, `3000`, `5000` |
| `stex_tp` | `1` KRX, `2` NXT, `3` 통합 |

응답 `pred_pre_flu_rt_upper[]`: `stk_cls`, `stk_cd`, `stk_nm`, `cur_prc`, `pred_pre_sig`, `pred_pre`, `flu_rt`, `sel_req`, `buy_req`, `now_trde_qty`, `cntr_str`(체결강도), `cnt`(횟수).

### 8.3 거래대금상위 — ka10032 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10032) [확인됨]

| 요청 필드(모두 필수) | 값 |
|---|---|
| `mrkt_tp` | `000`, `001`, `101` |
| `mang_stk_incls` | `0` 관리종목 **미포함**, `1` **포함** — ka10030과 의미가 반대다 |
| `stex_tp` | `1` KRX, `2` NXT, `3` 통합 |

응답 `trde_prica_upper[]`: `stk_cd`, `now_rank`, `pred_rank`, `stk_nm`, `cur_prc`, `pred_pre_sig`, `pred_pre`, `flu_rt`, `sel_bid`, `buy_bid`, `now_trde_qty`, `pred_trde_qty`, `trde_prica`(**백만원**).

### 8.4 거래량급증 — ka10023 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka10023) [확인됨]

요청: `mrkt_tp`, `sort_tp`(`1` 급증량, `2` 급증률, `3` 급감량, `4` 급감률), `tm_tp`(`1` 분, `2` 전일), `trde_qty_tp`(`5`~`1000`), `tm`(N, 분), `stk_cnd`(`0`, `1`, `3`, `11`, `4`, `5`~`9`, `12`, `13`, `17` ETN제외, `14`, `18` ETF+ETN제외, `15`, `20` ETF+ETN+스팩제외), `pric_tp`(`0`, `2` 5만↑, `5` 1만↑, `6` 5천↑, `8` 1천↑, `9` 10만↑), `stex_tp`.
응답 `trde_qty_sdnin[]`: `stk_cd`, `stk_nm`, `cur_prc`, `pred_pre_sig`, `pred_pre`, `flu_rt`, `prev_trde_qty`, `now_trde_qty`, `sdnin_qty`, `sdnin_rt`.

### 8.5 참고
- 순위 TR들의 `now_trde_qty`·`trde_qty`도 2³²−1로 포화될 수 있다(ka10023·ka10030·ka10032 실측). [확인됨·실측] [kwcli maps/api_commands.csv](https://pypi.org/project/kwcli/1.0.3/)
- 라이브 가이드에 애프터마켓등락률상위(ka11310, `stex_tp`는 `3` 통합만), KRX/NXT괴리율순위(ka11370)가 새로 있다. 스펙 JSON에는 없다. [확인됨] [가이드 ka11310](https://openapi.kiwoom.com/guide/apiGuideContents/05/ka11310)
- 시간외단일가등락율순위(ka10098)·시간외단일가요청(ka10087)은 2026-09-12 21시에 삭제됐다. [확인됨] [공지#60](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=60) 첨부 표, 라이브 가이드 목록에서 사라짐

```json
{"mrkt_tp": "000", "sort_tp": "1", "mang_stk_incls": "1", "crd_tp": "0", "trde_qty_tp": "0",
 "pric_tp": "0", "trde_prica_tp": "0", "mrkt_open_tp": "1", "stex_tp": "1"}
```

---

## 9. 계좌 TR (`/api/dostk/acnt`)

공통: 계좌번호 입력 없음(토큰의 계좌). 금액·수량은 대부분 **좌측 0-padding + 부호 포함 문자열**(예 `"000000017598258"`, `"-00000000196888"`). [확인됨] 가이드

### 9.1 계좌평가잔고내역 — kt00018 (초당 1회) [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00018) [확인됨]

| 요청 필드 | 필수 | 값 |
|---|---|---|
| `qry_tp` | Y | `1` 합산, `2` 개별 (의미 차이는 문서에 설명 없음 — 신용 구분별 분리 여부로 추정 **[불확실]**) |
| `dmst_stex_tp` | Y | `KRX`, `NXT` |

| 응답(요약) | 의미 |
|---|---|
| `tot_pur_amt` | 총매입금액 |
| `tot_evlt_amt` | 총평가금액 |
| `tot_evlt_pl` | 총평가손익금액 |
| `tot_prft_rt` | 총수익률(%) |
| `prsm_dpst_aset_amt` | 추정예탁자산 |
| `tot_loan_amt`, `tot_crd_loan_amt`, `tot_crd_ls_amt` | 총대출금, 총융자금액, 총대주금액 |

| 응답 `acnt_evlt_remn_indv_tot[]` | 의미 |
|---|---|
| `stk_cd` | 종목번호 = **접두어 1자리 + 6자리** (A 주식, J ELW, Q ETN). 예 `A005930` |
| `stk_nm` | 종목명 |
| `rmnd_qty` / `trde_able_qty` | 보유수량 / 매매가능수량 |
| `pur_pric` / `pur_amt` | 매입가 / 매입금액 |
| `cur_prc` / `pred_close_pric` | 현재가 / 전일종가 |
| `evlt_amt` / `evltv_prft` / `prft_rt` | 평가금액 / 평가손익 / 수익률(%) |
| `pur_cmsn` / `sell_cmsn` / `tax` / `sum_cmsn` | 매입수수료 / 평가(매도)수수료 / 세금 / 수수료합 |
| `pred_buyq`, `pred_sellq`, `tdy_buyq`, `tdy_sellq` | 전일·금일 매수·매도 수량 |
| `poss_rt` | 보유비중(%) |
| `crd_tp`, `crd_tp_nm`, `crd_loan_dt` | 신용구분, 이름, 대출일 |

```json
{"qry_tp": "1", "dmst_stex_tp": "KRX"}
```

```json
{
  "tot_pur_amt": "000000017598258", "tot_evlt_amt": "000000025789890",
  "tot_evlt_pl": "000000008138825", "tot_prft_rt": "46.25",
  "prsm_dpst_aset_amt": "000001012632507",
  "tot_loan_amt": "000000000000000", "tot_crd_loan_amt": "000000000000000", "tot_crd_ls_amt": "000000000000000",
  "acnt_evlt_remn_indv_tot": [
    {"stk_cd": "A005930", "stk_nm": "삼성전자", "evltv_prft": "-00000000196888", "prft_rt": "-52.71",
     "pur_pric": "000000000124500", "pred_close_pric": "000000045400", "rmnd_qty": "000000000000003",
     "trde_able_qty": "000000000000003", "cur_prc": "000000059000", "pur_amt": "000000000373500",
     "evlt_amt": "000000000177000", "poss_rt": "2.12", "crd_tp": "00", "crd_tp_nm": "", "crd_loan_dt": ""}
  ],
  "return_code": 0, "return_msg": "조회가 완료되었습니다"
}
```

### 9.2 예수금상세현황 — kt00001 (초당 1회) [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00001) [확인됨]

요청: `{"qry_tp": "3"}` — `3` 추정조회, `2` 일반조회.

| 응답(주요) | 의미 |
|---|---|
| `entr` | 예수금 |
| `d1_entra`, `d2_entra` | D+1, D+2 추정예수금 |
| `ord_alow_amt` | 주문가능금액 |
| `pymn_alow_amt` | 출금가능금액 |
| `20stk_ord_alow_amt` … `100stk_ord_alow_amt` (20·30·40·50·60·100%) | 증거금률별 종목주문가능금액 |
| `profa_ch` | 주식증거금현금 |
| `repl_amt` | 대용금 평가금액(합계) |
| `ch_uncla`, `ch_uncla_tot` | 현금미수금, 합계 |
| `d1_*`, `d2_*` | D+1·D+2 매수·매도 정산금, 출금가능금액 등 |
| `stk_entr_prst[]` | 통화별 예수금(외화) |

필드가 60여 개다. 전체 목록은 가이드를 따른다.

### 9.3 계좌평가현황 — kt00004 (초당 1회) [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00004) [확인됨]

요청: `qry_tp`(`0` 전체, `1` 상장폐지종목제외), `dmst_stex_tp`(`KRX`, `NXT`).
응답: `acnt_nm`(계좌 소유주 성명), `brch_nm`, `entr`, `d2_entra`, `tot_est_amt`(유가잔고평가액), `aset_evlt_amt`(예탁자산평가액), `tot_pur_amt`, `prsm_dpst_aset_amt`, `tdy_lspft`(당일투자손익), `tdy_lspft_rt`(당일손익율), `lspft2`/`lspft_ratio`(당월), `lspft`/`lspft_rt`(누적), `stk_acnt_evlt_prst[]`(종목별: `stk_cd`, `stk_nm`, `rmnd_qty`, `avg_prc`, `cur_prc`, `evlt_amt`, `pl_amt`, `pl_rt`, `pur_amt`, `setl_remn` 등).
- 응답에 **계좌 소유주 성명**이 들어 있다. [권고] 로그·화면에 그대로 남기지 않는다.

### 9.4 미체결 — ka10075 (초당 5회) [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10075) [확인됨]

| 요청 필드 | 필수 | 값 |
|---|---|---|
| `all_stk_tp` | Y | `0` 전체, `1` 종목 |
| `trde_tp` | Y | `0` 전체, `1` 매도, `2` 매수 — **주문 TR의 `trde_tp`(매매구분)와 이름만 같고 의미가 다르다** |
| `stk_cd` | N | 6자리(`all_stk_tp=1`일 때) |
| `stex_tp` | Y | `0` 통합, `1` KRX, `2` NXT |

응답 `oso[]`: `acnt_no`, `ord_no`(7자리), `stk_cd`, `stk_nm`, `ord_stt`(주문상태: 접수 등), `ord_qty`, `ord_pric`, `oso_qty`(미체결수량), `cntr_tot_amt`, `orig_ord_no`(없으면 `0000000`), `io_tp_nm`(주문구분: `+매수`, `-매도` 등), `trde_tp`(매매구분 **텍스트**: 보통·시장가 …), `tm`(HHmmss), `cntr_no`, `cntr_pric`, `cntr_qty`, `cur_prc`, `sel_bid`, `buy_bid`, `unit_cntr_pric`, `unit_cntr_qty`, `tdy_trde_cmsn`, `tdy_trde_tax`, `stex_tp`, `stex_tp_txt`, `sor_yn`, `stop_pric`.

```json
{"all_stk_tp": "0", "trde_tp": "0", "stk_cd": "", "stex_tp": "1"}
```

### 9.5 체결 — ka10076 (초당 5회) [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10076) [확인됨]

요청: `stk_cd`(N), `qry_tp`(Y: `0` 전체, `1` 종목), `sell_tp`(Y: `0` 전체, `1` 매도, `2` 매수), `ord_no`(N: 입력한 주문번호**보다 과거**에 체결된 내역을 조회), `stex_tp`(Y: `0`, `1`, `2`).
응답 `cntr[]`: `ord_no`, `stk_cd`, `stk_nm`, `io_tp_nm`, `ord_pric`, `ord_qty`, `cntr_pric`, `cntr_qty`, `oso_qty`, `tdy_trde_cmsn`, `tdy_trde_tax`, `ord_stt`, `trde_tp`, `orig_ord_no`, `ord_tm`, `stex_tp`, `stex_tp_txt`(예시에 `SOR`도 나옴), `sor_yn`, `stop_pric`.

### 9.6 실현손익 관련

| TR | 요청 | 응답 핵심 | 근거 |
|---|---|---|---|
| ka10077 당일실현손익상세 | `stk_cd`(**필수**, 6자리) | `tdy_rlzt_pl`(당일실현손익), `tdy_rlzt_pl_dtl[]`(`cntr_qty`, `buy_uv` 매입단가, `cntr_pric`, `tdy_sel_pl`, `pl_rt`, `tdy_trde_cmsn`, `tdy_trde_tax`, `stk_cd`=`A005930`형) | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10077) [확인됨] |
| ka10074 일자별실현손익 | `strt_dt`, `end_dt`(YYYYMMDD) | `tot_buy_amt`, `tot_sell_amt`, `rlzt_pl`, `trde_cmsn`, `trde_tax`, `dt_rlzt_pl[]`(`dt`, `buy_amt`, `sell_amt`, `tdy_sel_pl`, …) | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10074) [확인됨] |
| ka10072 / ka10073 일자별종목별실현손익(일자/기간) | `stk_cd`(N), `strt_dt`(+ `end_dt`) | 종목별 `tdy_sel_pl`, `pl_rt` 등 | [가이드 ka10072](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10072), [ka10073](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10073) [확인됨] |
| ka10170 당일매매일지 | `base_dt`(N, 빈 값=오늘, 최근 2개월), `ottks_tp`(`1` 당일매수분의 당일매도, `2` 당일매도 전체), `ch_crd_tp`(`0` 전체, `1` 현금, `2` 신용) | `tot_sell_amt`, `tot_buy_amt`, `tot_cmsn_tax`, `tot_exct_amt`, `tot_pl_amt`, `tot_prft_rt`, `tdy_trde_diary[]` | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/ka10170) [확인됨] |
| kt00004 | 위 9.3 | `tdy_lspft`, `tdy_lspft_rt` | [확인됨] |
| 실시간 04 | — | FID 990 당일실현손익(유가), 991 손익율, 950 당일총매도손익 | [확인됨] §11.6 |

- [권고] "오늘 계좌 실현손익 합계"는 ka10074에 `strt_dt=end_dt=오늘`로 조회한다. ka10077은 종목코드가 필수라 계좌 합계용으로 맞지 않는다.
- `buy_uv`·`tdy_sel_pl`이 소수(예 `"97602.9573459"`)로 올 수 있다. Decimal로 받는다. [확인됨] 가이드 예시

### 9.7 주문 이력·주문가능

| TR | 요청 | 비고 |
|---|---|---|
| kt00007 계좌별주문체결내역상세 (초당 1회) | `ord_dt`(N), `qry_tp`(`1` 주문순, `2` 역순, `3` 미체결, `4` 체결내역만), `stk_bond_tp`(`0`, `1` 주식, `2` 채권), `sell_tp`, `stk_cd`(N), `fr_ord_no`(N), `dmst_stex_tp`(`%`·`KRX`·`NXT`·`SOR`) | 응답 `acnt_ord_cntr_prps_dtl[]`: `ord_no`, `ori_ord`, `trde_tp`, `ord_qty`, `ord_uv`, `cnfm_qty`, `acpt_tp`, `cntr_qty`, `cntr_uv`, `ord_remnq`, `mdfy_cncl`, `ord_tm`, `cnfm_tm`, `dmst_stex_tp`, `cond_uv` [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00007) [확인됨] |
| kt00009 계좌별주문체결현황 (초당 1회) | `ord_dt`, `stk_bond_tp`, `mrkt_tp`, `sell_tp`, `qry_tp`(`0` 전체, `1` 체결), `stk_cd`, `fr_ord_no`, `dmst_stex_tp` | [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00009) [확인됨] |
| kt00010 주문인출가능금액 (초당 5회) | `stk_cd`(Y), `trde_tp`(Y: `1` 매도, `2` 매수), `uv`(Y, 가격), `trde_qty`(N), `io_amt`(N), `exp_buy_unp`(N) | 응답 `ord_alowa`(주문가능현금), `profa_100ord_alowq`(증거금100% 주문가능수량), `entr`, `d2entra`, `wthd_alowa` 등 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00010) [확인됨] |
| kt00011 증거금율별주문가능수량 (초당 5회) | `stk_cd`(Y), `uv`(N) | `min_ord_alow_amt`/`min_ord_alowq`는 수수료를 뺀 미수불가 기준 [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/08/kt00011) [확인됨] |
| ka10085 계좌수익률 (초당 5회) | `stex_tp`(`0`, `1`, `2`) | `setl_remn`은 문서상 "원"이지만 실제 **주 수량** [확인됨·실측] [kwcli maps](https://pypi.org/project/kwcli/1.0.3/) |

---

## 10. 주문 TR (`/api/dostk/ordr`, 초당 5회)

출처: [가이드 kt10000](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10000), [kt10001](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10001), [kt10002](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10002), [kt10003](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10003) [확인됨]

### 10.1 매수 kt10000 / 매도 kt10001 (요청 구조 같음)

| 요청 필드 | 필수 | 길이 | 설명 |
|---|---|---|---|
| `dmst_stex_tp` | Y | 3 | `KRX`, `NXT`, `SOR` (모의는 `KRX`만) |
| `stk_cd` | Y | 12 | 종목코드 6자리 |
| `ord_qty` | Y | 12 | 주문수량(1주) |
| `ord_uv` | N | 12 | 주문단가(원). 시장가 계열은 빈 값 `""` |
| `trde_tp` | Y | 2 | 매매구분(§10.3) |
| `cond_uv` | N | 12 | 조건단가(원). 스톱지정가(28)의 스톱가 |

| 응답 | 설명 |
|---|---|
| `ord_no` | 주문번호(7자리) |
| `dmst_stex_tp` | 국내거래소구분 |

```json
{"dmst_stex_tp": "KRX", "stk_cd": "005930", "ord_qty": "1", "ord_uv": "70000", "trde_tp": "0", "cond_uv": ""}
```

```json
{"ord_no": "0000138", "dmst_stex_tp": "KRX", "return_code": 0, "return_msg": "매도주문이 완료되었습니다."}
```

### 10.2 정정 kt10002 / 취소 kt10003

| kt10002 요청 | 필수 | 설명 |
|---|---|---|
| `dmst_stex_tp` | Y | `KRX`, `NXT`, `SOR` |
| `orig_ord_no` | Y | 원주문번호 7자리 |
| `stk_cd` | Y | 6자리 |
| `mdfy_qty` | Y | 정정수량. **`"0"`이면 잔량 전부 정정** |
| `mdfy_uv` | Y | 정정단가. 수량만 바꿔도 필수 |
| `mdfy_cond_uv` | N | 정정조건단가 |

| kt10003 요청 | 필수 | 설명 |
|---|---|---|
| `dmst_stex_tp` | Y | |
| `orig_ord_no` | Y | 원주문번호 7자리 |
| `stk_cd` | Y | 6자리 |
| `cncl_qty` | Y | 취소수량. **`"0"`이면 잔량 전부 취소** |

| 응답 | 설명 |
|---|---|
| `ord_no` | **새 주문번호**(정정·취소도 새 번호가 생긴다) |
| `base_orig_ord_no` | 모주문번호 |
| `mdfy_qty` / `cncl_qty` | 0-padding 12자리 부호 포함 |
| `dmst_stex_tp` | 정정 응답에만 |

```json
{"dmst_stex_tp": "KRX", "orig_ord_no": "0000139", "stk_cd": "005930", "mdfy_qty": "1", "mdfy_uv": "199700", "mdfy_cond_uv": ""}
```

```json
{"ord_no": "0000141", "base_orig_ord_no": "0000139", "cncl_qty": "000000000001", "return_code": 0, "return_msg": "매수취소 주문입력이 완료되었습니다"}
```

- 정정 요청에 `trde_tp`가 없다. 매매구분을 바꾸려면 취소 후 새 주문. [확인됨] 가이드 kt10002
- 정정·취소의 `dmst_stex_tp`는 원주문과 같아야 할 것으로 보이나 문서에 없다. **[불확실]**
- 신용 주문의 정정·취소는 `/api/dostk/crdordr`의 kt10008·kt10009를 쓴다. [확인됨] 스펙 목록
- [권고] `"0"`(잔량 전부)은 계산 결과로 새어 나가면 전량 취소가 된다. 별도 함수(`cancel_all_remaining`)로만 보낸다. ([AlgoLab 정정·취소 글](https://algolab.co.kr/blog/kiwoom-rest-api-order-modify-cancel-kt10002-2026)의 같은 지적)

### 10.3 `trde_tp` 매매구분 코드표 (라이브 가이드, 2026-11-15)

[확인됨] [가이드 kt10000](https://openapi.kiwoom.com/guide/apiGuideContents/13/kt10000). 가격 필드 정책 열은 [kwcli 1.0.3 `maps/order_price_policies.csv`](https://pypi.org/project/kwcli/1.0.3/) 기준 [확인됨] (GTP 행은 추론 **[불확실]**).

| 코드 | 이름 | `ord_uv` | `cond_uv` | 비고 |
|---|---|---|---|---|
| `0` | 보통(지정가) | 필수 | — | |
| `3` | 시장가 | 빈 값 | — | NXT 프리·애프터마켓 불가 |
| `5` | 조건부지정가 | 필수 | — | |
| `81` | 장마감후시간외 | 빈 값 | — | 15:40~16:00 종가 |
| `61` | 장시작전시간외 | 빈 값 | — | 08:30~08:40 전일 종가 |
| `6` | 최유리지정가 | 빈 값 | — | |
| `7` | 최우선지정가 | 빈 값 | — | |
| `10` | 보통(IOC) | 필수 | — | |
| `13` | 시장가(IOC) | 빈 값 | — | |
| `16` | 최유리(IOC) | 빈 값 | — | |
| `20` | 보통(FOK) | 필수 | — | SOR 불가(2025-10-27~) |
| `23` | 시장가(FOK) | 빈 값 | — | SOR 불가 |
| `26` | 최유리(FOK) | 빈 값 | — | SOR 불가 |
| `28` | 스톱지정가 | 필수 | **필수**(스톱가) | |
| `29` | 중간가 | 빈 값 | — | |
| `30` | 중간가(IOC) | 빈 값 | — | |
| `31` | 중간가(FOK) | 빈 값 | — | |
| `40` | 보통(GTP) | 필수(추정) | — | NXT 프리마켓 한정, 2026-09-12 추가 |
| `46` | 최유리(GTP) | 빈 값(추정) | — | 〃 |
| `47` | 최우선(GTP) | 빈 값(추정) | — | 〃 |
| ~~`62`~~ | ~~시간외단일가~~ | — | — | **2026-09-12 21시 삭제** ([공지#60](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=60)). 공식 스펙 JSON·공식 샘플 주석에는 아직 남아 있다 |

- OpenAPI+의 `sHogaGb`(`"00"` 지정가, `"03"` 시장가)와 값이 다르다. REST는 `"0"`, `"3"`. 그대로 옮기면 안 된다. [확인됨] [AlgoLab 전환 글](https://algolab.co.kr/blog/kiwoom-openapi-plus-to-rest-migration-2026)
- KRX 애프터마켓(16:00~20:00)에서 쓸 매매구분은 가이드에 명시가 없다. **[불확실]** (보통 `0` + `KRX`로 추정)

### 10.4 호가단위·가격제한

| 가격 구간(원) | 호가단위 | 근거 |
|---|---|---|
| < 2,000 | 1 | [확인됨] 키움 공식 [TradingView 샘플 common.js](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server/blob/main/common.js) `getKrxTickSize` (2023-01-25 KRX 개편 표와 일치) |
| 2,000 ~ 4,999 | 5 | 〃 |
| 5,000 ~ 19,999 | 10 | 〃 |
| 20,000 ~ 49,999 | 50 | 〃 |
| 50,000 ~ 199,999 | 100 | 〃 |
| 200,000 ~ 499,999 | 500 | 〃 |
| ≥ 500,000 | 1,000 | 〃 |

- ETF·ETN·ELW는 별도 호가단위가 있는 것으로 알려져 있으나 이번 조사에서 확인하지 못했다. **[불확실]**
- 가격제한폭: 정규시장 기준가 ±30%, KRX 애프터마켓도 당일 기준가 ±30%(VI 적용, CB·사이드카 미적용). [확인됨] [공지#59](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=59)
- 상·하한가는 ka10001의 `upl_pric`/`lst_pric`로 확인한다(부호 제거). [확인됨]

### 10.5 주문 오류와 상태 확인

| 사실 | 근거 |
|---|---|
| 주문 거부도 HTTP 200 + `return_code≠0`. 예: `{"return_code": 20, "return_msg": "[2000](RC4058:모의투자 장종료)"}` | [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) `api_error` 주석 |
| 주문번호는 7자리 문자열(앞자리 0 포함). 가이드 kt10000 예시엔 `"00024"`처럼 짧은 값도 있다 | [확인됨] 가이드. 짧은 값이 실제로 오는지 **[불확실]** |
| 공식 CLI는 전송 전에 `orig_ord_no`가 숫자 7자리인지 검사한다 | [확인됨] kwcli `executor/rest.py` |
| 체결·정정 결과는 실시간 00(주문체결)으로 받거나 ka10075·ka10076·kt00007로 조회 | [확인됨] |

**[권고] 주문 처리 원칙** (SPEC §3.4 "주문은 자동 재시도하지 않는다"와 일치)
1. `ord_no`는 문자열로 저장하고, 최초 주문번호를 키로 두고 정정 때마다 "현재 주문번호"를 갱신한다.
2. 타임아웃·연결 오류처럼 결과가 애매하면 **재전송하지 않는다.** ka10075(미체결)과 kt00007(주문체결내역, 초당 1회)로 같은 종목·수량·시각의 주문이 있는지 확인한 뒤 결정한다.
3. 429·1700은 주문이 접수되지 않은 것으로 보이지만, 그래도 재전송 전 미체결 조회를 거친다.

---

## 11. WebSocket 실시간

### 11.1 접속 순서

[확인됨] [ws_client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/ws_client.py), [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample), [튜토리얼](https://openapi.kiwoom.com/guide/index)

1. `wss://api.kiwoom.com:10000/api/dostk/websocket`(모의 `wss://mockapi.kiwoom.com:10000/...`)에 접속.
2. 바로 `{"trnm": "LOGIN", "token": "<access_token>"}` 전송(Bearer 없음).
3. `trnm == "LOGIN"` 응답의 `return_code == 0`을 기다린다. 0이 아니면 실패. 공식 런타임은 LOGIN 응답 전에 다른 메시지가 오면 오류로 본다(PING은 에코 후 계속 대기).
4. LOGIN 성공 뒤에만 REG·조건검색을 보낸다.
5. 수신 루프: `PING` → **받은 메시지를 그대로 다시 보낸다**. `REAL` → 처리. `REG`/`REMOVE`/`SEARCH`/`CNSR*` → 응답 확인. `SYSTEM` → 공지 처리.

- 서버가 PING을 보내고 클라이언트가 같은 값을 돌려보내는 방식이다. 클라이언트가 PING을 돌려보내지 않으면 서버가 연결을 끊는다. PING만 오고 데이터가 없으면 연결은 정상이고 데이터가 없는 것이다. [확인됨] [FAQ#15](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=15)
- PING은 `{"trnm": "PING", ...}` 형태이며, 공식 런타임은 문자열 `"PING"`도 PING으로 처리한다. [확인됨] [ws_client.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/ws_client.py) `_is_ping_message`
- 공식 런타임은 `websockets.connect(uri, open_timeout=30, ping_interval=None)`으로 라이브러리 자체 ping을 끈다. [확인됨] 라이브러리 ping과 키움 응용 PING이 충돌할 수 있다는 설명은 [AlgoLab 실시간 글](https://algolab.co.kr/blog/kiwoom-rest-api-realtime-websocket-0b-0d-2026). [권고] 공식과 같이 `ping_interval=None`.
- 전송 형식은 JSON(큰따옴표)이다. 가이드 예시의 작은따옴표는 파이썬 dict 표기일 뿐이다. 공식 런타임이 `json.loads`로 파싱한다. [확인됨]
- PING 주기는 문서에 없다. **[불확실]**

### 11.2 클라이언트 → 서버 메시지

| trnm | 형식 | 근거 |
|---|---|---|
| `LOGIN` | `{"trnm":"LOGIN","token":"..."}` | [확인됨] |
| `REG` | `{"trnm":"REG","grp_no":"1","refresh":"1","data":[{"item":["005930"],"type":["0B","0D"]}]}` | [확인됨] [packets.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/realtime/packets.py), [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B) |
| `REMOVE` | `{"trnm":"REMOVE","grp_no":"1","data":[{"item":["005930"],"type":["0B"]}]}` (`refresh` 불필요) | [확인됨] 〃 |
| `SEARCH` | `{"trnm":"SEARCH","grp_no":"1"}` — 그룹의 실시간 등록 현황 조회. 응답 형식은 문서에 없음 | [확인됨] [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample) 코드 / 응답 **[불확실]** |
| `PING` | 받은 그대로 에코 | [확인됨] |
| `CNSRLST`/`CNSRREQ`/`CNSRCLR` | 조건검색(§12) | [확인됨] |

- `grp_no`(최대 4자): 여러 종목을 묶어 등록·해제하는 단위. 화면별·관심그룹별로 나눠 쓰라는 용도. [확인됨] 가이드, [FAQ#5](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=5)
- `refresh`: `0` = 그 그룹의 기존 item/type을 모두 해지하고 새로 등록, `1` = 기존을 유지하고 추가(기본값). [확인됨] 라이브 가이드
- `item`: 종목코드 배열(KRX/NXT/통합 접미사). 00(주문체결)·04(잔고)·0s(장시작시간)·1h(VI)는 종목 지정 없이 전체가 오며, 라이브 가이드는 `"item": [""]`로 보내라고 적었다. 공식 파이썬 예제는 `"item": []`를 쓴다. 둘 다 허용되는지는 **[불확실]** — 라이브 가이드(`[""]`)를 우선한다.
- `type`: 실시간 타입 코드 배열(§11.5).
- REMOVE 변형(2025-05-29 개선): [확인됨] [공지#7](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=7)
  - 타입 전체 해지: `{"trnm":"REMOVE","grp_no":"1","data":[{"item":[],"type":["0D"]}]}` (정상) — `"item":[""]`로 보내면 `""` 종목만 지우려 해서 **삭제 안 됨**
  - 종목 해지(모든 타입): `{"item":["A","B"],"type":[]}` — `"type":[""]`는 오류
  - 복합: `{"item":["A","B"],"type":["0B","0D"]}`
  - 그룹 전체 해지: `{"trnm":"REMOVE","grp_no":"1"}`, `"data":[]`, `"data":[{"item":[],"type":[]}]` 모두 정상
- 같은 종목을 중복 요청하면 서버가 중복을 제거한다. [확인됨] [FAQ#8](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=8)
- 공식 테스트샘플은 "초당 유량 제어" 때문에 REG 전에 300ms를 기다린다. [확인됨] [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample) [권고] REG·REMOVE·CNSR 전송도 초당 몇 건 이하로 큐잉.

### 11.3 서버 → 클라이언트 메시지

| trnm | 형식 | 근거 |
|---|---|---|
| `LOGIN` | `{"trnm":"LOGIN","return_code":0,"return_msg":"..."}` | [확인됨] |
| `REG`/`REMOVE` | `{"trnm":"REG","return_code":0,"return_msg":""}` — 0 정상, 1 오류 | [확인됨] [가이드 00](https://openapi.kiwoom.com/guide/apiGuideContents/14/00) |
| `PING` | 그대로 에코 | [확인됨] |
| `REAL` | `{"trnm":"REAL","data":[{"type":"0B","name":"주식체결","item":"005930","values":{"10":"-20800", ...}}]}` — `data`에 여러 건이 올 수 있다. 실시간 데이터에는 `return_code`가 없다 | [확인됨] [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B), [events.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/realtime/events.py) |
| `SYSTEM` | VI·CB 등 공지, 연결 종료 안내. 공식 테스트샘플은 `code`·`message` 필드를 읽고 `code == "R10002"`이면 연결 끊김으로 처리한다 | [확인됨] [FAQ#3](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=3), [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample). 다른 `code` 목록은 **[불확실]** |

```json
{"trnm": "REAL", "data": [{"type": "0B", "name": "주식체결", "item": "005930",
  "values": {"20": "165208", "10": "-20800", "11": "-50", "12": "-0.24", "27": "-20800", "28": "-20700",
             "15": "+82", "13": "30379732", "14": "632640", "16": "20850", "17": "+21150", "18": "-20450",
             "25": "5", "228": "98.92", "290": "2", "9081": "KRX"}}]}
```

### 11.4 세션·연결 제약

| 사실 | 근거 |
|---|---|
| 계좌(토큰)당 세션 1개. 같은 토큰으로 두 번째 연결을 열면 서로 밀어낸다(`received 1000 (OK) Bye`) | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro) / [확인됨·실측] [kw_stream.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_stream.py) |
| 한 토큰으로 국내·미국 실시간을 한 연결에서 같이 받을 수 있다(국내 경로로 접속해 미국 TR 등록 가능, 반대도 가능) | [확인됨] [FAQ#43](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=43) |
| 서버 점검 단절: 월~토 07:50~07:55, 일 05:00~05:15. 이 시간 REST 사용 불가, WebSocket 끊김은 정상 종료 → close 이벤트에서 재연결 | [확인됨] [FAQ#42](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=42), [공지#46](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=46) |
| 소켓이 살아 있는데 서버가 푸시를 멈추는 경우가 있다(6분 수신 뒤 49분 무음 실측). 공식 플러그인은 데이터 무수신 180초를 정지로 보고 재시작한다 | [확인됨·실측] [kw_stream.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_stream.py) |
| 끊기면 서버 쪽 구독은 남지 않는다. 재접속 후 LOGIN → REG(조건검색은 CNSRLST → CNSRREQ)를 다시 보내야 하고, 끊긴 동안의 체결은 REST로 다시 맞춰야 한다 | [확인됨] 공식 런타임이 재연결 시 LOGIN부터 다시 함. 구독 미보존·REST 재동기화는 [AlgoLab 실시간 글](https://algolab.co.kr/blog/kiwoom-rest-api-realtime-websocket-0b-0d-2026) 설명 **[불확실]**(공식 문장 없음) |
| 짧은 간격으로 재접속하면 서버가 LOGIN 응답 없이 1000으로 닫는 경우가 있다 | **[불확실]** 커뮤니티 관찰 [websocket.py](https://github.com/younghwan91/kiwoom-rest-api/blob/main/src/kiwoom_client/websocket.py) |
| 토큰을 재발급(6시간 이후)해 기존 토큰이 폐기되면, 그 토큰으로 LOGIN한 기존 세션이 유지되는지 | **[불확실]** 문서 없음 |

**[권고]** 재연결은 지수 백오프(1→2→4…최대 30초), 구독 목록은 클라이언트가 보관해 재등록, 장중 데이터 워치독은 "PING은 오는데 REAL이 N초 없음"과 "PING도 없음"을 구분한다(장외 시간에는 REAL이 없는 게 정상).

### 11.5 실시간 타입 코드

[확인됨] 스펙 JSON 목록과 라이브 가이드 목록이 같다. [가이드 0B](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B)

| type | 이름 | item | type | 이름 | item |
|---|---|---|---|---|---|
| `00` | 주문체결 | 계좌 전체(`[""]`) | `0H` | 주식예상체결 | 종목 |
| `04` | 잔고 | 계좌 전체(`[""]`) | `0I` | 국제금환산가격 | |
| `0A` | 주식기세 | 종목 | `0J` | 업종지수 | 업종코드 |
| `0B` | 주식체결 | 종목 | `0U` | 업종등락 | 업종코드 |
| `0C` | 주식우선호가 | 종목 | `0g` | 주식종목정보 | 종목 |
| `0D` | 주식호가잔량 | 종목 | `0m` | ELW 이론가 | |
| `0E` | 주식시간외호가 | 종목 | `0s` | 장시작시간 | 없음(`[""]`) |
| `0F` | 주식당일거래원 | 종목 | `0u` | ELW 지표 | |
| `0G` | ETF NAV | 종목 | `0w` | 종목프로그램매매 | 종목 |
| `1h` | VI발동/해제 | 전체(`[""]`) | `02` | 조건검색 실시간 편입·이탈(ka10173 결과) | — |

- 대소문자가 구분된다(`0g`와 `0G`는 다른 타입). 공식 테스트샘플은 수신 시 `0d`·`0b`처럼 소문자도 같이 처리한다. [확인됨] 스펙 목록, [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample)

### 11.6 FID(필드 번호) 표 — 자주 쓰는 타입

`values`의 키는 FID 번호 **문자열**이다(예 `"10"` = 현재가). OpenAPI+와 대부분 같은 번호 체계다. [확인됨] 가이드 / [AlgoLab 전환 글](https://algolab.co.kr/blog/kiwoom-openapi-plus-to-rest-migration-2026)

**0B 주식체결** — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/0B) [확인됨]

| FID | 이름 | 형식 | FID | 이름 | 형식 |
|---|---|---|---|---|---|
| 20 | 체결시간 | HHmmss | 25 | 전일대비기호 | 1~5 |
| 10 | 현재가 | 원, 부호 | 26 | 전일거래량대비(주) | 부호 |
| 11 | 전일대비 | 원, 부호 | 29 | 거래대금증감 | 원, 부호 |
| 12 | 등락율 | %, 부호 | 30 | 전일거래량대비(%) | 부호 |
| 27 | (최우선)매도호가 | 원, 부호 | 31 | 거래회전율 | % |
| 28 | (최우선)매수호가 | 원, 부호 | 228 | 체결강도 | % |
| 15 | 거래량 | **+ 매수체결, − 매도체결** | 311 | 시가총액(억) | |
| 13 | 누적거래량 | 1주 | 290 | 장구분 | 1 장전시간외, 2 장중, 3 장후시간외 |
| 14 | 누적거래대금 | **백만원** | 567 / 568 | 상한가·하한가 발생시간 | HHmmss |
| 16 / 17 / 18 | 시가·고가·저가 | 원, 부호 | 1030 / 1031 | 매도·매수 체결량 | |
| 620 | 당일거래평균가 | | 1313 | 순간거래대금 | |
| 9081 | 거래소구분 | 라이브 가이드: `KRX`/`NXT` 문자열. 스펙 예시는 `"1"` — **[불확실]** | 1890~1892 | 시가·고가·저가 시간 | |

**0D 주식호가잔량** — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/0D) [확인됨]

| FID | 이름 |
|---|---|
| 21 | 호가시간(HHmmss) |
| 41~50 | 매도호가 1~10 (원, 부호) |
| 51~60 | 매수호가 1~10 |
| 61~70 | 매도호가수량 1~10 |
| 71~80 | 매수호가수량 1~10 |
| 81~90 / 91~100 | 매도·매수 호가 직전대비 1~10 |
| 121 / 122 | 매도호가총잔량 / 직전대비 |
| 125 / 126 | 매수호가총잔량 / 직전대비 |
| 23 / 24 | 예상체결가 / 예상체결수량 |
| 128 / 129 / 138 / 139 | 순매수잔량 / 매수비율 / 순매도잔량 / 매도비율 |
| 200, 201, 238, 291~295 | 예상체결가 관련(291은 예상체결 시간에만 유효) |
| 6044~6053 / 6054~6063 | KRX 매도 / 매수 호가잔량 1~10 |
| 6064 / 6065 | KRX 매도 / 매수 총잔량 |
| 6066~6075 / 6076~6085 | NXT 매도 / 매수 호가잔량 1~10 |
| 6086 / 6087 | NXT 매도 / 매수 총잔량 |
| 6100~6115 | KRX·NXT 중간가와 잔량·대비 |

- 라이브 가이드에서 LP 호가수량(621~640), 13, 299, 215, 216이 빠졌다(스펙 JSON에는 있음). [확인됨] 두 출처 대조

**00 주문체결** — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/00) [확인됨]

| FID | 이름 | 설명 |
|---|---|---|
| 9201 | 계좌번호 | 10자리 |
| 9203 | 주문번호 | 7자리 |
| 9001 | 종목코드 | |
| 912 | 주문업무분류 | 예시 `JJ` |
| 913 | 주문상태 | 접수, 체결, 확인, 취소, 거부 |
| 302 | 종목명 | |
| 900 / 901 / 902 | 주문수량 / 주문가격 / 미체결수량 | |
| 903 | 체결누계금액 | |
| 904 | 원주문번호 | 없으면 `0000000` |
| 905 | 주문구분 | `+매수`, `-매도`, 매수정정, 매수취소 등. `+`/`−`는 HTS 색(적/청) 표시 |
| 906 | 매매구분 | 보통, 시장가, … (텍스트) |
| 907 | 매도수구분 | 1 매도, 2 매수 |
| 908 | 주문·체결시간 | HHmmss |
| 909 | 체결번호 | 체결 시 |
| 910 | 체결가 | **평균체결가** |
| 911 | 체결량 | **누적체결량** |
| 914 / 915 | 단위체결가 / 단위체결량 | 이번 체결분 |
| 10 / 27 / 28 | 현재가 / 최우선 매도·매수호가 | |
| 938 / 939 | 매매수수료 / 매매세금 | |
| 919 | 거부사유 | |
| 920 / 921 | 화면번호 / 터미널번호 | |
| 922 / 923 | 신용구분(00 현금, 03 자기융자) / 대출일 | |
| 2134 / 2135 / 2136 | 거래소구분(0 통합, 1 KRX, 2 NXT) / 이름 / SOR여부 | |
| ~~10010~~ | ~~시간외단일가_현재가~~ | 2026-09-12 삭제 [공지#60](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=60) |

- 913 상태가 어떤 순서로 오는지(예: 정정 시 "확인"이 원주문·새 주문 어느 쪽에 오는지)는 문서에 없다. **[불확실]** — 모의에서 로그로 확인.

**04 잔고** — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/04) [확인됨]

| FID | 이름 | FID | 이름 |
|---|---|---|---|
| 9201 | 계좌번호 | 945 | 당일순매수량 |
| 9001 | 종목코드 | 946 | 매도/매수구분 |
| 917 / 916 | 신용구분 / 대출일 | 950 | 당일총매도손익 |
| 302 | 종목명 | 27 / 28 | 최우선 매도·매수호가 |
| 10 | 현재가(부호) | 307 | 기준가 |
| 930 | 보유수량 | 8019 | 손익률(실현손익) |
| 931 | 매입단가 | 990 / 991 | 당일실현손익(유가) / 손익율 |
| 932 | 총매입가(당일누적) | 992 / 993 | 당일실현손익(신용) / 손익율 |
| 933 | 주문가능수량 | 957 / 958 / 918 / 959 | 신용금액 / 신용이자 / 만기일 / 담보대출수량 |

**0s 장시작시간** — FID 215 장운영구분, 20 체결시간, 214 장시작예상잔여시간. [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/0s) [확인됨]

| 215 값 | 뜻 | 215 값 | 뜻 |
|---|---|---|---|
| `0` | 장시작전 알림(8:40부터 1분마다) | `g` | KRX 애프터마켓 시작(16:00) |
| `2` | 장마감전 알림(15:20부터 1분마다) | `h` | KRX 애프터마켓 종료(20:00) |
| `3` | 장시작(09:00) | `P` / `Q` | NXT 프리마켓 시작 / 종료 |
| `4` | 장마감(15:30) | `R` / `S` | NXT 메인마켓 시작 / 종료 |
| `8` | 정규장마감(15:30 이후) | `T` / `U` / `V` | NXT 애프터마켓 단일가 시작 / 시작 / 종료 |
| `9` | 전체장마감(20:00 이후) | `G` / `H` | 코스피 매도 / 매수 사이드카 |
| `a` / `b` | 시간외 종가매매 시작(15:40) / 종료(16:00) | `I` / `J` | 코스닥 매도 / 매수 사이드카 |
| `s` / `e` / `f` / `o` | 선물옵션 관련 | | |

- 스펙 JSON의 `c`/`d`(시간외 단일가 16:00~18:00)는 라이브에서 `g`/`h`(애프터마켓)로 바뀌었다. [확인됨] 두 출처 대조

**1h VI발동/해제** — [가이드](https://openapi.kiwoom.com/guide/apiGuideContents/14/1h) [확인됨]: 9001 종목코드, 302 종목명, 9068 VI발동구분(`1` 정적, `2` 동적, `3` 동적+정적, `4` VI연장 — 2026-09-12 추가), 1225 VI적용구분, 1221 VI발동가격, 1223 매매체결처리시각, 1224 VI해제시각, 1236/1237 기준가격(정적/동적), 1238/1239 괴리율, 1489 발동가 등락율, 1490 발동횟수, 9069 발동방향구분, 9008 시장구분, 9075 장전구분.

### 11.7 websockets 수신 루프 골격 [권고]

```python
async with websockets.connect(ws_url, open_timeout=10, ping_interval=None) as ws:
    await ws.send(json.dumps({"trnm": "LOGIN", "token": token}))
    while True:                                   # LOGIN 응답 대기(PING은 에코)
        msg = json.loads(await ws.recv())
        if msg.get("trnm") == "PING":
            await ws.send(json.dumps(msg)); continue
        if msg.get("trnm") != "LOGIN" or int(msg.get("return_code", 0)) != 0:
            raise LoginFailed(msg)                # 8005 등은 토큰 재확인 후 1회 재시도
        break
    await ws.send(json.dumps({"trnm": "REG", "grp_no": "1", "refresh": "1",
                              "data": [{"item": ["005930"], "type": ["0B", "0D"]}]}))
    async for raw in ws:
        msg = json.loads(raw)
        t = msg.get("trnm")
        if t == "PING":
            await ws.send(raw)                    # 받은 그대로
        elif t == "REAL":
            for entry in msg.get("data", []):
                dispatch(entry["type"], entry.get("item"), entry["values"])
        elif t == "SYSTEM":
            handle_system(msg)                    # code == "R10002" → 재접속
        else:
            handle_ack(msg)                       # REG/REMOVE/SEARCH/CNSR*: return_code 확인
```

---

## 12. 조건검색 (ka10171~ka10174, WebSocket)

출처: [가이드 ka10171](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10171), [ka10172](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10172), [ka10173](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10173), [ka10174](https://openapi.kiwoom.com/guide/apiGuideContents/15/ka10174) [확인됨]

| 사실 | 근거 |
|---|---|
| 조건식은 **영웅문4 HTS에서 만들고 저장한 것만** 불러 쓴다. REST로 조건식 작성·편집·저장 불가 | [확인됨] [FAQ#17](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=17) |
| ka10172·ka10173을 쓰기 전에 **같은 세션에서 ka10171(목록)을 먼저** 호출해야 실시간 서버가 고객의 조건식 목록을 인식한다 | [확인됨] [FAQ#4](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=4) |
| 실시간 조건검색은 세션당 10건, 조건당 결과 최대 100종목(HTS와 같음) | [확인됨] [FAQ#41](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=41), 라이브 가이드 |
| `stex_tp`: `K` KRX 시세 기준, `A` 통합시세 기준(2026-07-21~). 동시 사용 불가 | [확인됨] [공지#52](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=52) |
| 공식 CLI는 `NXT`를 `N`으로 바꿔 보내는 코드가 있으나 가이드에는 K·A만 있다 | **[불확실]** kwcli `executor/condition.py` |
| 모의투자에서 조건검색이 되는지 | **[불확실]** 문서 없음 |

| TR | 요청 | 응답 |
|---|---|---|
| ka10171 목록 | `{"trnm":"CNSRLST"}` | `{"trnm":"CNSRLST","return_code":0,"return_msg":"","data":[["0","조건1"],["1","조건2"]]}` — 예시는 `[seq, name]` 배열, 표는 `seq`/`name` 객체. 둘 다 처리한다(공식 CLI도 둘 다 처리) |
| ka10172 일반(1회) | `{"trnm":"CNSRREQ","seq":"4","search_type":"0","stex_tp":"K","cont_yn":"N","next_key":""}` | `seq`, `cont_yn`, `next_key`, `data[]`(FID 9001 종목코드 `A005930`형, 302, 10, 25, 11, 12, 13, 16, 17, 18). 결과가 많으면 **본문** `cont_yn="Y"` + `next_key`로 이어받는다 |
| ka10173 실시간 | `{"trnm":"CNSRREQ","seq":"4","search_type":"1","stex_tp":"K"}` | 먼저 현재 편입 목록 `data[{"jmcode":"A005930"}, ...]`, 이후 `REAL` 메시지(type `02`)로 편입·이탈 |
| ka10174 해제 | `{"trnm":"CNSRCLR","seq":"4"}` | `{"trnm":"CNSRCLR","seq":"4","return_code":0,"return_msg":""}` (2025-05-29부터 `seq` 포함) |

실시간 편입·이탈(`REAL`, type `02`) `values`: [확인됨] 라이브 가이드 ka10173, [공지#7](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=7)

| FID | 뜻 |
|---|---|
| 841 | 조건식 일련번호(2025-05-29부터 `"4"`처럼 seq만) |
| 9001 | 종목코드(예시는 접두어 없는 `005930`) |
| 843 | `I` 편입(삽입), `D` 이탈(삭제) |
| 20 | 체결시간 |
| 907 | 매도/수 구분 |
| 9081 | 거래소 구분(라이브에서 추가) |

ka10172 숫자 필드 형식: 현재가·전일대비·시고저는 0-padding 부호 포함 9자리, 누적거래량 10자리. **등락율(FID 12)은 정수 배율 표기**인데, 라이브 가이드는 8자리 `"00000150"` = +1.50%(×100), 스펙 JSON(2026-09-04)은 9자리 `"000001500"` = +1.50%(×1000)로 적었다. **[불확실]** — 실제 값을 ka10001 `flu_rt`와 비교해 배율을 확정한다.

[권고] 같은 종목이 편입·이탈을 반복하고 장 초반에 신호가 몰린다. 편입 즉시 주문하지 말고 위원회·리스크 게이트를 거친다(SPEC 파이프라인과 일치). 조건식은 이름으로 찾고 seq를 하드코딩하지 않는다([AlgoLab 조건검색 글](https://algolab.co.kr/blog/kiwoom-rest-condition-search-websocket-2026)).

---

## 13. 오류 코드 (API 서버)

출처: [오류코드 페이지](https://openapi.kiwoom.com/errorcode/errorCodeView)(2026-11-15) [확인됨]. 1518·1904와 8050의 새 문구는 라이브 페이지에만 있고 스펙 JSON에는 없다. 분류 열은 공식 런타임 [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py)의 분류.

| 코드 | 의미 | 분류·대응 |
|---|---|---|
| 1501 | API ID가 Null이거나 값이 없음 | 입력 오류 |
| 1504 | 해당 URI에서 지원하지 않는 API ID | 입력 오류(경로·api-id 짝 확인) |
| 1505 | 존재하지 않는 API ID | 입력 오류 |
| 1511 | 필수 입력 값 없음 | 입력 오류 |
| 1512 | Http header 값 없음·읽을 수 없음 | 입력 오류 |
| 1513 | authorization 헤더 필요 | 입력 오류 |
| 1514 | authorization 형식 오류 | 입력 오류 |
| 1515 | authorization의 Grant Type 형식 오류 | 입력 오류 |
| 1516 | authorization의 Token 없음 | 입력 오류 |
| 1517 | 입력 값 형식 오류(파라미터, 실패사유) | 입력 오류 |
| 1518 | next-key 형식 오류 | 입력 오류(연속조회 키 그대로 전달했는지) |
| 1687 | 재귀 호출로 API 호출 제한 | 입력 오류 |
| 1700 | 허용된 API 요청 개수 초과(유량, API ID) | 유량 → 백오프 |
| 1701 | 허용된 전체 요청 개수 초과 | 유량 → 백오프 |
| 1702 | 허용된 그룹 요청 개수 초과 | 유량 → 백오프 |
| 1901 | 시장 코드값 없음 | 종목 오류 |
| 1902 | 종목 정보 없음(종목코드 확인) | 종목 오류 |
| 1903 | 종목 정보 없음(종목코드·거래소구분 확인) | 종목 오류(접미사 확인) |
| 1904 | NXT 주문 불가 종목 | 주문 오류(nxtEnable 확인) |
| 1999 | 예기치 못한 에러 | 원문 노출·알림 |
| 8001 | App Key·Secret Key 검증 실패 | 자격 증명(토큰 만료, 타 계좌 토큰, 도메인 확인 — [FAQ#21](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=21)) |
| 8002 | App Key·Secret Key 검증 실패(사유) | 자격 증명 |
| 8003 | Access Token 조회 실패 | 토큰 |
| 8005 | Token이 유효하지 않음 | 토큰 → 재확인·재발급 후 1회 재시도 |
| 8006 | Access Token 생성 실패 | 토큰 |
| 8009 | Access Token 발급 실패 | 토큰 |
| 8010 | 토큰 발급 IP와 요청 IP가 다름 | 단말 인증(출구 IP 확인) |
| 8011 / 8012 | grant_type 누락 / 값 오류 | 자격 증명 |
| 8015 / 8016 | 토큰 폐기 실패 / 폐기 시 token 누락 | 토큰 |
| 8020 | appkey·secretkey 누락 | 입력 오류 |
| 8030 | 실전/모의 구분이 달라 Appkey 사용 불가 | 모드 불일치 |
| 8031 | 실전/모의 구분이 달라 Token 사용 불가 | 모드 불일치(공식은 재발급 후 1회 재시도 대상) |
| 8040 | 단말기 인증 실패 | 단말 인증 |
| 8050 | IP 미등록(포털 API 사용신청 화면에서 IP 등록) — 스펙 JSON 문구는 "지정단말기 인증 실패" | 단말 인증 |
| 8103 | 토큰 인증 또는 단말기 인증 실패 | 단말 인증(공식은 재발급 후 1회 재시도 대상) |
| 8104 | 모의투자에서 지원하지 않는 API | 모의 미지원 |
| 8200 | 법인 고객 미지원 API | — |

그 밖에 확인된 최상위 `return_code`
- `3` + 메시지 안 `[8005:...]`: 인증 실패 [확인됨] (§2.4)
- `20` + `[2000](RC4058:모의투자 장종료)`: 주문 업무 거부 예 [확인됨·실측]
- `5` "허용된 요청 개수를 초과하였습니다": 유량 초과 **[불확실]** (커뮤니티)
- WebSocket·주문 관련 오류코드는 "향후 추가 예정"이라고만 공지됐다. [확인됨] [공지#16](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=16)

[권고] 판정 순서: HTTP 429 → 유량. HTTP 401 → 토큰. 그 밖에는 본문 `return_code`(정수화), 0이 아니면 `return_msg`에서 `\[(\d{3,5}):` 또는 `CODE=(\d{3,5})`로 세부 코드를 뽑아 위 표로 분류한다(공식 [errors.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py)와 같은 방식).

---

## 14. 모의투자에서 다른 점

| 항목 | 내용 | 근거 |
|---|---|---|
| 도메인·키 | `mockapi.kiwoom.com`, 모의 전용 앱키. 실전 키·토큰을 쓰면 8030/8031 | [확인됨] |
| 거래소 | KRX만(매매·계좌조회). NXT 시세는 제공 | [확인됨] [모의투자 안내](https://openapi.kiwoom.com/intro/mockInvestInfo) |
| 유량 | TR당 초당 1회 | [확인됨] [서비스 소개](https://openapi.kiwoom.com/intro) |
| 미지원 API | 8104로 거절. 스펙에 명시된 것은 ka01690(일별잔고수익률) | [확인됨] 스펙 JSON ka01690 개요 |
| 장 종료 후 주문 | `[2000](RC4058:모의투자 장종료)`로 거부 | [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) |
| 서비스 유지 | 모의 도메인 접속만으로는 3개월 자동 해지를 막지 못한다 | [확인됨] [FAQ#19](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=19) |
| 앱키 만료 | 모의투자 신청 기간을 따른다 | [확인됨] [FAQ#11](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=11) |
| 신용주문·조건검색·NXT 전용 기능의 모의 지원 여부 | 문서 없음 | **[불확실]** |

[권고] SPEC의 "연결 테스트(모의에서 토큰 발급 + 잔고 조회)"는 kt00018(모의 초당 1회)을 한 번만 호출한다.

---

## 15. 데이터 파싱 함정

| # | 함정 | 대응 | 근거 |
|---|---|---|---|
| 1 | 가격 필드의 `+`/`−`는 **전일 대비 방향**이지 음수 가격이 아니다(`cur_prc: "-78800"`) | 가격은 절댓값 | [확인됨] 가이드 "부호가 포함된 숫자", [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) `price()` |
| 2 | `pred_pre`(전일대비)·`flu_rt`의 부호는 값의 일부 | 부호 유지 | [확인됨] |
| 3 | 0B FID 15 거래량의 부호는 매수(+)·매도(−) 체결 | 절댓값 = 수량, 부호 = 체결 방향 | [확인됨] 가이드 0B |
| 4 | 계좌 TR 금액이 0-padding + 부호: `"000000017598258"`, `"-00000000196888"` | 부호를 떼고 정수 변환. "앞자리 0이면 식별자"로 보는 범용 파서는 이 값을 숫자로 바꾸지 못한다(커뮤니티 래퍼의 `to_number` 사례) | [확인됨] 가이드 kt00018, [parsing.py](https://github.com/younghwan91/kiwoom-rest-api/blob/main/src/kiwoom_client/parsing.py) |
| 5 | 일부 API는 음수를 `--1200981`처럼 **이중부호**로 보낸다(ka10004·ka10007·ka10086·ka10061 등 19개 실측) | 부호는 하나로 정규화 | [확인됨·실측] [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py), [kwcli maps](https://pypi.org/project/kwcli/1.0.3/) |
| 6 | `"-0"`, `"-0.00"`, `""` 값 | `-0`→0, 빈 값→None | [확인됨] 가이드 예시, 실측 |
| 7 | 거래량 `4294967295`(2³²−1) 포화 | 결측으로 보고 거래대금÷가격으로 추정(공식 플러그인 방식) | [확인됨·실측] |
| 8 | ×100 정수 퍼센트: ka10059 `flu_rt`(`"+38"`=0.38%), ka10172 FID 12, 업종 차트 지수 OHLC | TR별 배율표를 둔다 | [확인됨·실측] [kwcli maps](https://pypi.org/project/kwcli/1.0.3/) |
| 9 | 종목코드 접두어: 잔고·실현손익 `A005930`, 조건검색 9001 `A005930`(A 주식, J ELW, Q ETN). 실시간 `item`·차트는 `005930` | 내부 키는 6자리로 정규화 | [확인됨] 가이드, [normalize.py](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) `stock_code` |
| 10 | 단위 혼재: 거래대금 일봉·0B FID14·순위표는 백만원, 주·월·년봉은 문서상 원. 시가총액 억원. 상장주식 천주. 매출·이익 억원 | 저장 전 원·주로 환산 | [확인됨] 가이드 / 주봉 단위 **[불확실]** |
| 11 | 주문번호·종목코드·날짜는 숫자처럼 보이는 문자열 | 문자열 유지(앞자리 0 보존) | [확인됨] |
| 12 | 시각 형식: 체결시간 HHmmss, 분봉 `cntr_tm` YYYYMMDDHHmmss(봉 시작), 일자 YYYYMMDD, `expires_dt` YYYYMMDDHHmmss. 모두 KST·시간대 표기 없음 | KST로 해석해 UTC 저장 | [확인됨] |
| 13 | 공식 문서 예시 JSON은 문법이 틀린 곳이 많다(쉼표 누락, 끝 쉼표, 작은따옴표, `"- item"` 같은 표 잔재)와 값 어긋남(ka10001) | 예시를 그대로 픽스처로 쓰지 말고 이 문서의 정리된 JSON이나 모의 실측 응답을 쓴다 | [확인됨] 가이드·스펙 JSON |
| 14 | ka10007 `pred_rt`는 거래량 비율, ka10085 `setl_remn`은 수량, 업종 일봉(ka20006) `trde_qty`는 천주 | 필드별 예외표 | [확인됨·실측] |
| 15 | 문서에 없는 필드가 오거나(분봉 `acc_trde_qty`), 문서 필드가 안 올 수 있다(ka10069 비율 필드 실측 없음) | 모델은 추가 필드 무시, 필드 누락 허용 | [확인됨·실측] |
| 16 | `return_code`가 int 또는 문자열, 일부 예시는 `returnCode` | 정수화·두 이름 모두 확인 | [확인됨] |

```python
from decimal import Decimal, InvalidOperation

SATURATED = 4_294_967_295

def kw_num(raw) -> Decimal | None:
    """'+73,200' '-00000000196888' '--1200981' '-0' '' → Decimal|None"""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("%", "")
    neg = s.startswith("-")
    s = s.lstrip("+-")
    if not s:
        return None
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return -v if (neg and v != 0) else v

def kw_price(raw) -> Decimal | None:   # 가격: 부호는 방향 표시 → 절댓값
    v = kw_num(raw)
    return abs(v) if v is not None else None

def kw_volume(raw) -> int | None:      # 2^32-1 포화 → None
    v = kw_num(raw)
    if v is None or abs(v) >= SATURATED:
        return None
    return int(abs(v))
```

---

## 16. 장 운영 시간 (2026-09-14 제도 변경 이후)

[확인됨] [공지#59](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=59)(운영시간 표 이미지), [공지#60](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=60)

| 시장 | 구간 | 시간 |
|---|---|---|
| KRX | 장시작전 시간외 종가(전일 종가) | 08:30~08:40 |
| KRX | 시가 단일가 / 접속매매 / 종가 단일가 | 08:30~09:00 / 09:00~15:20 / 15:20~15:30 |
| KRX | 장종료후 시간외 종가(당일 종가, 주문 접수 15:30~) | 15:40~16:00 |
| KRX | **애프터마켓**(기존 시간외단일가 16:00~18:00 대체) | 16:00~20:00 |
| NXT | 프리마켓 / 메인마켓 / 애프터마켓 | 08:00~08:50 / 09:00:30~15:20 / 15:40~20:00 |
| NXT | 종가매매(호가접수 15:00~16:00) | 15:30~16:00 |

- KRX 애프터마켓: 관리종목 제외 유가증권·코스닥 종목. ETF·ETN 불가. 정규장 미체결 주문은 애프터마켓으로 넘어가지 않아 새로 주문해야 한다. [확인됨] 공지#59
- 공지#60(오픈API 변경, 2026-09-12 21시 적용): 시간외단일가 TR(ka10098, ka10087) 삭제, 주문유형 62 삭제, 실시간 00 FID 10010 삭제, GTP 주문유형(40·46·47) 추가, 1h FID 9068에 `4` VI연장 추가. [확인됨]
- 서버 점검 단절: 월~토 07:50~07:55, 일 05:00~05:15. [확인됨] §11.4
- [권고] SPEC §3.5의 08:00 토큰 갱신은 단절 직후다. 07:56 이후 첫 호출이 실패하면 재시도하도록 여유를 둔다.

---

## 17. 구형 OpenAPI+(OCX)와의 차이

OpenAPI+는 Windows 전용 OCX(COM) 컨트롤이라 32비트 파이썬과 OCX 등록이 필요하고, `CommConnect()`로 로그인 창을 띄운 뒤 `OnEventConnect`로 결과를 받으며, `SetInputValue` → `CommRqData(…, sScreenNo)`로 opt 계열 TR을 요청하고 `OnReceiveTrData` 콜백에서 `GetCommData`로 필드를 하나씩 꺼내는 이벤트 방식이다. 연속조회는 `nPrevNext`, 실시간은 `SetRealReg`·`GetCommRealData`와 화면번호, 주문은 `SendOrder` 하나에 `sHogaGb`(`"00"` 지정가, `"03"` 시장가)를 넘긴다([AlgoLab 전환 글](https://algolab.co.kr/blog/kiwoom-openapi-plus-to-rest-migration-2026)) [확인됨·2차 출처]. REST API는 공인인증서 로그인 없이 OS·언어와 무관하게 HTTP로 쓰며([공지#1](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=1), [서비스 소개](https://openapi.kiwoom.com/intro)) [확인됨], 앱키·시크릿으로 24시간짜리 OAuth2 토큰을 받고 등록 IP에서만 인증하며, TR은 `api-id` 헤더 + JSON 본문 한 번의 POST로 응답을 받고, 연속조회는 응답 헤더 `cont-yn`·`next-key`, 실시간은 WebSocket의 `REG`/`REMOVE`와 `grp_no`(화면번호 대신), 조건검색도 같은 WebSocket의 `CNSRLST`/`CNSRREQ`로 처리한다. 계좌번호는 요청에서 빠지고 앱키(토큰)에 묶이며, 주문은 매수·매도·정정·취소가 kt10000~kt10003으로 나뉘고 `trde_tp`는 `"0"`·`"3"` 같은 다른 코드를 쓴다. 실시간 FID 번호는 대부분 같고 2134~2136(거래소·SOR) 같은 필드가 새로 붙었다. 신청은 한쪽만 해도 둘 다 쓸 수 있지만([FAQ#20](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=20)), OpenAPI+에서 되던 KOSPI200 선물·옵션은 REST에서 지원하지 않는다([FAQ#18](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=18)) [확인됨]. OpenAPI+의 TR 번호(opt10081 등)와 REST의 api-id(ka10081)가 비슷해 보여도 같은 데이터라고 가정하면 안 되며, 키움은 영웅문4 화면 ↔ REST ↔ OpenAPI+ TR 대응표 파일을 공지로 올렸다([공지#28](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=28)) [확인됨].

---

## 18. 어댑터 구현 체크리스트 [권고]

SPEC §3.4 `broker` 공통 인터페이스 기준.

| 인터페이스 | 키움 매핑 |
|---|---|
| 토큰 | au10001(단일 발급자, `expires_dt` KST 파싱, 만료 10분 전 갱신, 8005·8031·8103·401 → 저장소 재확인 → 재발급 1회) |
| 계좌 요약 | kt00004(초당 1회) + kt00001(초당 1회) |
| 보유 종목 | kt00018(`qry_tp=1`, `dmst_stex_tp=KRX`, 초당 1회, 연속조회) |
| 미체결 | ka10075(`all_stk_tp=0`, `trde_tp=0`, `stex_tp=1`) |
| 체결 | ka10076, 상세는 kt00007 |
| 주문 | kt10000/kt10001(`KRX`, `trde_tp` 0 또는 3), 정정 kt10002, 취소 kt10003. 자동 재시도 없음 |
| 현재가 | 실시간 0B, 보조로 ka10007 |
| 일봉 | ka11081(정규장) 또는 ka10081 + 연속조회, `upd_stkpc_tp=1` |
| 재무 | ka10001(일 1회 캐시) |
| 유니버스 | ka10099(마스터) + ka10032/ka10030/ka10027(순위) + 조건검색(선택) |
| 실시간 | WebSocket 1세션, `00`·`04` + 보유·감시 종목 `0B`(200종목 한도 관리), PING 에코, 워치독, 재연결 시 재등록 |

계약 테스트(pytest + respx) 픽스처는 이 문서의 정리된 JSON을 기본으로 쓰고, 모의 도메인 실측 응답(민감정보 제거)으로 교체한다. 실주문 경로는 테스트에서 호출할 수 없게 막는다(SPEC §9).

---

## 19. 확인하지 못한 항목 (키를 받은 뒤 모의 도메인에서 검증)

1. 토큰 재발급 규칙(6시간 이내 동일 토큰, 이후 새 토큰 + 기존 폐기)의 실제 동작, 그리고 재발급 시 기존 WebSocket 세션이 끊기는지.
2. au10001에 `api-id`·`authorization` 헤더를 같이 보내도 되는지(스펙 JSON과 라이브 가이드 불일치).
3. WebSocket 정식 경로: `/api/dostk/websocket` vs `/api/websocket`.
4. 유량 초과 응답의 정확한 본문(`return_code` 5 + `[1700:…]`인지)과 실제 체감 한도(공식 5회/초 vs 커뮤니티 1회/초·버스트 2).
5. 00·04 등록 시 `"item": [""]`와 `"item": []` 중 무엇이 맞는지, `SEARCH` 응답 형식, `SYSTEM` 메시지의 `code` 목록(R10002 외).
6. 0B FID 9081 값이 `KRX`/`NXT` 문자열인지 `1`/`2`인지.
7. ka10172 FID 12(등락율)의 배율(×100 vs ×1000).
8. 주봉·월봉·년봉 `trde_prica`의 실제 단위(문서상 원, 일봉은 백만원).
9. ka10081 등 기존 차트에 KRX 애프터마켓·NXT 체결이 섞이는지(정규장 전용 ka11081과 비교), 한 페이지 행 수.
10. 정정·취소 시 `dmst_stex_tp`를 원주문과 같게 보내야 하는지, 주문번호가 7자리 미만으로 오는 경우가 있는지.
11. KRX 애프터마켓(16:00~20:00) 주문에 쓸 `trde_tp`, GTP(40·46·47)의 가격 필드 정책.
12. 실시간 00의 상태(913) 전이 순서(접수 → 확인 → 체결, 정정·취소 시 어느 주문번호에 오는지).
13. 모의투자에서 조건검색·신용주문·일부 계좌 TR이 되는지(8104 목록).
14. kt00018 `qry_tp` 1(합산)과 2(개별)의 차이.
15. ka10001 매출액·영업이익·당기순이익의 기준 기간.
16. ETF·ETN 호가단위.
17. PING 주기와, 클라이언트 PING 무응답 시 서버가 끊기까지 걸리는 시간.

---

## 부록 A. 출처

공식(키움증권)
- 포털: [서비스 소개](https://openapi.kiwoom.com/intro) · [이용안내](https://openapi.kiwoom.com/intro/serviceInfo) · [모의투자 안내](https://openapi.kiwoom.com/intro/mockInvestInfo) · [API 가이드](https://openapi.kiwoom.com/guide/apiguide) · [오류코드](https://openapi.kiwoom.com/errorcode/errorCodeView) · [튜토리얼](https://openapi.kiwoom.com/guide/index) · [테스트샘플](https://openapi.kiwoom.com/guide/guideTestSample)
- 라이브 TR 상세(2026-11-15 조회): `https://openapi.kiwoom.com/guide/apiGuideContents/<분류>/<api-id>` — 분류 코드 a1 토큰발급, a2 토큰폐기, 01 종목정보, 02 시세, 05 순위정보, 07 차트, 08 계좌, 13 주문, 14 실시간시세, 15 조건검색
- 자주묻는질문: [게시판](https://openapi.kiwoom.com/board/Board0301View) — 본문은 `https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=<번호>` (사용: #2, #3, #4, #5, #7, #8, #10, #11, #12, #14, #15, #16, #17, #18, #19, #20, #21, #23, #25, #26, #27, #28, #39, #41, #42, #43)
- 공지사항: [게시판](https://openapi.kiwoom.com/board/Board0101View) — 본문은 `https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAZPagingDetailView?seqid=<번호>` (사용: #1, #7, #16, #18, #22, #25, #26, #28, #46, #49, #50, #52, #55, #59, #60, #61, #66, #68)
- GitHub [Kiwoom-Securities/Kiwoom-REST-API](https://github.com/Kiwoom-Securities/Kiwoom-REST-API) (커밋 c7a3d25, 2026-09-15): [`kiwoom/_data/kiwoom_api_spec.json`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/_data/kiwoom_api_spec.json) · [`kiwoom/core/auth.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/auth.py) · [`client.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/client.py) · [`errors.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/errors.py) · [`ws_client.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/core/ws_client.py) · [`realtime/packets.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/realtime/packets.py) · [`realtime/events.py`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/kiwoom/realtime/events.py) · [`.env.example`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/.env.example) · [`README.md`](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/main/README.md)
- GitHub [Kiwoom-Securities/Kiwoom-Plugins](https://github.com/Kiwoom-Securities/Kiwoom-Plugins) (커밋 7dcf821, 2026-09-15): [`kw_runtime/normalize.py`](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/normalize.py) · [`kw_stream.py`](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_stream.py) · [`kw_market.py`](https://github.com/Kiwoom-Securities/Kiwoom-Plugins/blob/main/kw_runtime/kw_market.py)
- PyPI [kwcli 1.0.3](https://pypi.org/project/kwcli/1.0.3/) (2026-09-16, 키움 공식 CLI): `kiwoom_cli/maps/api_commands.csv`(TR별 실측 주의), `order_price_policies.csv`, `arguments.csv`, `executor/condition.py`, `executor/rest.py` — 휠을 내려받아 읽기만 함
- GitHub [Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server): [`common.js`](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server/blob/main/common.js) · [`api-caller.js`](https://github.com/Kiwoom-Securities/tradingview-webhook-to-kiwoom-api-server/blob/main/api-caller.js)

교차 확인용(비공식)
- [younghwan91/kiwoom-rest-api](https://github.com/younghwan91/kiwoom-rest-api) (kiwoom-client, 2026-10-19): `README.md`, `src/kiwoom_client/base.py`, `rate_limiter.py`, `parsing.py`, `websocket.py`, `tick_size.py`
- AlgoLab 블로그: [429 유량](https://algolab.co.kr/blog/kiwoom-rest-api-429-rate-limit-2026) · [OpenAPI+ → REST 전환](https://algolab.co.kr/blog/kiwoom-openapi-plus-to-rest-migration-2026) · [실시간 0B·0D](https://algolab.co.kr/blog/kiwoom-rest-api-realtime-websocket-0b-0d-2026) · [조건검색](https://algolab.co.kr/blog/kiwoom-rest-condition-search-websocket-2026) · [정정·취소](https://algolab.co.kr/blog/kiwoom-rest-api-order-modify-cancel-kt10002-2026) · [토큰](https://algolab.co.kr/blog/kiwoom-rest-api-token-expiry-revoke-2026)

조사 메모
- 포털은 봇 차단(eversafe)이 있어 문서 데이터 일괄 내려받기 경로(`/guide/getApiInfoListAjax`)와 내장 브라우저 접속은 차단됐다. 우회하지 않았고, 일반 GET으로 열리는 TR 상세 조각·공지·FAQ 본문만 읽었다. 포털 화면의 "엑셀·PDF 다운로드"([FAQ#38](https://bbn.kiwoom.com/bbs/VBbsNoticeNOPAFPagingDetailView?seqid=38))는 이 데이터로 브라우저에서 생성되는 방식이다.
- wikidocs.net은 403으로 열리지 않아 쓰지 않았다.
