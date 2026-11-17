---
name: AlphaPilot
description: 국내 주식 자동매매 관제 — 엔진이 한 일과 안 한 일을 통장처럼 한 줄씩 적는 화면
colors:
  canvas: "#f5f4f0"
  surface: "#ffffff"
  surface-sunken: "#ebeae5"
  surface-inverse: "#121211"
  ink: "#121211"
  ink-secondary: "#47463f"
  ink-muted: "#696862"
  border: "#8f8d86"
  divider: "#e2e0da"
  primary: "#121211"
  on-primary: "#ffffff"
  secondary: "#e9e7e1"
  accent: "#4b3bb0"
  accent-subtle: "#ecebfa"
  success: "#08676f"
  warning: "#875200"
  danger: "#b3261e"
  up: "#c2272b"
  up-solid: "#d9363a"
  down: "#1d58d0"
  down-solid: "#2f6fed"
typography:
  page-title:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.018em"
  section-title:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
  caption:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  data:
    fontFamily: "IBM Plex Mono, Pretendard Variable, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: "4px"
  md: "8px"
  lg: "12px"
  xl: "20px"
  full: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "6": "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "0 16px"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "40px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "40px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
  approval-card:
    backgroundColor: "{colors.accent-subtle}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
  badge:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    height: "24px"
---

# Design System: AlphaPilot

## Overview

**Creative North Star: "통장정리"**

엔진이 한 일과 안 한 일을 은행 통장처럼 한 줄씩 적고, 돌아온 사용자에게 "지난번 확인한 뒤로" 밀린 줄을 정리해 보여준다. 통장은 꾸밈이 아니라 구조로 남는다: 번호가 붙은 줄, 현금 잔액 칸, "여기까지 확인함" 절취선, 거래번호를 눌러 한 판단의 처음부터 끝까지 따라가기.

