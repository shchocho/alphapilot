# Task List: AlphaPilot

검증 명령: 백엔드 `cd backend && uv run pytest -q`, 린트 `uv run ruff check .`, 프론트 `cd frontend && npm run typecheck && npm run test && npm run build`.

## Phase 1: 기반
- [x] T1 프로젝트 골격 — `backend/pyproject.toml`, 패키지 구조, 설정(`config.py`). 수용: `uv sync` 성공, `pytest` 0건 통과. 파일: pyproject, app/__init__, config
- [x] T2 시장 규칙 — 호가단위, 반올림 방향, 가격제한폭, 비용·세금, 거래일 달력. 수용: 구간 경계·상하한가·수수료 테스트 통과. 파일: core/market_rules.py, core/clock.py, tests/test_market_rules.py
- [x] T3 데이터 — 공급자 인터페이스, 샘플(합성)·네이버 공급자, SQLite 캐시, 유니버스 CSV. 수용: 샘플 공급자 결정론 테스트, 네이버 XML 파서 테스트(고정 응답), 유니버스 코드 검증 스크립트 실행. 파일: data/*, tests/test_data.py

### Checkpoint 1: `pytest` 통과, 실제 일봉 100종목 캐시 적재 확인

## Phase 2: 판단 재료
- [x] T4 지표·특성 — SMA/EMA/ATR/RSI/돈치안/52주/거래량비/RS 백분위. 수용: 손계산 값과 일치, 미래 참조 없음(잘라낸 데이터와 결과 동일) 테스트. 파일: indicators/*, tests/test_indicators.py
- [x] T5 기법 8종 — 체크리스트·점수·진입 계획 반환. 수용: 기법별 통과·실패 고정 데이터 테스트. 파일: techniques/*, tests/test_techniques.py
- [x] T6 시장 국면 — 분산일, FTD, 시장 폭, 결합 노출 상한. 수용: 인위 지수 시나리오 테스트. 파일: regime/*, tests/test_regime.py

### Checkpoint 2: 실제 데이터로 스크리너 결과 출력 확인

## Phase 3: 안전장치와 실행
- [x] T7 리스크 — 사이징, 축소 전용 게이트, 회로차단기, 보호 청산 규칙. 수용: 표 기반 사례 전부 통과, `risk` 분기 커버리지 100%. 파일: risk/*, tests/test_risk.py
- [x] T8 원장 — 해시 연결 추가·검증·내보내기. 수용: 변조 감지 테스트. 파일: journal/ledger.py, store/*, tests/test_ledger.py
- [x] T9 가상 체결 — 시가 체결, 손절·익절·돌파 재현, 비용. 수용: 갭·동시 도달 등 보수적 체결 테스트. 파일: engine/sim.py(코어 일부), tests/test_sim_fills.py
- [x] T10 키움 어댑터 — 파서, 유량 버킷, 토큰, REST 클라이언트, 브로커. 수용: 문서 예시 기반 계약 테스트(respx), 주문 재시도 없음 테스트. 파일: broker/kiwoom/*, tests/test_kiwoom_*.py

### Checkpoint 3: `pytest` 통과

## Phase 4: 위원회
- [x] T11 좌석·규칙 위원회 — Signal 계약(기권 포함), 혼합. 수용: 기권·가중·거부권 테스트. 파일: committee/seats.py, rules_committee.py
- [x] T12 AI 심의 — 프롬프트, 스키마, Anthropic 클라이언트, 예산·비용 기록, 실패 = HOLD. 수용: 가짜 클라이언트로 정상·거절·시간 초과·스키마 위반·예산 초과 테스트. 파일: committee/ai.py, deliberation.py, tests/test_committee.py

## Phase 5: 엔진·백테스트
- [x] T13 엔진 코어 — `advance(day)` 순수 로직. 수용: 샘플 데이터 3개월 재생 통합 테스트(주문 계획·체결·기록), AI 실패 시 신규 매수 0건, 손절 결정론 테스트
- [x] T14 서비스·스케줄러 — DB 영속, 자동화 단계, 승인·만료, 3단계 정지, 데드맨. 수용: 승인 흐름·정지·재시작 테스트
- [x] T15 백테스트 — 러너·지표. 수용: 100종목 × 3년 60초 이내, 지표 손계산 일치

### Checkpoint 4: 실제 데이터 시뮬레이션 30일 재생, 백테스트 시간 측정

## Phase 6: API
- [x] T16 인증·보안 — 설정·로그인(TOTP)·세션·CSRF·속도 제한·재인증·보안 헤더. 수용: TestClient 인증 흐름·401·CSRF 거부 테스트
- [x] T17 라우터·SSE — 상태, 관제, 원장, 스크리너, 종목, 위원회, 승인, 포트폴리오, 엔진 제어, 설정, 백테스트. 수용: 라우터별 스모크 테스트, 실전 전환 차단 테스트

## Phase 7: 화면
- [x] T18 셸·토큰 — 레이아웃, 상태 바, 내비, 테마, 포맷 유틸, API 클라이언트, 로그인·설정 흐름
- [x] T19 관제(통장정리)
- [x] T20 종목 발굴 + 종목 상세(차트·판단 패널)
- [x] T21 AI 위원회 + 자동매매(승인함·설정 마법사)
- [x] T22 포트폴리오 + 백테스트 + 설정
  - 화면 공통 수용: 375px·1440px, 밝은·어두운 테마, 키보드 조작, 대비 4.5:1, 빈·로딩·오류 상태

## Phase 8: 검증·배포
- [ ] T23 브라우저 검증·디자인 리뷰(critique, 접근성, 문구), 감지기 실행 — 브라우저 검증·감지기, 독립 디자인 리뷰·접근성 실측·문구 정리와 그 지적 반영은 끝남(2026-11-17, FINAL_IMPLEMENTATION_REPORT.md "로그인한 뒤 화면 UI 개선"). axe·Lighthouse, 스크린리더는 남음
- [ ] T24 Docker·Caddy·백업·배포 안내서, 키움 연동 안내서, README — 파일은 모두 작성. Docker 빌드를 실제로 돌려 보는 일이 남음

## Phase 9: 디자인 시스템 적용 (2026-11-16)
- [x] T25 Universal Design DNA로 화면 전면 개편 — 토큰 교체, 공용 부품·앱 틀·화면 9개. 기록: PROJECT_AUDIT.md, DESIGN.md, FINAL_IMPLEMENTATION_REPORT.md
- [x] T26 로그인 전 첫 화면(Brand 레이어, 실시간 3D) — `frontend/src/features/landing/`. 로그아웃 뒤 화면이 남던 버그 수정 포함

## 남은 큰 일
- [ ] 키움 모의투자 서버에서 미확인 17항목 검증 → 주문 실행기 → 화면의 환경 전환 열기
- [ ] 실제 Claude API로 AI 위원회 한 번 돌려 확인
- [ ] SPEC.md를 구현 내용에 맞게 갱신
