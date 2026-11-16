# Project Audit: AlphaPilot 화면 (2026-11-16)

Universal Design DNA로 화면을 전면 개편하기 전에 현재 상태를 적어 둔 기록이다. 개편 전 화면 소스는 `backups/ui-before-udi/`에, 개편 전 화면 캡처는 `.impeccable/review/`에 있다.

## 구조와 스택

| 항목 | 내용 |
|---|---|
| 화면 | React 19 + Vite 8 + TypeScript 7 + Tailwind 4 (`frontend/`), SPA, `react-router-dom` 7 |
| 서버 상태 | `@tanstack/react-query` 5, 실시간 알림은 SSE(`/api/events`) |
| 부품 라이브러리 | Radix Dialog·Dropdown Menu(접근성 동작만 사용), lucide 아이콘, sonner 토스트, lightweight-charts 5(일봉 차트) |
| 서버 | FastAPI(`backend/`), 화면 빌드 결과물을 직접 서빙. 보안 헤더(CSP `script-src 'self'`) |
| 스타일 | `frontend/src/styles/index.css` 한 파일에 CSS 변수 토큰 + Tailwind `@theme inline` 매핑 |
| 3D·장식 모션 | 없음 |

## 화면(경험 레이어는 모두 Utility)

| 주소 | 화면 | 파일 |
|---|---|---|
| (로그인 전) | 로그인, 처음 등록(비밀번호 + 인증 앱) | `app/AuthGate.tsx` |
| `/` | 관제(통장정리) | `features/dashboard/*` |
| `/discover` | 종목 발굴 | `features/discover/DiscoverPage.tsx` |
| `/stocks/:code` | 종목 상세(일봉 차트) | `features/stock/*` |
| `/committee`, `/committee/:id` | AI 위원회, 판단 상세 | `features/committee/*` |
| `/auto` | 자동매매(승인, 자동화 단계, 시뮬레이션) | `features/auto/*` |
| `/portfolio` | 포트폴리오(보유·계획·체결·일지·장부) | `features/portfolio/PortfolioPage.tsx` |
| `/backtest` | 백테스트 | `features/backtest/BacktestPage.tsx` |
| `/settings` | 설정 | `features/settings/SettingsPage.tsx` |

## 반드시 지킬 것(기능 보존)

- API 계약(`/api/*` 경로, 요청·응답 모양, 오류 코드), 세션 쿠키와 CSRF 헤더, 재인증(step-up) 흐름.
- 라우팅 주소와 쿼리(`?tab=`, `?t=`, `?day=`, `?run=`).
- 승인 카드가 결정 뒤 제자리에 남는 동작, 정지 메뉴의 세 단계와 확인 문구, 판단 사슬 대화상자, "여기까지 확인".
- 프론트 단위 테스트 21개(`format`, `chartmath`, `labels`)와 백엔드 테스트.

## Universal Design DNA와 다른 점

| # | 현재 | 기준 | 영향 |
|---|---|---|---|
| 1 | 토큰 이름이 자체 이름(`paper`, `rule`, `rail`, `plan`, `ok`, `warn`, `action` 등) | `canvas`·`surface*`·`ink*`·`border`·`divider`·`primary`·`accent`·상태색 | 모든 화면의 클래스 이름 |
| 2 | 주 버튼을 청록으로, 승인 버튼을 보라로 채움 | 주 행동은 잉크(`primary`), accent로 채운 버튼 금지 | 버튼 전체 |
| 3 | 청록 레일이 화면의 16%를 차지 | accent는 면적 5% 이하, 바탕은 잉크와 종이 | 앱 틀 |
| 4 | 보라("계획")와 청록(레일·주 버튼) 두 가지 브랜드 색 | accent 하나 | 색 체계 |
| 5 | 다크 모드가 `prefers-color-scheme` 미디어 쿼리 + `data-theme` 두 갈래 | `[data-theme="dark"]` 한 곳 | 토큰 파일, `theme.ts` |
| 6 | 본문 15px/1.5, 제목 22px | Utility 본문 `body-sm` 14/1.6, 타입 스케일 고정 | 전역 타이포 |
| 7 | 반경 4·6·10px | 역할별: 버튼·입력 8, 카드 12, 대화상자 20, 배지 full | 부품 전체 |
| 8 | 알약 모양으로 색을 채운 탭(`Segmented`) | 밑줄 탭, 필터는 토글 버튼 | 포트폴리오, 장부, 종목 발굴, 판단 주체 |
| 9 | 통장정리 머리띠의 보안 인쇄 무늬, 거래번호 도트 서체(DotGothic16) | 장식은 없어도 완성도가 유지되면 뺀다, mono는 IBM Plex Mono | 통장정리 표 |
| 10 | 안내 띠가 색 테두리 + 색 글자 | `*-subtle` 바탕 + 톤 색 아이콘 + 잉크 글자 | 안내·오류 표시 |
| 11 | 비활성 불투명도 0.5, 버튼 높이 36·44 | 0.4, 32·40·48 | 버튼·입력 |
| 12 | 토스트가 밝은 표면 | 반전 표면(`surface-inverse`) | 알림 |
| 13 | 확인한 해상도는 1440·375 | 1920·1440·1280·768·390(+375), 라이트·다크 | 검증 |

## 이미 맞는 것

왼쪽 정렬 기본, 블러·그라데이션·glow 없음, 카드 안 카드 없음, 상태색에 아이콘·단어 병기, 등락에 ▲▼ 부호 병기, 숫자 출처 표기(시뮬레이션·백테스트), 결과를 말하는 버튼 문구, `word-break: keep-all`, 고정폭 숫자, 포커스 링 2px/offset 2px, 누름 scale 0.98, reduced-motion 처리, 로딩·빈 상태·오류 상태.

## 재사용할 것

- 구조: 화면 구성과 정보 순서(개입 필요 여부 → 한 일 → 이유 → 승인·정지), 통장정리 표와 절취선, 판단 사슬, 승인 카드의 결과형 버튼.
- 코드: `lib/*`(API, 포맷, 라벨, 차트 계산, 재인증), 차트 부품의 계산부, 모든 화면의 데이터 흐름.

## 방향

1. `tokens.css`를 디자인 시스템의 것으로 교체하고 프로젝트가 정하는 값(accent 계열, 가격 색, 밀도)만 `DESIGN.md`에 적는다.
2. 공용 부품(`components/ui.tsx`)을 디자인 시스템의 상태·치수 규칙으로 다시 만든다.
3. 앱 틀을 잉크와 종이 바탕으로 바꾼다(색 레일 제거).
4. 화면별로 토큰 이름과 부품을 옮기고, 탭·필터·배지·안내를 기준에 맞춘다.
5. 품질 게이트(6개 해상도, 두 테마, 키보드, 테스트)를 실제로 돌린다.

## 리스크

- 화면 전체의 클래스 이름이 바뀐다. 타입 검사와 빌드, 전 화면 캡처로 회귀를 확인한다.
- 사용자가 고른 "통장정리" 방향의 청록 표지와 도트 인자체가 사라진다. 구조(한 줄씩 적는 장부, 절취선, 거래번호로 따라가기)는 남는다.
- 가격 색(빨강·파랑)과 위험 상태색(적색)이 가깝다. 위험은 항상 아이콘·단어와, 가격은 항상 ▲▼ 부호와 함께 쓴다.