바탕은 **Universal Design DNA**다(원본: https://claude.ai/artifact/LuwWSFPxRTpsb7DqRxL9xS, 스킬 `universal-design-intelligence`). 원칙·토큰 이름과 역할·상태 규칙·접근성 기준·품질 게이트는 그대로 따르고, 이 문서에는 **이 프로젝트가 다르게 정한 것만** 적는다. 로그인한 뒤의 화면은 모두 Utility 레이어다: 높은 정보 밀도, 일관된 부품, 빠른 피드백, 장식 모션 없음. 로그인 전 첫 화면 하나만 Brand 레이어다(아래 "첫 화면").

**Key Characteristics:**
- 잉크와 종이. 색은 뜻이 있을 때만: 계획(보라), 가격 방향(빨강·파랑), 상태(청록·호박·적색).
- 화면의 첫 줄은 "지금 내가 끼어들어야 하나"에 대한 답이다. 손익은 그다음이다.
- 숫자에는 출처를 붙인다(시뮬레이션·백테스트·모의투자·실전).

### Project DNA (디자인 시스템에서 바꾼 것)

| 항목 | 결정 | 이유 |
|---|---|---|
| accent | 보라 `#4b3bb0`(다크 `#b3a6ff`) | 기본값 코발트 블루는 하락 가격 색(파랑)과, 청록은 성공 상태색과 겹친다. 남는 색상대가 보라다. "아직 일어나지 않은 계획"이라는 뜻과 함께 쓴다 |
| 추가 토큰 | `up`·`up-solid`·`up-subtle`, `down`·`down-solid`·`down-subtle` | 국내 관례(상승 빨강, 하락 파랑). 상태색과 다른 토큰으로 둔다 |
| 서체 | Pretendard + IBM Plex Mono(기본 그대로) | 거래번호·종목코드는 mono `data` |
| 반경 | 기본 그대로(8·12·20) | 정밀한 데이터 제품 |
| 밀도 | 페이지 제목을 `heading-2`(34px, 좁은 화면 26px)로 한 단계 낮춤. 본문 `body-sm` 14/1.6. 표는 compact(40px) | 한 화면에 표와 계기가 함께 있는 관제 화면이라 44px 제목은 본문을 밀어낸다 |
| 경험 레이어 | 로그인 전 첫 화면만 Brand, 로그인한 뒤의 모든 주소는 Utility | 3D와 스크롤 연출은 첫 화면에만 둔다. 관제·설정 같은 화면에는 넣지 않는다 |

대비는 계산으로 확인했다(라이트 / 다크): accent 글자 8.2:1 / 8.5:1(surface 위), accent 위 글자 8.2:1 / 9.0:1, `up` 5.8:1 / 8.0:1, `down` 6.3:1 / 8.8:1, accent-subtle 위 잉크 15.9:1 / 13.3:1.

## Colors

잉크와 종이가 기본이고, 색은 다섯 가지 일만 한다.

### Primary
- **잉크** (`#121211`, 다크 `#edece8`): 본문·제목, 그리고 **주 행동 버튼의 채움**. 승인·저장·실행은 모두 잉크다.

### Secondary
- **계획 보라** (accent `#4b3bb0`): 링크, 포커스 링, 선택된 컨트롤, 그리고 **아직 일어나지 않은 계획**(승인 대기 카드의 옅은 바탕 `accent-subtle`, 장부의 "주문 계획"·"승인" 적요, 차트의 계획 가격선, 내 계좌 추이선).

### Tertiary
- **상승 빨강 / 하락 파랑** (`up` `#c2272b` / `down` `#1d58d0`): 가격·손익의 방향에만. 항상 ▲▼나 +− 부호와 함께 쓴다. 매수·매도 배지도 이 색이다.

### Neutral
- **종이** (canvas `#f5f4f0`): 페이지 바탕과 내비·상태 띠. 순백을 바탕으로 쓰지 않는다.
- **표면** (surface `#ffffff`): 패널과 입력. **가라앉은 표면** (`#ebeae5`): 계기 트랙, 선택된 항목, 스켈레톤.
- **경계** (border `#8f8d86`, 3:1): 입력·토글·표 머리. **구분선** (divider `#e2e0da`): 패널 외곽선과 행 구분.
- **상태**: 성공 `#08676f`, 주의 `#875200`, 위험 `#b3261e`. 옅은 `*-subtle` 바탕 위에는 잉크 글자를 쓰고, 항상 아이콘이나 단어가 함께 있다.

### Named Rules
**계획만 보라 규칙.** 보라는 "아직 일어나지 않은 것"과 링크·포커스에만 쓴다. 이미 체결된 줄은 잉크다.

**가격 색은 가격에만 규칙.** 빨강·파랑은 가격 방향 말고 다른 뜻으로 쓰지 않는다. 위험 상태(적색)는 반드시 아이콘과 단어를 달아 상승 빨강과 구별한다.

**버튼은 잉크 규칙.** 어떤 버튼도 accent로 칠하지 않는다. 승인 버튼도 잉크이고, 결과를 이름에 적는다("매수 승인 · 13주 · 약 285만 원").

**의견에는 색이 없다 규칙.** 위원 의견(긍정·부정)은 상태도 가격도 아니라서 중립 배지와 잉크 막대로 그린다. 방향은 단어·부호(+0.71 / −0.20)·막대가 뻗는 쪽이 전한다. 위험 빨강을 쓰면 바로 옆 '매수'(상승 빨강) 배지와 뜻이 섞인다(2026-11-17).

**링크는 보라 + 밑줄 규칙.** 문장 속 링크와 빈 상태의 다음 행동은 클래스 없이 쓰면 전역 규칙(`a:not([class])`)으로 보라 + 밑줄이 된다. 다른 화면으로 가는 단독 링크는 보라 글자 + → 화살표("판단 근거 보기 →", "장부 전체 보기 →"). 밑줄 글자는 링크에만 쓰고, 그 자리에서 펼치거나 더 불러오는 단추는 ghost 단추나 화살표 달린 펼침(`DisclosureIcon`)으로 그린다.

## Typography

**Display/Body Font:** Pretendard Variable (Apple SD Gothic Neo, 맑은 고딕 순으로 대체)
**Label/Mono Font:** IBM Plex Mono — 거래번호, 종목코드처럼 자리가 맞아야 하는 데이터에만

**Character:** 한 가족의 굵기 차이로 위계를 만든다. 숫자는 모두 고정폭(`tabular-nums`)이고 금액·수량 열은 오른쪽 정렬이다.

### Hierarchy
- **Page title** (700, 34px/1.2, 좁은 화면 26px): 화면마다 하나. 관제 화면에서는 판정 문장이 제목이다.
- **Section title** (600, 16px/1.5): 패널 머리.
- **Emphasis** (600, 18px 또는 26px): 수치 값(`Stat`), 종목 현재가.
- **Body** (400, 14px/1.6): 본문과 표. 긴 설명은 680px 안에서 줄을 바꾼다.
- **Label** (500, 13px): 표 머리, 필드 이름, 배지, 작은 버튼.
- **Caption** (400, 12px): 출처, 기준, 힌트. 이보다 작은 글자는 없다.

- **첫 화면 전용** (Brand 레이어): Display 700, 34~68px/1.1(화면 너비에 따라) · Heading 700, 28~46px/1.18 · Lead 400, 18px/1.6. 로그인한 뒤의 화면에서는 쓰지 않는다.

### Named Rules
**낱말 안에서 끊지 않기 규칙.** `word-break: keep-all`. 한글 낱말 중간에서 줄을 바꾸지 않는다.

## 첫 화면 (Brand 레이어, 2026-11-16)

로그인하지 않은 사람이 보는 한 장. 제품이 하는 일(종목을 세 번 걸러 주문 계획을 만든다)을 보여 주고 맨 아래에서 로그인한다. 코드는 `frontend/src/features/landing/`.

| 항목 | 결정 | 이유 |
|---|---|---|
| 3D 방식 | **실시간 3D**(WebGL2, three.js 0.169.0). 사전 렌더 영상이 아니다 | 스크롤 위치마다 장면 상태가 달라져야 하고, 테마 색을 토큰에서 읽어야 한다 |
| 무엇을 보이나 | 143종목 → 관문 셋(기법 조건, 위원회 심의, 리스크 점검) → 주문 계획 3건. 멈춘 종목은 관문 앞에 납작하게 남는다 | 장식이 아니라 엔진의 실제 순서다. 수는 2026-10-02 시뮬레이션 기록에서 왔고 화면에 출처를 적는다 |
| 형상 | 코드로 만든 형상(둥근 사각 기둥, 판, 선). 모델 파일(GLB) 없음 | 추상적인 도식이라 모델이 필요 없다 |
| 진행 | 스크롤 진행률 하나(0~1) → 감쇠 → 모든 상태가 그 값의 함수. 무대는 화면 3장 분량만 고정 | 글이 "38종목이 통과했습니다"라고 할 때 장면도 그 상태에 멈춰 있도록, 글이 보이는 구간에서는 천천히 간다(`funnel.ts`의 `TRAVEL_KEYS`, 테스트로 고정) |
| 재질·빛 | PBR 재질 + 환경광(RoomEnvironment) + 방향광 둘. 그림자 맵·후처리 없음. 바닥 반사는 뒤집은 기둥을 높이에 따라 옅게 그린 것(셰이더 한 줄 수정) | 한 프레임 드로우콜 6, 삼각형 약 5만 |
| 색 | 기둥 `ink-secondary`, 멈춘 것 `data-3`, 주문 계획 `accent`. 바탕은 투명 캔버스 뒤의 `canvas` 토큰 그대로, 안개도 같은 색 | accent는 여기서도 "계획"만 뜻한다 |
| 대체 화면 | 3D 묶음을 받는 동안: 같은 구도의 SVG. WebGL2 없음: 결과 전체가 보이는 SVG 정지 구도 + 단계 목록. 모션 줄이기·아주 낮은 화면(높이 560px 이하): 고정·스크롤 연출 없이 WebGL 정지 구도 한 장 + 단계 목록 | 어느 경우에도 같은 내용을 읽을 수 있다 |
| 묶음 | three.js는 첫 화면에서만 따로 내려받는다(약 517KB, gzip 약 132KB). 로그인한 화면의 묶음에는 들어가지 않는다 | |
| 등장 | 화면을 맨 위에서 처음 열 때 한 번: 기둥이 카메라 쪽 줄부터 바닥에서 올라온다(한 개 900ms, 시작 간격은 뒤로 갈수록 좁아져 전체 약 1.4초). 글은 제목 0ms·12px, 안내글 110ms·8px, 단추 190ms·6px(각 560ms). 관문·머리띠·바닥은 움직이지 않는다 | 첫 화면의 주인공은 장면과 제목이다. 단추는 보이는 순간부터 눌린다. 모션 줄이기에서는 전부 없다 |
| 주문 계획 이름표 | 마지막 장면의 기둥 셋에 종목 이름과 수량(장부 8734~8736번 그대로). 관문 이름표와 겹치면 관문 쪽이 물러난다 | 추상적인 기둥이 실제 기록이라는 것을 보인다 |
| 나머지 섹션 | 장부 표본(제품의 장부 표 부품에 시뮬레이션 장부 8734~8742번을 그대로) · 실제 관제 화면 캡처 · 안전 규칙 넷(반전 띠) · 백테스트 수치(불리한 것 그대로) · 로그인 | 꾸민 수치·후기·로고 없음. 섹션 등장 모션 없음. 장부 표본의 종목코드는 뺐다(로그인 전에는 종목 화면 링크를 만들지 않는다) |

첫 화면에서도 지키는 것: 주 행동 버튼은 잉크(`primary`), 블러·유리·그라데이션 장식 없음(장면 아래 가장자리를 바탕색으로 푸는 띠 하나만 있다), 다크는 `[data-theme="dark"]`.

## Layout

- 넓은 화면(1024px 이상): 왼쪽 240px 내비(종이 바탕, 오른쪽 구분선) + 위 48px 상태 띠 + 본문(최대 1440px, 좌우 24px). 좁은 화면: 내비가 아래 탭 5개(관제·발굴·자동매매·보유·더보기)로 바뀐다.
- 관제 화면은 1400px 이상에서만 두 열로 나눈다: 왼쪽(통장정리 → 자산 추이)과 오른쪽 352px(승인 → 감시 → 시장 국면)을 각각 세로로 쌓아, 한쪽이 길어도 다른 쪽에 빈자리가 생기지 않는다. 1400px보다 좁으면 오른쪽 열이 통장정리의 내용 칸을 140px 남짓으로 줄이므로 한 줄로 쌓고 승인 카드는 두 장씩 놓는다(2026-11-17).
- 상태 띠에서 가장 늦게 잘리는 것은 엔진 상태다. 자리가 모자라면 기준일 글자가 먼저 말줄임되고, 1024~1279px에서는 한도 이름을 "손실 한도"로 줄인다.
- 상태 띠는 항상 보인다: 거래 환경, 엔진 상태, 기준일(또는 장 운영), 시장 국면, 일 손실 한도, 승인 대기, 멈추기.
- 간격은 4px 배수만 쓴다. 패널 안 16px, 패널 사이 16px, 페이지 제목 아래 24px.
- 표는 좁은 화면에서 두 줄짜리 목록으로 바뀐다. 가로 스크롤은 열이 많은 표 안에서만 생기고 페이지 전체에는 생기지 않는다.
- 왼쪽 정렬이 기본이다. 빈 상태도 왼쪽 정렬이다.
- 확인하는 해상도: 1920·1440·1280·768·390·375, 라이트와 다크.

## Elevation & Depth

평평하다. 패널은 그림자 없이 구분선 외곽선으로 나눈다. 그림자는 떠 있는 표면에만 있다.

### Shadow Vocabulary
- **shadow-2**: 메뉴, 차트 값 풍선, 검색 결과, 토스트.
- **shadow-3**: 대화상자, 아래에서 올라오는 시트.

블러와 유리 효과는 쓰지 않는다. 대화상자 뒤는 블러 없는 `scrim`이다.

## Shapes

- 버튼·입력·토글 8px, 패널·안내·메뉴 12px, 대화상자 20px, 배지·계기 막대 999px, 체크박스 4px.
- 테두리는 1px 하나. 색 테두리, 이중 테두리, 왼쪽 색 띠는 없다.
- "여기까지 확인함" 절취선만 1px 점선이다(확인한 줄과 새 줄의 경계라는 뜻이 있다).

## Components

- **Button**: primary(잉크), secondary(옅은 채움), outline, ghost, danger. 높이 32·40·48. 누르면 scale 0.98, 비활성 불투명도 0.4, 처리 중에는 폭을 유지한 채 스피너.
- **primary를 두는 곳**: 승인 카드의 승인, 대화상자의 확정, 백테스트 실행. 상태 띠의 엔진 켜기·멈추기는 모든 화면에 붙어 있어 secondary다. 설정처럼 저장 단추가 여럿인 화면은 바꾼 값이 있는 묶음의 저장만 primary로 올라온다. 시뮬레이션 진행 단추는 승인 카드와 같은 화면에 있어 secondary다.
- **펼침(`<details>`)**: 앞에 → 화살표(`DisclosureIcon`)가 붙고 펼치면 아래로 돈다. 밑줄을 쓰지 않는다.
- **승인 카드**: `accent-subtle` 바탕. 승인 기한, 수량·금액, 주문 조건, 예상·손절 가격, 판단 요지, 결과형 승인 버튼과 거절. **결정한 카드는 사라지지 않고 제자리에 남는다**(다음 카드의 승인 버튼이 포인터 아래로 올라오지 않게). 승인·거절이 실패하면 카드 안에 이유를 남긴다(사라지는 알림으로만 알리지 않는다). 승인 대기 계획이 보이는 곳(관제, 자동매매, 종목 상세, 판단 상세)에서는 모두 같은 카드로 바로 결정한다.
- **통장정리 표**: 번호(mono, 판단 사슬이 있으면 점선 밑줄 버튼) · 날짜 · 적요 · 종목과 내용 · 수량 · 금액(매수 −, 매도 +) · 현금 잔액. 심의 전에 걸러진 후보는 접어 둔다.
- **판단 사슬 대화상자**: 거래번호를 누르면 같은 판단에서 나온 줄을 오래된 것부터 보여준다.
- **한도 계기**: 4px 트랙(오늘 손실 한도만 8px). 50% 이상은 주의, 80% 이상은 위험 배지를 함께 단다. 트랙은 `divider` 색이다(다크에서 `surface-sunken`은 바탕보다 어두워 트랙이 사라진다: 1.04:1 → 1.35:1).
- **Tabs**: 밑줄 탭(포트폴리오 보기 전환). **ToggleGroup**: 필터(장부 종류, 기법 고르기). **RadioRow**: 배타적 선택(판단 주체).
- **Notice**: 옅은 상태 바탕 + 톤 색 아이콘 + 잉크 글자.
- **Stat**: 위쪽 1px 잉크 룰 + 라벨 + 값 + 기준.
- **Toast**: 반전 표면, 오른쪽 아래(좁은 화면은 탭 위).
- **차트**: 주인공 하나만 `data-1`(보라), 비교 대상은 `data-2`(회색 점선). 일봉은 빨강·파랑 봉, 이동평균선은 20일 보라·50일 진회색·200일 회색.
- **차트의 숫자**: 축의 양 끝은 눈금 간격의 배수라서 모든 값이 눈금 사이에 놓인다. 눈금 글자는 반올림하지 않는다(`wonExact`, `stepDigits`: −2.5%를 −3%로 적지 않는다). 십자선 옆 값은 원 단위·소수 둘째 자리까지 그대로 적는다. 날짜 눈금은 달이 바뀌는 첫 거래일. 자산 추이에는 시작 금액 기준선을 긋는다. 일봉의 거래정지일(거래량 0, 값이 멈춘 날)은 회색 봉과 "거래정지" 글자로 구분한다.

## Do's and Don'ts

- Do: 숫자 옆에 무엇의 숫자인지(시뮬레이션·백테스트)와 기준일을 적는다.
- Do: 위험한 조작(정지한 엔진 켜기, 한도 완화, 실전 전환)은 인증 코드를 다시 받는다.
- Do: 한 화면에 승인 카드가 여럿이면 카드마다 승인 버튼이 primary다. 카드 하나가 결정 하나이기 때문이며, "primary는 화면에 하나" 규칙의 이 프로젝트 예외다.
- Don't: 총자산을 큰 숫자 타일로 화면 맨 위에 두지 않는다.
- Don't: 보라를 장식으로 쓰지 않는다. 버튼을 보라로 칠하지 않는다.
- Don't: 통장 무늬, 도트 서체 같은 통장 흉내를 넣지 않는다. 통장은 구조다.
- Don't: 축하 연출, 배지 수집, 순위표를 넣지 않는다.
- Don't: 3D와 스크롤 연출을 로그인한 뒤의 화면에 넣지 않는다. 첫 화면 한 장에만 둔다.
