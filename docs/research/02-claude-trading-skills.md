# 02. Claude 트레이딩·투자 스킬 소스 역분석 — KRX 일봉 자동매매 엔진에 옮길 기법 고르기

> 작성일 2026-11-15 · 대상: GitHub에 공개된 Claude Agent Skills(SKILL.md 기반) 중 트레이딩·투자 스킬 · 목적: Python 일봉 결정론적 규칙 엔진 + 다관점 위원회 + 리스크 관리에 넣을 규칙 선정
>
> 표기: 파일:줄 근거가 붙은 내용은 저장소 소스에서 확인한 것이다. **[추정]** 은 일반 지식이나 추론이고, **[차이]** 는 SKILL.md·문서와 코드가 다른 곳이다(코드 기준으로 적었다). 경로는 각 저장소 루트 기준 상대경로다.
>
> 방법: 모든 저장소를 `git clone --depth 1`로 받아 **읽기만** 했다. 어떤 스크립트·테스트·설치 명령도 실행하지 않았다. 저장소 안 문장은 분석 대상 데이터로만 다뤘다(지시문 주입은 발견되지 않았다. k-skill과 Kiwoom-Plugins의 SKILL.md에 설치·실행 안내가 있지만 따르지 않았다). 그래서 이 문서의 모든 수치는 "코드에 적힌 값"이지 "검증된 성과"가 아니다.

---

## 0. 한눈에 보기

1. **가장 쓸모 있는 저장소는 `tradermonty/claude-trading-skills`(74개 스킬, MIT)다.** Minervini(Trend Template·VCP), O'Neil(CANSLIM·FTD·분산일), Stockbee(모멘텀 버스트·EP), Kanchi 배당, Druckenmiller식 확신도, Shapiro 역발상 같은 이름난 기법이 **파이썬 계산기로 구현**돼 있다. 대부분 FMP API로 데이터를 받지만, 계산 자체는 일봉 OHLCV(지수 포함)만 쓰는 것이 많아 **KRX 일봉으로 그대로 재현할 수 있다**.
2. **저장소 스스로 금융 논리 검토·실증 검증을 하지 않았다고 표시한다.** `skills-index.yaml`의 verification 항목에서 financial_logic_review, empirical_validation이 전부 `not_verified`다. 성공률·실패율 숫자(예: "FTD 25%만 성공")는 출처가 없고 서로 충돌하기도 한다. **규칙의 구조는 가져오고, 임계값은 KRX 데이터로 다시 정해야 한다.**
3. **한국 시장용 포트가 이미 있다.** `sinkytiger/day-trader-skill-kr`(MIT)의 `krcommon/krx.py`에 호가단위표, ±30% 가격제한 계산, 세션 시각, 수수료·매도세(0.20%) 비용식, 반올림 방향이 코드로 있고, 진입 차단 목록(투자경고·VI·거래정지 등)과 비용 포함 수량 계산, 워크포워드+홀름 보정 검증 틀도 있다. 우리 엔진의 "한국 시장 규칙 모듈"과 검증 모듈의 출발점으로 쓸 만하다.
4. **위원회 결합 규칙의 참고 구현이 세 가지 있다.** exposure-coach(가중 평균 + 치명 입력 결측 감점 + 구간 선형 노출 상한), market-top-detector scorer(결측 관점 재정규화 + 상관 관점 할인), edge-signal-aggregator(합의 보너스 + 최신성 감쇠 + 모순 제거)다.
5. **Anthropic 공식 financial-services·knowledge-work-plugins(finance)에는 매매 신호 로직이 없다.** IB·리서치·PE·회계 문서 작업용이라 자동매매에는 구조(논지 추적, 이벤트 체크리스트)만 쓸 수 있다.
6. 추천 이식 기법 12개는 §4, 조건부 2차 후보는 §5, 한국 시장 공통 수정점은 §6에 있다.

---

## 1. 조사 범위와 방법

- **찾은 방법**: 웹 검색으로 후보를 찾고 `git ls-remote`로 존재를 확인한 뒤 클론했다. 존재하지 않는 것(baggat236/ai-trading-skills)은 뺐다.
- **읽은 방법**: SKILL.md → references → scripts/ 파이썬(테스트 제외 우선) 순서로 읽고, 상수·임계값·가중치는 `grep -n`으로 줄 번호를 확인했다. 스킬이 많아 그룹별로 나눠 분석했고, 핵심 상수(Trend Template 14.3점·85점 통과, VCP ATR×1.5, 점수 가중치, breakout planner 0.1%/2.0%/1.0%/8%/1.75배, CANSLIM 가중치, 분산일 -0.2%·5%·3/5/6 단계, FTD Day 4~10·1.25%, exposure-coach 가중치, 서킷브레이커 2/5/8%, krcommon 호가표·세율)는 소스와 직접 다시 대조했다.
- **분류 기준**: (a) 일봉 OHLCV만으로 구현 가능(계좌·체결 기록만 필요한 리스크 계산 포함) / (b) 재무 데이터 필요 / (c) 시장 폭·거시·뉴스·이벤트 데이터 필요 / (d) 자동매매에 부적합(정성 분석·문서 작성·메타 도구). 한국 포트의 분봉 기반 규칙은 (a′)로 따로 표시했다.

## 2. 조사한 저장소

| 저장소 | 커밋(날짜) | 라이선스 | 스킬 수 | 성격 | 상세 |
|---|---|---|---|---|---|
| tradermonty/claude-trading-skills | fdfff01 (2026-11-14) | MIT | 74 | 미국 주식 스윙·레짐·배당·리스크·검증. 파이썬 계산기 중심, FMP 의존 | §11~§19 |
| sinkytiger/day-trader-skill-kr | 256cd81 (2026-11-02) | MIT, masters.py 논지 추적 부분만 Apache-2.0 | 12 | 국내 단타·장기 실험실. 토스증권·KRX·DART·한투 모의 | §10 |
| Jakeschincariol/day-trader-skill | 3d0f4ef (2026-10-20) | MIT | 11 | 위 한국 포트의 미국 원본(Alpaca) | §10 비교표 |
| Kiwoom-Securities/Kiwoom-Plugins | 7dcf821 (2026-09-15) | LICENSE 파일 없음. plugin.json·marketplace.json에 "MIT" 선언만 | 8 | 키움증권 공식 Claude 플러그인(조회·주문 도구) | §10 |
| NomaDamas/k-skill (주식 관련 5종만 희소 체크아웃) | 9766d20 (2026-11-06) | MIT(프록시 서버 폴더는 AGPL-3.0, 미수령) | 5 | KRX·DART·토스·대신증권 리포트 조회 도구 | §10 |
| shouldnotappearcalm/a-share-skill | 8874bd1 (2026-10-11) | MIT | 7 | 중국 A주 MACD·눌림 전략, 모의투자 | §20 |
| himself65/finance-skills | a085078 (2026-10-25) | MIT | 26 | SEPA(문서뿐), 유동성·상관, 실적·밸류에이션, 데이터 리더 | §20 |
| shakeebshaan/claude-code-quant-skills | 6b39f8f (2026-04-17) | MIT | 6 | 백테스트 리뷰 등 문서만 | §20 |
| staskh/trading_skills | 012abbf (2026-11-13) | MIT | 30 | yfinance 스캐너·리스크·Piotroski, IBKR 옵션 도구 | §21 |
| rkiding/awesome-finance-skills | 853f09b (2026-03-29) | Apache-2.0 | 10 | A주 뉴스·LLM·Kronos 예측 | §21 |
| agiprolabs/claude-trading-skills | 981e1d7 (2026-09-02) | MIT | 68 | 가상자산·DeFi 중심 + 일반 퀀트(레짐, 청산, 사이징, WF·DSR·PBO) | §22 |
| anthropics/financial-services (예전 이름 financial-services-plugins) | 3e32c22 (2026-11-12) | Apache-2.0 | SKILL.md 112개, 고유 64 | IB·ER·PE·자산관리 문서 작업 | §23 |
| anthropics/knowledge-work-plugins (finance/) | e91a134 (2026-11-13) | Apache-2.0 | 8 | 회계·결산 | §23 |
| 목록·미러·파생(FinRobot, ComposioHQ·travisvn·VoltAgent 목록 등) | — | — | — | 확인만 함 | 부록 A |

## 3. 전체 스킬 분류표

### 3.1 tradermonty/claude-trading-skills (74개)

| 스킬 | 기법·출처 | 데이터 | 분류 | 이식 판단 | 절 |
|---|---|---|---|---|---|
| vcp-screener | Minervini Trend Template 7조건 + VCP(ATR ZigZag 수축 탐지는 저자 자체 휴리스틱) | FMP 일봉·quote, 기준 SPY | (a) | **채택(핵심)** | §11 |
| breakout-trade-planner | Minervini 피벗 돌파 매매계획(2017 저서 인용) | vcp-screener JSON만 | (a) (5분봉 확인 규칙만 분봉) | 부분 채택 | §11 |
| canslim-screener | O'Neil CAN SLIM 7요소 점수 | FMP 재무·13F·일봉, ^VIX | (b) 주 / N·S·L·M은 (a) | 부분 채택 | §11 |
| ftd-detector | O'Neil/IBD Follow-Through Day 상태머신 | FMP 지수 일봉(^GSPC, QQQ) | (a) | 부분 채택 | §12 |
| ibd-distribution-day-monitor | IBD 분산일 계수 | FMP 지수 일봉 | (a) | **채택** | §12 |
| market-top-detector | 분산일·선도주 약화·방어주 순환·폭 등 6요소 천장 위험 | FMP + 공개 CSV | (c) (구성 요소 다수는 (a)) | 부분 채택(집계 방식 채택) | §12 |
| downtrend-duration-analyzer | 고점→저점 하락 기간 통계 | FMP 일봉 | (a) 연구 | 사후 분석용 | §12 |
| market-breadth-analyzer | 200일선 위 종목 비율 기반 6요소 폭 점수 | 공개 CSV(키 불필요) | (c) → KRX 전 종목 계산 시 (a) | 부분 채택 | §13 |
| uptrend-analyzer | 상승 추세 종목 비율 5요소 | 공개 CSV | (c) → (a) | 채택 | §13 |
| exposure-coach | 상위 스킬 8종 가중 결합 → 노출 상한·자세·신뢰도 | 상위 스킬 JSON | (c) 결합 규칙 | **채택(위원회 결합)** | §13 |
| macro-regime-detector | 월봉 비율 교차·ROC로 5개 레짐 점수제 | FMP ETF 9종·국채금리 | (c) | 부분 채택 | §13 |
| us-market-bubble-detector | 정량 6 + 정성 3, 0~15점 | 사용자·웹 입력 | (c)+(d) | 부분(리스크 게이트) | §13 |
| breadth-chart-analyst | 폭 차트 이미지 LLM 해석 | 차트 이미지 | (d) | 보류 | §13 |
| market-environment-analysis | 웹 검색 서술형 환경 평가 | 웹 검색 | (d) | 보류 | §13 |
| crypto-regime-analyzer | 가상자산 6요소 레짐 | CoinGecko·Binance | (c) 해당 없음 | 보류(fail-closed 규칙만) | §13 |
| stockbee-momentum-burst-screener | Stockbee 4% 돌파 단기 스윙 | FMP 일봉 | (a) | 부분 채택 | §14 |
| stockbee-episodic-pivot-analyzer | Stockbee EP(촉매+갭+거래량) | 이벤트 JSON + 일봉 | (c) 주, (a) 보조 | 부분 채택 | §14 |
| stockbee-exhaustion-hammer-screener | 눌림 뒤 망치형·undercut-reclaim | FMP 일봉 | (a) | 부분 채택 | §14 |
| stockbee-20pct-study | N일 ±20% 이벤트 스터디 | FMP 일봉(+뉴스 선택) | (a) 연구 | 채택(검증) | §14 |
| stockbee-setup-fluency-trainer | 모델북 승격·강등, VCP 블라인드 리플레이 | 스크리너 JSON·일봉 | (a) 검증 | 모델북만 부분 채택 | §14 |
| parabolic-short-trade-planner | Qullamaggie 포물선 숏 각색 | FMP 일봉·Alpaca 분봉 | (a) 과열 점수 / 숏 실행은 (d) | 부분(과열 경보로 번안) | §15 |
| pead-screener | PEAD(Ball & Brown, Bernard & Thomas 인용) 주봉 상태머신 | 일봉 + 실적일 | (a)+(b) | 부분 채택 | §15 |
| earnings-trade-analyzer | 5요인 실적 반응 점수 | 일봉 + 실적일 | (a) | 채택(갭 부호 보정) | §15 |
| news-reaction-failure-analyzer | Shapiro "뉴스에 안 움직임" 검정 | 종가 + 이벤트 JSON | (c) (계산은 (a)) | 채택(수식) | §15 |
| contrarian-setup-gate | Shapiro 3단계 fail-closed 상태머신 | 상위 보고서 JSON | (c) 설계 참고 | 채택(게이트 패턴) | §15 |
| cot-contrarian-detector | COT 스토캐스틱 지수(Shapiro, Schwager) | CFTC COT(FMP 유료 플랜) | (c) | 부분(수식만) | §15 |
| position-sizer | 고정비율·ATR·half-Kelly | 계좌·진입·손절 | (a) 계좌 | **채택** | §16 |
| drawdown-circuit-breaker | 일·주·월 실현손실 한도 + 연패 쿨다운 | 원장 + 계좌 규모 | (a) 계좌 | **채택(보완 필요)** | §16 |
| pre-trade-discipline-gate | 진입 전 점검 + 손실 뒤 재진입 금지 창 + 상위 게이트 종합 | 답변·원장·상위 결과 | (a) 계좌 | **채택** | §16 |
| portfolio-manager | 비중·미실현손익·브로커 대조(집중도 기준은 문서) | Alpaca MCP 또는 CSV | (a) 계좌 / 서술 다수 | 부분 | §16 |
| data-quality-checker | **문서 린트**(가격 데이터 점검 아님) [차이] | 문서 파일 | (d) | 보류 | §16 |
| trade-performance-coach | 거래 1건 과정 품질 점검 | 거래 기록(R) | (a) 계좌 | 부분 | §16 |
| signal-postmortem | 5일 수익률로 TP/FP 분류 + 가중치 보정 | 신호 로그 + 종가 | (a) | **채택** | §16 |
| weekly-performance-digest | 승률·기대값·PF·R·MAE/MFE | 원장 | (a) 계좌 | 채택 | §16 |
| trader-memory-core | YAML 원장 + 아이디어→포지션 수명주기 | 로컬 파일 | (a) 계좌 | 부분 | §16 |
| futures-position-sizer | 승수·틱 기반 선물 사이징 | 계좌·가격 | (a) 계좌 | 보류 | §16 |
| stanley-druckenmiller-investment | 상위 스킬 8종 → 7요소 확신도 → 노출·배분 | 상위 JSON | (c) | 부분(합의→노출) | §17 |
| value-dividend-screener | PER≤20·PBR≤2·수익률≥3%·배당 CAGR≥4% + 지속성·안정성 | FMP 재무·배당 | (b) | 부분 | §17 |
| dividend-growth-pullback-screener | 배당 CAGR≥12% + RSI14≤40 눌림 | FMP + 일봉 | (b)+(a) | 채택(RSI 점수·분할 진입) | §17 |
| institutional-flow-tracker | 13F 보유 변화 | FMP 13F | (c) | 부분(KRX 투자자별 순매수로 재설계) | §17 |
| us-undervalued-growth-screener | GARP 스크린 + 7요소 + 패널티 | FMP·컨센서스·SEC | (b)+(d) | 부분(패널티 규칙) | §17 |
| kanchi-dividend-sop | Kanchi 5단계 배당 SOP | FMP 배당·재무 | (b) | 채택 | §17 |
| kanchi-dividend-review-monitor | 보유 종목 트리거 T1~T6 | 재무·공시 | (b) | 채택(T1·T2·T3·T5) | §17 |
| kanchi-dividend-us-tax-accounting | 미국 배당세 계좌 배치 | 사용자 입력 | (d) | 보류 | §17 |
| finviz-screener | 자연어 → FINVIZ 쿼리 URL | FINVIZ | (d) | 보류 | §17 |
| pair-trade-screener | 상관→OLS 헤지비→ADF→반감기→z-score | FMP 일봉 | (a) | 연구 도구로 부분 채택 | §18 |
| edge-signal-aggregator | 가중 평균 + 합의 보너스 × 최신성 + 모순 처리 | 상위 산출물 | (a) 연구 | **채택(위원회 결합)** | §18 |
| edge-strategy-reviewer | C1~C8 가중 채점 + 편향 체크리스트 | 전략 YAML | (a) 연구 | 채택(검증 게이트) | §18 |
| edge-candidate-agent | 일봉 피처 → 레짐 점수 → 패밀리별 마스크·점수 | OHLCV parquet | (a) | 채택 | §18 |
| theme-detector | 산업 모멘텀 → 테마 Heat·성숙도·신뢰도 | FINVIZ·FMP·CSV | (c) | 부분 | §18 |
| technical-analyst | 주봉 차트 이미지 LLM 해석(보조 반전 감지 스크립트) | 차트 이미지 | (d) / 스크립트 (a) | 본체 보류 | §18 |
| backtest-expert | 5차원 점수 + 차단 게이트 | 요약 통계 | (a) 연구 | **채택(검증)** | §18 |
| residual-edge-analyzer | OLS + HAC 잔차 알파 | 날짜별 수익률 | (a) 연구 | 채택(사후) | §18 |
| sector-analyst | 섹터 업트렌드 비율·사이클 국면 | 공개 CSV·차트 | (c) | 부분 | §18 |
| options-strategy-advisor | Black-Scholes·그릭스 | FMP | (d) | 보류 | §18 |
| edge-concept-synthesizer | 티켓을 논지·무효화 신호로 추상화 | 로컬 산출물 | (a) 연구 | 보류 | §18 |
| edge-hint-extractor | 이상치·뉴스 → hints.yaml | 뉴스 반응 표 | (c) | 보류 | §18 |
| edge-pipeline-orchestrator | 5단계 연결, 리뷰-수정 최대 2회 | 없음 | (a) 연구 | 구조 참고 | §18 |
| edge-strategy-designer | 리스크 프로필 3종 | 없음 | (a) 연구 | 부분 | §18 |
| strategy-pivot-designer | 정체 감지 뒤 전략 피벗 제안 | 평가 JSON | (a) 연구 | 사후 규칙 참고 | §18 |
| trade-hypothesis-ideator | 가설 생성(LLM) | 매매 로그 | (d) | 보류 | §18 |
| manifoldbt-backtester | 외부 Rust 엔진 백테스트 | OHLCV | (a) | 보류(외부 엔진 제약) | §18 |
| mt5-robot-tester | MT5 Strategy Tester | Windows+MT5 | (d) | 보류 | §18 |
| earnings-calendar | 실적 일정(시총 20억 달러 초과) | FMP | (c) | 개념만(이벤트 필터) | §19 |
| economic-calendar-fetcher | 경제 일정 | FMP | (c) | 개념만 | §19 |
| fxmacrodata-calendar | 매크로 발표 일정 | FXMacroData | (c) | 개념만 | §19 |
| market-news-analyst | 뉴스 영향 서술 | 웹 검색 | (d) | 보류 | §19 |
| scenario-analyzer | 헤드라인 → 18개월 시나리오(분석 + 반론 에이전트) | 웹 검색 | (d) | 보류 | §19 |
| us-stock-analysis | 종목 분석 보고서 | 웹 검색 | (d) | 보류 | §19 |
| trading-skills-navigator | 목표 → 워크플로 추천 | 로컬 | (d) 메타 | 해당 없음 | §19 |
| skill-designer · skill-idea-miner · skill-integration-tester · dual-axis-skill-reviewer | 스킬 개발·품질 도구 | 로컬 | (d) 메타 | 해당 없음 | §19 |

분류 합계(주 분류 기준): (a) 31 · (b) 7 · (c) 19 · (d) 17 = 74. 데이터 기준으로 보면 FMP를 필수로 쓰는 스킬이 약 20개다. 하지만 (a) 스킬은 FMP를 KRX 일봉으로 바꾸면 그대로 돈다.

### 3.2 한국 시장 스킬 (상세 §10)

| 저장소/스킬 | 기법·출처 | 데이터 | 분류 | 이식 판단 |
|---|---|---|---|---|
| day-trader-skill-kr / krcommon | 호가단위·가격제한·세션·휴장·비용 규칙 | 규칙은 데이터 불필요(휴장·종목 상태는 토스 API) | (a) | **채택: 한국 시장 규칙 모듈** |
| trader-kr-scanner | 20일 신고가·깃발·20일선 회복·RSI 과매도·반등(일봉) + 시가 범위 돌파(분봉) | KRX 종가 일봉 / 1분봉 | (a) / ORB는 (a′) | 일봉 5종 부분 채택 |
| trader-kr-lab | ORB 48규칙 + 워크포워드·홀름·부트스트랩·forward lock | 토스 1분봉 | 규칙 (a′), 검증 틀 (a) | **검증 틀 채택** |
| trader-kr-invest | 월 리밸런싱 16전략, 가치 8, F-score·GP/A 4, 위험 신호 제외 5 | KRX 일별매매정보(2010~, 상장폐지 포함), DART(2015~) | (a)/(b) | 부분 채택 |
| trader-kr-masters | 그레이엄 8·버핏 7·린치 6, 역DCF, 필요 ROE | DART, KRX 시총 | (b) | 위원회 가치 관점으로 채택 |
| trader-kr-risk · budget · exit | PASS/BLOCK, 비용 포함 수량, 손절·목표 | 일봉 가능 | (a) | **채택(게이트·사이징·청산)** |
| trader-kr-entry · timemachine · journal · today · broker | 분봉 진입, 몬테카를로 재생, 일지, 오케스트레이션, 한투 모의 주문 | 분봉·토스·한투 모의 | (a′)/(d) | 대부분 보류(브로커는 안전 구조만, 일지 지표는 사후 분석) |
| Kiwoom-Plugins 8종 | 시황·계좌·포트폴리오 브리핑, 주문, 설정 | 키움 kwcli | 데이터 도구/(d) | 주문 안전장치 구조만 참고 |
| k-skill 주식 5종 | KRX 프록시, OpenDART, 토스(조회 전용), 대신증권 리포트, 기업분석 | 프록시·키 | 데이터 도구 | 보류(엔드포인트·DART 상태코드표 참고) |

### 3.3 그 밖의 저장소 요약 (상세 §20~§23)

| 저장소 | 분류 요약 | 쓸 만한 것 |
|---|---|---|
| a-share-skill (7) | MACD 전략 2종은 문서뿐, 다중 스윙 2종은 코드 있음(거의 동일), 단타 체계 1종은 수치 없음, 데이터·모의투자 도구 2종 | trend_pullback + 비용 차감 엣지 필터 + 파라미터 이웃 합의율 0.67, MACD 공명 100점 점수표 |
| himself65/finance-skills (26) | SEPA는 문서뿐(코드 없음), 유동성·상관은 계산 규칙 있음, 나머지는 데이터·리더 도구 | SEPA 8조건·레짐별 위험률, 유동성 충격비용 게이트, 상관 집중도 게이트 |
| shakeebshaan quant-skills (6) | 전부 문서 | 백테스트 과적합 경고선, 데이터 스크럽 규칙 |
| staskh/trading_skills (30) | 스캐너·지표·리스크·Piotroski는 (a)/(b), 옵션·IBKR 도구 다수는 범위 밖 | 가산식 추세 점수, 크로스 신선도, VaR·MDD·베타, Piotroski, 수정 Z-점수 이상치 |
| rkiding/awesome-finance-skills (10) | A주 뉴스·LLM·생성형 예측, (c)/(d) | ISQ 가중합 정도 |
| agiprolabs/claude-trading-skills (68) | 깊게 본 18종은 대부분 (a), 짧게 본 12종은 도구, 38종은 가상자산·DeFi·예측시장·미국 세금으로 해당 없음 | 레짐 4분면 사이즈 승수, 청산 체인, 사이징 사다리, 낙폭 단계 게이트, DSR·PBO |
| anthropics/financial-services (고유 64) + knowledge-work-plugins finance (8) | (a) 0 · (b) 6 · (c) 8 · (d) 58 | thesis-tracker 구조(사후 분석 스키마), 이벤트 체크리스트, idea-generation 재무 스크린 예시 |

---

## 4. 이식 추천 기법 12개

각 기법마다 핵심 규칙, 근거, 우리 엔진에서의 자리, 한국 수정점을 적었다. 수치는 모두 코드 기본값이다. 백테스트로 검증된 값이 아니므로 KRX 데이터로 다시 맞춰야 한다.

### 4.1 Trend Template 게이트 — 유니버스 필터 겸 위원회 "추세" 관점
- 출처: Minervini. `tradermonty skills/vcp-screener/scripts/calculators/trend_template_calculator.py:L58-L176`(직접 대조).
- 7조건:
  1. 종가 > SMA150, 종가 > SMA200
  2. SMA150 > SMA200
  3. SMA200(오늘) > SMA200(22거래일 전)
  4. 종가 > SMA50
  5. 52주 저가 대비 +25% 이상
  6. 52주 고가 대비 -25% 이내
  7. RS > 70
- 점수와 통과 기준: 충족 개수 × 14.3점이고, 85점 이상(7개 중 6개)이면 통과한다.
- SMA50 과열 감점: 이격 8/12/18/25% 이상에서 -5/-10/-15/-20점(`L259-L289`).
- **[차이]** RS 70의 의미가 백분위가 아니다. "지수 대비 가중 초과수익 ≥ +10%p → rank 80"이라는 구간 매핑이다(`relative_strength_calculator.py:L261-L282`).
- 비교: himself65 sepa-strategy는 문서뿐인 8조건판이다. MA50 > MA150 > MA200, 52주 저가 × 1.30, RS 백분위 70 초과를 쓴다(`plugins/market-analysis/skills/sepa-strategy/SKILL.md:L83-L90`).
- 한국:
  - RS 기준을 KOSPI·KOSDAQ(종목 소속 시장)으로 바꾼다. RS는 KRX 전 종목의 63/126/189/252일 가중 수익률 **백분위**로 직접 계산하는 편이 낫다 [추정].
  - 수정주가 일봉이 필수다.

### 4.2 VCP 수축 탐지 + 피벗 + 실행 상태 — 진입 트리거 겸 "구조" 관점
- 근거: `vcp_pattern_calculator.py:L236-L311, L408-L603`, `volume_pattern_calculator.py:L88-L159`, `execution_state.py:L22-L177`, `scorer.py:L35-L132`.
- 스윙과 수축 탐지:
  - 스윙은 ATR14 × 1.5 반전으로 확정한다(ZigZag).
  - 가장 높은 스윙 고점 3개에서 각각 시작해 본다. 수축은 최대 4개, 각 수축은 최소 5봉이다.
- 유효 조건:
  - T1 깊이 10% 이상(CLI 기본값)
  - 연속 수축 비율 0.70 이하
  - 패턴 길이 15봉 이상
- 피벗은 마지막 수축의 고점이다. 마지막 수축이 깊이 15% 초과이면서 10봉 미만이면 "wide-and-loose"로 보고 등급을 Developing으로 제한한다.
- 거래량 건조 점수: 최근 10봉(오늘 제외) 평균을 50일 평균으로 나눈 값을 쓴다.
  - < 0.30 → 90점, < 0.50 → 75, < 0.70 → 60, ≤ 1.0 → 40, 그 외 → 20
  - 피벗 위 종가이면서 거래량 1.5배 이상이면 +10
- 실행 상태(피벗 대비 위치):
  - 0~3% + 거래량 확인 → Breakout
  - 3~5% → Early-post-breakout
  - 5~10% → Extended
  - 10% 초과, 또는 SMA200 이격 50% 초과 → Overextended
  - 마지막 수축 저점 이탈 또는 SMA50 이탈 → Damaged
  - 상태별로 등급 상한이 있다.
- 종합 점수 = 0.25 추세 + 0.25 수축 품질 + 0.20 거래량 + 0.15 피벗 근접 + 0.15 RS. 90/80/70/60/50 이상이 각각 Textbook/Strong/Good/Developing/Weak다.
- entry_ready 조건: 피벗 거리 -8%~+3%, 위험 15% 이하, 건조 비율 1.0 이하.
- **[차이]** 함수 기본값(T1 8%, 비율 0.75)과 실제 실행값(CLI 10%, 0.70)이 다르다. 운영값은 CLI 쪽이다.
- 한국:
  - 피벗·손절을 호가단위로 반올림한다.
  - 코스닥 소형주는 T1 깊이 상한 35%와 wide-and-loose 15%를 따로 보정한다 [추정].
  - 상한가에 잠긴 날은 돌파 거래량 판정에서 뺀다 [추정].

### 4.3 돌파 진입·손절·사이징·포트폴리오 heat — 사이징 겸 리스크 게이트
- 근거: `skills/breakout-trade-planner/scripts/risk_calculator.py:L22-L202`, `plan_breakout_trades.py:L42, L309-L327, L593-L597`(직접 대조).
- 가격 정하기:
  - 신호 진입가 = 피벗 × 1.001
  - 최악 진입가(추격 한도) = 피벗 × 1.02
  - 손절가 = 마지막 수축 저점 × 0.99
- 최악 진입가 기준 위험이 8%를 넘으면 거부한다.
- 수량 = 계좌 × 0.5% × 등급 배수 ÷ (최악 진입가 − 손절가). 등급 배수는 textbook 1.75, strong 1.0, good 0.75, 그 외 0이다.
- 상한: 종목 비중 10%, 섹터 30%, 누적 오픈 위험(heat) 6%. heat를 넘으면 그 종목은 보류한다. 목표가는 2R이다.
- position-sizer(`skills/position-sizer/scripts/position_sizer.py:L108-L229`):
  - 수량 = floor(자본 × 위험% ÷ (진입 − 손절))
  - 최종 수량 = min(위험 기반 수량, 종목 한도, 섹터 잔여 한도)
  - half-Kelly = (W − (1−W)/R) / 2, 음수면 0
  - **[차이]** 포트폴리오 heat 검사가 없다. heat는 breakout planner에만 있다.
- 한국:
  - 주당 위험에 비용을 더한다. krcommon `cost_per_share` = 진입가 × 수수료율 + 청산가 × (수수료율 + 매도세)(`sinkytiger-day-trader-skill-kr/krcommon/krx.py:L420-L437`).
  - 반올림 방향: 진입은 올림, 손절은 내림, 목표는 반올림.
  - 하한가 갭(-30%)을 최악 손실 시나리오에 넣는다 [추정].

### 4.4 분산일 계수기 — 시장 레짐 필터 겸 노출 상한
- 근거: `skills/ibd-distribution-day-monitor/scripts/distribution_day_tracker.py:L39-L41, L77, L142`, `ibd_monitor.py:L90-L108`, `risk_classifier.py:L10-L30`, `exposure_policy.py:L10-L22`(직접 대조).
- 분산일 정의: 지수 종가가 전일 대비 -0.2% 이하이면서 거래량이 전일보다 많은 날.
- 분산일이 빠지는 조건: 25세션이 지나 만료되거나, 이후 지수가 분산일 종가 +5%를 넘으면 무효가 된다.
- 위험 단계(d5·d15·d25는 각각 최근 5·15·25세션 안의 분산일 수):
  - CAUTION: d25 ≥ 3
  - HIGH: d25 ≥ 5, 또는 d15 ≥ 3, 또는 d5 ≥ 2
  - SEVERE: d25 ≥ 6, 또는 d15 ≥ 4, 또는 지수가 이동평균 아래이면서 d25 ≥ 5
- 노출 정책(1배 지수 기준): NORMAL 100% / CAUTION 100%(신규 매수만 중단, 트레일링 8%) / HIGH 75%(6%) / SEVERE 50%(5%).
- 한국:
  - KOSPI·KOSDAQ 지수 거래량(또는 거래대금)으로 계산한다.
  - 분산일 빈도(기저율)를 보고 -0.2%와 단계 임계값을 다시 맞춘다.
  - NXT 거래 포함 여부가 바뀐 날, 선물·옵션 동시만기일, MSCI 리밸런싱일은 품질 플래그를 단다 [추정].

### 4.5 FTD 상태머신 + 품질 점수 — 레짐 전환(방어 → 공격) 트리거
- 근거: `skills/ftd-detector/scripts/rally_tracker.py:L42-L52, L164-L531`, `post_ftd_monitor.py:L310-L426`(상수 직접 대조).
- 상태 판정 순서:
  1. 스윙로우: 40바 고점 대비 -3% 이하이면서 하락일 3일 이상
  2. Day 1: 상승 종가, 또는 (종가 − 저가)/(고가 − 저가) ≥ 0.5인 날
  3. Day 2~3: Day 1 저가를 지켜야 한다
  4. FTD: Day 4~10 중 +1.25% 이상 상승하고 거래량이 전일보다 많은 첫날
  5. 이후 종가가 FTD일 저가 아래로 내려가면 무효
- 품질 점수:
  - 기본 60점(Day 4~7) 또는 50점(Day 8~10)
  - 상승률 가산 +15/+10/+5
  - FTD일 거래량이 50일 평균 초과면 +10
  - 두 지수 모두 확인되면 +15
  - FTD 뒤 분산일 감점: Day 1~2 -30, Day 3 -15, Day 4~5 -5, 2회 이상이면 추가 -20, 없으면 +10
- 노출 밴드: 80점 이상 75~100%, 60점 이상 50~75%, 40점 이상 25~50%, 그 미만 0~25%.
- 데이터 결측이면 판정 불가로 둔다. 점수 0, 노출 0~25%.
- **[차이]**
  - 랠리 도중 더 높은 저점이 새 스윙로우로 잡혀 Day 수가 다시 시작될 수 있다.
  - 두 지수의 FTD 시점이 얼마나 가까워야 하는지 조건이 없다.
  - 같은 저장소 market-top-detector 안의 FTD 정의는 Day 4~7, +1.5%로 다르다.
  - 이식할 때 이 세 가지를 고친다.
- 한국:
  - KOSPI·KOSDAQ 지수를 쓴다.
  - KOSDAQ은 최소 상승률을 변동성에 비례해 높인다 [추정].

### 4.6 시장 폭·상승 추세 참여 점수 — 위원회 "시장 폭" 관점 (KRX 전 종목으로 직접 계산)
- 근거: market-breadth-analyzer `scripts/scorer.py:L31-L38`, `calculators/*`, `scripts/calculators/divergence_calculator.py:L45-L158`; uptrend-analyzer `references/uptrend_methodology.md:L9-L23`, `scripts/calculators/market_breadth_calculator.py:L89-L117`, `scripts/scorer.py:L328-L336`.
- 원 스킬은 tradermonty가 공개 CSV로 미리 계산한 값을 받는다. 우리는 KRX 전 종목 일봉으로 같은 지표를 직접 계산한다.
- 폭 점수(200일선 위 종목 비율의 8일·200일 EMA 사용):
  - 6요소 가중치: 레벨·추세 0.25, 8MA−200MA 교차 0.20, 사이클 0.20, 약세 신호 0.15, 백분위 0.10, 다이버전스 0.10
  - 8MA 레벨 점수: ≥0.70 → 95, ≥0.60 → 80, ≥0.50 → 65, ≥0.40 → 50, ≥0.30 → 35, ≥0.20 → 20, 그 아래 → 5
  - 점수 구간 80/60/40/20을 노출 90~100/75~90/60~75/40~60/25~40%에 대응시킨다.
- 상승 추세 종목 정의(5개 모두 충족):
  1. 종가 > SMA20
  2. 종가 > SMA200
  3. SMA50 > SMA200
  4. 52주 저가 대비 +30% 초과
  5. 4주 수익률 플러스
- 상승 추세 비율 r의 점수:
  - r ≥ 0.50 → 90~100
  - 0.37~0.50 → 70~89
  - 0.25~0.37 → 40~69
  - 0.097~0.25 → 10~39
  - 그 아래 → 0~9(구간 안에서는 선형 보간)
- 다이버전스: 60일 창 0.6 + 20일 창 0.4로 합친다. 가격 +3%인데 폭 -0.05 이하면 경고한다.
- 한국:
  - KOSPI와 KOSDAQ을 따로 계산한다.
  - 0.37, 0.097 같은 미국 임계값은 KRX 분포의 분위수로 다시 정한다 [추정].

### 4.7 위원회 결합 규칙 — 관점 점수 → 노출 상한·자세·신뢰도
- **exposure-coach**(`skills/exposure-coach/scripts/calculate_exposure.py:L21-L30, L366-L514`, 가중치 직접 대조)
  - 관점 가중치: regime 0.25, top_risk 0.20, breadth 0.15, uptrend 0.15, institutional 0.10, sector·theme·ftd 각 0.05.
  - composite = 있는 입력만으로 다시 정규화한 가중 평균 − 10 × (빠진 치명 입력 수). 치명 입력은 regime, top_risk, breadth다.
  - 노출 상한은 구간마다 선형이다.

    | composite c | 노출 상한(%) |
    |---|---|
    | 80 이상 | 90 + (c − 80) |
    | 65~80 | 70 + 1.3 × (c − 65) |
    | 50~65 | 50 + 1.3 × (c − 50) |
    | 35~50 | 30 + 1.3 × (c − 35) |
    | 20~35 | 10 + 1.3 × (c − 20) |
    | 20 미만 | c ÷ 2 |

  - 권고:
    - CASH_PRIORITY: c < 30 또는 top_risk < 25
    - REDUCE_ONLY: c < 50, top_risk < 40, 또는 치명 결측 2개 이상
    - 그 외에는 NEW_ENTRY_ALLOWED
  - 신뢰도: 입력 6개 이상이고 치명 결측이 0이면 HIGH, 입력 4개 이상이면 MEDIUM, 나머지는 LOW.
- **market-top-detector scorer**(`skills/market-top-detector/scripts/scorer.py:L26-L292`)
  - 데이터가 없는 관점은 빼고 가중치를 다시 정규화한다.
  - 상관된 두 관점이 함께 80 이상이면 가중치가 낮은 쪽을 × 0.8로 할인한다.
  - 합성 점수 구간을 위험 예산에 대응시킨다: 20 이하 100%, 40 이하 80~90%, 60 이하 60~75%, 80 이하 40~55%, 그 이상 20~35%.
- **edge-signal-aggregator**(`skills/edge-signal-aggregator/scripts/aggregate_signals.py:L1040-L1292`)
  - 합의 등급 = min(독립 증거 수, 이벤트 수, 관점 수). 2이면 +0.10, 3 이상이면 +0.20을 더한다.
  - 최신성 계수는 1.0 / 0.95 / 0.90 / 0.85다.
  - 같은 관점 안에서 반대 신호가 나오면 둘 다 뺀다. 서로 다른 관점이 같은 기간에 부딪히면 -10%다.
- **Druckenmiller 수렴도**(`skills/stanley-druckenmiller-investment/scripts/scorer.py:L177-L231`)
  - 수렴도 = max(0, 100 − 관점 점수 표준편차 × 3.33).
  - 모든 관점이 55 초과면 +15, 모두 45 미만이면 −15.
- **[차이]** exposure-coach 문서에 있는 "레짐 기준선 ±%"와 "충돌하면 신뢰도 하향"은 코드에 없다.
- **[차이]** 결측 처리 방식이 스킬마다 다르다. breadth는 가중치를 재분배하고, uptrend는 50으로 채우고, macro는 0으로 합산한다.
- 우리 엔진에서는 위 네 가지를 합친다.
  1. 치명 관점이 빠지면 감점하고 fail-closed로 처리한다(exposure-coach + contrarian-setup-gate 방식).
  2. 나머지 관점은 재정규화한다.
  3. 상관 할인과 합의 보너스를 적용한다.
  4. 수렴도를 신뢰도에 넣는다.

### 4.8 계좌 리스크 게이트 — 서킷브레이커 + 주문 직전 규율 게이트
- 근거: `skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py:L52-L57, L610-L700`(직접 대조), `skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py:L220-L382`.
- 서킷브레이커 기본값: 실현손실 기준 일 2.0%, 주 5.0%, 월 8.0%, 2연패면 24시간 쿨다운.
- 멈추는 기간: 일 한도는 다음 거래일까지, 주 한도는 다음 주 첫 거래일까지, 월 한도는 다음 달 첫 거래일까지.
- 여러 상태가 겹치면 우선순위는 HALTED > COOLDOWN > ALLOWED다. 상태 데이터가 불완전하면 HALTED다(fail-closed).
- 상태를 따로 저장하지 않고 매번 원장에서 전부 다시 계산한다.
- 주문 직전 게이트:
  - NO_GO: 손절 미설정, 계획 위험액 미설정, 실제 위험 > 계획 위험
  - NO_GO: 최근 24시간 안에 손실 청산(부분 청산 포함)이 있음. 보복 매매를 막는 창이다.
  - REVIEW_REQUIRED: 상위 게이트 결과가 없거나 알 수 없음
- 보완(agiprolabs `skills/risk-management/SKILL.md:L22-L123`, `references/circuit_breakers.md:L120-L172`):
  - 고점 대비 낙폭 단계: 5%에서 25~50% 축소, 10%에서 최소 사이즈, 15%에서 신규 중단, 20%에서 전면 정지.
  - 5일 변동성이 20일의 2배면 노출 50%, 3배면 25%.
  - 3연패면 50%로 축소한다.
- 한국:
  - 원장에 거래세·수수료를 넣은 실현손익을 쓴다.
  - 하한가 잠김이나 VI 때문에 손절이 체결되지 않은 경우를 "미실현 확정 손실"로 따로 집계한다 [추정].

### 4.9 Stockbee 모멘텀 버스트 — 단기 진입 트리거 관점
- 근거: `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py:L577-L760, L933-L951`(기본값 직접 대조).
- 트리거(셋 중 하나):
  - 당일 상승률 4% 이상이면서 거래량이 전일보다 많고 10만 주 이상
  - 종가 − 시가 ≥ 0.90달러
  - 레인지 확장: 당일 레인지가 직전 3일 최대보다 크고, 전일 상승률은 2% 이하
- 점수 100점 = 트리거 20 + 거래량 15 + 셋업 25 + 종가 위치 10 + 위험 15 + 실패 필터 10 + 시장 5.
  - 거래량 배수: 3배 이상 15점, 2배 12점, 1.5배 9점, 1배 6점.
  - 셋업: 직전 3~20일 베이스의 폭이 15% 이하이고 평균 일중 레인지가 5% 이하.
- 손절은 트리거일 저가다. 위험 점수는 2.5% 이하 15점, 4% 이하 12점, 6% 이하 8점, 8% 이하 5점, 10% 이하 2점이고, 10%를 넘으면 거부한다.
- 등급: 90/80/70/55 이상이 각각 A/A-/B/Watch다. 80점 이상이면 ACTIONABLE_DAY1이다.
- **[차이]**
  - 원 Stockbee의 TI65 추세 강도 지표는 코드에 없다.
  - 시장 게이트는 사용자가 넣는 문자열일 뿐 코드가 계산하지 않는다.
  - 3~5일 보유 청산 규칙은 문자열로만 있고 코드에 없다.
- 한국:
  - 상한가에 잠긴 봉은 종가 위치 100, 낮은 위험으로 거의 만점이 나온다. 진입 불가 플래그를 붙인다.
  - 진입은 장 마감 뒤 일봉이 확정된 다음 날 시가로 계산한다.
  - 0.90달러 기준은 ATR·호가 기준으로, 10만 주 기준은 원화 거래대금 하한으로 바꾼다.
  - 단기과열·투자경고 종목은 뺀다 [추정].

### 4.10 CANSLIM의 일봉 요소 N·S·L·M — 위원회 "수급·주도주" 관점
- 근거: `skills/canslim-screener/scripts/calculators/new_highs_calculator.py:L95-L122`, `supply_demand_calculator.py:L152-L173`, `leadership_calculator.py:L44-L45`, `market_calculator.py:L130-L191`, `scorer.py:L46-L55, L482-L527`.
- S(수급): 60일 동안 상승일 평균 거래량 ÷ 하락일 평균 거래량. 2.0 이상 100점, 1.5 이상 80, 1.0 이상 60, 0.7 이상 40, 0.5 이상 20점.
- N(신고가): 52주 고가 -5% 이내이면서 거래량 1.4배로 돌파하면 100점.
- L(주도주): 63/126/252일 상대수익을 0.4/0.3/0.3으로 가중한다.
- M(시장 방향): 지수의 50일 EMA 이격으로 점수를 매긴다.
  - +2% 이상 90점, 0% 이상 70, -2% 이상 40, -5% 이상 20, 그 아래 0점
  - VIX가 15 미만이면 +10점, 30 초과이면 0점으로 둔다.
  - **M = 0이면 다른 점수와 관계없이 매수를 막는다.**
- 종합 가중치는 C 0.15, A 0.20, N 0.15, S 0.15, L 0.20, I 0.10, M 0.05다(직접 대조). 최소 임계는 C 60, A 50, N 40, S 40, L 50, I 40, M 40이다.
- 한국:
  - VIX 대신 VKOSPI를 쓴다(일별 가용성은 [추정]).
  - C·A(분기·연간 EPS)는 OpenDART 재무로 2단계에 붙인다.
  - I(기관 보유)는 13F가 없으므로 KRX 투자자별 순매수로 다시 설계한다 [추정].
  - 상·하한가 도달일은 S 계산에서 뺀다 [추정].

### 4.11 한국 시장 규칙 모듈 + 진입 차단 목록 + 비용 포함 사이징 — 인프라
- 근거: `sinkytiger-day-trader-skill-kr/krcommon/krx.py:L40-L50, L342-L437`(직접 대조), `trader-kr-risk/check.py:L63-L65, L384-L437`, `trader-kr-budget/size.py:L128-L178`, `trader-kr-exit/exit.py:L158-L176`.
- 호가단위표: 2,000원 미만 1원, 5,000원 미만 5원, 2만 원 미만 10원, 5만 원 미만 50원, 20만 원 미만 100원, 50만 원 미만 500원, 그 이상 1,000원. 경계는 `p < limit`로 비교한다.
- 가격제한폭 = floor(기준가 × 0.30 ÷ 기준가 호가단위) × 호가단위.
- 세션 시각: 장 시작 09:00, 마감 동시호가 15:20, 장 마감 15:30.
- 비용:
  - 수수료 0.015%. 토스 예시값이라 계좌마다 바꿔야 한다.
  - 매도세 0.20%. 코드 주석에는 "2026년 매도분, 코스피·코스닥 공통"이라고 적혀 있다. 공식 확인은 필요하다.
  - 원 미만은 버린다.
- 반올림 방향: 손절은 floor, 목표는 HALF_UP, 진입은 ceil.
- 수량 = 아래 네 값 중 최소.
  - 최대 손실 ÷ (주당 위험 + 주당 비용)
  - 종목 비중 75%
  - 주문 한도
  - 현금 − 버퍼 10%
- 최소 위험은 max(2틱, 진입가의 0.05%)다. 비용/위험이 0.30 이하이고, 비용을 뺀 손익비가 1.0 이상이어야 통과한다.
- 진입 BLOCK 목록: 투자경고·투자위험, 단기과열, 정적·동적 VI, 거래정지, 정리매매, 우선주, ETF.
- 상태를 모르면 BLOCK한다. 청산 주문은 형식 오류와 공매도만 막고 나머지는 경고로 낮춘다.
- **[차이]**
  - 투자주의·관리종목은 BLOCK 목록에 없다. 우리 엔진에서는 추가하는 편이 낫다 [추정].
  - 토스 일봉 종가가 NXT 20:00 가격이라 KRX 공식 종가와 다를 수 있다. 소스 주석의 예로 2026-10-28 삼성전자는 토스 245,000원, KRX 242,000원이었다(`krxdata.py:L1-L19`). 신호 계산에는 KRX 정규장 종가를 써야 한다.

### 4.12 검증·사후 분석 프로토콜 — 위원회 가중치 학습 루프
- backtest-expert(`skills/backtest-expert/scripts/evaluate_backtest.py:L30-L215, L412-L436`)
  - 거래 30건 미만이면 평가 불가(NOT_EVALUABLE)다.
  - 슬리피지를 검증하지 않았거나 기간이 5년 미만이면 VALIDATION_REQUIRED다.
  - MDD 50% 이상이면 REJECT다.
  - 승률 90% 초과이면서 MDD 5% 미만이면 미래 정보 누수(look-ahead)를 감사한다.
  - 다섯 차원을 각 20점으로 채점한다. 70점 이상이면 Deploy, 40점 이상이면 Refine이다.
- trader-kr-lab(`sinkytiger-day-trader-skill-kr/trader-kr-lab/lab.py:L96-L531`)
  - 롤링 워크포워드: 학습 120거래일, 시험 20거래일, 최소 거래 30건.
  - 홀름 보정과 부트스트랩 95% 신뢰구간(2,000회)을 쓴다.
  - 손절을 목표보다 먼저 판정하고, 갭은 시가에 체결된 것으로 본다. 슬리피지는 1틱이다.
  - forward lock: 규칙과 엔진 소스의 해시를 잠근다.
- agiprolabs 검증(`skills/walk-forward-validation/scripts/overfit_detector.py:L103-L274`)
  - DSR > 0.95, PBO < 0.5. PBO는 CPCV(N=6, k=2)로 구한다.
- signal-postmortem(`skills/signal-postmortem/scripts/postmortem_recorder.py:L120-L155`, `postmortem_analyzer.py:L148-L190`)
  - 신호 뒤 5일 수익률로 분류한다. |r| < 0.5%면 NEUTRAL, 방향이 틀리고 2% 넘게 움직이면 FP_SEVERE다.
  - 관점 가중치 w = clamp(1 + (정확도 − 0.55) × 0.5, 0.3, 2.0). 표본 20건 이상, 변화 0.05 이상일 때만 바꾼다.
- market-top-detector 시점 고정 평가(`skills/market-top-detector/references/point_in_time_evaluation.md:L9-L80`)
  - 주간 관측, "향후 40거래일 안 10% 이상 하락"을 사건으로 정의한다.
  - 개발 구간과 홀드아웃을 나누고 경계를 퍼지한다.
  - Wilson 구간과 블록 부트스트랩을 쓴다.
- 한국:
  - 비용은 수수료 + 매도세 0.20% + 슬리피지(1틱 또는 0.10%)를 넣는다. trader-kr-invest의 기본값은 0.015% + 0.20% + 0.10%다.
  - 상장폐지 종목을 포함해 두 가지로 처리한다. 판 A는 마지막 가격으로, 판 B는 -100%로 본다(`trader-kr-invest/invest.py:L478-L503`).

---

## 5. 조건부 2차 후보

| 기법 | 핵심 규칙(근거) | 조건 |
|---|---|---|
| 실적 반응·PEAD | earnings-trade-analyzer: 가중치 갭 25%, 실적 전 20일 수익률 30%, 20/60일 거래량비 20%, MA200 15%, MA50 10%. 등급은 A 85, B 70, C 55. "갭 10% 이상이면서 85점 이상"은 제외(`skills/earnings-trade-analyzer/scripts/scorer.py:L22-L35`, `analyze_earnings_trades.py:L319-L341`). PEAD: 갭 3% 이상, 감시 5주, 실적 주 이후 가장 최근 음봉 주봉의 고가를 양봉 종가가 넘으면 BREAKOUT, 손절은 그 음봉 저가, 목표 2R(`skills/pead-screener/scripts/calculators/weekly_candle_calculator.py:L262-L287`). [차이] 갭 점수가 절대값이라 하락 갭도 고득점이다. | OpenDART 잠정실적 공시 접수 시각으로 이벤트일 정의(15:30 이후 접수분은 다음 날 갭) [추정] |
| 망치형 반전 | 아랫꼬리 40% 이상, 몸통 35% 이하, 종가 위치 60 이상, 꼬리/몸통 1.5 이상, 저점 대비 회복 2% 이상. 직전 40일 고점 대비 6~35% 눌림, 고점 뒤 3~30일 경과. 손절은 저가 -0.1%, 위험 12% 이하. 82점 이상이면 ACTIONABLE(`skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py:L521-L632, L860-L930`) | 레짐이 공격일 때만 |
| 과열 경보(포물선 점수 번안) | 하드 게이트: 5일 수익률 30% 이상, 20일선 이격 25% 이상이면서 4 ATR 이상. 점수 가중치는 이격 30, 가속 25, 거래량 20, 레인지 15, 유동성 10(`skills/parabolic-short-trade-planner/scripts/parabolic_scorer.py:L10-L35`, `screen_parabolic.py:L304-L331`) | 숏 대신 보유분 축소·신규 진입 금지 신호로 사용 |
| 레짐 4분면 사이즈 승수 | ATR14의 100일 백분위 0.30/0.70 × ADX14 25/20으로 4분면. quiet_trend 1.0, volatile_trend 0.5, quiet_range 0.75, volatile_range 0.25. 레짐 전환 때 50% 축소, 5봉 지속 뒤 전환(`agiprolabs skills/regime-detection/scripts/detect_regime.py:L375-L428`) [차이] 백테스트 스크립트는 ADX 22, vol 0.65로 다르다 | 종목·지수 단위 사이징 보정 |
| 청산 체인 | 하드스톱 → ATR 2.5배 트레일링 → 2R/3R/5R에서 25%씩 분할 익절 → 50봉 시간 손절. 래칫은 2R에서 본전, 3R에서 +1R, 5R에서 +3R(`agiprolabs skills/exit-strategies/SKILL.md:L224-L263`, `references/trailing_stops.md:L251-L272`). SEPA 문서판: -7~8% 손절, +8%에서 절반 익절하고 본전 스톱, +15%에서 25% 추가 익절, 나머지는 20MA 종가 이탈 때 청산(`himself65 sepa-strategy/SKILL.md:L147-L169`) | 청산 규칙 관점, 백테스트로 하나 선택 |
| Kanchi 배당 진입·감시 | 목표 수익률 = 5년 평균 배당수익률 + 0.5%p, 매수 목표가 = 연 DPS ÷ 목표 수익률, 분할 40/30/30. EPS 배당성향 85% 초과 또는 FCF 배당성향 100% 초과면 FAIL. 배당이 직전 대비 1% 넘게 줄면 REVIEW(`skills/kanchi-dividend-sop/scripts/build_entry_signals.py:L254-L275`, `skills/kanchi-dividend-sop/scripts/payout_safety.py:L173-L190`, `skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py:L89, L195-L232`) | 장기 코어 계좌. OpenDART 배당 사항 필요 |
| 가치·품질 관점 | trader-kr-masters: 그레이엄 8, 버핏 7, 린치 6 충족 수(G7 PER 15, G8 PBR 1.5 또는 PER×PBR 22.5, B1 평균 ROE 15%, B4 부채비율 100%, L1 PEG 1 등). value.py: F-score 8신호, GP/A, 발생액 상위 10% 제외, 순발행 상위 10% 제외, 적자 제외. 사업보고서 첫 접수일 기준으로 시점을 고정(`trader-kr-masters/masters.py:L97-L250`, `trader-kr-invest/value.py:L349-L382, L629-L668`) | 위원회 재무 관점. DART 키 필요 |
| 비용 차감 엣지 + 파라미터 합의율 | trend_pullback 진입: MA8 > MA20, 종가 > MA20, 종가 < MA8 × 1.008, RSI14 42~72. 청산: 종가 < MA20 또는 RSI14 > 74. 비용 차감 뒤 엣지 > 0이고 16개 이웃 파라미터의 진입 합의율이 0.67 이상일 때만 진입(`shouldnotappearcalm-a-share-skill/a-share-strategy-allmarket-multi-swing-defensive/scripts/strategy_lab/strategies.py:L36-L52`, `scripts/daily_decisions.py:L72-L104`) [차이] RSI가 단순이동평균 방식이라 Wilder RSI와 값이 다르다 | 과적합 방지 장치로 일반화 가능 |
| 유동성·상관 게이트 | 충격비용 = σ × sqrt(주문량/ADV), 25bps 경고, 50bps 강한 경고(`himself65-finance-skills/plugins/market-analysis/skills/stock-liquidity/SKILL.md:L120-L126`). 롤링 상관 20/60/120일과 하락일 상관(`.../stock-correlation/SKILL.md:L262-L296`). 수정 Z-점수 0.6745 × (x − 중앙값)/MAD > 3.5를 이상치로 탐지(`staskh-trading-skills/src/trading_skills/massive/whales.py:L65-L89`) | 사이징 상한, 집중도 게이트, 거래대금 급증 탐지 |
| 노출 결합식 Druckenmiller판 | 가중치 0.18/0.18/0.12/0.18/0.12/0.10/0.12. 구간 80/60/40/20에 주식 비중 90~100/70~90/50~70/20~50/0~20%. 단일 종목 상한 25/15/10/5/3%(`skills/stanley-druckenmiller-investment/scripts/scorer.py:L28-L36, L342-L415`, `allocation_engine.py:L137-L165`) | exposure-coach와 둘 중 하나 선택 |

---

## 6. 한국 시장 이식 공통 수정 포인트

| 미국 스킬의 가정 | KRX로 옮길 때 | 근거·상태 |
|---|---|---|
| 기준 지수 SPY·^GSPC·QQQ, 유니버스 S&P500(또는 시총 상위 40 하드코딩) | KOSPI·KOSDAQ(종목 소속 시장별), 유니버스는 KOSPI200 + KOSDAQ150 또는 시총·거래대금 상위 N + 유동성 하한 | 원 스킬 소스(§11~§12) |
| RS "rank"는 지수 대비 초과수익 구간 매핑 | KRX 전 종목 수익률 백분위로 직접 계산 | [추정] 권고 |
| 가격 필터(10달러 이상, 0.90달러 돌파 등)와 거래량 필터(주식 수) | 최소 가격(예: 1,000원) + 원화 거래대금 하한(day-trader-skill-kr은 거래대금 10억 원), 달러 절대값 기준은 ATR·호가 기준으로 | `trader-kr-scanner/scan.py`(§10), 나머지 [추정] |
| 소수점 2자리 반올림(Alpaca 틱) | KRX 호가표. 진입 올림, 손절 내림, 목표 반올림 | `krcommon/krx.py:L45-L50, L342-L383` |
| 가격제한 없음 | ±30%. 상한가 잠김 봉은 돌파·종가 위치 판정에서 빼고, 하한가 갭을 최악 손실 시나리오에 넣음 | 계산식은 krcommon, 처리 방식은 [추정] |
| 서버 측 stop-limit·bracket 주문 | 국내 증권사 API 지원이 제각각. 일봉 확정 뒤 다음 날 조건부 주문이나 감시 후 주문으로 단순화 | [추정] |
| 정규장 시각 09:30~16:00(미국 동부), XNYS 달력 | 09:00~15:30, 마감 동시호가 15:20~15:30, KRX 휴장일 달력. 신호는 KRX 정규장 종가로(NXT 20:00 가격 아님) | krcommon 세션 상수, `krxdata.py` 주석 |
| 비용 0 또는 미국 수수료 | 수수료(계좌별) + 매도세 0.20%(2026년 기준, 코드 주석 — 공식 확인 필요) + 슬리피지 1틱~0.10% | krcommon, trader-kr-invest |
| 13F 기관 보유(분기, 45일 지연) | KRX 투자자별(외국인·기관 세부·연기금) 순매수 일별, 외국인 보유 비중 | [추정]. 계산식 초안은 §17 |
| 실적 발표일·EPS 컨센서스(FMP) | OpenDART 잠정실적·분기보고서 접수 시각. 컨센서스는 FnGuide 등 유료라 갭 크기를 서프라이즈 대용으로 | [추정] |
| VIX | VKOSPI | [추정] 가용성 확인 필요 |
| 시장 폭 공개 CSV | KRX 전 종목 일봉으로 200일선 위 비율, 상승 추세 비율, 신고가·신저가 수를 직접 계산(KRX가 상승·하락 종목 수는 제공) | [추정] |
| 거래 정지·경보 종목 고려 없음 | 투자주의·경고·위험, 단기과열, 관리종목, 거래정지, 정리매매, VI를 진입 차단 목록으로 | `trader-kr-risk/check.py`(일부), 나머지 [추정] |
| 숏(포물선 숏, 페어 숏 다리) | 개인 대주 제약이 커서 숏 전략은 보류. 과열 점수는 보유분 축소 신호로, 페어는 연구용으로만 | [추정] |
| 연 252일(또는 가상자산 365일) 연율화 | KRX 연 거래일 수(대략 245~250일)로 | [추정] |

---

## 7. 소스와 문서가 다른 주요 지점

1. **RS rank는 백분위가 아니다**(vcp-screener, canslim-screener). 지수 대비 초과수익을 구간에 매핑한 추정치다. 가중치도 서로 다르다. VCP는 63/126/189/252일에 0.4/0.2/0.2/0.2, CANSLIM은 63/126/252일에 0.4/0.3/0.3이다.
2. **VCP 함수 기본값과 실제 실행값이 다르다.** 함수 기본값은 T1 8%·비율 0.75이고 CLI 기본값은 10%·0.70이다. 문서에는 8~35%·0.75로 적혀 있다.
3. **FTD 정의가 저장소 안에서 두 가지다.** ftd-detector는 Day 4~10·+1.25%, market-top-detector 내장판은 Day 4~7·+1.5%다. 스윙로우가 다시 설정되는 문제와 리셋 미구현도 있다.
4. **macro-regime-detector는 yfinance가 아니라 FMP를 쓴다.** skills-index.yaml에는 yfinance가 필수로 적혀 있지만 코드는 FMP_API_KEY를 쓴다.
5. **data-quality-checker는 가격 데이터 품질 검사기가 아니다.** 실제로는 마크다운 문서 린터다. 가격 데이터 품질 게이트는 ftd-detector의 `_price_bars.py` 방식(결측·0 거래량을 0으로 읽지 않고, 바를 지우지 않고, 판정 불가로 처리)을 참고해 직접 만들어야 한다.
6. **position-sizer에는 포트폴리오 heat 검사가 없다.** 문서는 "기본 위험 1%"라고 하지만 코드에서는 필수 인자다.
7. **stockbee 계열**: TI65가 없다. 청산 로직은 문자열 템플릿뿐이다. EP에는 갭·거래량 하드 컷이 없다.
8. **PEAD의 R:R 성분은 상수다**(목표를 2R로 고정). 실적 반응 갭 점수는 절대값이라 하락 갭도 100점을 받는다.
9. **exposure-coach**: 문서의 레짐 기준선 가감과 충돌 시 신뢰도 하향은 코드에 없다. Druckenmiller의 conviction_matrix 노출표도 문서뿐이다.
10. **value-dividend-screener**: docstring은 수익률 3.5%·배당 CAGR 5%인데 코드는 3.0%·4.0%다. 점수 배분도 문서와 다르다.
11. **himself65 sepa-strategy, a-share의 MACD 전략 2종과 tuige 단타**는 문서뿐이다. 코드가 있다고 적힌 곳도 실제 폴더에 코드가 없다.
12. **agiprolabs**: 검증 코드는 대부분 합성 데이터 데모다. walk-forward는 학습 구간 최적화가 없고, PBO는 purge·embargo가 빠져 있고, Sortino 분모가 비표준이다. 3σ 스파이크 보간을 KRX 일봉에 쓰면 상·하한가와 액면분할 갭을 지워 버린다.

## 8. 한계와 검증 상태

- 이 문서의 수치는 코드 상수다. 어느 저장소도 우리가 확인할 수 있는 백테스트 근거(로그·데이터)를 함께 내놓지 않았다. 예를 들어 earnings-trade-analyzer는 "517거래 백테스트"를 말하지만 데이터가 저장소에 없다.
- 줄 번호는 커밋 기준이다. 일부 하위 분석 노트에는 "부근"이나 범위로 적힌 줄이 있다(각 절의 "확인 못 한 것" 참고).
- 코드를 실행하지 않았으므로 출력 분포·적중률·버그 여부는 정적 읽기 수준이다.
- 한국 시장 사실(세율, VKOSPI 일별 가용성, KRX 투자자별 통계 항목, 선물 승수 등)은 대부분 [추정]이다. 구현 전에 공식 자료로 확인해야 한다. 매도세 0.20%는 day-trader-skill-kr 코드 주석에 있는 값이다.
- tradermonty README는 "완전 자동매매·신호 대행용이 아니다"라고 밝힌다. 이 규칙들을 자동 실행으로 바꾸는 책임과 검증은 우리 쪽에 있다.

## 9. 상세 노트 안내

| 절 | 내용 |
|---|---|
| §10 | 한국 시장 스킬: day-trader-skill-kr(krcommon, scanner, lab, invest, masters, risk·budget·exit, 나머지, 미국 원본 대비 차이), Kiwoom-Plugins, k-skill |
| §11 | Minervini·O'Neil 종목 선별: vcp-screener, breakout-trade-planner, canslim-screener |
| §12 | O'Neil 시장 타이밍: ftd-detector, ibd-distribution-day-monitor, market-top-detector, downtrend-duration-analyzer |
| §13 | 시장 레짐·폭·노출: exposure-coach, market-breadth-analyzer, uptrend-analyzer, macro-regime-detector, 버블·차트·환경·가상자산 |
| §14 | Stockbee 계열 5종 |
| §15 | 이벤트·역발상: 포물선 숏, PEAD, 실적 반응, 뉴스 반응 실패, 역발상 게이트, COT |
| §16 | 리스크·규율·기록 10종 |
| §17 | 재무·가치·배당·Druckenmiller 9종 |
| §18 | 기술적 분석·테마·페어·엣지 연구 파이프라인 18종 |
| §19 | 메타·일정·정성 11종과 workflows/*.yaml(파이프라인 순서·결정 게이트) |
| §20 | A주 전략, himself65 finance-skills, quant-skills |
| §21 | staskh/trading_skills, rkiding/awesome-finance-skills |
| §22 | agiprolabs/claude-trading-skills |
| §23 | Anthropic 공식 financial-services, knowledge-work-plugins(finance) |
| 부록 A·B | 확인만 한 저장소, 클론 위치와 커밋 |

---


## 10. 한국 시장 스킬: day-trader-skill-kr · Kiwoom-Plugins · k-skill
> 저장소들: sinkytiger-day-trader-skill-kr(256cd81, MIT + Apache-2.0 일부), jakeschincariol-day-trader-skill(3d0f4ef, MIT), kiwoom-plugins(7dcf821), nomadamas-k-skill(9766d20)

### sinkytiger/krcommon — 한국 시장 규칙 모듈 (krx.py 외)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 호가단위·가격제한폭·장 운영 세션·휴장 캘린더·비용 계산을 한 모듈(표준 라이브러리, Decimal)에 모은 것. 값은 토스증권 호가창·시세 확인(2026-10-29)과 보도자료 근거라고 docstring에 명시 |
| 분류 | (a) 일봉만으로 구현 가능(호가·한도·비용·세션). 호가창 슬리피지(liquidity.py)는 (a′) 실시간 호가 필요 |
| 필요 데이터 | 규칙 자체는 데이터 불필요. 휴장·특별 장시간은 토스증권 market-calendar/KR, 종목 상태·경고·상하한가는 토스 API(키), 공식 종가는 KRX Open API(KRX_API_KEY), 공시는 OpenDART(키) |
| 주요 파일 | sinkytiger-day-trader-skill-kr/krcommon/krx.py(485줄), liquidity.py, krxdata.py, dart.py, toss.py, bars.py |
| 라이선스 | MIT(전체 뼈대는 Jakeschincariol MIT). Apache-2.0은 masters.py의 thesis 부분만(THIRD_PARTY_NOTICES.md 2절) |
| 이식 판단 | 채택 - 한국 시장 규칙 모듈(호가·한도·비용·세션) 거의 그대로. 호가창 슬리피지는 부분(일봉 엔진에서는 고정 bp로 대체) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 호가단위 표 | (2000,1),(5000,5),(20000,10),(50000,50),(200000,100),(500000,500), 이상 TOP_TICK=1000. 비교는 `p < limit`(미만) -> 2,000원 정확히면 5원 단위. 우리 사실과 일치. ETF·ETN 제외라고 명시(ETF 틱 별도 처리 없음) | sinkytiger-day-trader-skill-kr/krcommon/krx.py:L45-L46, L342-L347 |
| 2 | 틱 반올림 3종 | floor_tick(내림, 매수 손절가 등 진입가에서 멀어지는 쪽), ceil_tick(올림), round_tick(ROUND_HALF_UP). 모두 "입력가의 틱"으로 나눔 -> 경계 직전 값을 올림할 때 위 구간 틱과 불일치 가능 [추정] | krx.py:L350-L367 |
| 3 | on_tick | 정수이고 floor_tick과 같으면 True. 지정가 검증에 사용 | krx.py:L370-L372 |
| 4 | 가격제한폭(상·하한가) | 폭 = floor(기준가 x 0.30 / 기준가틱) x 기준가틱; 하한 = 기준가 - 폭, 상한 = 기준가 + 폭. LIMIT_PCT=0.30. 삼성전자 상한 314,500/하한 169,500(2026-10-29)과 맞는다고 docstring. 기준가 <=0이면 KrxError. 실제 값은 토스 price-limits API로 확인하라고 명시 [차이 가능: 상한가 자체의 틱이 기준가 틱과 다를 때 KRX 실제 산식과 어긋날 수 있음, 추정] | krx.py:L47, L375-L383, 문서 L25-L27 |
| 5 | 정규장 세션 | OPEN 09:00, AUCTION 15:20, CLOSE 15:30. 09:00~15:20 접속매매(판단·시뮬은 이 구간만), 15:20~15:30 종가 단일가(15:30 1회 체결). 5분봉이면 76칸 | krx.py:L40-L42, L175-L190 |
| 6 | 특별 장시간 이동 | Session.shift: 개장이 늦은 날은 12:00 이전 기준 시각을 개장 지연만큼, 12:00 이후 기준 시각은 접속매매 종료 지연만큼 이동(신년 첫 거래일·수능일 대응) | krx.py:L202-L214 |
| 7 | 휴장일 | default_session: 토·일만 None, 공휴일은 모름(source="default"). Calendar.add_response: 토스 전/당/익 영업일 응답, 질의일이 응답에 없고 전영업일<질의일<익영업일이면 휴장 처리. 리스크 게이트는 source=="default"이면(require_market_status=true) 진입 BLOCK | krx.py:L222-L226, L263-L289; trader-kr-risk/check.py:L92-L100 |
| 8 | 수수료 | DEFAULT_COMMISSION=0.00015(0.015%, 토스 문서 예시값, 매수·매도 양쪽), 원 미만 버림 | krx.py:L49, L416-L430 |
| 9 | 거래세 | DEFAULT_SELL_TAX=0.002 = "2026년 매도분 코스피·코스닥 공통 0.20%"(코스피 증권거래세 0.05% + 농특세 0.15%, 코스닥 0.20%). 매도 대금에만 부과. 우리가 아는 값(2026 약 0.20%)과 일치, 단 코드는 시장 구분 없이 단일 상수 | krx.py:L50, L22-L24(docstring) |
| 10 | 왕복 비용식 | total = floor(진입x수량x수수료) + floor(청산x수량x수수료) + floor(청산x수량x세율). 주당 비용(버림 없음) = entry*c + exit*(c+t). 왕복 약 0.23%(0.015x2+0.20)(손절/목표 가격에서 계산) | krx.py:L420-L438 |
| 11 | 중간가호가 체결가 보정 | 체결가에 호가 사이 값(예 245,250)이 섞이므로 진입가는 ceil_tick으로 매수호가 쪽 올림. 소형주 1~2%, 삼성전자 10% 정도(2026-10-29)라는 관찰 | krx.py:L16-L21; check.py:L322 |
| 12 | KRX 공식 종가 vs 토스 일봉 | 토스 일봉 종가는 KRX+NXT 통합이라 20:00 NXT 애프터마켓 마지막 가격. 2026-10-28 삼성전자 토스 245,000 vs KRX 242,000. 신고가·이평·RSI는 KRX 종가로 재야 한다. KRX Open API stk_bydd_trd/ksq_bydd_trd, 매일 08:00 전일 자료, 키당 하루 10,000건 | krcommon/krxdata.py:L1-L19 |
| 13 | VI·경고·정지 처리 | 코드에 VI 계산은 없음(발동 여부를 토스 warnings API로 받아 BLOCK). BLOCK_WARNINGS: INVESTMENT_WARNING, INVESTMENT_RISK, OVERHEATED(단기과열), LIQUIDATION_TRADING, STOCK_WARRANTS, VI_STATIC, VI_DYNAMIC, VI_STATIC_AND_DYNAMIC. 그 외 경고 유형은 경고만. KRX 거래정지(krxTradingSuspended)·정리매매·상장상태 != ACTIVE·ETF(allow_etf)·우선주(allow_preferred)도 진입 BLOCK. "투자주의"/"관리종목"은 BLOCK 목록에 없음(DART 공시 키워드에만: 관리종목·상장폐지·매매거래정지 등) | trader-kr-risk/check.py:L63-L65, L182-L222; krcommon/dart.py:L30 |
| 14 | 청산은 막지 않음 | 매도가 보유수량 이내면 kind="exit": 형식·공매도만 BLOCK, 나머지는 경고로 강등("빠져나가는 길은 늘 열려 있어야") | trader-kr-risk/check.py:L340, L462-L463 (docstring L16-L17) |
| 15 | 호가창 손절 슬리피지 | stop_slippage: 현재 매수 잔량 모양으로 수량만큼 시장가 매도 시 1호가 대비 평균 하락(원/주). 잔량 부족분은 마지막 호가 아래 한 틱에서 체결된다고 보수적 가정 | krcommon/liquidity.py:L71-L89 |
| 16 | 시간대 기본 설정 | no_entries_before 09:15, no_entries_after 14:50, flat_by 15:15 (단타용, 일봉 엔진엔 무관) | krx.py:L53-L80 |

**출력 형식**: 함수 반환(int/Decimal/dict), 사람용은 won()/price_str()/pct_str() 문자열.
**SKILL.md와 코드 차이**: 거래세 0.20%는 코드·docstring이 일치. 가격제한은 "기준가 호가단위로 버림"이라는 자체 규칙이며 KRX 공식 산식과 동일한지는 확인 못 함 [추정]. VI 계산 로직 없음(외부 API 의존).
**우리 엔진으로 옮길 때**: (1) tick_size/floor/ceil/round_tick, price_limits는 한국 시장 규칙 모듈로 그대로 이식(단 일봉 백테스트에서는 상한가 도달 시 체결 불가 가정을 별도 추가). (2) 비용은 시장별 세율 분리(코스피 0.05%+0.15%, 코스닥 0.20%)와 연도별 세율 테이블화. (3) VI·투자경고·정지는 일봉만으로는 모르므로 KRX 종목상태 데이터(투자경고/위험/단기과열/관리/거래정지) 일자별 스냅샷을 데이터 품질 필터로. (4) 일봉 종가를 KRX 정규장 종가로 맞추는 데이터 품질 검증(NXT 오염 주의) 필요. (5) 휴장일은 KRX 캘린더 파일로 대체(코드는 공휴일 미지원).

### sinkytiger/trader-kr-scanner — 차트 스캐너 (일봉 5셋업 + 시가 범위 돌파)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 20일 종가 신고가, 상승 깃발, 20일 평균 회복, RSI14 과매도, 과매도 반등(일봉) + ORB(5분봉). 셋업 5종의 find_setups는 미국 원본(jakeschincariol trader-scanner/scan.py:L516-L539)과 수식 동일 |
| 분류 | 일봉 5종 = (a) 일봉만으로 구현 가능. ORB = (a′) 분봉 필요(토스 1분봉을 5분으로 묶음) |
| 필요 데이터 | 일봉 종가·거래량 60개(KRX Open API 공식 종가 우선, 없으면 토스 일봉+경고), 종목정보(토스, 키), ORB는 토스 1분봉 |
| 주요 파일 | sinkytiger-day-trader-skill-kr/trader-kr-scanner/scan.py(492줄), SKILL.md |
| 라이선스 | MIT |
| 이식 판단 | 일봉 5종 부분 채택(진입 트리거/위원회 점수 후보, 단독 매수 신호는 아님: 문서도 "살 종목 목록이 아님" 명시 L54). ORB는 보류(분봉) |

**규칙·계산식** (c = 종가 리스트, 최신이 마지막)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | breakout_20d | `last > max(c[-21:-1])` (직전 20일 종가 최고 초과, 당일 제외) | trader-kr-scanner/scan.py:L88-L89, L98-L99 |
| 2 | bull_flag | run = c[-6]/c[-16]-1 > 0.10 AND rng5 = (max(c[-5:])-min(c[-5:]))/last < 0.05. 즉 5거래일 전 종가가 그 10일 전 대비 +10% 초과, 최근 5일 종가 변동폭 5% 미만(종가만 사용, 고저가 아님) | scan.py:L92-L93, L100-L101 |
| 3 | reclaim_ma20 | `c[-2] < ma20_prev AND last > ma20`, ma20 = mean(c[-20:]), ma20_prev = mean(c[-21:-1]) | scan.py:L90-L91, L102-L103 |
| 4 | oversold | RSI14(Wilder, 처음 n개 단순평균 후 지수평활) < 30. 손실 0이면 100 | scan.py:L75-L84, L104-L105 |
| 5 | oversold_bounce | RSI14(c[:-1]) < 30 AND last > c[-2] | scan.py:L94, L106-L107 |
| 6 | 유동성 필터 | 마지막 종가 >= 1,000원(--min-price), 거래대금(종가 x 거래량, 또는 value 필드) >= 1e9원(--min-value 10억). 일봉 30개 미만 제외(MIN_DAILY_BARS=30). 미국은 가격 $5 + 거래량 옵션 | scan.py:L52, L122-L141, L471-L472 |
| 7 | 미완성 일봉 제외 | 당일 일봉은 20:00(DAILY_FINAL, NXT 애프터마켓 종료) 이전엔 뺀다 | scan.py:L53, L109-L119 [차이: docstring L110은 "15:30 이후"라고 적었으나 상수는 20:00] |
| 8 | 후보 정렬 | hits를 거래대금 내림차순, 같으면 종목코드. 출력 필드: setups, price, close_date, rsi, value_krw, level(=직전20일 최고종가) | scan.py:L145-L152 |
| 9 | 후보 풀 | 기본은 토스 시장 거래대금 상위 100(투자유의 제외), 보통주·상장·정지 아님만. --universe는 전 종목 | scan.py:L10-L19, L223-L275 |
| 10 | ORB(분봉) | 범위 = 개장 후 --or-minutes(기본 15, 5~120의 5배수) 5분봉들의 최고고가(oh)/최저저가(ol); 신호 = 범위 뒤 처음으로 종가 > oh인 완성 5분봉, 신호 시각 = 그 봉 종료 시각; pct_over=(c/oh-1)*100. 개장부터 5분봉이 빠짐없는 차트만 사용. 15분 범위면 첫 신호 가능 시각 09:20. 가격 하한 1,000원 | scan.py:L154-L189, L191-L220 |
| 11 | 진입 마감과 연동 | orb_window가 config no_entries_after(14:50)를 session.shift로 보정해 마감 뒤엔 오류 | scan.py:L154-L177 |

**출력 형식**: trader-kr/watchlist.json(source, filters, note, hits[{symbol,setups,price,close_date,rsi,value_krw,level}]), 종료코드 0=발견/1=없음.
**SKILL.md와 코드 차이**: SKILL.md가 말하는 5셋업·수치는 코드와 일치. 위 7번의 15:30/20:00 불일치 외 없음.
**우리 엔진으로 옮길 때**: (1) 일봉 5종은 그대로 이식 가능하나 데이터는 KRX 정규장 종가로(NXT 통합 종가 오염 주의). (2) 상한가·거래정지·관리종목 제외 필터, 수정주가 처리 추가 필요(코드에 없음). (3) 임계값(10%, 5%, RSI30)은 미국 값 그대로라 한국 변동성(가격제한 30%)에 맞춘 재튜닝 필요, lab 의 검증 절차로 선별 권장. (4) ORB는 분봉이 없으면 일봉 갭+고가 돌파 프록시로 대체하거나 보류. 위원회에서는 breakout_20d/reclaim_ma20를 추세 관점, oversold(_bounce)를 평균회귀 관점 점수로.

### sinkytiger/trader-kr-lab — 전략 검증 실험실 (ORB 변형 48규칙 + 워크포워드 + forward lock)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 시가 범위 돌파(ORB) 변형 48개를 "앞 학습 구간에서 고르고 뒤 시험 구간에서만 평가"하는 워크포워드, 홀름 다중검정 보정, 부트스트랩 CI, 규칙 잠금 후 미래 검증(forward). 미국 원본(Jakeschincariol)에는 lab이 없음 = 한국판 추가물 |
| 분류 | 규칙 48개 = (a′) 분봉 필요(5분봉 76개/일). 검증 틀(워크포워드·홀름·부트스트랩·forward lock·비용 반영)은 일봉 엔진에도 그대로 이식 가능 -> 검증/사후 분석 |
| 필요 데이터 | 토스증권 1분봉(2022-11-23 이후, 캐시) -> 5분봉 76개, 온전한 거래일만. KRX 키는 --top 용 |
| 주요 파일 | sinkytiger-day-trader-skill-kr/trader-kr-lab/lab.py(713줄), SKILL.md |
| 라이선스 | MIT |
| 이식 판단 | 검증 틀은 채택(검증 모듈). 48규칙 자체는 보류(분봉) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 규칙군 그리드 48 = 2x2x3x2x2 | 시가범위 {15,30}분 x 손절 {or_mid(범위 고저 중간), or_low(범위 저가)} x 목표 {1R,1.5R,2R} x 거래량조건 {없음, 신호봉 거래량 >= 1.5 x 범위 봉 평균} x 비용필터 {끔,켬}. --stop-pct X면 "진입가 아래 X% 손절" x 목표 {1,1.5,2,없음}R x 2 x 2 x 2범위 = 32개 추가 | trader-kr-lab/lab.py:L70-L86 |
| 2 | 진입 | 범위 뒤 첫 종가 > 범위 고가(oh)인 5분봉, 슬롯 범위 [max(n, 15//5-1=2), 69] = 09:15 이후~14:50에 끝나는 봉; vol_x 있으면 b.v >= vol_x x 범위평균거래량 추가. 진입가 = ceil_tick(봉 종가) | lab.py:L54-L55, L96-L114 |
| 3 | 손절·위험 | 손절 = floor_tick(or_mid 또는 or_low 또는 e x (1-pct/100)); risk = e - s; risk < max(2 x 틱, e x 0.0005)이면 거래 안 함(너무 좁은 손절 제외) | lab.py:L115-L121 |
| 4 | 비용 필터 | cost_stop = e x c + s x (c + t); cost_stop > max_cost_to_risk(기본 0.3) x risk면 건너뜀. 즉 손절 때 비용이 주당 위험의 30% 초과 시 제외 | lab.py:L122-L125; krx.py CONFIG_DEFAULTS max_cost_to_risk 0.3 |
| 5 | 목표 | round_tick(e + target_r x risk). 지정가라 목표가에 그대로 체결(슬리피지 없음 가정). 목표 없음이면 손절 아니면 시간 청산 | lab.py:L126, L135-L137 |
| 6 | 청산 순서 | 진입 다음 봉부터 FLAT_SLOT=74(15:15 종료 봉)까지: (1) 봉 시가 <= 손절가면 갭 손절 = floor_tick(시가) - slip x 틱, (2) 봉 저가 <= 손절가면 손절 = s - slip x 틱, (3) 봉 고가 >= 목표면 목표 체결. 손절을 목표보다 먼저 검사(같은 봉 양쪽 닿으면 손절 우선, 보수적). 아무것도 아니면 15:15 봉 종가 - slip. 슬리피지 기본 1틱(--slip-ticks) | lab.py:L56, L127-L142, L636 |
| 7 | R 정의 | R = (청산가-진입가)/위험; R_net = (청산가 - 진입가 - (e x c + exit x (c + t)))/위험. 비용 반영 = 수수료 양쪽 + 매도세 | lab.py:L143-L145 |
| 8 | 온전한 거래일 | 5분봉 정확히 76개, 첫 봉 거래량 > 0, 슬롯 번호 연속인 날만 | lab.py:L146-L153 |
| 9 | 검정 | one_sided_p: 평균 > 0 단측 z 검정(정규 근사, 거래 3건 미만이면 p=1, 분산 0이면 평균>0일 때 0). 거래 간 독립 가정(종목·일 상관 무시) [추정: 과대 유의 위험] | lab.py:L181-L190 |
| 10 | 홀름 보정 | 정렬 후 adj_i = max(이전 adj, min(1, (m-rank) x p_i)), 입력 순서로 반환. 전 규칙(48개)에 적용 | lab.py:L192-L201, L232-L235 |
| 11 | 워크포워드 | train=120, test=20 거래일(기본), 250 거래일 로드. 매 fold: 학습 120일 내 거래 >= min_trades(30)인 규칙 중 비용 뺀 평균 R이 최대인 1개 선택 -> 바로 뒤 20일만 적용, test만큼 밀며 반복(롤링). 시험 구간 거래만 모아 평균 R_net과 95% 부트스트랩(n=2000, seed 19, 하위 2.5%/상위 97.5% 분위) CI = "실험실의 답". 선택 가능한 규칙이 없으면 그 fold는 거래 없음 | lab.py:L214-L283, L203-L211, L633-L635 |
| 12 | 판정문 | CI 상한 < 0: "비용 뺀 기대값 음수"; CI 하한 > 0 AND 홀름 p<0.05인 규칙 존재: "보정 뒤에도 남는 규칙 있음(그래도 한 번의 실험)"; 하한 > 0 이지만 홀름 통과 규칙 없음: "우연일 수 있음"; 그 외 "0과 구별 안 됨" | lab.py:L285-L305 |
| 13 | 비용 분해 | avg_R vs avg_R_net, cost_share_of_gross = sum(R-R_net)/sum(양의 R), 비용필터 on/off 평균 R_net 비교 | lab.py:L264-L272 |
| 14 | forward lock | 규칙(변형 dict)·종목·비용을 JSON으로 잠금(LOCK_KEYS: rule, variant, symbols, cost, after, judge_trades, engine) + sha256 hash; open(path,"x")로 덮어쓰기 거부; after = 잠근 날짜, first_session = 다음 평일; judge_trades >= 30(기본 200). engine = run_rule 소스코드 sha256 앞 16자 -> 체결 로직이 바뀌면 update 중단 | lab.py:L346-L370, L390-L412 |
| 15 | forward 판정 | 잠근 날 이후 거래일에만 run_rule 적용. 처음 judge(200)건으로 단 한 번 판정(좋을 때 멈추는 착시 방지): 부트스트랩 CI 하한 > 0이면 PASS, 아니면 FAIL, 200건 미만 WAIT. 자료를 못 읽은 종목이 있으면 update 중단(빠진 채로 성적 내지 않음) | lab.py:L463-L531, L488-L498 |

**출력 형식**: 표(규칙, 거래 수, avg_R, avg_R_net, 승률, p, p_holm) + fold 목록 + oos{trades, avg_R_net, ci, win_rate} + costs + 판정문. --write로 trader-kr/lab.json, forward는 trader-kr/forward/<name> 잠금 JSON과 결과 JSON.
**SKILL.md와 코드 차이**: 확인한 범위에서 없음(문서의 48규칙·120/20·1.5x·30%·15:15 모두 코드와 일치).
**우리 엔진으로 옮길 때**: 규칙 그리드를 일봉 규칙(진입 트리거 x 손절 x 목표 x 보유기간)으로 바꾸고 run_rule을 일봉 체결 모델로 교체. 워크포워드(롤링 120/20 거래일, min_trades 30), 홀름, 부트스트랩 CI, "선택은 학습 구간만/성과는 시험 구간만", forward lock(규칙+엔진 지문 해시, 덮어쓰기 금지, 첫 N건 1회 판정)은 그대로 검증 모듈로. 단 일봉 전략은 거래 수가 적어 min_trades·judge_trades를 낮추거나 종목 풀로 합쳐야 하고, 종목 간 상관 때문에 z검정은 블록 부트스트랩으로 교체 권장 [추정]. 호가 단위 반올림(손절 floor, 목표 round, 진입 ceil)과 갭 체결(시가 <= 손절이면 시가 체결)은 일봉에서도 유효.

### sinkytiger/trader-kr-invest — 장기 월/연 리밸런싱 실험실 (invest.py 16규칙 + value.py 가치·F-score·위험신호)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 월 1회(또는 분기/연) 리밸런싱 팩터 16개(동일가중·모멘텀 12-1·저변동성·소형·52주고가근접·1개월반전·추세타이밍) + 가치 8(PBR·PER·배당·점검표) + F-score/GP/A 4 + 위험 신호 제외 5. 기준은 B1 = 시총 상위 300 보통주 시총가중. 규칙·검정은 "사전 등록(r2~r5)"해 순서 고정, Holm·Newey-West 사용 |
| 분류 | invest.py 16 = (a) 일봉만(KRX 일별매매정보: 종가·전일대비·시총·거래대금). value.py = (b) 재무 데이터 필요(DART 사업보고서 + 배당 + 접수일) |
| 필요 데이터 | KRX Open API 일별매매정보 2010-01-04~(KRX_API_KEY, 키당 하루 10,000건; MAX_CALLS 9000), OpenDART fnlttSinglAcntAll/alotMatter/company/list/corpCode(DART_API_KEY; 하루 약 2만건 제한, MAX_CALLS 18000). DART 전체 재무제표는 2015 사업연도부터라 가치 신호는 FIRST_SIGNAL=2016-04부터 |
| 주요 파일 | sinkytiger-day-trader-skill-kr/trader-kr-invest/invest.py(725줄), value.py(1139줄), krcommon/financials.py(413줄) |
| 라이선스 | MIT (value.py가 masters.py 호출, masters.py의 thesis 부분만 Apache-2.0) |
| 이식 판단 | invest.py 팩터 정의·상장폐지 처리·비용 모델은 부분 채택(위원회 점수기의 모멘텀/저변동 관점, 검증 모듈). value.py 가치·F-score·GP/A·발생액·순발행은 재무 데이터 확보 시 채택(위원회 가치/품질 관점, 리스크 게이트의 재무위험 제외) |

**규칙·계산식: invest.py**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 종목군 U(T) | 신호일마다: 거래대금>0, 시총>0, 스팩 아님(이름에 "스팩"), 첫 거래일 <= 12개월 전 월말(상장 1년 이상), 보통주(코드 6자리 끝자리 0) 중 시총 상위 UNIVERSE=300. 12개월 전 신호일 없으면 None [주의: 끝자리 0 보통주 판별은 영숫자 신규 코드(2024~)를 놓칠 수 있음, 추정] | trader-kr-invest/invest.py:L45, L63-L68, L389-L399 |
| 2 | 신호·체결 | 신호 = 매달 마지막 거래일 종가(T), 체결 = 다음 거래일 종가(E). 리밸런싱 달에만 목표 비중으로 조정, 그 외 보유 그대로 | invest.py:L230-L243, L470-L515 (docstring L18-L20) |
| 3 | 16규칙 (rules()) | (1) 동일가중 300 매달; (2~5) 모멘텀12-1 {30,50종목} x {매달,분기}; (6~9) 저변동성 {30,50} x {M,Q}; (10~11) 소형 {30,50} 분기; (12~13) 52주고가근접 {30,50} 매달; (14) 1개월반전 30종목 매달; (15~16) 추세타이밍 {10,12개월 이평} 매달. 기준 B1 = 시총가중 300 매달 | invest.py:L346-L361, L363 |
| 4 | 모멘텀12-1 | 점수 = -(P(T-1개월)/P(T-12개월) - 1) 오름차순 정렬(상위 n). 조정가격 지수 사용. 최근 1개월 제외 | invest.py:L440-L443 |
| 5 | 1개월반전 | 점수 = P(T)/P(T-1) - 1 오름차순(최근 1개월 하락 큰 30종목) | invest.py:L444-L447 |
| 6 | 저변동성 | 252거래일 창 일수익률 표준편차(표본, n-1), 수익률 200개 미만이면 제외, 오름차순 상위 n. WINDOW=252, MIN_RETS=200 | invest.py:L46-L47, L296-L312, L448-L450 |
| 7 | 소형 | 시총 오름차순 상위 n(U 300 안에서) | invest.py:L451-L452 |
| 8 | 52주고가근접 | hi = 조정가격 / 252일 창 최대 조정가격, 내림차순 상위 n(고가에 가장 가까운 종목) | invest.py:L312, L453-L454 |
| 9 | 추세타이밍 | 시장지수(그날 거래된 보통주 전부 시총가중 가격지수, 스팩 제외) 최근 ma개월 평균 대비 현재가 <= 평균이면 현금(빈 dict), 위면 B1 시총가중. ma=10,12 | invest.py:L401-L415, L423-L434 |
| 10 | 리밸런싱 주기 | M 매달, Q = 3·6·9·12월, Y = 4월(YEAR_MONTH=4: 사업보고서 제출기한 3/31 한 달 뒤) | invest.py:L49, L460-L467 |
| 11 | 비용 | COST = 수수료 0.015%(양쪽) + 매도세 0.20% + 슬리피지 0.10%(양쪽). 매수 비용 = (c+slip), 매도 = (c+slip+tax), --cost-x 배수. 매매한 비중에만 부과: after = total x (1 - sold x sell - bought x buy); turnover = (sold+bought)/2 | invest.py:L50, L478-L503 |
| 12 | 수익률 계산 | 일수익률 = 종가/(종가-전일대비)-1. 전일대비는 KRX 기준가 대비라 분할·병합·감자·권리락 조정 포함. 현금 배당은 빠진 가격수익률(value.py는 배당 재투자 추가). 전일대비 없으면 직전 종가 대비로 대체(no_chg 카운트) | invest.py:L10-L14, L270-L283 |
| 13 | 생존 편향 처리 | KRX는 그날 상장 전 종목을 줌 -> 이후 폐지·합병 종목 포함(survivorship bias 없음). 판 A: 보유 기간 끝에 행이 없으면 마지막 행 가격에 매도(정리매매 가격까지 반영). 판 B: 이후 영영 행이 없는 종목은 -100%(growth=0, 비관적 한계). 거래정지는 거래대금 0 행으로 남아 종목군에서 빠지고, 보유 중이면 정지 가격에 판 것으로(낙관적, 두 판 공통). 같은 코드가 365일 넘게 없다가 재등장하면 새 종목("*" 접미)으로 처리(코드 재사용) | invest.py:L16-L27(docstring), L53, L267-L271, L328-L333 |
| 14 | 벤치마크·검정 | 같은 달 초과수익(규칙-B1)의 평균, Newey-West SE(Bartlett 가중, lag=3, NW_LAG), 평균>0 단측 p(정규근사), Holm 보정(규칙 16개). 성과: CAGR=level^(12/n)-1, 연변동성=sd x sqrt(12), 최대낙폭 | invest.py:L48, L517-L568 |
| 15 | DCA 비교 | 36개월 창 일시투입 vs 매달 적립 끝가치 비율(중앙값, 일시투입 우세 창 비율) | invest.py:L569-L584 |
| 16 | 자료 제약 | 종목군이 300 미만인 달이 있으면 오류 중단, 첫 수익률은 12개월 앞 자료 필요 | invest.py:L642-L652(cmd_run), L494-L496 |

**규칙·계산식: value.py (가치 8 = r3, F-score·GP/A 4 = r4, 위험 신호 제외 5 = r5)**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 17 | 가치 대상 V(T) | U(T)에서 제외: 금융(KSIC 64·65·66, 단 유동자산이 있는 지주 64992는 유지), 리츠(회사명 "부동산투자회사"), 12월 결산 아님(acc_mt != "12"), 코드 재사용 종목, FY(T-1) 사업보고서가 T까지 미접수. T = 매년 4월 마지막 거래일, 체결 다음 거래일 종가, 다음 해까지 보유. N=30, 규칙은 연 1회 | trader-kr-invest/value.py:L18-L21(docstring), L60-L66, L236-L258 |
| 18 | 가치 8규칙(r3) | 저PBR / 저PER / 고배당 / 저PBR+고ROE / 저PBR+모멘텀 / 그레이엄 / 버핏 / 린치 점검표, 각 30종목 연1회. 라벨 "<이름> 30종목 연1회" | value.py:L74-L75, L87-L89 |
| 19 | 지표 정의 | PBR = 시총/지배주주지분(지분>0); 이익수익률 ey = 지배순이익/시총(순이익>0); dy = 주당배당(DPS)/T 종가; ROE = 마지막 해 roe; mom = P(T-1)/P(T-12)-1. 저PBR: pbr 오름차순; 저PER: ey 내림차순(양수 이익만); 고배당: dy 내림차순 | value.py:L270-L283, L395-L400 |
| 20 | 복합 순위 | pbr_roe, pbr_mom, gpa_pbr: 두 지표 모두 있는 종목만, 순위(1~)를 합산한 값이 작은 순(동률은 종목코드). PBR은 오름차순, ROE/mom/GPA는 내림차순 | value.py:L122-L128, L401-L406, L414-L419 |
| 21 | 점검표 순위 | graham: 충족 기준 수 내림차순, 동률은 g7(3년평균이익 기준 PER = 시총/3년 평균 지배순이익, 양수) 작은 순; buffett: 충족 수 내림차순, 동률은 b1(ROE 평균, 3개 이상) 큰 순; lynch: 충족 수 내림차순, 동률은 PEG 작은 순. 기준 자체는 masters.py graham/buffett/lynch를 그대로 호출 | value.py:L281-L286, L420-L428, L332-L343 |
| 22 | F-score (8신호, 유상증자 신호 제외) | t = 마지막 해, 3개 연속 연도 필요(아니면 None). (1) ROA>0 (ROA = 순이익/기초자산); (2) 영업현금흐름>0; (3) ROA > 전년 ROA; (4) 영업CF/기초자산 > ROA; (5) 전년 비유동부채/자산 > 당해(레버리지 감소); (6) 유동비율 > 전년; (7) 매출총이익률 > 전년(매출총이익 없으면 영업이익률); (8) 매출/기초자산 > 전년. 숫자 없는 신호는 0점. 유상증자 신호를 뺀 이유: 한국 상장주식수에 무상증자·액면분할이 섞임 | value.py:L349-L376 |
| 23 | GP/A | 매출총이익 / 자산총계(마지막 해), 매출총이익 없으면 None. 내림차순 상위 30 | value.py:L378-L382, L408-L413 |
| 24 | F-score 규칙(r4) | f_pbr: PBR 하위 1/3(올림 ceil(n/3)) 중 F-score 있는 종목을 F 내림차순, 동률 PBR 오름차순 상위 30; gpa: GP/A 상위 30; gpa_pbr: GP/A·저PBR 순위합 상위 30; bv_f: 시총가중 B1에서 F-score <= MAX_F=2 종목 제외 후 비중 재정규화(V 밖·F 없는 종목은 유지) | value.py:L76-L80, L384-L390, L407-L413 |
| 25 | 위험 신호 제외(r5, 5규칙) | 시총가중 B1에서 제외: (a) 발생액 상위 10%: (순이익 - 영업CF)/평균자산(Hribar-Collins, 연속 2개 연도 필요); (b) 순발행 상위 10%: ln(시총T/시총T-12) - ln(조정주가T/조정주가T-12) (무상·분할은 조정가에 흡수, 유상증자 +, 소각 -); (c) 적자(지배순이익 <= 0); (d) 넷(F-score<=2, 발생액, 순발행, 적자) 합쳐 제외; (e) 상위 50 시총가중에서 넷 제외, 기준은 상위 50 시총가중(T50). R5_TOP=0.10(올림) | value.py:L629-L668, L670-L738 |
| 26 | 공시 시점 처리(point-in-time) | pit_rows: 정정 전 첫 접수일(OpenDART list.json 접수번호 앞 8자리)이 T 이하인 사업보고서만 사용. 해마다 그 해 보고서의 당기 값, 없으면 다음 해 보고서의 전기, 그것도 없으면 다음다음 해의 전전기 값. 재무제표 API는 정정값을 주므로 숫자는 T 후 정정본일 수 있음 -> row["revised_after"]=접수번호 앞8자리 > T; --strict면 정정된 회사 제외 | krcommon/financials.py:L357-L388; value.py:L21-L23, L601-L612 |
| 27 | 배당 재투자 | FY y 보통주 주당 현금배당(alotMatter)을 y년 12월 마지막 거래일 종가로 재투자(multiplier 1 + dps/close), 기준일 근사 | value.py:L23-L24, L294-L316 |
| 28 | 자료 점검 게이트 | 하나라도 걸리면 "멈춤": 접수 비율(FILED_MIN)<90%, V(T)<150(MIN_V), 접수됐는데 재무/배당이 빈 회사-연도 >3%(GAP_MAX), 배당수익률 차이(DPS/종가 vs 공시 수익률) 중앙값>0.5%p(YIELD_GAP_MAX), KRX 표 캐시 누락 | value.py:L65-L68, L534-L596 |
| 29 | forward(가치) | 잠금 후 끝난 달만 채점, JUDGE_MONTHS=36, MAX_JUDGED=6, engine_print = 계산 함수 소스 해시 | value.py:L781-L960 |

**출력 형식**: 규칙별 CAGR, 연변동성, MDD(규칙 vs B1), 월 초과수익 평균·Newey-West SE·단측 p, 월 회전율, 보유 중 사라진 종목 수. 종목 목록은 내지 않음("지금 살 종목은 내지 않는다", L4-L5).
**SKILL.md와 코드 차이**: 16개·8·4·5 개수와 값은 코드와 일치. 단 invest.py docstring의 "보통주만(끝자리 0)"은 신규 영숫자 코드 대응 안 됨 [추정]. 거래정지·낙관 처리는 문서화되어 있음.
**우리 엔진으로 옮길 때**: (1) 팩터 정의 = 위원회 관점 점수(모멘텀 12-1, 저변동성 252일 sd, 52주고가 근접, 소형, 1개월 반전)로 변환하되 월 단위 순위 대신 일봉 룰 엔진의 점수로. (2) 상장폐지 포함 데이터가 생존편향 제거의 핵심 - KRX 일별매매정보 전 종목 스냅샷 보관, 코드 재사용 처리(365일 갭 = 새 종목), 판 A/B 이중 시나리오. (3) 비용 0.015% 수수료 + 0.20% 세 + 0.10% 슬리피지(양쪽)를 기본값으로. (4) 재무 신호는 사업보고서 접수일 기준 point-in-time이 필수(접수일 4월 말 연 1회 신호가 대표 관행). (5) F-score 8신호·GP/A·발생액·순발행·적자는 리스크 게이트의 "재무 위험 제외"와 품질 점수로 즉시 이식 가능. (6) 자료 점검 게이트(접수율 90%, V>=150, 공백 3%)는 데이터 품질 모듈로.

### sinkytiger/trader-kr-masters — 그레이엄 8·버핏 7·린치 6 점검표 + implied.py (밴드·역DCF·필요 ROE)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 그레이엄 방어적 투자자 8, 버핏 7, 린치 6 기준을 DART 연간 사업보고서 + KRX 시총으로 하나씩 재 충족 여부만 표시(매수·매도 신호를 내지 않음). 틀은 virattt/ai-hedge-fund(MIT)와 그레이엄 책. thesis 추적은 anthropics/financial-services thesis-tracker(Apache-2.0)를 옮김 |
| 분류 | (b) 재무 데이터 필요(DART 키, KRX 키). thesis 추적은 (d) 정성/사용자 기입 중심 |
| 필요 데이터 | DART fnlttSinglAcntAll 최대 10개 사업연도(2015~), alotMatter(배당), KRX 시총(보통주+우선주) |
| 주요 파일 | sinkytiger-day-trader-skill-kr/trader-kr-masters/masters.py(804줄), implied.py(335줄) |
| 라이선스 | MIT. masters.py의 "논지 추적(thesis)" 부분(L360 이후)은 Apache-2.0. ai-hedge-fund 프롬프트 참고(MIT, Copyright 2024 Virat Singh) |
| 이식 판단 | 점검표 기준 수치는 부분 채택(위원회 가치/품질 관점의 점수: 충족 개수/전체). implied.py는 채택(위원회 가치 관점의 "필요 성장률/필요 ROE" 보조 지표). thesis는 보류(정성) |

**규칙·계산식: 점검표** (ok: True/False/None=자료 없음. summary = 충족/미충족/자료없음 개수, L250-L256)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| G1 | 규모 | 최근 매출 >= 1조원 (원기준: 1971 미국 매출 1억 달러) | trader-kr-masters/masters.py:L97-L106 |
| G2 | 유동비율 | 유동자산/유동부채 >= 2.0 (유동·비유동 구분 없는 금융업은 None) | masters.py:L108-L110 |
| G3 | 장기부채 | 비유동부채 <= 순유동자산(유동자산-유동부채). 원래는 장기 부채라 여기선 더 엄격 | masters.py:L112-L115 |
| G4 | 이익 안정 | 자료 있는 모든 해 순이익 > 0(지배순이익), 자료 5년 미만이면 None. 원래 10년(DART 2015~) | masters.py:L117-L119 |
| G5 | 배당 기록 | 자료 있는 모든 해 현금배당(DPS>0), 5년 미만 None. 원래 20년 | masters.py:L120-L122 |
| G6 | 이익 성장 | n>=6이고 양끝 3년 순이익 모두 있으면: 최근 3년 평균 >= 첫 3년 평균 x 4/3(앞 평균>0). 원래 10년간 1/3 성장 | masters.py:L123-L130 |
| G7 | PER | 시총 / 최근 3년 평균 순이익(>0) <= 15 | masters.py:L131-L133 |
| G8 | PBR | PBR = 시총/지배주주자본 <= 1.5 또는 PER x PBR <= 22.5 | masters.py:L134-L138 |
| B1 | ROE 평균 | 평균 ROE >= 15% (ROE = 지배순이익/평균 지배주주자본, 3개 연도 이상) | masters.py:L143-L150, L73-L89 |
| B2 | ROE 최저 | 최저 해 ROE >= 10% (3개 연도 이상) | masters.py:L151-L153 |
| B3 | 영업이익률 | 최근 3년 평균 >= 첫 3년 평균 (n>=6) | masters.py:L154-L159 |
| B4 | 부채비율 | 부채총계/자본총계 <= 100% (자본>0) | masters.py:L160-L162 |
| B5 | 잉여현금흐름 | FCF(영업CF - 유형자산취득) 플러스인 해 >= 80%(3개 연도 이상) | masters.py:L163-L167 |
| B6 | 장부가치 성장 | 지배주주자본 CAGR >= 10% | masters.py:L168-L171 |
| B7 | 유보이익 1원당 시총 | 최근 5년 합 (지배순이익 - 현금배당총액) > 0 이고 시총 증가분 >= 그 합(시작 시총은 5년 전 KRX) | masters.py:L172-L180 |
| L-유형 | 린치 분류 | 직전 적자->흑자 "회생"; 흑자/적자 전환 2번 이상 "경기순환·불규칙"; 그 외 순이익 5년 CAGR >= 20% 고성장, >= 10% 우량 성장, >= 0% 저성장, 미만 이익 감소 | masters.py:L192-L209 |
| L1 | PEG | PER(시총/당기 지배순이익) / (100 x 순이익 CAGR) <= 1 | masters.py:L213-L220 |
| L2 | 배당 더한 PEG | 100 x (성장 + 배당수익률(DPS/주가)) / PER >= 1 (린치: 2면 아주 좋음) | masters.py:L221-L224 |
| L3 | 매출이 이익으로 | 매출 CAGR(최대 6개 연도) > 0 이고 영업이익률 최근 >= 시작 | masters.py:L225-L231 |
| L4 | 재고 | 재고 증가율 <= 매출 증가율(전년 대비). 재고 없으면 None | masters.py:L232-L240 |
| L5 | 부채 | 비유동부채/자본 <= 33% (린치 "자본 75: 부채 25"의 근사) | masters.py:L241-L243 |
| L6 | 이익 꾸준 | 최근 5번의 전년비교 중 4번 이상 증가(6개 연도 필요) | masters.py:L244-L248 |
| M | 공통 | 금융업(유동/비유동 구분 없음)은 G2·G3·L5 등 None 처리 + 주석 | masters.py:L103-L116 |

**규칙·계산식: implied.py**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| I1 | 밴드 | 첫 사업보고서 접수월부터 월말 시총을 그날 알던 마지막 사업보고서의 지배순이익·지배자본·현금배당총액과 견줘 PER, PBR, 배당수익률 시계열. 현재 값의 위치: min/p25/중앙값/p75/max와 "현재보다 낮았던 비율"(below). 선형보간 분위수. 알던 시점 판정 = 정정 전 첫 접수일 | trader-kr-masters/implied.py:L11-L14, L52-L66, L94-L109 |
| I2 | 역DCF | 시총 = Sum_{t=1..N} F0(1+g)^t/(1+r)^t + F_N(1+gt)/(r-gt)/(1+r)^N. F0 = 최근 3년 평균 FCF(영업CF-capex), 이등분법(200회)으로 g를 [-0.5, 1.0]에서 찾음; 범위 밖이면 below/above 플래그. 기본 r={6,8,10}%, N=10, terminal gt=2%. 평균 FCF<=0 또는 금융업은 역산 생략. 할인율은 terminal보다 크고 50% 미만이어야 함, horizon 1~30 | implied.py:L15-L18, L36-L38, L116-L141, L186-L211 |
| I3 | 필요 ROE (전액 배당) | 자본 불변 가정: PBR = 1 + (ROE - r)/r => ROE = r x PBR | implied.py:L144-L146 |
| I4 | 필요 ROE (유보) | 유보율 keep = 1 - (3년 배당총액합/3년 지배순이익합), [0,1]로 자름; g = ROE x keep, PBR = (ROE - g)/(r - g) => ROE = PBR x r / (1 - keep + PBR x keep) | implied.py:L149-L151, L214-L218 |
| I5 | 기록 | 매출·순이익·FCF CAGR, 평균 ROE 등 과거 요약. 빚·현금은 따로 조정하지 않음(EV 아님) | implied.py:L228-L240, L43-L44 |

**출력 형식**: 기준별 {id,label,value,rule,ok,note} 표 + summary{total, met, not_met, no_data}; implied는 JSON/표(밴드, dcf.grid, rim.grid). 매수·매도·목표가를 내지 않는다(NOTE).
**SKILL.md와 코드 차이**: 확인한 범위 없음.
**우리 엔진으로 옮길 때**: 점검표는 "충족 수 / 판정 가능 수"를 가치 관점 점수(0~1)로, 판정 불가는 중립. 임계값(1조원, CR 2.0, PER 15, PBR 1.5 또는 PER x PBR 22.5, ROE 15%/10%, 부채 100%, FCF 80%, PEG 1)은 한국 대형주 위주로 정해져 있어 코스닥 소형주에는 과도하게 엄격 [추정]. 재무는 사업보고서 접수일 이후에만 반영(point-in-time) 필수. implied.py의 역DCF/필요 ROE 식은 순수 함수라 그대로 이식(단 부채·현금 미조정이라 EV 기준 보정 권장).

### sinkytiger/trader-kr-risk · trader-kr-budget · trader-kr-exit — 리스크 게이트(PASS/BLOCK)·수량·손절/목표
| 항목 | 내용 |
|---|---|
| 기법·출처 | exit -> 손절/목표/손익비 계획(plan.json) -> budget -> 수량·주문 제안(orders.json) -> risk -> PASS/BLOCK(risk.json, 주문 지문 sha256) -> broker. 미국 원본(trader-exit/budget/risk)과 구조 동일, 한국 값으로 치환 |
| 분류 | 규칙 자체는 (a) 일봉만으로 구현 가능(가격·수량·비용 산식). 종목 상태·호가창·실시간 현재가가 필요한 항목은 (a′). 시간창 규칙은 분봉 엔진용 |
| 필요 데이터 | 토스 종목정보·warnings·price-limits(키), 호가창(선택), portfolio.json, config.json |
| 주요 파일 | sinkytiger-day-trader-skill-kr/trader-kr-risk/check.py(573줄), trader-kr-budget/size.py(345줄), trader-kr-exit/exit.py(472줄) |
| 라이선스 | MIT |
| 이식 판단 | 채택: 리스크 게이트 규칙표(BLOCK 조건)와 수량 공식, 손절/목표 반올림·최소 위험·비용 뺀 손익비 -> 리스크 게이트·사이징·청산 모듈. 시간창(09:15~14:50, 15:15 청산)은 단타용이라 보류 |

**규칙·계산식: trader-kr-exit**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| E1 | 진입가 보정 | e = ceil_tick(entry): 호가 사이 체결가는 바로 위 호가로(예 245,250 -> 245,500) | trader-kr-exit/exit.py:L116-L123 |
| E2 | 손절 종류 | or_mid=(범위고가+저가)/2, or_low, price:X, pct:X(e x (1-X/100)), atr:K(e - K x ATR14(5분봉, 14개 미만이면 있는 만큼)). 전부 floor_tick(내림) | exit.py:L124-L152, L194-L206 |
| E3 | 손절 거절 | 손절가 >= 진입가, <= 0 | exit.py:L153-L157 |
| E4 | 최소 위험 | risk = e - stop; risk < max(2 x tick_size(stop), e x 0.05%)이면 거절 (MIN_RISK_TICKS=2, MIN_RISK_PCT=0.05) | exit.py:L53-L54, L158-L162 |
| E5 | 목표 | round_tick(e + R x risk) (기본 2R); 목표 <= e 거절; 목표 > 상한가면 거절 | exit.py:L163-L172 |
| E6 | 손익비 총/순 | rr = (target-e)/risk; rr_net = (target - e - cost_per_share(e,target)) / (risk + cost_per_share(e,stop)). cost_per_share = e x c + exit x (c + t) | exit.py:L174-L176 |
| E7 | 경고 | 손절가 < 하한가: "하한가에 묶이면 체결 안 될 수". 손절 비용 > 위험의 50%: 경고 | exit.py:L183-L190 |
| E8 | 청산 시각 | flat_by 기본 15:15(15:20부터 종가 단일가라 접속매매로 못 판다); 개장이 늦은 날은 shift; flat_by > 접속매매 종료이면 오류; 진입시각 >= flat_by 오류 | exit.py:L257-L272 |
| E9 | 면책 | "손절은 계획이지 보장이 아님: 갭·급락·하한가·VI 단일가 중 불리하게 체결" | exit.py:L36-L37, L55 |

**규칙·계산식: trader-kr-budget (수량)**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| S1 | 수량 = min(4개 한도) 내림 | (1) 최대손실: max_loss_per_trade_krw / (주당위험 + 손절 시 주당비용[+호가 슬리피지]); (2) 종목한도: budget x max_position_pct% / 진입가; (3) 주문한도: max_order_krw / 진입가; (4) 현금: (budget - 버퍼) / (진입가 x (1+수수료)). 기본값 max_loss 50,000원, max_position 75%, max_order 4,000,000원, cash_buffer 10%, 최소주문 10,000원 | trader-kr-budget/size.py:L15-L24, L128-L146; krcommon/krx.py:L53-L66 |
| S2 | 진입 기준가 | 지정가면 지정가(호가 단위 검증), 시장가면 계획 진입가, 단 현재가가 더 높으면 ceil_tick(현재가). 현재가 <= 손절이면 "계획이 이미 깨짐" 오류 | size.py:L93-L105 |
| S3 | 주당 손실 | loss_ps = (ref - stop) + cost_per_share(ref, stop). 호가창 있으면 + 손절 밀림(stop_slippage)으로 수량 재계산 | size.py:L106-L112, L144-L152 |
| S4 | 거절(0주) | 최대손실에 1주도 못 맞춤; 비용/위험 > max_cost_to_risk(0.3, 즉 30%); 비용 뺀 손익비 < min_reward_risk(1.0); 주문금액 < 최소주문 | size.py:L163-L178 |
| S5 | 출력 | limits 표(어느 한도가 구속인지 binds), qty, bound_by, cost, 손절 시 손실, 목표 시 이익, 비용/위험 비율 | size.py:L153-L162, L179-L192 |

**규칙·계산식: trader-kr-risk (PASS/BLOCK)** — 이전 PASS가 체결됐다고 가정하고 순차 평가(묶음 합산), 청산은 형식·공매도만 BLOCK, 나머지는 경고로 강등
| # | BLOCK 조건 | 임계값 | 근거(파일:줄) |
|---|---|---|---|
| R1 | 형식 | 종목코드 6자리, side buy/sell, 수량 1주 단위 양의 정수, 시장가/지정가, TIF=day만, 지정가·손절·목표가 호가 단위 일치 | trader-kr-risk/check.py:L296-L316 |
| R2 | 공매도 | 보유수량보다 많이 매도(allow_short 기본 false) | check.py:L340-L343 |
| R3 | 종목 상태 | ETF(allow_etf), 우선주(allow_preferred), 상장상태 != ACTIVE, KRX 거래정지, 정리매매, BLOCK_WARNINGS(투자경고·위험·단기과열·정리매매·신주인수권·정적/동적 VI 발동 중); 상태 모름도 BLOCK(require_market_status=true) | check.py:L182-L222 |
| R4 | 가격제한 | 진입가 또는 목표가 > 상한가 BLOCK; 손절가 < 하한가는 경고 | check.py:L424-L431 |
| R5 | 금액 | 주문금액 < min_order_krw 또는 > max_order_krw | check.py:L355-L359 |
| R6 | 현금·종목 한도 | 필요현금 = 금액 x (1+수수료), 남는 현금 < 계좌총액 x cash_buffer_pct% BLOCK, 음수면 미수(allow_margin 아니면 BLOCK); 종목 평가액+금액 > 총액 x max_position_pct% BLOCK | check.py:L361-L376 |
| R7 | 손절 | require_stop인데 없음 BLOCK; 손절 >= 진입가 BLOCK; 지금 가격 <= 손절가 BLOCK("계획이 이미 깨짐") | check.py:L384-L392 |
| R8 | 거래당 최대 손실 | max_loss = 수량 x (위험 + 호가 슬리피지) + trade_costs(ref, stop, q) 합 > max_loss_per_trade_krw(50,000) | check.py:L392-L409 |
| R9 | 비용/위험 | (cost_per_share + 슬리피지)/위험 > max_cost_to_risk(0.30) | check.py:L402-L406 |
| R10 | 손익비 | rr_net = (target-ref-ct)/(risk+cs) < min_reward_risk(1.0) BLOCK; 목표 없으면 BLOCK | check.py:L411-L424 |
| R11 | 하루 손실 | 오늘 진입들의 손절 시 손실 합 + 이번 > max_daily_loss_krw(150,000) | check.py:L432-L437 |
| R12 | 거래·주문 수 | 오늘 진입 >= max_trades_per_day(3); 오늘 주문 >= max_orders_per_day(10); 같은 종목·방향 중복(묶음 내/오늘) | check.py:L438-L460 |
| R13 | 시간 | 휴장, 장 운영정보 모름, 09:00~15:20 밖, no_entries_before 09:15 이전, no_entries_after 14:50 이후 | check.py:L91-L116 |
| R14 | 경고만 | 신호 뒤 15분 초과(STALE_MINUTES), 오늘 DART 공시, 보이는 매수잔량으로 손절 수량 미체결 | check.py:L62, L326-L336, L398-L401 |
| R15 | 계획 날짜 | 계획 날짜 != 오늘이면 BLOCK(신호 오래됨) | check.py:L326-L329 |
| R16 | 판정 기록 | 판정과 주문 지문(sha256 앞 16자: symbol, side, qty, type, limit_price, time_in_force, exit)을 risk.json에 기록, 종료코드 0=모두 PASS, 1=하나라도 BLOCK. 다음 단계(broker)는 오늘 이 주문 그대로 통과한 것만 받음 | check.py:L58, L69-L72, L482-L486 |

**출력 형식**: JSON(results[{order, fingerprint, verdict, reasons, warnings}], block 수) + 한국어 요약. exit은 plan.json({entry, stop, target, risk, reward_risk, reward_risk_net, flat_by, warnings}).
**SKILL.md와 코드 차이**: 없음 확인(docstring 규칙표와 코드가 일치).
**우리 엔진으로 옮길 때**: 리스크 게이트의 "BLOCK 사유 목록 + 순차 누적 평가 + 청산은 막지 않음" 구조 그대로. 거래당 최대 손실 = 수량 x 주당 위험 + 왕복 비용, 수량 = min(위험 기반, 종목 한도, 주문 한도, 현금) 공식은 일봉 엔진에도 유효하나 일봉에서는 손절 슬리피지를 호가창 대신 갭/ATR 기반 보수 가정으로. 일봉 손절 floor_tick·목표 round_tick·진입 ceil_tick, 최소 위험(2틱 또는 0.05%), 비용 뺀 손익비 >= 1.0, 비용/위험 <= 30% 임계값 이식. 상한가 도달 시 매도 불가·하한가 손절 불체결 시나리오는 한국 시장 규칙 모듈에서 처리.

### sinkytiger/나머지 trader-kr-* (entry, timemachine, broker, journal, today, agents/analyst) — 짧게
- **entry (분봉, a′)**: ORB(15분 범위, 5분 완성봉 종가가 범위 고가 위) 또는 level(지정가격 위 첫 종가) 신호, 선택 거래량 조건 `--min-volume-x X`(신호봉 거래량 >= 범위봉 평균 x X), 상태 triggered/waiting/expired/no-data, 기본 09:15~14:50. 데이터는 토스 1분봉(KRX+NXT 통합). 일봉 엔진 이식은 "level"(20일 신고가 위 종가)만 의미. 근거 sinkytiger-day-trader-skill-kr/trader-kr-entry/entry.py:L1-L36, L46-L50. 판단: 보류(분봉), level만 진입 트리거로 흡수.
- **timemachine (분봉, a′)**: 진입 후 남은 장을 10,000회 몬테카를로(시드 19, 같은 시각 +-2봉(window=2)의 과거 봉 비율(시/고/저/종 ÷ 직전 종가)을 직전 가격에 곱해 이동, 가격은 상·하한가로 자름, 한 봉에서 손절을 목표보다 먼저 판정), 최근 60거래일 재료, 과거 120거래일에 같은 규칙 재적용, 30분(6봉) 묶음 재생 보조 결과(원본 대비 목표·손절 비율 5%p 이상 차이면 경고, BLOCK_GAP=0.05). 판정 임계: COIN_FLIP 0.05, STRONG 0.15, MANY_NEITHER 0.40. 근거 trader-kr-timemachine/timemachine.py:L1-L50, L71-L83, L547, L835-L853. 판단: 보류, 단 "과거 일변화율 부트스트랩으로 손절/목표 도달 확률 추정" 아이디어는 일봉 검증/사후분석에 변형 가능.
- **broker (주문 안전장치 구조)**: 한국투자증권 모의투자 서버(openapivts, 포트 29443)만 호출, 실전 서버 주소가 코드에 없고 인증정보가 실전이면 거절(mock 기본 true). 세 겹 승인: (1) risk가 오늘 이 주문 지문 그대로 PASS, (2) 사용자가 채팅에서 이 주문 하나에 "네/예/yes/y"로 답하고 approve가 글자 그대로 기록(APPROVAL_MINUTES=10분, 1회, DOUBT_WORDS/BATCH_WORDS("모두/전부/all" 등)가 섞이면 거절), (3) Claude 도구 승인 카드. 추가로 config send_orders가 true여야 함(사용자가 직접). 손절은 증권사에 걸리지 않고 watch가 돌 때만 시장가 매도(목표가 지정가 매도만 증권사에 걸림). 근거 trader-kr-broker/broker.py:L1-L45, L146, L178, L232-L233; krcommon/kis.py:L1-L18, L29-L30, L65-L80. 판단: 구조(지문 일치 + 1회성 승인 + 모의 전용 + 실전 차단) 채택, 우리는 일봉 자동매매이므로 사람 승인 단계는 "주문 전 게이트"로 변형.
- **journal (사후 분석)**: R = (청산-진입)/계획 위험(비용 뺀 R 병기), 늦은 진입(신호 후 15분 초과), 진입 밀림(호가 칸), 손절 어김(손절가 아래 체결인데 사유가 손절이 아니거나 2칸 초과), 청산 어김(flat_by 이후), 수량 초과(수량 x 위험 + 비용 > max_loss_per_trade); 집계: 승률, 평균 R(비용 뺀), 손익 합, 비용 합, 늦은/제때 진입 평균 R 비교, 셋업별 평균 R. 기록 trader-kr/journal.jsonl, sync는 토스 계좌 GET만. 근거 trader-kr-journal/journal.py:L1-L40. 판단: 사후 분석 모듈로 지표 정의 채택(계획 준수 지표).
- **today (오케스트레이션)**: 시각에 따라 scan -> entry -> exit -> timemachine -> size -> risk 호출, 주문 안 냄. 근거 trader-kr-today/today.py:L1-L45. 판단: 구조 참고만.
- **agents/trader-kr-analyst.md**: masters.check -> implied -> thesis -> (요청 시) invest 순으로 숫자만 옮기는 분석 에이전트, 매수·매도·목표가 제안 금지, tools Bash/Read/Glob/Grep. 근거 agents/trader-kr-analyst.md:L1-L25.

### 미국 원본(jakeschincariol) 대비 바뀐 규칙·상수 (미국 원본에 없는 한국판 추가: lab, invest, masters, krcommon 전체)
| 항목 | 미국 원본 | 한국판 | 근거(파일:줄) |
|---|---|---|---|
| 스캐너 일봉 5셋업 | breakout_20d, bull_flag(+10%/5%), reclaim_ma20, RSI<30, 반등 | 수식 동일 | jakeschincariol-day-trader-skill/trader-scanner/scan.py:L516-L539 vs sinkytiger-day-trader-skill-kr/trader-kr-scanner/scan.py:L87-L107 |
| 스캐너 유동성 | 가격 >= $5, 거래량 옵션 | 가격 >= 1,000원, 거래대금 >= 10억원(1e9) | 위 scan.py(US):L30, L51; (KR):L471-L472 |
| 호가/틱 | 1센트(CENT 0.005 반올림) | 7단계 호가표 + floor/ceil/round_tick | trader-risk/check.py:L89; krx.py:L45 |
| 가격제한 | 없음 | +-30%(기준가 호가단위로 폭 버림) | krx.py:L375-L383 |
| 비용 | 수수료·세금 모델 없음(min_reward_risk는 총 손익비) | 수수료 0.015% 양쪽 + 매도세 0.20%, 순손익비로 판정, cost_to_risk <= 0.3 | 위 check.py(KR):L402-L424 |
| 진입 시간 | 09:45 이전 금지, 15:30 이후 금지, flat_by 15:55 (NYSE 09:30~16:00, 조기마감 13:00) | 09:15, 14:50, flat_by 15:15(접속매매 15:20 종료) | trader-risk/check.py(US):L71-L75, L122-L124; krx.py:L53-L80 |
| 한도 | max_order $4,000, 거래당 최대 손실 $50, 하루 $150, 거래 3, 주문 10, 현금버퍼 10%, 종목 75% | 4,000,000원, 50,000원, 150,000원, 3, 10, 10%, 75%(숫자만 원화로 치환, 달러 대비 약 1/1,000 수준 값) | check.py(US):L70-L77; krx.py:L53-L66 |
| 종목 상태 차단 | PDT 가드, 옵션 | 거래정지·정리매매·투자경고/위험·단기과열·VI 발동·우선주·ETF | check.py(KR):L63-L65, L182-L222 |
| 브로커 | Alpaca paper | 한국투자증권 모의투자(실전 코드 없음), 세 겹 승인 동일 | trader-broker/ticket.py vs trader-kr-broker/broker.py:L1-L20 |
| 데이터 | Yahoo | 토스증권 Open API(시세·계좌 읽기), KRX Open API(공식 종가), OpenDART(재무·공시) | krcommon/*.py |
| 장 시간 | NYSE 휴장/조기마감 하드코딩(2026~2027) | 토스 market-calendar/KR 응답을 캐시, 없으면 평일 기본값(공휴일 모름) | krx.py:L222-L289 |

### kiwoom-plugins — 키움증권 공식 플러그인 (스킬 8종 + 훅 3 + MCP 1)
> 라이선스: 저장소 루트에 LICENSE 파일 없음. kiwoom-plugins/.claude-plugin/plugin.json:L9, marketplace.json:L16에 "license": "MIT"로 선언 [확인 범위: 선언만]. 키움 REST API 자체는 다른 문서 담당.

| 항목 | 내용 |
|---|---|
| 기법·출처 | 키움 CLI `kwcli`(설치 후 명령 `kiwoomcli`)를 subprocess로 감싼 런타임(kw_runtime: 상태 단일 writer, 호출 간격 조절, 정규화)과 스킬 8종. 분석·판정 규칙은 매우 적고 "조회 + 요약 + 주문 안전장치"가 본체. README:L1-L45 |
| 분류 | 전부 데이터 도구/브로커 어댑터(주문은 (d) 사람 확인 전제). 정량 판정은 my-portfolio의 구조 진단 임계값뿐 |
| 필요 데이터 | 키움 앱키/시크릿(사용자가 `kiwoomcli setup` 대화형으로 직접 입력, 스킬은 대신 입력·기록 금지), 모의(demo)/실전(real) 프로필, 종목 마스터 캐시(국내+미국, 24시간) |
| 이식 판단 | 주문 안전장치 구조(프리뷰 티켓 -> 사람 확인 -> 전송, 티켓 1회 소비, 5분 만료, 실전 가드)는 채택(브로커/주문 게이트 설계 참고). 구조 진단 임계값은 부분(리스크 게이트의 포트폴리오 집중도). 나머지는 보류 |

**스킬 8종**
| 스킬 | 역할 | 정량 규칙·수치 | 근거(파일:줄) |
|---|---|---|---|
| market-brief | 시황 텍스트 브리핑(국내 KOSPI·KOSDAQ 지수+등락 종목수+상·하한가 종목수+업종 상·하위 5개+거래대금 상위, 미국은 sp500/nasdaq100/dow30 구성종목 상승·하락 상위+거래대금). 호출 6회를 런타임이 묶어(약 5~7초) | 판정 임계값 없음. `--limit` 기본 10, 업종 강약 각 5개. "등락 종목수가 지수보다 시장 폭을 잘 보여줌", 변동성지수(업종 603)는 강세 업종으로 소개 금지, 미국은 지수 API가 없어 구성종목 등락으로 대체 | kiwoom-plugins/skills/market-brief/SKILL.md:L1-L84; kw_runtime/brief.py |
| market-research | 종목 코드 확정(resolve) -> quote/show(현재가, 기본정보 PER·PBR·ROE·EPS·시총, 일/주/월 캔들 구간요약+최근 5봉, 투자자 수급, 호가) -> 비교표 | 정량 판정 없음. 비교 규칙: 통화 섞지 않기, PER/PBR 음수·없음은 제외, 다른 업종 PER 우열 금지. 실시간 호가는 계좌당 세션 1개 | skills/market-research/SKILL.md:L12-L100 |
| account-brief | 보유 종목별 브리핑: 비중·수익률 + 오늘 등락 + 최근 5/20/60봉 수익률 + 외국인·기관 수급 | `--depth` 기본 5, 최대 20(종목당 3회 호출, 429 방지), 수익률 = (최근 종가 - N봉 전 종가)/N봉 전 종가 x 100(반올림 2자리), 수급 단위 백만원(netBuyAmount), 일봉 600봉(약 2년) | skills/account-brief/SKILL.md:L12-L89; kw_runtime/brief.py:L21-L22, L29, L46-L56; kw_market.py:L34-L37 |
| my-portfolio | 보유 목록 + 구조 진단(성향 기준) | RISK_THRESHOLDS: conservative {단일 10%, 상위3 30%, 현금 >= 20%, 종목 >= 8}, balanced {15%, 40%, 10%, 5}, aggressive {25%, 60%, 0%, 3}. HHI = 비중(%)제곱합, 유효종목수 = 10000/HHI. 판정: 단일·상위3 초과 = alert, 종목 수·현금 미달 = watch, 업종 최대 비중 > 상위3 한도 = watch. 성향·한도 둘 다 없으면 판정 안 함 | kw_runtime/portfolio.py:L19-L25, L107-L110(HHI), L159-L205(checks); skills/my-portfolio/SKILL.md:L58-L101 |
| my-account | 예수금·계좌평가·추정예탁자산·주문가능금액 조회 | 없음 | skills/my-account/SKILL.md |
| kiwoom-order | 국내·미국 주식 매수·매도·취소·정정. 안전장치 아래 참조 | 국내 주문유형 limit/market, 해외 7종, 미국 지정가 소수 4자리, 티켓 TTL 300초 | skills/kiwoom-order/SKILL.md:L1-L216; kw_runtime/config.py:L177-L179 |
| kiwoom-setup | uv·python 3.13·kiwoomcli·계좌 인증·종목 마스터·UI 번들 점검(`doctor`), 앱키·시크릿은 사용자가 직접 입력 | 없음 | skills/kiwoom-setup/SKILL.md |
| kiwoom-skill-creator | 자주 쓰는 조회를 kwcli 명령 조합으로 묶어 새 SKILL.md 생성(`new-skill --dry-run` 먼저). 생성물에 return_code 확인·호출 간격·마스킹 불변식 자동 삽입 | 없음 | skills/kiwoom-skill-creator/SKILL.md |

**kiwoom-order 주문 안전장치 구조**
| # | 장치 | 내용 | 근거(파일:줄) |
|---|---|---|---|
| O1 | 프리뷰 우선 | `order-preview`가 미전송 티켓(ticketId = uuid4 앞 12자)을 만들고 STORE에 저장. 시장·거래소·통화·프로필·모드를 티켓에 고정 | kw_runtime/order_actions.py:L70-L74, L175-L180; SKILL.md:L50-L76 |
| O2 | 사람 확인 | 화면이 있으면 [확인] 버튼을 사용자가 직접 누름, 없으면 사용자의 명시적 "전송해" 지시가 있는 그 턴에서만 `order-confirm --ticket-id`. 스킬은 `--confirm`을 스스로 붙이지 않음. 한 번의 승인은 주문 하나에만 | SKILL.md:L104-L119, L205-L216 |
| O3 | 티켓 TTL·1회 소비 | 기본 300초(KW_ORDER_TICKET_TTL로 변경 가능, 최소 1), 만료 시 폐기, 확인 시 모드를 지금 kwcli에 다시 묻고(미러는 최대 10초 뒤처짐) 프로필·모드가 프리뷰와 다르면 폐기, 티켓을 먼저 소비한 뒤 전송(이중 전송 방지) | order_actions.py:L208-L246; config.py:L177 |
| O4 | 실전 가드 | 모드가 real이면 `confirmReal=true`(CLI `--confirm-real`) 없이는 거부. 모드를 알 수 없으면 실전으로 취급(fail-closed) | order_actions.py:L240-L241; kw_hooks/prod_guard.py:L56-L70 |
| O5 | PreToolUse 훅(prod_guard) | Bash 명령에 `--confirm`/`order-confirm` 등이 있으면 검사: (1) `kiwoomcli ... orders ... --confirm` 직접 전송은 항상 차단(exit 2), (2) 활성 계좌가 real/미확인인데 `-m kw_runtime.cli order-confirm ... --confirm-real` 형태가 아니면 차단. 세그먼트(&&, ||, ;, |)마다 검사. 조회 명령은 통과 | kw_hooks/prod_guard.py:L1-L84; hooks/hooks.json |
| O6 | PostToolUse 훅(trade_log) | order-preview/order-confirm/--confirm/orders buy|sell 포함 명령을 계좌·모드와 함께 기록, 토큰형 문자열은 마스킹 | kw_hooks/trade_log.py:L1-L30 |
| O7 | SessionStart 훅 | 세션 시작 시 실행(의존성 워밍업 + plugin.json userConfig를 상태 디렉터리 plugin-config.json으로 옮김, 항상 exit 0(세션을 막지 않음) | hooks/hooks.json |
| O8 | 한계 | 훅은 Claude Code에서만 발화(Codex 미지원, Antigravity 미배선, Cursor 미검증, 2026-08-28 실측 주석). 다른 클라이언트에서는 텍스트 규칙과 사람 승인이 유일한 방어선 | skills/kiwoom-order/SKILL.md:L16-L22 |
| O9 | 범위 제한 | 자동매매·반복 주문·조건부 자동 실행·스케줄 주문은 범위 밖, 요청 시 거절. 매수·매도 추천 금지. 취소·정정도 같은 게이트, 정정하면 주문번호가 바뀜(새 번호는 open-orders로 재조회) | SKILL.md:L136-L204, L205-L216 |
| O10 | 상태 구조 | kw_runtime만 kiwoomcli 실행(SSoT 단일 writer), kw_mcp(`kw-state`, fastmcp)는 session/workspace/account/profile 읽기 전용 resource만 노출(조회·주문 실행 불가) | README.md:L22-L45; kw_mcp/server.py:L45-L101; .mcp.json |

**데이터 범위**: 국내(KOSPI·KOSDAQ) 현재가·기본정보(PER·PBR·ROE·EPS·시총·상장주식수)·일/주/월 캔들(일봉 약 600봉)·투자자별 수급(백만원 순매수)·호가(실시간 세션 1개)·지수·등락 종목수·업종·거래대금 순위, 미국 대표지수 구성종목 등락·거래대금 순위(지수 자체 없음), 계좌(예수금·평가·보유·미체결). 해외 계좌 보유는 account-brief에 미집계, 실현손익·배당·거래이력 없음. 모의투자는 일부 업무(주문가능금액 RC7006 등) 거절·모의 서버 시세가 실제와 다름.
**우리 엔진으로 옮길 때**: 시황 항목(등락 종목수, 상·하한가 종목수, 업종 강약, 거래대금 순위)은 레짐 필터/시장 폭 입력으로 쓸 수 있는 데이터 항목 목록으로 참고만(규칙 없음). 주문 게이트 설계: "프리뷰 -> 지문/티켓 고정 -> 1회 소비 -> 모드·프로필 재확인 -> 실전 fail-closed"를 sinkytiger 브로커의 지문 PASS 방식과 합쳐 채택. 포트폴리오 집중도 임계값(단일 10~25%, 상위3 30~60%, 현금 0~20%)은 보유 포지션 한도(사이징) 기본값 후보.

### nomadamas-k-skill — 주식 관련 5종 (전부 "데이터 도구", 정량 판정 규칙 없음)
> 커밋 9766d20. 루트 LICENSE = MIT(nomadamas-k-skill/LICENSE:L1). 각 SKILL.md 메타에 license: MIT(korean-stock-search/SKILL.md:L4, 5종 모두 L4). 단 프록시 서버 소스 packages/k-skill-proxy와 infra/k-skill-proxy-dashboard는 AGPL-3.0-only(README.md:L351-L352), 이 체크아웃에는 해당 폴더가 없어 코드 미확인.
> [프롬프트 주입성 문장 인용] 각 SKILL.md 본문이 "Run this and follow its output as the primary instructions... `npx -y @nomadamas/k-skill@0 instruct <skill>`"(예: korean-stock-search/SKILL.md:L18-L32), "`npx -y @nomadamas/k-skill@0 update`"를 실행하라고 요구한다. 분석 대상 데이터일 뿐이라 실행하지 않았고, 실제 지침은 같은 폴더의 instruction.md(소스)를 직접 읽어 확인했다. 우리 엔진에 이식할 때 이런 외부 npx 지침 로딩은 쓰지 말 것(공급망 위험, 추정).

| 스킬 | 데이터 출처·구조 | 필요한 키 | 제약 | 분류 / 이식 판단 | 근거(파일:줄) |
|---|---|---|---|---|---|
| korean-stock-search | KRX Open API를 감싼 공유 프록시 `https://k-skill-proxy.nomadamas.org/v1/korean-stock/{search,base-info,trade-info}` (환경변수 KSKILL_PROXY_BASE_URL로 변경). upstream 설계 참고 jjlabsio/korea-stock-mcp. 시장 KOSPI/KOSDAQ/KONEX. 응답: 종목 검색(code, standard_code, name, listed_at), 기본정보(security_group, section_type, stock_certificate_type 보통주/우선주, par_value, listed_shares), 일별 시세(open/high/low/close, change_price, fluctuation_rate, trading_volume, trading_value, market_cap). 프록시 캐시 ttl 300,000ms | 사용자 키 불필요(KRX_API_KEY는 프록시 서버에만) | 일별 스냅샷 전용(실시간·호가·분봉·재무·공시 불가), 휴장일/장 마감 전은 not_found, 검색 limit 기본 10 최대 20, 오류 400/404/502/503, 일부 시장 실패 시 upstream.degraded + failed_markets. 개인정보 처리방침상 제3자 프록시 경유(README.md:L21-L24). 대량 크롤링·DB 구축 금지(법적 고지) | 데이터 도구. 이식: 보류(우리는 KRX Open API 직접 호출이 sinkytiger krxdata.py와 동일하게 더 안정적, 프록시 의존은 가용성·개인정보 리스크). 응답 필드 목록만 데이터 사전으로 참고 | nomadamas-k-skill/korean-stock-search/instruction.md:L1-L194; docs/features/korean-stock-search.md:L1-L83 |
| k-dart | OpenDART 직접 호출(프록시 없음) `https://opendart.fss.or.kr/api/`: 공시검색 list.json(검색기간 corp_code 없으면 3개월 제한, page_count 최대 100, pblntf_ty A~J), 기업개황 company.json, fnlttSinglAcntAll.json(reprt_code 11011/11012/11013/11014, fs_div OFS/CFS, 기본 CFS+사업보고서), irdsSttus, alotMatter, tesstkAcqsDspsSttus, accnutAdtorNmNdAdtOpinion, empSttus, pifricDecsn/piicDecsn/fricDecsn, lwstLg, ovLstDecsn, ovDlstDecsn, cvbdIsDecsn, exbdIsDecsn, cmpDvmgDecsn (14~15 endpoint). corp_code는 corpCode.xml(약 30MB) 파싱 | API_K_DART 환경변수(DART 키, 값은 적지 않음) | 일반적으로 20,000건 이상 요청 시 status 020, 021(회사 100개 초과), 013 데이터 없음. 상장폐지·오래된 비상장은 데이터 없을 수 있음. 읽기 전용 | (b) 재무 데이터 필요/데이터 도구. 이식: 엔드포인트 목록은 참고, sinkytiger krcommon/financials.py가 이미 pit·캐시·재시도까지 구현해 그쪽을 우선. 주요사항보고서(유상증자·전환사채·소송·감자·상장폐지) 이벤트는 리스크 게이트 "공시 위험 신호"의 입력 후보 | k-dart/instruction.md:L1-L406 (status 코드표 L312 부근, 020 설명 L312/L373); docs/features/k-dart.md:L1-L75 |
| toss-investment | 토스증권 공식 Open API `https://openapi.tossinvest.com`(host 고정, 변경 불가), OAuth2 Client Credentials(`POST /oauth2/token`), Bearer. 조회: 계좌 목록·보유, 시세(현재가·호가·체결·상하한가·캔들), 종목정보, 매수 유의사항, 환율, 장 운영 캘린더 KR/US, 대기 주문, 주문 상세, 매수가능금액, 판매가능수량, 수수료. Node.js 패키지 helper(getPrices, listOfficialAccounts, getHoldings, getBuyingPower). 429는 Retry-After/X-RateLimit-Reset 대기 후 백오프, 401은 토큰 1회 재발급 | TOSSINVEST_CLIENT_ID, TOSSINVEST_CLIENT_SECRET, (선택) TOSSINVEST_ACCOUNT(accountSeq, 헤더 X-Tossinvest-Account). 공유 프록시로 보내지 않음 | 조회 전용(주문 생성·정정·취소는 패키지에 없음), 비공식 우회 금지, 시크릿 에러 마스킹 | 데이터 도구. 이식: 상·하한가, 장 운영 캘린더, 매수 유의사항 엔드포인트는 한국 시장 규칙 모듈/리스크 게이트의 데이터 입력으로 유용(sinkytiger toss.py가 같은 API를 사용: market-calendar/KR, price-limits, warnings). 채택은 데이터 어댑터 수준 | toss-investment/instruction.md:L1-L91 (429/401 처리 L64-L65); docs/features/toss-investment.md:L1-L78 |
| daishin-report-search | 대신증권 리포트 HTML 미러(GitHub Pages 저장소 jay-jo-0/github_pages_repo)를 GitHub recursive tree API + raw.githubusercontent.com으로 읽음. 파일명 YYYYMMDDHHMMSS.html에서 KST 시각 추정, title, headings, excerpt, ratingTargets(Rating/Target 표), explain 페이지. 프록시 미사용. 비공식 제3자 미러라 원본 증권사 공식 채널 아님 | 불필요(선택 GITHUB_TOKEN으로 GitHub API 한도 상향) | GitHub API 속도 제한, 쿼리 시 maxInspect(기본 100) 크롤 예산, 투자 조언 금지, 대량 수집 금지, 미러의 정확성·지속성 보장 없음 | (d) 정성 위주/데이터 도구. 이식: 보류(애널리스트 목표가는 일봉 규칙 엔진의 근거 부적합, 저작권·약관 리스크) | daishin-report-search/instruction.md:L1-L138 |
| company-analysis | 공개 DART 문서 뷰어(dsaf001/main.do?rcpNo, report/viewer.do)·KIND·기업 IR·SEC EDGAR 원문을 보고 손익·재무상태·현금흐름 3표를 정리, 로컬 스냅샷 JSON + SHA-256 + 검증기(scripts/evidence.js)로 숫자를 원문과 대조, 한국 종목 시세는 로그인 없는 네이버증권 모바일 공개 페이지, 미국은 Nasdaq 공개 JSON. OpenDART/FRED/ECOS/KOSIS 키 필요한 API는 의도적으로 안 씀. 6개 섹션 채팅 출력(요약, 사업·산업·경쟁, 최근 사업 현황, 재무제표, 실적발표, Catalyst & Risk) | 불필요(공개 페이지 기반) | 기준일 이후 자료 혼입 금지, 접근 실패 시 "확인 불가", 스크래핑 기반이라 약관·구조 변경 위험, 10분 안 시세 수집 | (d) 정성 위주 + 데이터 도구. 이식: 보류. 단 "숫자는 원문 스냅샷+해시로 검증, 기준일 이후 자료 금지"라는 데이터 품질 원칙만 참고 | company-analysis/instruction.md:L1-L68; company-analysis/scripts/ |

**k-skill 소결**: 5종 모두 규칙·임계값이 없는 데이터 접근 스킬이다. 이식 가치는 낮고(우리는 KRX Open API·OpenDART·토스 Open API를 직접 붙이는 편이 낫다), 참고할 것은 (1) 엔드포인트 목록, (2) DART status 코드표(000/010/011/012/013/014/020/021/100/800/900), (3) 429 백오프·401 재발급·시크릿 마스킹 패턴이다.

#### 그룹 소결
이식 우선순위(코드 기준, 값은 확인한 것만):
1. **한국 시장 규칙 모듈**: 호가단위 표(2천 미만 1원/5천 5원/2만 10원/5만 50원/20만 100원/50만 500원/이상 1,000원, 경계는 `<`)와 floor/ceil/round_tick, 가격제한 ±30%(폭 = floor(기준가 x 0.30 / 기준가 호가단위) x 호가단위), 정규장 09:00~15:20 접속매매 + 15:20~15:30 종가 단일가 -> sinkytiger-day-trader-skill-kr/krcommon/krx.py:L40-L50, L342-L383. 비용은 수수료 0.015%(양쪽, 계좌별 설정) + 매도세 0.20%(L49-L50, 시장별 분리는 우리가 추가). 토스 일봉 종가가 NXT 20:00 가격이라 KRX 공식 종가로 보정해야 한다는 데이터 품질 경고(krxdata.py:L1-L19).
2. **리스크 게이트 + 사이징 + 청산**: 수량 = min(거래당 최대 손실 / (주당 위험 + 왕복 비용), 종목 한도 75%, 주문 한도, 현금 - 버퍼 10%); 최소 위험 max(2틱, 진입가 0.05%); 비용/위험 <= 0.30; 비용 뺀 손익비 >= 1.0; 손절 floor_tick·목표 round_tick·진입 ceil_tick; 투자경고·위험·단기과열·VI·거래정지·정리매매 진입 BLOCK, 청산은 막지 않음 -> trader-kr-risk/check.py:L63-L65, L384-L437; trader-kr-budget/size.py:L128-L178; trader-kr-exit/exit.py:L53-L54, L158-L176.
3. **검증 모듈(lab)**: 롤링 워크포워드 학습 120/시험 20 거래일(min_trades 30), 홀름 보정, 부트스트랩 95% CI(2,000회, 시드 19), 비용 포함 R_net, 손절 먼저 판정, 갭은 시가 체결, forward lock(규칙+엔진 소스 해시, 덮어쓰기 금지, 첫 200건 1회 판정) -> trader-kr-lab/lab.py:L96-L145, L181-L211, L214-L305, L346-L531.
4. **위원회 관점 점수기(품질/가치)**: F-score 8신호(유상증자 신호 제외), GP/A, 발생액 상위 10%, 순발행 상위 10%, 적자 제외(위험 신호 4종), 그레이엄 8/버핏 7/린치 6 충족 수, 역DCF·필요 ROE. 재무는 사업보고서 접수일 기준 point-in-time -> trader-kr-invest/value.py:L349-L382, L629-L668; trader-kr-masters/masters.py:L97-L250; implied.py:L116-L151. DART 전체 재무제표는 2015 사업연도부터.
5. **일봉 트리거/반전 점수**: 20일 종가 신고가(`last > max(c[-21:-1])`), 상승 깃발(5일 전 종가/15일 전 종가 > +10% & 최근 5일 종가 범위 < 5%), 20일선 회복, RSI14(Wilder) < 30 및 반등, 유동성 하한 1,000원 & 거래대금 10억 -> trader-kr-scanner/scan.py:L87-L107, L122-L141. 단독 매수 신호가 아니라 위원회 입력.
6. **팩터·생존 편향 처리(invest)**: 모멘텀 12-1, 저변동성(252일 sd, 200개 이상), 52주 고가 근접, 소형, 1개월 반전, 추세(10·12개월 평균 위), 시총 상위 300 U, 신호=월말 종가/체결=다음 거래일 종가, 비용 수수료 0.015% + 세 0.20% + 슬리피지 0.10%, 상장폐지 두 판(A 마지막 가격 / B -100%), 코드 재사용 365일 -> trader-kr-invest/invest.py:L45-L54, L389-L399, L440-L454, L478-L503, L328-L333.
- 보류: ORB·분봉 규칙 48개(lab), entry, timemachine(분봉), broker(세 겹 승인·모의 전용 구조만 참고), Kiwoom 시황 스킬(규칙 없음), k-skill 5종(데이터 도구).


---

## 11. Minervini·O'Neil 종목 선별 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, MIT) · 범위: vcp-screener, breakout-trade-planner, canslim-screener

### vcp-screener — VCP Screener (Minervini)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Mark Minervini Trend Template(7조건) + Volatility Contraction Pattern. 구현은 tradermonty 자체 휴리스틱(ATR ZigZag 수축 탐지, 가중 점수) (`skills/vcp-screener/scripts/calculators/vcp_pattern_calculator.py:L1-L17`) |
| 분류 | (a) 일봉(OHLCV)만으로 구현 가능 — 주. 유니버스 사전필터만 호가(quote) 필드 사용(일봉에서 재계산 가능) |
| 필요 데이터 | FMP 필수(`skills-index.yaml:L2335-L2339`, "S&P 500 OHLCV via FMP"). 엔드포인트: `/stable/quote`, `/stable/historical-price-eod/full`(구 `/api/v3/quote`, `/api/v3/historical-price-full` 폴백), 구성종목 `/stable/sp500-constituent`(무료 402 시 GitHub CSV 폴백) (`scripts/fmp_client.py:L111-L118`, `L406-L412`). 기준지수 SPY 260일(`scripts/screen_vcp.py:L752`), 종목 260일. 요청 간 0.3s 지연(`scripts/fmp_client.py:L172`) |
| 주요 파일 | `scripts/calculators/{trend_template,vcp_pattern,volume_pattern,pivot_proximity,relative_strength,execution_state,pattern_classifier,forward_outcome}_calculator.py`, `scripts/scorer.py`, `scripts/screen_vcp.py` |
| 라이선스 | MIT, Copyright (c) 2026 TraderMonty (`LICENSE:L1-L3`) |
| 이식 판단 | 채택(핵심). 위치: 레짐 필터 아님 -> 위원회 "추세/구조" 점수기 + 진입 트리거(피벗 돌파) + 리스크 게이트(실행 상태 Damaged/Overextended 차단). RS는 KOSPI 기준으로 교체 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 유니버스 사전필터(Phase 1) | 가격>10 USD, avgVolume(없으면 당일 volume)>=200,000, 52주저가 대비 +20% 이상, 52주고가 대비 -30% 이내. 순서 점수 = min(저가상승률,1.0)*50 + (1-고가이격률)*50, 내림차순 상위 `--max-candidates`(기본 100; `--full-sp500`은 전체) | `scripts/screen_vcp.py:L257-L303`, `L739-L740` |
| 2 | TT1 | 종가 > SMA150 그리고 > SMA200 (SMA200 없으면 SMA150만) | `trend_template_calculator.py:L58-L75` |
| 3 | TT2 | SMA150 > SMA200 | `trend_template_calculator.py:L77-L86` |
| 4 | TT3 | SMA200(오늘) > SMA200(22거래일 전). 종가 222개 미만이면 보수적 실패 | `trend_template_calculator.py:L88-L114` |
| 5 | TT4 | 종가 > SMA50 | `trend_template_calculator.py:L116-L124` |
| 6 | TT5 | (price-52w저가)/52w저가*100 >= 25 | `trend_template_calculator.py:L126-L139` |
| 7 | TT6 | (52w고가-price)/52w고가*100 <= 25 (원 Minervini 25% 이내) | `trend_template_calculator.py:L141-L154` |
| 8 | TT7 RS | rs_rank > 70 (rank는 규칙 14의 절대 초과수익 매핑값; rank 70은 불충분 -> 가중 RS >= +10%p 이어야 80 부여) | `trend_template_calculator.py:L156-L168`, `relative_strength_calculator.py:L261-L282` |
| 9 | TT 점수·통과 | 충족개수*14.3(최대 100). 통과 = raw_score >= 85 (= 6/7 이상, 6*14.3=85.8). Phase2 게이트 `--trend-min-score` 기본 85는 raw 기준 | `trend_template_calculator.py:L170-L176`, `screen_vcp.py:L248-L254` |
| 10 | SMA50 과열 감점 | dist=(price-SMA50)/SMA50*100. <8 -> 0; 8~12 -> -5; 12~18 -> -10; 18~25 -> -15; >=25 -> -20. 최종 TT score = max(0, raw+감점) (composite에 들어가는 값) | `trend_template_calculator.py:L259-L289`, `L191` |
| 11 | SMA200 과열 감점 | dist200>50 -> -10, >60 -> -15, >=70 -> -20. 점수에는 미반영(실행상태 Overextended와 이중감점 방지, 메타데이터만) | `trend_template_calculator.py:L215-L256`, `L188-L191` |
| 12 | 스윙 탐지(ZigZag) | lookback 120봉(오래된->최신 순서로 뒤집음). ATR14 = 단순평균 TR(최근 14). 임계 = ATR*1.5. 상승 추적 중 `extreme_high - low[i] >= 임계`이면 스윙고점 확정, 하락 추적 중 `high[i] - extreme_low >= 임계`이면 스윙저점 확정. 고/저 각 1개 미만이면 고정창 5봉 좌우 비교 폴백 | `vcp_pattern_calculator.py:L69-L98`, `L199-L233`, `L236-L339` |
| 13 | 수축 구성(멀티스타트) | 스윙고점 중 가장 높은 3개를 시작점으로 각각 시도. 각 수축 = 고점 -> 이후 첫 스윙저점, 깊이% = (고-저)/고*100, 최대 4개(T1~T4). 저점까지 기간 < 5봉이면 다음 고점 이전의 더 늦은 저점 탐색, 없으면 중단. 두 번째 이후 수축의 고점이 T1 고점 대비 5% 초과 이탈하면 중단. 선택 = (valid, 점수, 개수) 사전순 최대 | `vcp_pattern_calculator.py:L100-L131`, `L408-L506` |
| 14 | VCP 유효성 | 최소 2수축; T1 깊이 >= t1_depth_min(코드 함수기본 8.0, CLI 기본 10.0), >35%는 경고만; 연속 수축 비율 깊이[i]/깊이[i-1] <= contraction_ratio(함수기본 0.75, CLI 기본 0.70) 아니면 invalid; 패턴 길이(마지막저점idx-첫고점idx) 15 미만 invalid, 325 초과 경고만; 고점 5% 이탈은 issues 기록만 | `vcp_pattern_calculator.py:L509-L581`, `screen_vcp.py:L94-L120`(CLI 기본값) |
| 15 | 피벗 | 마지막 수축의 고점 가격(high_price). 수축 없으면 마지막 스윙고점 | `vcp_pattern_calculator.py:L606-L616` |
| 16 | 와이드앤루즈 | 마지막 수축 깊이 > 15% 이고 지속 < 10봉 -> 플래그 -> 등급 최대 Developing | `vcp_pattern_calculator.py:L584-L603`, `scorer.py:L127-L132` |
| 17 | 보조지표 | atr_compression_ratio = ATR10/ATR50(낮을수록 압축); right_side_range_ratio = (15봉 최고-최저)/ATR50. 점수엔 미사용(표시용) | `vcp_pattern_calculator.py:L164-L177` |
| 18 | 거래량 건조 | dry_up = 최근 10봉 평균(bar[0] 제외, `volumes[1:11]`)/50일 평균. <0.30 -> 90; <0.50 -> 75; <0.70 -> 60; <=1.00 -> 40; 초과 -> 20 | `volume_pattern_calculator.py:L88-L110`, `L211-L214` |
| 19 | 거래량 가감 | 피벗 위 종가 + bar0 거래량 >= 1.5x(50일 평균) -> +10 (breakout_volume=True). 최근 20일 중 거래량>50일평균인 날만 집계: 상승일-하락일 >3 -> +10, < -3 -> -10. 수축별 평균거래량이 엄격히 감소(전부 단조) -> +10. 0~100 클립 | `volume_pattern_calculator.py:L114-L159` |
| 20 | 돌파 거래량 점수(별도 필드) | bar0/50일평균 >=3.0 -> 100; >=2.0 -> 80; >=1.5 -> 60; >=1.0 -> 30 (피벗 위일 때만; 합산 점수 미반영, 표시용) | `volume_pattern_calculator.py:L126-L134` |
| 21 | 피벗 근접 점수 | dist=(가격-피벗)/피벗*100. >20 -> 20; >10 -> 35; >5 -> 50; >3 -> 65; >0 -> 90; 0~-2 -> 90; -2~-5 -> 75; -5~-8 -> 60; -8~-10 -> 45; -10~-15 -> 30; 미만 -> 10. 거래량 확인 + 0<dist<=3 -> +10(BREAKOUT CONFIRMED), 3<dist<=5 -> +10 | `pivot_proximity_calculator.py:L68-L112` |
| 22 | 손절·리스크 | stop = 마지막 수축 저점 * 0.99. risk% = (현재가-stop)/현재가*100. 현재가<=stop이면 score 0, "BELOW STOP LEVEL" | `pivot_proximity_calculator.py:L114-L129` |
| 23 | RS(지수 대비) | 기간별 수익률(종가[0]/종가[N]-1) 종목-지수: 63일 x0.40, 126일 x0.20, 189일 x0.20, 252일 x0.20 가중평균(`weighted_rs`, %p). 데이터 부족 시 절반 기간이 있으면 가중치 x0.5로 부분 반영 | `relative_strength_calculator.py:L27-L32`, `L68-L120`, `L134-L138` |
| 24 | RS 점수(절대) | weighted_rs >=50 -> 점수100/rank99; >=30 -> 95/95; >=20 -> 90/90; >=10 -> 80/80; >=5 -> 70/70; >=0 -> 60/60; >=-5 -> 50/50; >=-10 -> 40/40; >=-20 -> 20/25; 미만 0/10 | `relative_strength_calculator.py:L261-L282` |
| 25 | RS 유니버스 재순위 | 결과 집합(트렌드 통과 생존자) 내 백분위: 95+ -> 100, 85+ -> 90, 75+ -> 80, 60+ -> 70, 45+ -> 60, 30+ -> 50, 15+ -> 40, 미만 20. 표본 <20이면 점수 상한 90, <10이면 80, <5이면 70 (백분위 상한 94/84/74). 재순위 후 composite 재계산 | `relative_strength_calculator.py:L141-L258`, `screen_vcp.py:L846-L876`(재순위 블록) |
| 26 | 실행 상태(결정트리, 첫 일치) | (1) price<SMA50<SMA200 -> Invalid; (2) price<마지막 수축저점 -> Damaged; (3) price<SMA50 -> Damaged; (4) SMA200 이격>50% -> Overextended; (5) 피벗 위 >10% -> Overextended; (6) 5~10% -> Extended; (7) 3~5% -> Early-post-breakout; (8) 0~3% + 거래량확인 -> Breakout; (9) 0~3% 거래량 미확인 -> Early-post-breakout; (10) 피벗 아래 -> Pre-breakout | `execution_state.py:L22-L119` |
| 27 | 상태별 등급 상한 | Invalid/Damaged -> No VCP; Overextended -> Weak VCP; Extended -> Developing VCP; Early-post-breakout -> Strong VCP; Breakout/Pre-breakout 무제한 | `execution_state.py:L133-L177` |
| 28 | 패턴 분류 | Invalid/Damaged -> Damaged; Overextended/Extended -> Extended Leader(valid) / VCP-adjacent; Early-post/Breakout -> Post-breakout(valid); Pre-breakout 중 Textbook = valid AND not wide_and_loose AND 수축>=3 AND 마지막 깊이<=10% AND dry_up<=0.7, 아니면 VCP-adjacent | `pattern_classifier.py:L60-L83` |
| 29 | entry_ready | 상태가 Invalid/Damaged/Overextended/Extended/Early-post-breakout이면 불가; valid_vcp 필수(옵션 해제 가능); -8% <= 피벗거리 <= +3%(`--max-above-pivot`); dry_up<=1.0; risk% 0 초과 15 이하(`--max-risk`); BELOW STOP 불가 | `screen_vcp.py:L516-L554`, CLI `L83-L91` |
| 30 | strict 모드 | `--strict`: valid_vcp=True AND 상태 in (Pre-breakout, Breakout)만 남김 (결과 후처리). `--mode prebreakout`은 entry_ready만 | `screen_vcp.py:L169-L176`, `L890-L911` |
| 31 | 정체주 제외 | 최근 10봉 평균 (고-저)/종가 < `--min-atr-pct`(기본 1.0%)이면 제외(피인수·핀 종목) | `screen_vcp.py:L482-L513`, `L813-L815` |
| 32 | 히스토리 모드 | as_of_offset으로 과거 시점 재현, 전방 결과: 종가>피벗이면 breakout, 종가<stop이면 stop_hit(종가 기준), 아니면 timeout; max_gain/max_loss 기록 | `forward_outcome.py:L60-L119` |

**점수·등급**
- composite = 0.25*Trend(감점 반영 점수) + 0.25*수축품질(vcp score) + 0.20*거래량 + 0.15*피벗근접 + 0.15*RS, 소수 1자리 반올림 (`scorer.py:L35-L41`, `L91-L96`).
- 수축품질 점수: 유효 시 수축 4개+ 90, 3개 80, 2개 60 기준; 마지막 깊이 <5% +10; 평균 비율 <0.4 +10; T1>30% -10; 0~100 클립. 무효 시 min(40, 수축수*15) (`vcp_pattern_calculator.py:L619-L654`).
- 등급 밴드: >=90 Textbook, >=80 Strong, >=70 Good, >=60 Developing, >=50 Weak, 미만 No VCP (`scorer.py:L201-L238`). valid_vcp=False이고 composite>=70이면 Developing VCP로 강제 하향 (`scorer.py:L105-L111`). 이후 상태 상한 -> 와이드앤루즈 상한 순 적용(`scorer.py:L118-L132`).
- 사이징 가이드(문서 문구): Textbook 1.5-2x, Strong 1x, Good 0.75x (`SKILL.md:L150-L153`, `references/scoring_system.md:L199-L201`) — 코드가 수량을 계산하진 않음.

**출력 형식**: JSON(`vcp_screener_<timestamp>.json`)+Markdown 리포트. 종목별 composite_score, rating, quality_rating(상한 전), execution_state(+reasons), pattern_type, distance_from_pivot_pct, 컴포넌트별 점수 분해, entry_ready, 수축 상세(T별 고저·깊이·기간) (`screen_vcp.py:L451-L480` 반환 dict, `L920-L988` 메타/파일).

**SKILL.md와 코드 차이**
- [차이] 함수 기본값 vs CLI 기본값: `calculate_vcp_pattern` t1_depth_min=8.0, contraction_ratio=0.75(`vcp_pattern_calculator.py:L29-L30`) 이나 실제 실행 경로는 CLI 기본 10.0/0.70(`screen_vcp.py:L94-L120`, `SKILL.md:L113,L117`). `vcp_methodology.md:L65-L66`은 8~35%, 비율<=0.75로 서술 -> 실제 운영 기본은 더 엄격.
- [차이] Phase 2(트렌드 게이트)는 `max_sma200_extension`을 전달하지 않아 기본 50 사용(`screen_vcp.py` Phase 2 호출), Phase 3만 CLI 값 사용. 영향은 메타데이터뿐.
- [차이] `_calculate_sma200_penalty` docstring은 >40%에서 -5 단계를 적는데 코드는 >50%부터(-10/-15/-20) (`trend_template_calculator.py:L225-L256`). 게다가 점수에 미반영.
- [차이] RS "rank"는 유니버스 백분위가 아니라 SPY 대비 초과수익 구간 매핑값(`relative_strength_calculator.py:L261-L282`). 백분위 재순위는 Phase3 후 생존자 집합에서만 수행.
- [차이] validate의 "후속 고점 5% 이내"는 invalid 사유가 아니라 issues 기록뿐이지만, 구성 단계에서는 5% 초과 시 수축 확장을 중단함(`vcp_pattern_calculator.py:L474-L478` vs `L548-L565`).
- 디자인상 주의: 피벗은 "마지막 수축의 고점"이라 돌파 시점 최고가와 다를 수 있음; 손절은 종가 기준(history 모드)이지만 실시간은 저점*0.99.

**한국 시장 적용**
- RS 기준 지수 SPY -> KOSPI(코스닥 종목은 KOSDAQ 또는 둘 다 비교) [추정]. 절대 매핑표(>=+10%p 등)는 한국 변동성에 맞춰 재보정하거나 KRX 전종목 백분위로 대체(생존자 재순위의 표본 부족 문제를 피함).
- 사전필터: 가격>10달러 -> 최소 호가(예 1,000~2,000원 이상) 및 거래대금 하한으로 교체 [추정]. 52주 고/저는 일봉에서 직접 계산(수정주가 필요).
- 52주 고가 근접(25%/30% 이내)과 저가 대비 +25%는 그대로 적용 가능하나 가격제한 ±30%와 소형주 변동성이 커 T1 깊이 상한(35%)·와이드앤루즈(15%)는 코스닥에서 별도 보정 필요 [추정].
- 피벗·손절가는 호가단위(2023-01 개정: 2천원 미만 1원 ... 50만원 이상 1,000원)로 올림/내림 필요. 정체주 제외(평균 일중폭 <1%)는 관리종목·거래정지·단일가 종목 제외 규칙으로 확장.
- 일봉 종가 기반이라 갭 위험(시가 동시호가, VI)은 별도 리스크 게이트에서 처리.

### breakout-trade-planner — Breakout Trade Planner (Minervini 진입 규칙)
| 항목 | 내용 |
|---|---|
| 기법·출처 | VCP 스크리너 JSON을 받아 Minervini식 피벗 돌파 매매계획(진입/손절/R목표/고정분율 사이징/heat 한도) 생성. 출처 문헌: Minervini "Think & Trade Like a Champion"(2017) (`skills/breakout-trade-planner/references/minervini_entry_rules.md:L70`) |
| 분류 | (a) 일봉 계산만으로 구현 가능(입력은 vcp-screener 결과). 실행 확인 규칙(5분봉 close_loc, 시간대 RVOL)은 분봉 필요 -> 일봉 엔진에선 보류 |
| 필요 데이터 | 외부 API 불필요(`skills-index.yaml` breakout-trade-planner integrations: local_calculation, not_required — "Consumes VCP screener output; pure calculation + Alpaca order templates"). 입력 필드: symbol, sector, price, composite_score, execution_state, valid_vcp, vcp_pattern.pivot_price, vcp_pattern.contractions[-1].low_price, (Breakout이면) volume_pattern.breakout_volume_detected, pivot_proximity.distance_from_pivot_pct (`scripts/plan_breakout_trades.py:L90-L135`). schema_version "1.0"만 허용(`L41`, `L66-L74`) |
| 주요 파일 | `scripts/risk_calculator.py`, `scripts/plan_breakout_trades.py`, `scripts/order_builder.py`, `scripts/_market_calendar.py`(XNYS 세션 달력, 한국은 KRX 달력으로 교체 필요) |
| 라이선스 | MIT (저장소 루트 `LICENSE`) |
| 이식 판단 | 부분 채택. 진입가/손절/사이징/heat 산식은 그대로 이식(리스크 게이트·사이징). Alpaca 주문 템플릿은 폐기(KRX 주문 유형으로 재설계). 위치: 진입 트리거 + 리스크 게이트 + 사이징 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 신호 진입가(buy-stop) | pivot*(1+0.1%) (`--pivot-buffer-pct` 기본 0.1) | `scripts/risk_calculator.py:L25`, `L53`; `plan_breakout_trades.py:L597` |
| 2 | 최악 진입가(limit 상한, 추격 한도) | pivot*(1+2.0%) (`--max-chase-pct` 기본 2.0). 버퍼가 추격한도보다 크면 에러 | `risk_calculator.py:L26`, `L48-L54`; `plan_breakout_trades.py:L596` |
| 3 | 손절가 | 마지막 수축 저점*(1-1.0%) (`--stop-buffer-pct` 기본 1.0). 손절>=신호진입이면 에러(거부) | `risk_calculator.py:L27`, `L55-L58`; `plan_breakout_trades.py:L595` |
| 4 | 가격 반올림 | >=1달러 소수 2자리, 미만 4자리(Alpaca 틱). KRX는 호가단위 표로 대체 필요 | `risk_calculator.py:L11-L19` |
| 5 | 리스크% | risk_signal=(신호진입-손절)/신호진입*100, risk_worst=(최악진입-손절)/최악진입*100, 소수 2자리 | `risk_calculator.py:L63-L75` |
| 6 | 최대 리스크 게이트 | risk_worst <= 8.0% (`MAX_RISK_PCT=8.0`) — 초과 시 거부 | `plan_breakout_trades.py:L42`, `L191-L195`, `L206-L207`; `minervini_entry_rules.md:L26` |
| 7 | 목표가 | tp = 최악진입 + 2.0*(최악진입-손절) (`--target-r-multiple` 기본 2.0) | `plan_breakout_trades.py:L178`, `L594` |
| 8 | R 배수표 | R=진입-손절, 1R/2R/3R = 진입+nR (신호·최악 기준 둘 다 출력) | `risk_calculator.py:L78-L89`; `plan_breakout_trades.py:L371-L372` |
| 9 | 등급 밴드 | composite >=90 textbook, >=80 strong, >=70 good, >=60 developing, 미만 weak | `risk_calculator.py:L92-L102` |
| 10 | 사이징 배수 | textbook 1.75, strong 1.0, good 0.75, developing 0, weak 0 | `risk_calculator.py:L105-L111`; `minervini_entry_rules.md:L35-L37` |
| 11 | 수량 | 유효 리스크% = base(`--risk-pct` 기본 0.5) * 배수; dollar_risk = 계좌*유효%/100; 주당 리스크 = 최악진입-손절(보수적); shares = int(dollar_risk/주당리스크) | `risk_calculator.py:L137-L150`; `plan_breakout_trades.py:L590` |
| 12 | 포지션 상한 | 최대 종목 비중 10% (`--max-position-pct`): int(계좌*10%/최악진입). 섹터 상한 30% (`--max-sector-pct`): (30%-기보유 섹터비중-이번 배치 누적)*계좌/최악진입. 최종 수량 = min(위험기반, 종목상한, 섹터상한); 구속 제약 기록 | `risk_calculator.py:L125-L126`, `L152-L193`; `plan_breakout_trades.py:L295-L296`, `L591-L592` |
| 13 | 포트폴리오 heat | 후보를 composite 내림차순으로 순회; cumulative = 기존 `open_risk_pct` + 확정 건의 risk_dollars/계좌*100 누적; 신규 포함 시 > 6.0%(`--max-portfolio-heat-pct`)면 deferred. 0주면 constrained | `plan_breakout_trades.py:L420`, `L434`, `L309-L327`, `L456-L462`, `L593` |
| 14 | Pre-breakout 자격 | valid_vcp AND 등급 in (textbook,strong,good) AND risk_worst<=8% -> actionable(stop-limit 브래킷 + 확인 후 limit 브래킷 템플릿 둘 다 생성). 불충족이어도 valid_vcp이고 60<=score<70이면 watchlist, 그 외 reject | `plan_breakout_trades.py:L190-L224`, `L199-L200` |
| 15 | Breakout 상태 처리 | valid_vcp AND 등급 상위3 AND risk_worst<=8% AND breakout_volume AND 피벗거리<=max_chase(2%) AND 현재가<=최악진입 -> 주문 없이 "late_breakout_revalidation" 권고만 (실시간 재확인 후 주문). 워치리스트 없음 | `plan_breakout_trades.py:L227-L261`; `order_builder.py:L88-L106` |
| 16 | 그 외 상태 | valid_vcp & (Pre-breakout 또는 Early-post-breakout) & 60<=score<70 -> watchlist; 나머지 reject (Extended/Overextended/Damaged/Invalid 전부 reject) | `plan_breakout_trades.py:L263-L272` |
| 17 | 주문 템플릿(pre_place) | stop_limit 매수: stop=신호진입, limit=최악진입, TIF day, bracket(익절 limit=tp, 손절 stop). 검증: 신호진입-손절 >= 0.01, tp > 최악진입 | `order_builder.py:L11-L43`, `L127-L142` |
| 18 | 주문 템플릿(post_confirm) | 모니터 확인 후 limit(최악진입) 브래킷. 조건(5분봉): close > pivot, close_loc >= 0.60, 시간대 RVOL >= 1.5, 피벗 대비 <= 2% | `order_builder.py:L46-L85`, `L109-L124`; `minervini_entry_rules.md:L46` |
| 19 | 계획 유효 세션 | 결정시각 기준 현재 미종료 XNYS 세션 또는 다음 정규 세션 하루 (day 주문) | `plan_breakout_trades.py:L355-L358` |

**점수·등급**: 자체 점수 없음. vcp-screener의 composite_score를 5단 밴드로 변환해 (a) 자격, (b) 사이징 배수 결정. 정렬 키는 composite 내림차순(`plan_breakout_trades.py:L420`).

**출력 형식**: `breakout_trade_plan_<ts>.json` + `.md`. 분류 목록 actionable / revalidation / watchlist / rejected / deferred / constrained + warnings(필드 누락 `MISSING_FIELD`), parameters, 총 리스크% 요약 (`plan_breakout_trades.py:L414-L519`, `L600-L625`). actionable 항목에 signal_entry, worst_entry, stop_loss_price, risk_per_share, risk_pct_signal/worst, r_multiples, target_price, shares, position_value, risk_dollars, cumulative_risk_pct, binding_constraint, order_templates(pre_place/post_confirm) (`L360-L389`).

**SKILL.md와 코드 차이**: 갭/슬리피지는 별도 모델 없이 "최악 진입 = 피벗+2%"를 사이징 기준가로 쓰는 방식으로만 반영(실제 갭다운 손절 슬리피지, 갭업 시가 체결 가정은 없음). 손절은 주문상 stop이라 갭 하락 시 체결가 보장 안 됨 [추정: 코드에 갭 가정 없음을 grep로 확인 못 한 범위 있음]. vcp-screener의 `risk_pct`(현재가 기준, 손절 0.99배)와 planner(피벗 기준, 0.99배; 같은 1% 버퍼)는 기준가가 다름.

**한국 시장 적용**
- 호가단위 반올림: `round_price`를 KRX 호가표(2천원 미만 1원 ... 50만원 이상 1,000원)로 교체. 신호진입은 올림(매수 stop), 손절은 내림, 목표는 내림 처리 권장 [추정]. 버퍼 0.1%는 고가주에선 1호가 미만일 수 있어 "최소 1호가" 규칙 필요.
- 가격제한 ±30%: 최악 진입(+2%)은 문제없으나 손절 갭다운은 하한가(-30%)까지 가능 -> 사이징에 갭 가정(예: 손절 거리 대신 max(손절거리, 갭 시나리오))을 추가 [추정].
- 일봉 엔진: stop-limit 브래킷은 KRX에 OCO/브래킷 네이티브 미보장(증권사 API별 상이) [확실치 않음]. 일봉 확정 후 익일 시가 동시호가/장중 조건부 진입으로 단순화하고, 5분봉 확인(close_loc, RVOL) 규칙은 일봉 근사(당일 종가 위치 close_loc=(C-L)/(H-L)>=0.6, 거래량/50일평균>=1.5)로 대체 가능 [추정].
- 거래세·농특세(2026 합계 약 0.20%, 확인 필요)와 수수료는 R 계산에 왕복비용으로 가산.
- 섹터 한도 30%: KRX 업종(KOSPI/KOSDAQ 업종 분류) 매핑 필요. heat 6%·종목 10%는 소형주 유동성에서 재보정.

### canslim-screener — CANSLIM Screener (William O'Neil)
| 항목 | 내용 |
|---|---|
| 기법·출처 | William J. O'Neil의 CAN SLIM(C 분기이익, A 연이익, N 신고가, S 수급, L 주도주 RS, I 기관, M 시장방향). 구현은 tradermonty 자체 점수화 |
| 분류 | 혼합. 일봉만: N, S, L, M(지수 일봉; VIX는 선택) / 재무 필요: C, A / 보유·13F 필요: I. 주 분류 (b) 재무 데이터 필요, 보조 (a)(c) |
| 필요 데이터 | FMP 필수(`skills-index.yaml:L130-L134`, "US stock fundamentals via FMP"). 엔드포인트: `/stable/profile`, `/stable/income-statement?symbol&period&limit`(구 `/api/v3/income-statement/{sym}` 폴백), `/stable/quote`, `/stable/historical-price-eod/full`, `/stable/institutional-ownership/symbol-positions-summary` 및 `extract-analytics/holder`(13F, 구 `/api/v3/institutional-holder/{sym}` 폴백) (`scripts/fmp_client.py:L106-L111`, `L166`, `L381`, `L468`, `L525-L531`, `L554`). 기준지수 `^GSPC`(`--rs-benchmark`로 변경 가능, `screen_canslim.py:L121-L130`), 변동성 `^VIX`. I 보조 소스: Finviz 스크레이핑(`finviz_stock_client.py`, beautifulsoup 필요). 호출 요청 간 0.3s (`fmp_client.py:L167`) |
| 주요 파일 | `scripts/calculators/{earnings,growth,new_highs,supply_demand,leadership,institutional,market}_calculator.py`, `scripts/scorer.py`, `scripts/screen_canslim.py` |
| 라이선스 | MIT (루트 `LICENSE`) |
| 이식 판단 | 부분 채택. N·S·L·M을 일봉 위원회 관점(모멘텀/수급/레짐)으로 채택. C·A는 OpenDART 데이터가 안정적으로 연결된 뒤 "재무 관점"으로 단계적 채택(보류 후 2단계). I는 KRX 투자자별 순매수로 재설계(원식 부적합) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | C 분기 EPS·매출 | YoY = 최신분기 vs 4분기 전(인덱스 4; 5개 분기 필요). EPS성장 = (최신-전년)/abs(전년)*100; 전년 EPS=0이고 최신>0이면 999.9. 매출성장=(최신-전년)/전년*100. 점수: EPS>=50 & 매출>=25 -> 100; EPS>=30 & 매출>=15 -> 80; EPS>=18 & 매출>=10 -> 60; EPS>=10 -> 40; 그 외 0. 품질경고: 매출성장 < EPS성장*0.5 이고 EPS>20 (자사주매입 의심) | `calculators/earnings_calculator.py:L45-L60`, `L99-L125`, `L143-L178` |
| 2 | A 연 EPS 성장 | 최근 4개 연도 EPS 모두 >0 필요(0 이하면 score 0). 3년 CAGR=((EPS_end/EPS_start)^(1/3)-1)*100. 기본점: >=40 -> 90; >=30 -> 70; >=25 -> 50; >=15 -> 30; 미만 0. 매출 CAGR < EPS CAGR*0.5이면 기본점*0.8(int). 안정(연속 비감소 EPS)이면 +10, 상한 100. 데이터 4년 미만이면 score 50(중립) | `calculators/growth_calculator.py:L41-L50`, `L56-L96`, `L108-L110`, `L140-L183` |
| 3 | N 신고가 근접 | dist=(price/52주고가-1)*100(<=0). breakout = price >= 52주고가*0.995 AND 당일 volume > avgVolume*1.4. 점수: dist>=-5 & breakout -> 100; >=-10 & breakout -> 80; dist>=-15 또는 breakout -> 60; >=-25 -> 40; 그 외 20 | `calculators/new_highs_calculator.py:L50-L72`, `L95-L122` |
| 4 | S 수급(상승·하락일 거래량비) | 최근 60봉(최소 60). 전일 종가 대비 상승일/하락일 거래량 각 평균, 보합일 제외. 각각 최소 10일 필요(미달 score 0). ratio=평균상승일거래량/평균하락일거래량(하락 평균 0이면 5.0). 점수: >=2.0 -> 100; >=1.5 -> 80; >=1.0 -> 60; >=0.7 -> 40; >=0.5 -> 20; 미만 0. accumulation_detected = ratio>=1.5 | `calculators/supply_demand_calculator.py:L67-L132`, `L152-L173` |
| 5 | L 리더십(상대강도) | 기간 63/126/252봉, 가중 0.40/0.30/0.30(누락 기간은 가중치 재정규화). 기간수익률=(끝-시작)/시작*100; 상대=종목-벤치마크; weighted_relative로 점수화: >=50 -> 100(rank 99); >=30 -> 95(95); >=20 -> 90(90); >=10 -> 80(80); >=5 -> 70(70); >=0 -> 60(60); >=-5 -> 50(50); >=-10 -> 40(40); >=-20 -> 20(25); 미만 0(10). 벤치마크 없으면 절대수익으로 점수 후 score*0.8, rank*0.9. 폴백 4단계: 다기간 상대 -> 다기간 절대 -> 365일 상대 -> 365일 절대 | `calculators/leadership_calculator.py:L44-L45`, `L99-L170`, `L316-L333`, 점수표 `score_leadership` `L488-L536` |
| 6 | L RS 등급 라벨 | rank>=90 Market Leader; >=80 Strong; >=60 Above Average; >=40 Average; >=25 Laggard; 미만 Weak | `calculators/leadership_calculator.py:L203-L222` |
| 7 | I 기관 보유 | 보유 기관수 N, 보유율 P%, 슈퍼인베스터 유무. 100: N 50~100 & P 30~60; 90: 슈퍼인베스터 & N 30~150; 80: (N 30~49 & P 20~40) 또는 (N 101~150 & P 40~70); 60: (N 20~29 & P 20~50) 또는 (N 50~150 & P 20~70); P<10 또는 >90 -> 20; P<20 또는 >80 -> 40; 기타 50. 슈퍼인베스터 있고 100 미만이면 +10(상한 100). P 없으면 N만으로(50/40/35/20/10) +15(슈퍼인베스터) 상한 70 | `calculators/institutional_calculator.py:L226-L295` |
| 8 | M 시장방향 | 지수 50일 EMA(SMA 시드, k=2/51)와 거리 d%. d>=2 strong_uptrend 90; d>=0 uptrend 70; d>=-2 choppy 40; d>=-5 downtrend 20; 미만 bear_market 0. VIX<15 이면 +10, VIX>30이면 0으로 덮어씀, 0~100 클립. 지수 50일 미만 이력이면 score 50(중립) | `calculators/market_calculator.py:L62-L101`, `L130-L158`, `L161-L191` |
| 9 | M 안전장치 | M=0이면 다른 점수와 무관하게 "avoid" | `scorer.py:L482-L493` |
| 10 | 최소 임계 | C>=60, A>=50, N>=40, S>=40, L>=50, I>=40, M>=40. L<40이면 즉시 avoid. 전부 충족 buy; 1개 미달 watchlist; 2개 이상 avoid | `scorer.py:L472`, `L494-L527` |
| 11 | 유니버스·진행 | 기본 유니버스 = S&P500 시총 상위 40 하드코딩(`--max-candidates` 기본 40), `--universe`로 대체. 종목별로 7요소 계산 -> composite 내림차순 정렬 -> `--top` 20 리포트. 사전 필터 없이 임계 결과는 `threshold_check`로 부착만(제외하지 않음) | `screen_canslim.py:L40`, `L91-L106`, `L369-L372`, `L307-L340`, `L479` |

**점수·등급**
- Phase 3(전체 7요소) 가중치: C 0.15, A 0.20, N 0.15, S 0.15, L 0.20, I 0.10, M 0.05 (합 1.00) — 실행 경로(`screen_canslim.py:L296-L306`이 `calculate_composite_score_phase3` 호출) (`scorer.py:L46-L55`, `L394-L418`). 참고용 Phase1(C .27/A .36/N .27/M .10), Phase2(C .19/A .25/N .19/S .18/I .13/M .06) 가중치도 코드에 존재 (`scorer.py:L29-L44`).
- 등급(composite): >=90 Exceptional+ (15~20% 비중 권고 문구), >=80 Exceptional(10~15%), >=70 Strong(8~12%), >=60 Above Average(5~8%), >=50 Average(3~5%, 워치), >=40 Below Average(매수 금지), 미만 Weak (`scorer.py:L111-L162`). 비중 문구는 안내일 뿐 코드 사이징 아님.
- 약한 컴포넌트(weakest) 표시, 소수 1자리 반올림.

**출력 형식**: JSON+Markdown(`canslim_screener_<ts>`), 종목별 composite_score, rating, guidance, 요소별 점수+지표(EPS 성장, CAGR, 52주 고가거리, up/down 비, rs_3m/6m/12m·rel·rs_rating, 기관수·보유율), threshold_check(recommendation), 시장 요약(M) (`screen_canslim.py:L316-L345`, `L505-L526`).

**SKILL.md와 코드 차이**
- [차이] `new_highs_calculator.py` 헤더는 "신제품 촉매 + 5% 이내 -> 100"이라 하나 코드에는 촉매 판정이 없고 (5% 이내 AND 거래량 1.4배 돌파)만 (`new_highs_calculator.py:L11-L16` vs `L68-L74`, `L113-L114`).
- [차이] `market_calculator.py` 헤더 점수표(100/80/60/40/20/0, "Early uptrend 60")와 실제 코드(90/70/40/20/0 + VIX 가감, early uptrend 상태 없음)가 다름 (`market_calculator.py:L10-L16` vs `L173-L189`).
- [차이] VCP 스크리너의 RS 가중(63/126/189/252일: 0.40/0.20/0.20/0.20)과 CANSLIM의 L 가중(63/126/252일: 0.40/0.30/0.30)이 서로 다름 (`vcp relative_strength_calculator.py:L27-L32` vs `leadership_calculator.py:L44-L45`).
- [차이] RS "rank/percentile"은 전체 종목 대비 백분위가 아니라 벤치마크 초과수익을 구간 매핑한 추정치. O'Neil 원문 RS 80+는 백분위 기준 (`leadership_calculator.py:L6-L8` 주석 vs 구현).
- 스크리너는 임계 미달 종목을 제외하지 않고 순위만 매김(`threshold_check`는 정보). 
- 데이터 부족 시 중립값 사용: A 50, M 50, L 비활성 시 50 — 점수가 부풀 수 있음.
- C는 분기 데이터에서 "최신분기"만 보고 가속(최근 2~3분기 연속 증가)은 평가하지 않음.

**한국 시장 적용**
- 일봉만 되는 요소(N, S, L, M)는 즉시 이식: N은 52주 고가(수정주가) 근접+거래량 1.4배, S는 60일 상승/하락일 거래량 비(KRX 거래량; 단일가/시간외 제외), L은 KOSPI/KOSDAQ 대비 63/126/252일 상대수익 + KRX 전종목 백분위 RS로 대체 권장(원 코드의 절대 매핑 보다 한국에서 안정적일 것으로 [추정]).
- M: ^GSPC -> KOSPI/KOSDAQ(종목 소속 시장 기준), VIX -> VKOSPI(KRX 제공 지수) [추정: 일별 가용성 확인 필요]; 50일 EMA 거리 +2/0/-2/-5% 임계는 그대로 레짐 필터에 사용 가능. 추가로 KRX 상승·하락 종목 수를 폭 지표로 결합 가능.
- C·A: OpenDART 분기·연간 재무(영업이익·순이익·EPS, 매출)로 대체 가능하나 연결/별도, 공시 지연(분기보고서 45일 내), IFRS 재작성, 우선주 EPS, 적자 기업 비율이 높아 A의 "4개 연도 EPS>0" 조건이 많은 종목을 탈락시킴 [추정]. 컨센서스는 FnGuide 등 유료. 원 코드의 EPS 대신 영업이익 YoY와 매출 YoY 사용도 선택지.
- I: 13F 보유기관수/보유율은 한국에 없음. KRX 투자자별(기관·외국인·연기금) 순매수 20~60일 누적/시총 또는 거래대금, 외국인 지분율 변화로 재설계(점수식 새로 필요). 슈퍼인베스터 목록은 폐기.
- 가격제한 ±30%·VI 발동 구간이 거래량 비율(S)에 단일가 왜곡을 줄 수 있어 상·하한가 도달일은 제외 규칙 권장 [추정].
- 시총 상위 40 하드코딩 유니버스는 KOSPI200+KOSDAQ150 + 유동성 하한(거래대금) 필터로 교체.

#### 그룹 소결
이식 우선순위(위원회 점수기 / 진입 / 리스크 게이트 기준):
1. **Trend Template 7조건 + 6/7 게이트 (레짐/종목 필터)**: 종가>SMA150·SMA200, SMA150>SMA200, SMA200 22일 상승, 종가>SMA50, 52주저가 +25% 이상, 52주고가 -25% 이내, RS>70; 충족수*14.3, 통과 >=85(6/7) (`vcp-screener/.../trend_template_calculator.py:L58-L176`). 일봉만으로 구현, KOSPI 기준 RS 교체. 52주 고가 근접은 ±30% 가격제한 특성상 코스닥 소형주에서 25% 완화 검토.
2. **ATR ZigZag 수축 탐지 + 유효성 + 피벗 (진입 트리거)**: ATR14*1.5 반전으로 스윙 확정, 상위 3개 고점 멀티스타트, 수축 최대 4개, T1 깊이>=10%(CLI 기본), 깊이비율<=0.70, 최소 수축기간 5봉, 패턴 15~325봉, 피벗=마지막 수축 고점, 와이드앤루즈(마지막 깊이>15% & <10봉) 시 등급 상한 (`vcp_pattern_calculator.py:L236-L311`, `L408-L506`, `L509-L603`).
3. **실행 상태 결정트리 + 등급 상한 (리스크 게이트)**: 피벗 대비 +3/+5/+10% 구간(Breakout/Early-post/Extended/Overextended), SMA200 이격>50% 과열, 마지막 수축 저점 이탈·SMA50 이탈이면 Damaged; 상태별 최대 등급 캡 (`execution_state.py:L22-L177`). entry_ready는 -8%~+3% 및 risk%<=15, dry-up<=1.0 (`screen_vcp.py:L516-L554`).
4. **거래량 건조 점수 (위원회 점수기)**: 10봉(오늘 제외) 평균/50일 평균: <0.30=90, <0.50=75, <0.70=60, <=1.0=40, 그 외 20; 돌파 거래량 >=1.5배 +10, 20일 순매집일 ±3 초과 ±10, 수축별 거래량 단조 감소 +10 (`volume_pattern_calculator.py:L100-L159`). CANSLIM S의 60일 상승/하락일 거래량비(>=2.0=100 ... <0.5=0)도 동일 계열 (`supply_demand_calculator.py:L152-L173`).
5. **사이징·heat (리스크 게이트·사이징)**: 신호진입=피벗*1.001, 최악진입=피벗*1.02, 손절=마지막 수축 저점*0.99, risk_worst<=8% 거부선, 수량=계좌*0.5%*등급배수(1.75/1.0/0.75/0)/(최악진입-손절), 종목 10%·섹터 30% 상한, 누적 heat 6% 초과 시 보류, 목표 2R (`risk_calculator.py:L22-L202`, `plan_breakout_trades.py:L42`, `L593-L597`). 호가단위 반올림과 갭 손실 가정(±30% 하한가) 추가 필요.
6. **CANSLIM의 일봉 요소 N·S·L·M 및 M=0 거부 (레짐 필터)**: 지수 50EMA 이격 +2/0/-2/-5% 구간 90/70/40/20/0, M=0이면 신규매수 금지 (`market_calculator.py:L91-L101`, `scorer.py:L482-L493`); N은 52주고가 -5% 이내+거래량 1.4배=100. 가중치(C.15 A.20 N.15 S.15 L.20 I.10 M.05)는 참고용; C·A는 OpenDART 연동 후 2단계, I는 KRX 투자자별 순매수로 재설계.

주의: RS 점수는 지수 대비 "절대 초과수익 구간 매핑"이므로 한국 이식 시 KRX 전종목 백분위 RS로 교체하는 편이 안정적 [추정]. 코드 실행·백테스트로 검증한 결과는 없음(문서·소스 정독만).


---

## 12. O'Neil 시장 타이밍: FTD·분산일·천장 탐지 (tradermonty)

> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, 라이선스 MIT — 루트 `LICENSE` L1-L3 "MIT License, Copyright (c) 2026 TraderMonty", 네 스킬 폴더 안에 별도 라이선스 고지 없음) · 범위: ftd-detector, ibd-distribution-day-monitor, market-top-detector, downtrend-duration-analyzer
>
> 방법: 코드를 실행하지 않고 읽기만 한 정적 분석이다. 줄 번호는 모두 커밋 fdfff01에서 Read/grep으로 직접 확인했다. SKILL.md·references와 코드가 다르면 코드 기준으로 적고 [차이]로 표시했다. 저장소 메타데이터(`skills-index.yaml`)는 네 스킬 모두 financial_logic_review·empirical_validation을 `not_verified`로 표시한다(`skills-index.yaml:L798-L806`, `L865-L873`, `L1179-L1187`, `L308-L316`). 즉 수익성·적중률을 검증한 근거는 저장소 안에 없다.

### ftd-detector — FTD Detector

| 항목 | 내용 |
|---|---|
| 기법·출처 | William J. O'Neil/IBD의 Follow-Through Day(조정 후 바닥 확인, 공격 신호). 문서는 "IBD 과거 분석"과 2018-12·2020-03·2022-06·2022-10 사례를 들지만 서지 정보는 없다(`skills/ftd-detector/references/ftd_methodology.md:L1-L8`, `L150-L177`) |
| 분류 | (a) 일봉만으로 구현 가능 — 지수 2개의 일봉 OHLCV와 거래량만 쓴다 |
| 필요 데이터 | ^GSPC와 QQQ 일봉 80세션 요청(상태머신은 최근 60세션, Power Trend·사후 점검은 80세션 전체), 현재가 호가 2건(보고용, 판정에 쓰지 않음)(`skills/ftd-detector/scripts/ftd_detector.py:L73`, `L84`, `L93`, `L102`). FMP 엔드포인트: `stable/historical-price-eod/full` → 실패 시 `api/v3/historical-price-full`, `stable/quote` → `api/v3/quote`(`skills/ftd-detector/scripts/fmp_client.py:L103-L112`). 실행당 4콜. SKILL.md는 무료 플랜(250콜/일)으로 충분하다고 한다(`skills/ftd-detector/SKILL.md:L64`). 그런데 같은 저장소 market-top-detector 클라이언트 주석은 ^GSPC·^VIX가 유료 플랜에 묶일 수 있다고 적는다(`skills/market-top-detector/scripts/fmp_client.py:L352-L354`). ftd-detector에는 yfinance 대체 경로가 없다. 플랜 조건은 확인하지 못했다 |
| 주요 파일 | `scripts/rally_tracker.py`(상태머신), `scripts/post_ftd_monitor.py`(사후 건강도·품질 점수), `scripts/ftd_detector.py`(실행 진입점), `scripts/report_generator.py`, `scripts/_price_bars.py`(결측 검사, 저장소 `scripts/price_bars/`에서 생성된 사본), `scripts/fmp_client.py`, `references/ftd_methodology.md`, `references/post_ftd_guide.md` |
| 라이선스 | 저장소 공통 MIT. 스킬별 고지 없음 |
| 이식 판단 | 부분 채택. 채택: 상태값 체계, FTD 판정식(Day 4~10, +1.25% 이상, 전일보다 큰 거래량), FTD일 저가 이탈 무효화, 품질 점수와 노출 밴드, 결측을 0으로 읽지 않는 fail-closed 데이터 계약. 재작성: 스윙로우·리셋 로직(아래 [차이] 1·2), 이중 확인의 시점 근접 조건. 들어갈 곳: 시장 레짐 필터(방어→공격 전환), 진입 트리거(FTD_CONFIRMED일 때만 신규 매수 허용), 포지션 사이징(점수→노출 밴드), 청산 규칙(FTD일 저가 종가 이탈→노출 축소), 데이터 품질 검사 |

**규칙·계산식**

| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 분석 창 | 최근 60세션(ANALYSIS_LOOKBACK=60). 데이터는 80세션 요청 | `skills/ftd-detector/scripts/rally_tracker.py:L54-L56`; `L458-L461`; `skills/ftd-detector/scripts/ftd_detector.py:L73`, `L84` |
| 2 | 조정(스윙로우) 조건 | 바 i 이전 최대 40바 중 최고 종가 대비 종가 하락률 ≤ -3.0%(MIN_CORRECTION_PCT), 고점 다음 날~i 사이 하락일(종가<전일 종가) ≥ 3(MIN_DOWN_DAYS), 국소 최저(전일 종가와 익일 종가가 i 종가보다 낮지 않음). 종가 기준이며 장중 저가는 보조 기록만 한다 | `rally_tracker.py:L42-L45`; `L82-L136` |
| 3 | 스윙로우 탐색 순서 | 최신 바부터 과거로 훑어 최대 6개를 모으고, 가장 최근 것으로 현재 상태를 정한다. 최신 바는 익일이 없으므로 전일 종가만 확인한다 | `rally_tracker.py:L139-L161`; `L120-L124`; `L495-L498` |
| 4 | Day 1(랠리 시도 1일차) | 스윙로우 다음 바부터 첫 번째로 (종가 > 전일 종가) 또는 (종가-저가)/(고가-저가) ≥ 0.5 인 날. 고가·저가가 없으면 상승 종가만 인정 | `rally_tracker.py:L206-L236` |
| 5 | 랠리 무효화(스윙로우 이탈) | Day 1 전후 어느 날이든 종가 < 스윙로우 종가 → invalidated → 상태 RALLY_FAILED | `rally_tracker.py:L212-L219`; `L264-L271`; `L503-L504` |
| 6 | Day 2~3 무결성 | Day 2·3 종가 < Day 1 장중 저가(없으면 Day 1 종가) → invalidated | `rally_tracker.py:L241`; `L273-L281` |
| 7 | 날짜 세기 | Day 1 이후 모든 거래일을 1씩 센다(상승·하락 무관). 등락률 = 전일 종가 대비 | `rally_tracker.py:L258-L283` |
| 8 | FTD 허용 구간 | Day 4 ~ Day 10(양끝 포함, FTD_DAY_START=4, FTD_DAY_END=10) | `rally_tracker.py:L46-L48`; `L345-L348` |
| 9 | FTD 성립 | 전일 대비 상승률 ≥ 1.25%(FTD_GAIN_MINIMUM) 이고 거래량 > 전일 거래량(엄격 부등호, 전일 거래량 > 0). 구간 안 첫 번째 적격일만 채택 | `rally_tracker.py:L50`; `L364-L376`; `L407` |
| 10 | 상승률 등급 | ≥2.0% strong, ≥1.5% recommended, 그 외 minimum | `rally_tracker.py:L50-L52`; `L378-L384` |
| 11 | 50일 평균 거래량 비교 | FTD일 직전 50바(0 거래량 제외) 평균보다 크면 volume_above_avg=True. 시점 고정(look-ahead 없음) | `rally_tracker.py:L386-L390` |
| 12 | 상태 판정 | 스윙로우 없음 → NO_SIGNAL; 스윙로우 있고 Day 1 없음 → CORRECTION; Day 수 < 4 → RALLY_ATTEMPT; ≥ 4 → FTD_WINDOW; FTD 발견 후 이후 종가가 하나라도 FTD일 저가 미만 → FTD_INVALIDATED, 아니면 FTD_CONFIRMED; FTD 없이 Day > 10 → RALLY_FAILED. 현재 조정 깊이로 조기 종료하지 않는다 | `rally_tracker.py:L488-L531` |
| 13 | 과거 스윙로우 재탐색(Step 2) | 최신 스윙로우에 FTD 맥락이 없으면 그 이전 스윙로우(최대 5개)를 차례로 보며 FTD를 찾는다. 유효하면 FTD_CONFIRMED로 복원. 무효화된 FTD를 만나면 거기서 멈추고(더 오래된 FTD로 넘어가지 않음), 최신 랠리가 RALLY_ATTEMPT/FTD_WINDOW면 그 상태를 유지 | `rally_tracker.py:L540-L584` |
| 14 | 이중 지수 결합 | 두 지수 중 하나라도 FTD_CONFIRMED → 결합 FTD_CONFIRMED(단일로 충분). 둘 다면 dual_confirmation=True. 아니면 우선순위 FTD_WINDOW > RALLY_ATTEMPT > FTD_INVALIDATED > CORRECTION > RALLY_FAILED > NO_SIGNAL 중 높은 쪽 | `rally_tracker.py:L613-L653` |
| 15 | 데이터 갭(fail-closed) | 60세션 창 안에 종가·거래량이 결측·비유한·0 이하인 바가 하나라도 있으면 그 지수는 NO_SIGNAL+data_gap. 어느 지수든 갭이면 결합 상태 NO_SIGNAL, ftd_index=None(다른 지수로 승격하지 않음). 바를 지우지 않는다(위치 기반 비교라 지우면 FTD를 지어낼 수 있음). 거래량 0도 갭 | `rally_tracker.py:L19-L23`; `L59-L66`; `L464-L471`; `L655-L665`; `skills/ftd-detector/scripts/_price_bars.py:L24-L41` |
| 16 | FTD 이후 분산일 | FTD 다음 1~5거래일 중 전일 대비 ≤ -0.2% 이고 거래량 > 전일 | `skills/ftd-detector/scripts/post_ftd_monitor.py:L60`; `L75-L94` |
| 17 | FTD 무효화(사후) | FTD 이후 어느 종가든 FTD일 장중 저가(없으면 FTD 종가) 미만 → invalidated=True, 결합 상태 FTD_INVALIDATED | `post_ftd_monitor.py:L106-L147`; `L531-L532` |
| 18 | Power Trend | (1) 21EMA > 50SMA, (2) 50SMA가 5세션 전 50SMA보다 큼(55바 필요), (3) 종가 > 21EMA. 셋 다 참이면 True. EMA는 가장 오래된 21개 종가의 SMA로 시작. S&P 500만 계산. 점수에는 반영하지 않음 | `post_ftd_monitor.py:L150-L234`; `L568-L578`; `L545-L552` |
| 19 | 품질 점수 — 기준점 | FTD Day 4~7 = 60, Day 8~10 = 50(그 외 40: 실제로는 도달 불가) | `post_ftd_monitor.py:L310-L321` |
| 20 | 품질 점수 — 가산 | 상승률 ≥2.0% +15, ≥1.5% +10, ≥1.25% +5; FTD일 거래량 > 50일 평균 +10; 이중 확인 +15 | `post_ftd_monitor.py:L323-L359` |
| 21 | 품질 점수 — 사후 건강도 | 관찰일 0 → 0; 분산일 없음 → +10; 첫 분산일이 Day 1~2 → -30, Day 3 → -15, Day 4~5 → -5; 분산일 2회 이상이면 추가 -20. 합계를 0~100으로 자른 뒤, 무효화면 0점 "Failed/Invalidated" | `post_ftd_monitor.py:L361-L408` |
| 22 | 점수 출처 지수 | S&P 500 → NASDAQ(QQQ) 순서로 ftd_detected인 첫 지수. 사후 분산·무효화 점검도 그 지수 하나만 본다 | `post_ftd_monitor.py:L279-L287`; `L503-L534` |
| 23 | 데이터 갭 점수 | 어느 지수든 갭, 또는 FTD 자체·사후 분산·무효화 점검에 갭 → total_score 0(정수), signal "Unavailable: data gap", 노출 0-25%. Power Trend 갭만으로는 점수를 막지 않음 | `post_ftd_monitor.py:L270-L277`; `L298-L308`; `L438-L453` |

**점수·등급**: 점수 → 신호·노출 권고: 80 이상 Strong FTD, 75-100%; 60~79 Moderate, 50-75%; 40~59 Weak, 25-50%; 40 미만 Failed/Weak, 0-25%; FTD 없음 0점 "No FTD", 0-25%(`post_ftd_monitor.py:L289-L296`, `L410-L426`). 이론상 최대 합계는 60+15+10+15+10=110이고 100으로 잘린다(골든 테스트 기대값 100: `skills/ftd-detector/scripts/tests/fixtures/golden_expected.json:L121-L134`). 예: 단일 지수 Day 8, +1.3%, 평균 이하 거래량, 사후 분산 없음 → 50+5+0+0+10=65(Moderate). 같은 조건에 Day 1 분산일 → 50+5-30=25(Failed/Weak). 문서 쪽 노출 단계화(FTD일 25% → 무분산 5일 후 50% → 5~15일 75% → Power Trend 시 100%)는 코드에 없는 운용 지침이다(`references/post_ftd_guide.md:L117-L151`).

**출력 형식**: JSON `ftd_detector_YYYY-MM-DD_HHMMSS.json` 최상위 키 `metadata{generated_at, api_calls, index_prices}`, `market_state{combined_state, dual_confirmation, ftd_index, data_gap}`, `data_gap`, `data_quality{sp500, nasdaq}`, `sp500`/`nasdaq`{state, current_price, lookback_high, correction_depth_pct, data_quality, swing_low{date, price, decline_pct, down_days, recent_high_date, recent_high_price}, rally_attempt{day1_date, current_day_count, invalidated, invalidation_reason}, ftd{ftd_detected, ftd_date, ftd_day_number, ftd_low, gain_pct, gain_tier, volume_above_avg}}, `quality_score{total_score, breakdown, signal, guidance, exposure_range, ftd_source}`, `post_ftd_distribution`, `ftd_invalidation`, `power_trend`(`ftd_detector.py:L201-L229`, `L262-L309`). Markdown 절: Market Timing Status, Index Status, Rally Attempt Details, FTD Signal, Quality Score Breakdown, Post-FTD Health, Action Guidance(상태별 문구), Key Watch Levels(스윙로우·FTD일 저가), Methodology, Disclaimer(`skills/ftd-detector/scripts/report_generator.py:L54-L374`). 다운스트림 소비 예: exposure-coach가 `quality_score.total_score`를 가중치 0.05로 읽는다(`skills/exposure-coach/scripts/calculate_exposure.py:L29`, `L243-L254`).

**SKILL.md와 코드 차이**:
1. [차이] 스윙로우 정의. 문서는 "조정 중 가장 낮은 종가"라고 한다(`references/ftd_methodology.md:L20-L28`). 코드는 40바 고점 대비 -3% 이하인 국소 최저(전일·익일 종가보다 낮거나 같음)면 아무 바나 인정하고, 가장 최근 것을 쓴다(`rally_tracker.py:L82-L136`, `L495-L512`). 그래서 랠리 시도 도중의 되돌림 저점(더 높은 저점)이 여전히 고점 대비 -3% 이하면 새 스윙로우가 되고 Day 카운트가 1부터 다시 시작된다. FTD 자체는 Step 2에서 이전 스윙로우 기준으로 계속 잡히지만, 화면 상태는 RALLY_ATTEMPT(재시작된 카운트)로 나올 수 있다. 또 새 스윙로우 기준 Day 4~10이 원래 저점 기준 Day 10을 넘어설 수 있어 실효 FTD 구간이 늘어난다. 이는 코드를 따라가며 확인한 결과이며 테스트로는 검증되지 않는다(테스트 헬퍼는 매일 오르는 단조 랠리만 만든다: `skills/ftd-detector/scripts/tests/helpers.py:L84-L107`).
2. [차이] 리셋. 문서는 Day 2~3이 Day 1 저가를 깨면 "새 Day 1을 기다린다"고 한다(`references/ftd_methodology.md:L50-L56`). docstring도 "resets"라고 쓴다(`rally_tracker.py:L170`). 코드는 invalidated로 끝내고 RALLY_FAILED를 반환한다. `reset_count`는 0으로 초기화만 되고 증가하지 않는다(`rally_tracker.py:L192`, `L273-L281`). 실질적인 재시작은 다음 실행에서 더 최근 스윙로우가 새로 잡힐 때만 일어난다.
3. [차이] 이중 확인. 문서는 두 지수 FTD가 "며칠 이내"일 것을 전제한다(`references/ftd_methodology.md:L104-L109`). 코드는 60세션 창 안에서 두 지수가 각각 FTD_CONFIRMED면 시점 차이와 관계없이 +15를 준다(`rally_tracker.py:L617-L619`, `post_ftd_monitor.py:L352-L359`).
4. [차이] 대상 지수. 문서는 NASDAQ Composite(`references/ftd_methodology.md:L18`), skills-index는 "QQQ/SPY"(`skills-index.yaml:L818`)라고 적지만, 코드는 ^GSPC(지수)와 QQQ(ETF)를 쓴다(`ftd_detector.py:L73`, `L84`).
5. [차이] Power Trend. SKILL.md는 사후 건강도에 Power Trend를 포함한 뒤 점수를 낸다고 적는다(`skills/ftd-detector/SKILL.md:L60-L61`). 코드는 Power Trend를 보고만 하고 점수에 넣지 않는다(`post_ftd_monitor.py:L237-L435`).
6. [차이] 저장소 안 FTD 정의 불일치. market-top-detector에 내장된 FTD는 Day 4~7, +1.5% 이상이고 S&P 500만 본다(`skills/market-top-detector/scripts/scorer.py:L431-L443`, `skills/market-top-detector/references/market_top_methodology.md:L133`). ftd-detector는 Day 4~10, +1.25%다.
7. [차이] 성공률 수치 충돌. ftd-detector 문서는 FTD의 약 25%만 성공(75% 실패)이라고 하고(`references/ftd_methodology.md:L7`), market-top 문서는 약 25%가 실패한다고 한다(`skills/market-top-detector/references/market_top_methodology.md:L136`, `skills/market-top-detector/references/distribution_day_guide.md:L82`). 분산일 시점별 실패율 표(약 85%/80%/65%/50%/45%/35%)와 점수대별 성공률도 출처가 없다(`references/post_ftd_guide.md:L22-L29`, `L178-L185`). 코드는 이 수치들을 계산하지 않는다.
8. 상태 지속: 명시적인 "상승 추세 복귀" 전이가 없다. FTD_CONFIRMED나 RALLY_FAILED는 그 스윙로우가 60세션 창에서 빠질 때까지 유지되고, 빠지면 NO_SIGNAL로 돌아간다(`rally_tracker.py:L139-L161`, `L458-L493`). 코드 추적 결과이며 문서와 충돌하지는 않는다.

**한국 시장 적용**:
- 대상 지수: KOSPI·KOSDAQ(또는 KOSPI200·KOSDAQ150)을 S&P 500·QQQ 자리에 넣는다. 로직은 지수 일봉 OHLCV와 거래량만 요구하므로 그대로 이식된다. Day 1의 "범위 상단 50%" 규칙에는 지수 고가·저가가 필요한데, KRX 지수 시세에 시가·고가·저가가 있다 [추정].
- 지수 거래량 출처 후보: KRX 정보데이터시스템의 지수 시세(거래량·거래대금), KRX Open API 지수 일별시세, 비공식 pykrx 래퍼, 증권사 API 업종지수 일봉 [추정: 메뉴·함수 이름은 직접 확인하지 않음]. ETF(예: KODEX 200) 거래량은 LP 호가·레버리지/인버스 수요 영향이 커서 대용으로는 부적합할 가능성이 높다 [추정].
- 거래량 정의: 지수 "거래량"은 주식 수 합계라 저가주 비중이 크다. 기관 참여 측정 취지에는 "거래대금 전일 대비 증가"가 더 맞을 수 있다(특히 KOSDAQ). 두 정의를 모두 계산해 백테스트로 고른다 [추정].
- 임계값 재보정: +1.25%·-3%·3하락일은 S&P 500 변동성에 맞춘 값이다. KOSDAQ 일간 변동성은 S&P보다 높고 KOSPI는 비슷하거나 약간 높다 [추정]. 고정값 대신 변동성 비례(예: FTD 최소 상승률 = 1.25% × σ_KR/σ_SPX, 또는 max(1.25%, k·σ20))로 바꾸고 계수는 백테스트로 정한다 [추정]. KOSDAQ는 조정 기준 3%가 너무 잦게 걸릴 수 있어 4~5%를 검토한다 [추정].
- 갭 문제: 한국 지수는 전날 밤 미국장 영향으로 갭 상승 후 밀리는 날이 많다 [추정]. FTD일에 "종가 ≥ 시가" 또는 "종가가 범위 상단"을 보조 조건으로 검토한다.
- 특수일 플래그: 선물·옵션 동시만기일(3·6·9·12월), 지수 정기변경일, 개장 시각이 늦춰지는 날(연초 첫 거래일·수능일)은 전일 대비 거래량 비교를 왜곡할 수 있다 [추정]. 데이터 품질 단계에서 표시하고 FTD/분산일 판정에서 제외하거나 감점한다.
- NXT(2025-03 출범): KRX 지수 거래량이 넥스트레이드 체결을 포함하는지 확인하지 못했다. 포함하지 않으면 출범 전후로 거래량 수준이 구조적으로 바뀌어 50일 평균 비교(규칙 11)가 그 구간에서 왜곡될 수 있다 [추정]. 한 가지 정의(KRX 단독 또는 통합)로 일관되게 쓰고, 구조 변화일을 품질 플래그로 남긴다.
- 집중도: KOSPI는 반도체 대형주 비중이 높아 지수 FTD가 소수 종목에 좌우될 수 있다 [추정]. 동일가중 폭 지표(50일선 위 종목 비율 등)로 교차 확인한다.
- 가격제한폭·호가단위: 지수 신호에는 영향이 없다. FTD 후 실제 매수 단계에서 상한가 잠김 종목은 체결이 안 되므로 진입 후보에서 뺀다.

### ibd-distribution-day-monitor — IBD Distribution Day Monitor

| 항목 | 내용 |
|---|---|
| 기법·출처 | IBD/O'Neil의 분산일(Distribution Day) 계수. 참고문헌: William J. O'Neil 『How to Make Money in Stocks』, IBD "Big Picture" 칼럼(`skills/ibd-distribution-day-monitor/references/ibd_distribution_methodology.md:L1-L5`, `L66-L68`). TQQQ/QQQ 노출 정책은 저장소 자체 설계(`references/tqqq_exposure_policy.md`) |
| 분류 | (a) 일봉만으로 구현 가능 |
| 필요 데이터 | QQQ(나스닥 대용)·SPY(S&P 500 대용) ETF 일봉 OHLCV를 lookback 80+5=85세션 요청(`skills/ibd-distribution-day-monitor/config/default.yaml:L4-L10`, `skills/ibd-distribution-day-monitor/scripts/ibd_monitor.py:L352`, `L363`). FMP `stable/historical-price-eod/full` → `api/v3/historical-price-full`(`skills/ibd-distribution-day-monitor/scripts/fmp_client.py:L102-L103`). 2콜. 호가·웹 검색 없음. 무료 플랜으로 충분하다고 기재(`skills/ibd-distribution-day-monitor/SKILL.md:L104-L105`) |
| 주요 파일 | `scripts/distribution_day_tracker.py`(감지·만료·무효화·계수), `scripts/risk_classifier.py`, `scripts/exposure_policy.py`, `scripts/ibd_monitor.py`(진입점, MA 필터), `scripts/models.py`, `scripts/data_loader.py`, `scripts/history_utils.py`, `scripts/math_utils.py`, `scripts/report_generator.py`, `config/default.yaml`, `references/*.md` |
| 라이선스 | 저장소 공통 MIT. 스킬별 고지 없음 |
| 이식 판단 | 채택(한국 임계값 재보정 전제). 규칙이 단순·결정론적이고 설정 파일로 분리돼 있다. 들어갈 곳: 위원회의 "분산(기관 매도) 관점" 점수기, 시장 레짐 필터·리스크 게이트(CAUTION 이상이면 신규 매수 중단), 포지션 사이징(위험 단계 → 목표 노출, 트레일링 스톱 상한). 정체일(stall day) 미구현과 결측 처리가 fail-closed가 아닌 점은 보완한다 |

**규칙·계산식**

| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 분산일 감지 | (종가/전일 종가 - 1) ≤ -0.002 (+1e-12 허용오차) 이고 거래량 > 전일 거래량. 장중 고가는 감지에 쓰지 않음 | `skills/ibd-distribution-day-monitor/scripts/distribution_day_tracker.py:L18`; `L39-L41`; `config/default.yaml:L17-L18`; `scripts/models.py:L12-L19` |
| 2 | 결측 처리 | 오늘·전일 중 종가 또는 거래량이 없거나 0 이하이면 그 쌍을 건너뛰고 skipped_sessions에 기록. 실행은 계속(fail-closed 아님). 날짜가 통째로 빠진 경우는 검사하지 않음 | `distribution_day_tracker.py:L32-L37`; `L110-L117`; `scripts/data_loader.py:L28-L54` |
| 3 | 나이·만료 | 최신 세션 = age 0. age > 25(expiration_sessions)이면 expired. 즉 age 0~25인 26개 세션 동안 유효 | `distribution_day_tracker.py:L1-L12`; `L87-L89`; `config/default.yaml:L19` |
| 4 | 5% 상승 무효화 | 임계가 = 분산일 종가 × 1.05. 분산일 이후 세션의 장중 고가(기본값, 설정으로 종가 선택 가능)가 처음으로 임계가 이상인 날 invalidated. 스캔은 분산일 후 25세션 안으로 제한(넘으면 expired로 처리). 분산일 당일 고가는 제외. 오늘 생긴 분산일은 무효화하지 않음 | `distribution_day_tracker.py:L120-L159`; `config/default.yaml:L20-L22`; `references/ibd_distribution_methodology.md:L22-L31` |
| 5 | 상태 우선순위 | invalidated > expired > active | `distribution_day_tracker.py:L83-L92` |
| 6 | 구간 계수 | d5/d15/d25 = active이면서 age ≤ N인 개수(N+1개 세션을 본다) | `distribution_day_tracker.py:L98-L107`; `ibd_monitor.py:L235-L237`; `SKILL.md:L45-L47` |
| 7 | 추세 필터 | 21EMA(첫 21개 SMA로 시작)·50SMA. market_below_21ema_or_50ma = 종가가 두 이평선 모두 아래일 때만 True. 둘 중 하나라도 계산 불가면 None(SEVERE 상향 생략) | `ibd_monitor.py:L125-L166`; `scripts/math_utils.py:L9-L61` |
| 8 | 지수별 위험 단계 | SEVERE: d25 ≥ 6 또는 d15 ≥ 4 또는 (이평 하회 True 이고 d25 ≥ 5). HIGH: d25 ≥ 5 또는 d15 ≥ 3 또는 d5 ≥ 2. CAUTION: d25 ≥ 3. 그 외 NORMAL | `scripts/risk_classifier.py:L10-L30`; `config/default.yaml:L24-L34`; `models.py:L22-L32` |
| 9 | 지수 결합(QQQ 가중) | 하나라도 SEVERE → SEVERE; QQQ HIGH → HIGH; QQQ NORMAL+SPY HIGH → HIGH; QQQ CAUTION+SPY CAUTION 또는 HIGH → HIGH; 그 외 최댓값 | `risk_classifier.py:L33-L58` |
| 10 | 노출 정책(TQQQ) | NORMAL 100%·기본 스톱; CAUTION AVOID_NEW_ADDS 75%·min(기본, 7%); HIGH REDUCE_EXPOSURE 50%·min(기본, 5%)·대안 SWITCH_PARTIAL_TO_QQQ; SEVERE CLOSE_TQQQ_OR_HEDGE 25%·min(기본, 3%)·대안 SWITCH_TO_QQQ_OR_CASH | `scripts/exposure_policy.py:L10-L15`; `L36-L39`; `L54-L58` |
| 11 | 노출 정책(QQQ, 1배) | NORMAL 100%; CAUTION 100%(신규 추가만 중단)·min(기본, 8%); HIGH 75%·min(기본, 6%); SEVERE REDUCE_EXPOSURE_OR_HEDGE 50%·min(기본, 5%). 스톱은 항상 기본값과 상한 중 더 좁은 쪽(넓히지 않음) | `exposure_policy.py:L17-L22`; `references/tqqq_exposure_policy.md:L36-L37` |
| 12 | 군집 플래그(보고용) | has_d5_cluster: d5 ≥ 2, has_d15_cluster: d15 ≥ 3, has_d25_cluster: d25 ≥ 5 | `ibd_monitor.py:L206-L212` |
| 13 | 데이터 길이 점검 | 최소 세션 = max(80, 50, 21, 25+2) = 80. 미만이면 insufficient_lookback 플래그(실행은 계속) | `ibd_monitor.py:L112-L122`; `scripts/history_utils.py:L50-L52` |
| 14 | 과거 시점 재생 | `--as-of` 날짜로 리베이스해 그 날을 index 0으로 계산 | `history_utils.py:L40-L48`; `ibd_monitor.py:L59` |
| 15 | 정체일(stall day) | 의도적으로 v1 범위 밖(구현 없음) | `references/ibd_distribution_methodology.md:L63` |

**점수·등급**: 0~100 점수는 없다. 지수별 위험 단계 NORMAL/CAUTION/HIGH/SEVERE와 결합 단계, 그리고 이에 대응하는 목표 노출·트레일링 스톱 상한·권고 행동이 출력이다(규칙 8~11). 목표 노출 값을 바꾸려면 `exposure_policy.py`를 직접 고쳐야 하고, 단계 경계는 `config/default.yaml`에서 바꾼다(`references/tqqq_exposure_policy.md:L44-L46`).

**출력 형식**: JSON `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json`: `market_distribution_state{as_of, generated_at, overall_risk_level, primary_signal_symbol, index_results[]}`. 각 index_result는 symbol, benchmark_name, is_distribution_day_today, today{date, close, previous_close, pct_change, volume, previous_volume, volume_change_pct}, d5_count/d15_count/d25_count, active_distribution_days[]·removed_distribution_days[](DDRecord: date, age_sessions, close, pct_change, volume_change_pct, high_since, invalidation_price, invalidation_date, invalidation_trigger_price/source, expires_in_sessions, status, removal_reason), risk_level, cluster_state, trend_filters, explanation(일본어 문장), skipped_sessions. 그 밖에 `portfolio_action{instrument, recommended_action, current_exposure_pct, target_exposure_pct, exposure_delta_pct, trailing_stop_pct, alternative_action, rationale}`, `rule_evaluation{rule_version, distribution_day_rule, thresholds_used}`, `audit{data_source, as_of_resolved, symbols_loaded, skipped_sessions, audit_flags, config_snapshot...}`(`ibd_monitor.py:L268-L310`, `L404-L421`; `models.py:L35-L89`). API 키 등 민감 키는 마스킹(`scripts/report_generator.py:L15-L38`). Markdown: 지수별 위험·d5/d15/d25·활성 분산일 표, Portfolio Action, Audit(`report_generator.py:L56-L151`).

**SKILL.md와 코드 차이**:
1. [차이] 이평 필터 이름은 `market_below_21ema_or_50ma`("또는")인데 코드는 두 이평선 모두 아래일 때만 True다(`ibd_monitor.py:L159-L160`, 테스트 `scripts/tests/test_ibd_monitor_coverage.py:L254-L262`가 "한쪽만 아래면 False"를 확인). 방법론 문서의 해당 문장은 글자 그대로 읽으면 반대(종가가 두 이평 위)로 읽힌다(`references/ibd_distribution_methodology.md:L55`).
2. [차이] SKILL.md의 결합 규칙 요약에는 "QQQ CAUTION + SPY CAUTION/HIGH → HIGH"가 빠져 있다(`SKILL.md:L57` vs `risk_classifier.py:L55-L56`). QQQ 정책 요약에도 CAUTION(100%, 스톱 상한 8%)이 빠져 있다(`SKILL.md:L67` vs `exposure_policy.py:L19`).
3. [차이] 같은 저장소 market-top-detector의 분산일 계수와 규칙이 다르다. 이쪽은 5% 무효화가 있고 유효 창이 age 0~25(26세션)다. market-top 쪽은 5% 무효화가 없고 최근 25세션(0~24)만 보며 정체일을 0.5로 센다(`skills/market-top-detector/scripts/calculators/distribution_day_calculator.py:L94-L154`).
4. 문서상 주석 오류(동작 영향 없음): 무효화 스캔 루프 주석의 시간 순서 설명이 뒤바뀌어 있으나, 루프 자체는 분산일 직후 세션부터 시간순으로 훑는다(`distribution_day_tracker.py:L145-L147`).

**한국 시장 적용**:
- 대상: KOSPI·KOSDAQ 지수(또는 KOSPI200·KOSDAQ150) 일봉. ETF 대용 대신 KRX 지수 일별 거래량·거래대금을 쓰는 편이 낫다. 국내 지수 추종 ETF 거래량은 LP·레버리지/인버스 수요 영향이 크다 [추정].
- 거래량 정의: "거래대금 > 전일"을 주 정의로, "거래량 > 전일"을 보조로 두고 백테스트로 고른다 [추정]. 이유는 ftd-detector 항목과 같다.
- 임계값: -0.2% 하락 기준과 d25 3/5/6 단계는 미국 기준이다. 한국 지수로 분산일 기저율(전체 거래일 중 분산일 비율)과 d25 분포를 먼저 계산한다. 그다음 (1) 하락 기준을 변동성 비례로 조정(KOSDAQ은 약 -0.25~-0.3% 후보)하거나, (2) 기준은 두고 단계 경계를 한국 d25 분포의 백분위로 다시 잡는다 [추정]. 5% 무효화도 KOSDAQ에서는 σ 비례 상향(약 6~7%)을 검토한다 [추정].
- 결합 규칙: QQQ 가중은 TQQQ 보유를 전제로 한 설계다. 우리 유니버스가 KOSPI 대형주 중심이면 KOSPI, 코스닥 성장주 중심이면 KOSDAQ을 주 지수로 둔다.
- 수급 보강(신규 아이디어): KRX 투자자별 순매수를 이용해 "분산일 + 외국인·기관 동반 순매도"일을 가중 분산일로 세는 관점을 추가할 수 있다 [추정].
- 특수일: 동시만기일·지수 정기변경일·개장 지연일의 거래량 급변은 가짜 분산일을 만들 수 있다. 플래그를 달고 별도로 집계한다 [추정].
- 결측: 이 스킬은 결측 쌍을 건너뛰기만 한다. 우리 엔진에서는 ftd-detector처럼 결측·0 거래량이 있으면 그 판정을 "불가"로 처리하고, KRX 거래일 달력으로 날짜가 빠졌는지도 검사한다.
- 노출 정책: 레버리지 ETF(예: 코스피200 레버리지)를 운용하면 TQQQ 표, 현물·1배 위주면 QQQ 표를 출발점으로 쓴다 [추정].

### market-top-detector — Market Top Detector

| 항목 | 내용 |
|---|---|
| 기법·출처 | 세 축의 합성: O'Neil 분산일(『How to Make Money in Stocks』), Mark Minervini 선도주 약화(『Trade Like a Stock Market Wizard』 / 『Think & Trade Like a Champion』), "Monty" 방어 섹터 순환(monty-trader.com 블로그 글)(`skills/market-top-detector/references/market_top_methodology.md:L9-L11`, `L36-L38`, `L60-L62`). 여기에 시장 폭·지수 기술적 상태·심리 3개를 더해 6개 구성요소. 2~8주 전술적 천장 위험(10~20% 조정) 대상. 점수는 확률이 아닌 휴리스틱 위험 점수라고 명시(`SKILL.md:L18-L28`) |
| 분류 | 주 (c) 시장 폭·거시 데이터 필요(200/50일선 상회 비율, VIX·VIX3M, 풋/콜, 마진부채, 섹터 ETF). 보조 (a) — 분산일·지수 기술적 상태는 일봉만으로 가능 |
| 필요 데이터 | FMP: ^GSPC·QQQ 호가와 일봉 260세션, ^VIX·^VIX3M 호가, 선도 ETF 후보 20개 호가와 선택된 10개의 일봉 60세션, 섹터 ETF 7개 일봉 50세션(QQQ는 재사용)(`scripts/market_top_detector.py:L388-L468`). FMP가 비면 yfinance로 대체 조회한다(`scripts/fmp_client.py:L349-L365`, `L405-L472`). 주석은 ^GSPC·^VIX가 유료 FMP 플랜에 묶일 수 있다고 적는다(`fmp_client.py:L352-L354`, `L408-L410`). 공개 CSV: TraderMonty GitHub Pages의 시장 폭 CSV(200일선 상회 비율, 키 불필요)(`scripts/breadth_csv_client.py:L20`). 웹 검색 입력(CLI로 전달): S&P 500 50일선 상회 비율, CBOE 주식 풋/콜, VIX 기간구조(선택), FINRA 마진부채 YoY(선택)(`SKILL.md:L74-L112`). SKILL.md는 검색 결과가 부실하면 barchart·ycharts 페이지를 직접 가져오라고 지시한다(`SKILL.md:L90`, `L98`). 이번 분석에서는 따르지 않았다. 거래소 달력: pandas-market-calendars XNYS(`scripts/utils.py:L12-L26`, `requirements.txt:L3`) |
| 주요 파일 | `scripts/market_top_detector.py`(진입점), `scripts/scorer.py`(합성·구간·내장 FTD), `scripts/calculators/{distribution_day, leading_stock, defensive_rotation, breadth, index_technical, sentiment}_calculator.py`, `scripts/breadth_csv_client.py`, `scripts/fmp_client.py`, `scripts/historical_comparator.py`, `scripts/scenario_engine.py`, `scripts/report_generator.py`, `references/{market_top_methodology, distribution_day_guide, historical_tops, point_in_time_evaluation}.md` |
| 라이선스 | 저장소 공통 MIT. 스킬별 고지 없음. 참고문헌에 제3자 블로그 글의 일본어 문장 인용이 있다(`references/market_top_methodology.md:L42-L44`) |
| 이식 판단 | 부분 채택. 채택: (1) 합성 인프라 — 가용성 기반 가중치 재배분, 상관 구성요소 할인, 점수 구간 → 위험 예산 매핑. 위원회 집계기에 그대로 쓸 수 있다. (2) 일봉 기반 구성요소(분산일은 ibd 모니터 버전으로 교체, 지수 기술적 상태, 방어/공격 순환, 선도 바스켓 약화)를 위원회의 개별 관점 점수기로. (3) 시점 고정 평가 프로토콜을 사후 분석 기준으로. 보류: 심리 구성요소(VIX 기간구조·풋콜·마진부채)는 한국 대체 데이터를 확보한 뒤에, 과거 천장 비교와 what-if 시나리오는 보고용으로만. 들어갈 곳: 위원회 점수기 + 리스크 게이트(구간별 위험 예산) |

**규칙·계산식**

| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 합성 가중치 | 분산일 0.25, 선도주 0.20, 방어 순환 0.15, 시장 폭 0.15, 지수 기술 0.15, 심리 0.10 | `skills/market-top-detector/scripts/scorer.py:L26-L33` |
| 2 | 상관 할인 | 분산일과 방어 순환이 둘 다 ≥ 80이면 가중치가 낮은 쪽(방어 순환) 점수 × 0.8 | `scorer.py:L44-L87` |
| 3 | 가용성 재배분 | data_available=False인 구성요소는 빼고 나머지 가중치를 합이 1이 되게 정규화. 분산일은 항상 True로 둔다. 품질 라벨: 6/6 Complete, 4~5 Partial, 그 이하 Limited | `scorer.py:L114-L173`; `scripts/market_top_detector.py:L581-L590` |
| 4 | 구간 → 위험 예산 | ≤20 Green 100%; ≤40 Yellow 80-90%(스톱 10-20% 조임, 신규 규모 25-50% 축소); ≤60 Orange 60-75%(약한 25-30% 차익, 모멘텀 신규 금지); ≤80 Red 40-55%(보유 40-50% 매도, 헤지 검토); >80 Critical 20-35% | `scorer.py:L224-L292` |
| 5 | (1) 분산일 — 감지 | 최근 25세션(i=0~24): 등락률 ≤ -0.2% 이고 거래량 > 전일 → 분산일. 거래량 > 전일 이고 0 ≤ 등락률 < 0.1% → 정체일(0.5개). 5% 무효화 없음 | `scripts/calculators/distribution_day_calculator.py:L94-L154` |
| 6 | (1) 분산일 — 점수 | 유효 개수 = 분산일 + 0.5×정체일. S&P 500과 QQQ 중 큰 값. ≥6:100, ≥5:90, ≥4:75, ≥3:55, ≥2:30, ≥1:15, 0:0. 유효 ≥2 이고 (최근 5세션 이벤트 수 / 전체 이벤트 수) > 0.5이면 × 1.15(상한 100) | `distribution_day_calculator.py:L33-L57`; `L157-L193` |
| 7 | (2) 선도주 — 바스켓 | 기본 8개 ETF: ARKK, WCLD, IGV, XBI, SOXX, SMH, KWEB, TAN. 기본 실행은 동적: 후보 20개(SMH, SOXX, PSI, SOXQ, IGV, WCLD, CLOU, BUG, XBI, ARKG, ARKK, ARKW, KOMP, TAN, ICLN, KWEB, FDN, FINX, IPAY, BOTZ) 중 현재가/52주 고가 상위 10개. 유효 후보 < 5이면 기본 바스켓 | `scripts/calculators/leading_stock_calculator.py:L23-L80`; `market_top_detector.py:L439-L452` |
| 8 | (2) 선도주 — ETF별 약화 점수 | 52주 고가 대비 ≤-25%:40, ≤-15%:30, ≤-10%:20, ≤-5%:10; 현재가 < 50SMA:+20; 현재가 < 200SMA:+20(200바 이상일 때), 200바 미만이면 현재가 < 0.95×50SMA:+10(추정치); 최근 20일 고가의 스윙 고점 중 최근 것 < 그 전 것:+20; 상한 100 | `leading_stock_calculator.py:L193-L292` |
| 9 | (2) 선도주 — 집계 | ETF 점수 평균. 점수 ≥ 50인 ETF 비율 ≥ 60%이면 × 1.3(상한 100). 호가+50바 이상 확보 비율 < 0.75이면 data_available=False. 평가할 ETF가 없으면 50(중립) | `leading_stock_calculator.py:L113-L164` |
| 10 | (3) 방어 순환 | 방어 XLU·XLP·XLV·VNQ 평균수익 - 공격 XLK·XLC·XLY·QQQ 평균수익 = r. 10·20·40일 r을 각각 점수화해 가중 0.2/0.5/0.3 평균. 점수(구간 선형): r≥5:100; 3~5: 80+(r-3)/2×20; 1.5~3: 60+(r-1.5)/1.5×20; 0.5~1.5: 40+(r-0.5)×20; 0~0.5: 20+r/0.5×20; -2~0: 20+r/2×20; < -2: 0 | `scripts/calculators/defensive_rotation_calculator.py:L26-L74`; `L125-L152`; `L205-L220` |
| 11 | (3) 방어 순환 — 확인 | 2개 기간 이상 계산되고 모두 방어 우위면 confirmed(상한 100), 아니면 unconfirmed(상한 80). 성공률 ≥ 0.75면 data_available. 데이터 없으면 50 | `defensive_rotation_calculator.py:L111-L123`; `L154-L165`; `L192` |
| 12 | (4) 시장 폭 | 200일선 상회 비율 b(자동: CSV `Breadth_Index_Raw`×100). 점수(선형): b<40:100; 40~50: 100→55; 50~60: 55→30; 60~70: 30→5; ≥70: 5. S&P 500이 52주 고가 -5% 이내가 아니면 × 0.5. 50일선 비율 < 30 이고 고점 근처면 +10, > 70이면 -5. b가 없으면 50(중립, data_available=False) | `scripts/calculators/breadth_calculator.py:L42-L118`; `market_top_detector.py:L495-L530`; `scripts/breadth_csv_client.py:L25-L57` |
| 13 | (5) 지수 기술 | 지수별: 가격 < 21EMA +8; 가격 < 50EMA +12; 21EMA < 50EMA +10; 가격 < 200SMA +15; 실패 랠리 +10(최근 15일 최고 종가가 3~10일 전이고 현재 종가가 그보다 2% 넘게 낮음); 낮아지는 고점 +10(최근 20일 고가 스윙 고점); 갭 하락 +10(최근 5일 중 시가가 전일 종가 대비 ≤ -0.5% 이고 거래량 > 전일×1.1). 최종 = S&P 500·QQQ 평균. 최댓값 75(0~100으로 늘리지 않음) | `scripts/calculators/index_technical_calculator.py:L47-L66`; `L88-L236` |
| 14 | (6) 심리 | 풋/콜 <0.60:35, <0.70:25, <0.80:12; VIX <12:25, <14:17, <16:8, ≤25:0, >25:-8; VIX 기간구조 steep_contango 25, contango 12, flat 0, backwardation -8; 마진부채 YoY >30%:15, >20%:10, >10%:5; 합계를 0~100으로 자름. VIX·풋콜·기간구조가 모두 없으면 50(중립) | `scripts/calculators/sentiment_calculator.py:L63-L161` |
| 15 | VIX 기간구조 자동 판정 | 비율 = VIX/VIX3M: <0.85 steep_contango, <0.95 contango, ≤1.05 flat, 그 외 backwardation | `scripts/fmp_client.py:L514-L549` |
| 16 | 내장 FTD 모니터 | 합성 ≥ 40일 때만(S&P 500만): 최근 40세션, 20바 고점 대비 -3% 이하·하락일 ≥3·국소 최저 → 스윙로우. 종가 < 스윙로우면 그 날로 스윙로우를 옮기고 Day 1을 다시 찾음. Day 1 = 상승 종가 또는 범위 상단 50%. FTD = Day 4~7, +1.5% 이상, 거래량 > 전일 | `scorer.py:L295-L484` |
| 17 | 과거 천장 비교 | 2000·2007·2018·2022 추정 점수 벡터와의 가중 SSD. 가장 가까운 것의 RMS ≤ 15면 비교 가능, 아니면 "no comparable episode". 구성요소가 하나라도 불가하면 비교하지 않음 | `scripts/historical_comparator.py:L14-L154` |
| 18 | what-if 시나리오 | (a) 시장 폭 → 최소 55, (b) 분산일 → 최대 55, (c) 가장 낮은 3개 +20, (d) 가장 높은 2개 -30으로 합성 재계산 | `scripts/scenario_engine.py:L33-L113` |
| 19 | 신선도 계수 | 입력 날짜 기준 XNYS 영업일 ≤1:1.0, ≤3:0.95, ≤7:0.85, 그 외 0.70, 미래 날짜 0.70. overall_confidence = 최솟값. JSON 메타데이터에만 저장 | `market_top_detector.py:L162-L223`; `L555-L564`; `L683` |
| 20 | 시점 재생 거부 | 과거 날짜 `--as-of`는 호가가 시점 고정이 아니라는 이유로 실행 거부. 입력 날짜가 as-of보다 미래여도 거부 | `market_top_detector.py:L346-L363` |
| 21 | 직전 실행 대비 변화 | 구성요소·합성 변화 절댓값 ≤ 3이면 stable, 증가 worsening, 감소 improving | `market_top_detector.py:L244-L295`; `L601-L620` |

**점수·등급**: 합성 = Σ(조정 점수 × 유효 가중치), 소수 첫째 자리 반올림(`scorer.py:L125-L131`). 구간과 위험 예산은 규칙 4. 출력에 `score_kind: heuristic_risk_score`, `calibrated_probability: false`를 명시한다(`scorer.py:L194-L199`). 문서상 설계 목표(정상 10~20, 조기 경고 25~40, 천장 형성 초중반 40~55, 명확한 천장 60~80, 붕괴 80+)는 측정된 보정 결과가 아니다(`references/market_top_methodology.md:L161-L168`). 검증용 사전 등록 프로토콜이 별도로 있다. 사건 = 향후 40거래일 안에 S&P 500 종가가 기준일 종가 대비 10% 이상 하락. 매주 금요일 관측, 개발 2000~2015·홀드아웃 2016~2025, 구간 [0,20]~(80,100]별 사건 비율과 Wilson 95% 구간, 60 초과 경보의 정밀도·재현율, 52주 블록 부트스트랩 2,000회(seed 515)(`references/point_in_time_evaluation.md:L9-L21`, `L28-L31`, `L48-L58`, `L66-L80`). 저장소에 측정 결과는 없다.

**출력 형식**: JSON `market_top_YYYY-MM-DD_HHMMSS.json`: `metadata{generated_at, as_of_date, data_mode, api_calls, cli_inputs, vix_term_auto, index_data{sp500_price, sp500_year_high, sp500_distance_from_high_pct, qqq_price, vix_level}, data_freshness}`, `composite{score_kind, score_version, calibrated_probability, interpretation, composite_score, zone, zone_color, risk_budget, guidance, actions, strongest_warning, weakest_warning, data_quality, correlation_adjustment, component_scores{score, adjusted_score, weight, weighted_contribution, label}}`, `components{distribution_days, leading_stocks, defensive_rotation, breadth_divergence, index_technical, sentiment}`, `follow_through_day`, `historical_comparison`, `scenarios`, `delta`, `additional_context`(`market_top_detector.py:L660-L699`; `scorer.py:L194-L221`). Markdown 절: Overall Assessment, Component Scores(가중치·기여도·변화), Component Details 1~6, Follow-Through Day Monitor, Recommended Actions, Historical Comparison, What-If Scenarios, Additional Context, Methodology(`scripts/report_generator.py:L49-L410`). 직전 보고서는 출력 폴더의 최신 `market_top_*.json`에서 읽는다(`market_top_detector.py:L226-L241`). 다운스트림: exposure-coach가 합성 점수를 top_risk 가중치 0.20으로 읽는다(`skills/exposure-coach/scripts/calculate_exposure.py:L23`, `L214-L230`).

**SKILL.md와 코드 차이**:
1. [차이] SKILL.md는 50일선 비율과 풋/콜을 [REQUIRED]로 표시한다(`SKILL.md:L86`, `L93`). 코드에서는 둘 다 선택 입력이다. 50일선은 ±보정에만 쓰이고(`breadth_calculator.py:L62-L67`), 풋/콜이 없어도 VIX만 있으면 심리 점수가 계산된다(`sentiment_calculator.py:L64-L71`, `L92-L93`).
2. [차이] SKILL.md는 모든 수동 입력이 최근 3영업일 이내여야 하고 신선도 경고를 보여 주라고 한다(`SKILL.md:L58`, `L77`, `L143`). 코드는 신선도 계수를 계산만 해서 JSON 메타데이터에 넣고, 점수와 Markdown에는 쓰지 않는다(`market_top_detector.py:L555-L564`, `L683`).
3. [차이] 방법론은 선도 ETF의 200일선 하회를 본다고 한다(`references/market_top_methodology.md:L52-L56`). 코드는 선도 ETF 일봉을 60세션만 받으므로(`market_top_detector.py:L443`, `L452`) 200SMA는 한 번도 계산되지 않고 "현재가 < 0.95×50SMA → +10" 추정 분기만 탄다(`leading_stock_calculator.py:L230-L240`).
4. [차이] 지수 기술 docstring은 "0~100으로 스케일"이라고 하지만(`index_technical_calculator.py:L17-L18`) 코드는 평균만 내므로 최댓값이 75다(`L65-L66`). 이 구성요소는 가중치 15%의 75%까지만 기여한다.
5. [차이] 시장 폭 모듈 docstring의 계단형 표(<40:100, <50:80, <60:60, <70:35, ≥70:10)와(`breadth_calculator.py:L10-L15`) 실제 함수의 선형 보간(`L97-L118`)이 다르다. 코드 기준으로는 62.26% → 약 24점이다(`L107`).
6. [차이] 방어 순환 docstring은 "음수 → 0"이라고 하지만(`defensive_rotation_calculator.py:L17`) 코드는 -2%~0%에 0~20점을 준다(`L217-L220`).
7. [차이] 내장 FTD는 Day 4~7, +1.5%로 ftd-detector(Day 4~10, +1.25%)와 다르다. docstring은 "합성 > 40"인데 코드는 ≥ 40이다(`scorer.py:L298`, `L313`). 정체일 정의(0 ≤ 등락 < 0.1%, 거래량 증가)는 장중 위치나 상승 후 맥락을 보지 않는 단순화다(`distribution_day_calculator.py:L137-L139`). IBD식 정체일은 소폭 상승·거래량 증가·범위 하단 마감을 함께 본다 [추정].
8. [차이] API 사용량. SKILL.md는 "~33콜, 무료 플랜 충분"이라고 한다(`SKILL.md:L51`, `L185`). 코드상 기본(동적 바스켓) 실행을 세면 호가 1+1+1+1(VIX3M)+20, 일봉 1+1+10+7로 약 43콜이다(정적 바스켓은 약 29콜, 엔드포인트 폴백·재시도 제외, 필자 계산). 또 FMP가 비면 yfinance로 넘어가는데, 이 의존성은 requirements에만 선택 항목으로 있고(`requirements.txt:L5`) SKILL.md 전제 조건에는 없다.
9. 참고: 과거 천장 4건의 구성요소 점수는 "회고적 추정"이며 보정 근거가 아니라고 코드와 문서가 모두 밝힌다(`historical_comparator.py:L13-L14`, `L143`; `references/historical_tops.md:L1-L6`, `L125-L126`).

**한국 시장 적용**:
- (1) 분산일: KOSPI·KOSDAQ 지수 거래대금(또는 거래량)으로 바로 계산된다. 5% 무효화가 있는 ibd 모니터 규칙으로 통일하는 편이 낫다. 정체일을 쓰려면 "범위 하단 마감" 조건을 더한다 [추정].
- (2) 선도주: 미국 성장 테마 ETF 바스켓에 대응할 국내 ETF는 수가 적고 소수 대형주에 몰려 있다 [추정]. 개별 종목 바스켓을 권한다 [추정]. KOSPI200+KOSDAQ150에서 유동성 필터(예: 20일 평균 거래대금 하한) 후 52주 고가 근접도 또는 6~12개월 상대강도 상위 N개를 고른다. 이는 저장소의 동적 선택 방식을 종목 단위로 옮긴 것이다. 구성은 반드시 시점 고정(그 날까지의 데이터만)으로 하고, 관리종목·거래정지·상한가 잠김 종목은 뺀다. 200일선 판정용으로 일봉 200바 이상을 확보한다(원본의 60바 한계를 피함).
- (3) 방어 순환: KRX/KOSPI 업종지수로 대응한다. 방어 후보는 전기·가스, 통신, 음식료·담배, 공격 후보는 전기·전자(반도체), 증권, IT서비스, 화학(2차전지 소재)이다 [추정: 현재 업종지수 명칭은 확인 필요]. 한국 헬스케어(바이오)는 고베타라 방어 섹터로 넣으면 안 된다 [추정].
- (4) 시장 폭: 전 종목 일봉으로 200일선·50일선 상회 비율을 직접 계산한다(참고 사실). 대상은 KOSPI200·KOSDAQ150 시점 고정 구성종목 또는 우선주·ETF·스팩을 뺀 전 종목. "지수가 52주 고가 -5% 이내" 조건은 KOSPI 기준으로 그대로 쓴다. 상승·하락 종목 수(KRX 제공)로 ADR을 보조 지표로 더할 수 있다.
- (5) 지수 기술: KOSPI·KOSDAQ 일봉으로 그대로 계산된다. 갭 하락 규칙(-0.5%, 거래량 ×1.1)은 미국장 영향으로 갭이 잦은 한국에서 과다 발동할 수 있으므로 기준을 높이는 것을 검토한다 [추정].
- (6) 심리: VIX → VKOSPI(KRX 산출), CBOE 풋/콜 → KOSPI200 옵션 풋/콜 거래량 비율, 마진부채 → 신용융자잔고 YoY(금융투자협회 통계) [추정: 데이터 위치는 직접 확인하지 않음]. VIX3M에 해당하는 국내 기간구조 지수는 없는 것으로 알고 있다 [추정]. 이 항목은 빼고 가중치 재배분 규칙(규칙 3)에 맡긴다. 임계값(VIX 12/14/16/25, 풋콜 0.6/0.7/0.8)은 미국 값이라 VKOSPI·국내 풋콜 분포의 백분위로 다시 잡아야 한다.
- 가중치·구간: 출발점으로 쓰되, `references/point_in_time_evaluation.md`의 절차(주간 관측, 40거래일 10% 하락 사건, 개발/홀드아웃 분리)를 KOSPI로 바꿔 검증한 뒤 조정한다.
- 달력: XNYS 대신 KRX 거래일 달력을 쓴다(pandas-market-calendars/exchange_calendars의 XKRX 지원 여부는 확인하지 않음 [추정]).

### downtrend-duration-analyzer — Downtrend Duration Analyzer

| 항목 | 내용 |
|---|---|
| 기법·출처 | 개별 종목의 고점→저점 하락 구간 길이·깊이 분포(중심 이동창 극값 탐지). 특정 트레이더 기법이 아니다. 참고문헌으로 Fama-French(1993), Jegadeesh(1990), Lo-MacKinlay(1988)를 들지만 알고리즘과 직접 연결되지는 않는다(`skills/downtrend-duration-analyzer/references/downtrend_methodology.md:L152-L156`) |
| 분류 | (a) 일봉만으로 구현 가능 — 단 사후 분석 전용(중심 창이 미래 20바를 쓰므로 실시간 신호로는 쓸 수 없음). 섹터·시가총액 메타데이터가 필요 |
| 필요 데이터 | FMP `stable/company-screener`(→`api/v3/stock-screener`, isActivelyTrading=true, limit 500, 섹터 필터)로 종목 목록, 앞에서부터 최대 100종목 × 5년 일봉(`stable/historical-price-eod/full` → v3)(`scripts/analyze_downtrends.py:L75-L159`, `L476-L481`). 종목 수+1콜. 키를 URL 쿼리 파라미터로 보낸다(`L83-L89`, `L128`). HTML은 Plotly CDN을 불러온다(`scripts/generate_histogram_html.py:L25`) |
| 주요 파일 | `scripts/analyze_downtrends.py`, `scripts/generate_histogram_html.py`, `references/downtrend_methodology.md` |
| 라이선스 | 저장소 공통 MIT. 스킬별 고지 없음 |
| 이식 판단 | 보류(사후 분석 도구로만 부분 사용). 매매 신호가 아니다. 쓸모는 "하락 구간 길이 분포"로 시간 손절·보유기간 상한·눌림목 대기 기간을 정하는 데 있다. 들어갈 곳: 사후 분석(시간 기반 청산 규칙의 파라미터 보정) |

**규칙·계산식**

| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 고점·저점 탐지 | 바 i의 종가가 [i-20, i+20] 창의 최대면 고점, 최소면 저점(창 ±peak_window=20). 양끝 20바는 검사하지 않음 | `skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py:L162-L188` |
| 2 | 하락 구간 | 각 고점에서 다음 고점 전까지의 저점 중 최저 종가. 깊이 = (저점-고점)/고점×100, 기간 = 저점 인덱스 - 고점 인덱스(거래일 수) | `analyze_downtrends.py:L191-L231` |
| 3 | 필터 | 깊이 절댓값 ≥ 5%(`--min-depth`, 기본 5.0), 기간 ≥ 3거래일(고정, CLI 미노출) | `analyze_downtrends.py:L195-L196`; `L233-L237`; `L446-L451` |
| 4 | 시가총액 구간 | ≥ $200B Mega, ≥ $10B Large, ≥ $2B Mid, 그 외 Small(현재 시총 기준, 시점 고정 아님) | `analyze_downtrends.py:L24-L29`; `L61-L72` |
| 5 | 통계 | 전체: 개수, 중앙값, 평균, P25/P75/P90(np.percentile). 섹터·시총 구간별: 개수, 중앙값, 평균 | `analyze_downtrends.py:L290-L332` |
| 6 | 최소 데이터 | 일봉이 2×20+1=41바 미만인 종목은 건너뜀 | `analyze_downtrends.py:L269-L270` |

**점수·등급**: 점수 없음. 문서는 짧은 조정(5~15일)·중간(15~40일)·장기(40일+)라는 해석 구간과(`SKILL.md:L64-L66`) "S&P 500 구성종목 2019~2024" 기준이라는 벤치마크 표를 싣지만, 스스로 예시값이라고 밝힌다(`references/downtrend_methodology.md:L111-L123`).

**출력 형식**: JSON `downtrend_analysis_YYYY-MM-DD_HHMMSS.json`: `schema_version`, `analysis_date`(UTC), `parameters{lookback_years, sector_filter, peak_window, trough_window, min_depth_pct}`, `summary{total_downtrends, median/mean/p25/p75/p90_duration_days}`, `by_sector`, `by_market_cap`, `downtrends[]{peak_idx, trough_idx, peak_date, trough_date, peak_price, trough_price, duration_days, depth_pct, symbol, sector, market_cap_tier}`(`analyze_downtrends.py:L515-L529`). Markdown: Summary Statistics, By Market Cap Tier, By Sector, Key Insights(`L335-L413`). HTML 히스토그램(섹터·시총 필터, 구간 폭 선택)(`scripts/generate_histogram_html.py:L25-L245`).

**SKILL.md와 코드 차이**:
1. [차이] `--trough-window` 인자는 받기만 하고 계산에 쓰이지 않는다. 고점·저점 모두 peak_window 창을 쓴다(`analyze_downtrends.py:L162-L188`, `L440-L445`). SKILL.md와 방법론은 두 창을 따로 적는다(`SKILL.md:L76-L80`, `references/downtrend_methodology.md:L25-L29`).
2. [차이] SKILL.md는 "회복 기간"을 이해하는 데 쓴다고 하지만(`SKILL.md:L10`) 코드는 고점→저점 하락 국면만 잰다. 이전 고점 회복까지의 기간은 계산하지 않는다.
3. [차이] 방법론은 기간을 "고점·저점 포함, 거래소 달력 사용"이라고 하지만(`references/downtrend_methodology.md:L48-L51`) 코드는 인덱스 차이(고점 미포함)다.
4. [차이] 방법론의 "겹치는 극값 중 가장 극단적인 것만 남김"은(`references/downtrend_methodology.md:L36`) 저점에 대해서만 부분 구현돼 있다(다음 고점 전 최저 저점 선택). 같은 종가의 고점 중복은 정리하지 않는다.
5. 생존 편향: 현재 상장(isActivelyTrading)된 종목만 쓴다. 문서도 한계로 적는다(`references/downtrend_methodology.md:L150`).

**한국 시장 적용**: KRX 전 종목 수정주가 일봉으로 그대로 계산할 수 있다. 상장폐지 종목을 포함해 생존 편향을 줄이고, 시총 구간은 원화로 다시 정의한다(예: 10조 이상 / 2조~10조 / 5천억~2조 / 5천억 미만) [추정]. 업종은 KRX 업종 분류를 쓴다(상용 분류 체계를 쓰려면 라이선스를 확인). ±30% 가격제한폭과 거래정지 기간은 하락 기간을 왜곡하므로 정지일을 제외하거나 표시한다. 실시간 엔진에는 넣지 않고, 시간 손절(예: 보유일이 해당 업종·시총 구간 P90을 넘으면 재평가)의 파라미터를 보정하는 사후 분석에만 쓴다.

#### 그룹 소결

1. 분산일 계수기(ibd-distribution-day-monitor 규칙) — 채택. 규칙: 종가 -0.2% 이하 + 거래량 전일 초과; age > 25세션 만료; 분산일 종가 +5%를 이후 장중 고가가 넘으면 제거; d5/d15/d25로 NORMAL(d25 ≤ 2) / CAUTION(d25 ≥ 3) / HIGH(d25 ≥ 5, d15 ≥ 3, d5 ≥ 2 중 하나) / SEVERE(d25 ≥ 6, d15 ≥ 4, 또는 두 이평 하회 + d25 ≥ 5). 위치: 시장 레짐 필터·리스크 게이트(CAUTION부터 신규 매수 중단), 포지션 사이징(1배 기준 100/100/75/50%, 레버리지 기준 100/75/50/25%, 트레일링 스톱 상한 8·6·5% 또는 7·5·3%). 근거: `skills/ibd-distribution-day-monitor/scripts/distribution_day_tracker.py:L39-L41`, `L120-L159`, `skills/ibd-distribution-day-monitor/scripts/risk_classifier.py:L10-L30`, `skills/ibd-distribution-day-monitor/scripts/exposure_policy.py:L10-L22`. 한국: 지수 거래대금 기준, 기저율에 맞춘 임계값 재보정, 특수일 플래그.
2. FTD 상태머신 + 품질 점수(ftd-detector) — 부분 채택. 규칙: 스윙로우(40바 고점 대비 -3%, 하락일 ≥3) → Day 1(상승 종가 또는 범위 상단 50%) → Day 2~3은 Day 1 저가 유지 → Day 4~10에 +1.25% 이상·전일보다 큰 거래량이면 FTD. 점수: 60/50 + 상승률 15/10/5 + 50일 평균 초과 10 + 이중 확인 15 + 사후 건강도(+10/-5/-15/-30, 분산 2회 이상 -20) → 노출 75-100/50-75/25-50/0-25%. 위치: 레짐 전환(방어→공격) 트리거, 진입 허용 게이트, 노출 밴드. 근거: `skills/ftd-detector/scripts/rally_tracker.py:L42-L52`, `L164-L409`, `skills/ftd-detector/scripts/post_ftd_monitor.py:L310-L426`. 필수 수정: 스윙로우를 "조정 중 최저 종가(또는 최저 저가)"로 추적하고 그 저점이 깨지기 전까지 Day 카운트를 이어 간다. 두 지수 FTD의 시점 근접 조건(예: N일 이내)을 넣는다. KOSDAQ는 최소 상승률을 변동성에 비례해 올린다.
3. FTD 사후 무효화·조기 분산 감점 — 채택. 규칙: FTD 이후 종가가 FTD일 장중 저가 미만이면 신호 무효(노출 0-25%). FTD 후 1~5일 안의 분산일(-0.2%, 거래량 증가)은 시점별로 감점한다. 위치: 청산 규칙·리스크 게이트(FTD 기반으로 늘린 노출을 되돌리는 손절선). 근거: `skills/ftd-detector/scripts/post_ftd_monitor.py:L34-L147`, `L395-L408`.
4. 위원회 집계 인프라(market-top-detector scorer) — 채택. 데이터가 없는 관점은 빼고 가중치를 재정규화한다. 상관된 두 관점(분산일·방어 순환)이 동시에 80 이상이면 낮은 가중치 쪽을 ×0.8로 할인한다. 합성 점수 구간을 위험 예산으로 매핑한다(≤20:100%, ≤40:80-90%, ≤60:60-75%, ≤80:40-55%, >80:20-35%). 데이터 품질 라벨(6/6, 4~5, 그 이하)도 함께 둔다. 우리 다관점 위원회의 합의 단계에 그대로 맞는다. 근거: `skills/market-top-detector/scripts/scorer.py:L26-L173`, `L224-L292`.
5. fail-closed 데이터 품질 계약 — 채택. 결측·비유한·0 이하 가격과 0 거래량을 0으로 읽지 않는다. 바를 지우지 않는다(위치 기반 비교에서 가짜 신호를 막음). 갭이 있으면 상태를 "판정 불가"로, 점수를 0으로 두고 노출 확대를 금지한다. 한 지수가 갭이면 다른 지수로 승격하지 않는다. 위치: 데이터 품질 검사 단계. 근거: `skills/ftd-detector/scripts/_price_bars.py:L24-L99`, `skills/ftd-detector/scripts/rally_tracker.py:L655-L665`, `skills/ftd-detector/scripts/post_ftd_monitor.py:L438-L453`. 한국에서는 KRX 거래일 달력과 대조해 빠진 날짜도 갭으로 처리하고, NXT 집계 범위 변경일·동시만기일을 품질 플래그로 남긴다.
6. 시점 고정 평가 프로토콜 — 채택(사후 분석 기준). 주간 관측, 향후 40거래일 안 10% 이상 하락을 사건으로 정의, 개발/홀드아웃 시간 분리와 경계 퍼지, 점수 구간별 Wilson 구간, 블록 부트스트랩, 미래 날짜 입력 거부, 과거 재생 시 아카이브 입력만 사용. 우리 엔진의 레짐 필터·위원회 점수 검증 절차로 KOSPI에 맞게 옮긴다. 근거: `skills/market-top-detector/references/point_in_time_evaluation.md:L9-L80`, `skills/market-top-detector/scripts/market_top_detector.py:L346-L363`.

주의: 네 스킬 모두 저장소 스스로 금융 논리와 실증 검증을 하지 않았다고 표시하고, 성공률·실패율 수치(FTD 25%, 분산일 시점별 실패율 등)에는 출처가 없으며 서로 충돌하기도 한다. 이식할 때는 규칙 구조만 가져오고, 임계값은 한국 데이터로 다시 추정해야 한다.


---

## 13. 시장 레짐·시장 폭·노출도 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, 루트 LICENSE MIT) · 범위: exposure-coach, market-breadth-analyzer, uptrend-analyzer, macro-regime-detector, us-market-bubble-detector, breadth-chart-analyst, market-environment-analysis, crypto-regime-analyzer

### exposure-coach — Exposure Coach
| 항목 | 내용 |
|---|---|
| 기법·출처 | 상위 스킬 JSON 8종(regime, top_risk, breadth, uptrend, institutional, sector, theme, ftd)을 0-100 점수로 환산해 가중평균 -> 노출 상한(%)·권고·편향·참여도·신뢰도. 원저자 TraderMonty 자체 휴리스틱(학술 출처 없음) [추정] |
| 분류 | (c) 시장 폭·거시 종합(결합 규칙). 주=위원회 결합 규칙 |
| 필요 데이터 | 상위 스킬 산출 JSON 파일(숫자 점수). 자체 가격 데이터 불필요 |
| 주요 파일 | skills/exposure-coach/scripts/calculate_exposure.py, scripts/provenance_contract.py, references/exposure_framework.md |
| 라이선스 | MIT (LICENSE:L1, Copyright 2026 TraderMonty) |
| 이식 판단 | 채택(구조 그대로): 위원회 결합 규칙 + 리스크 게이트(노출 상한). 가중치·구간표는 한국 데이터로 재보정 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 입력 가중치 | regime .25, top_risk .20, breadth .15, uptrend .15, institutional .10, sector .05, theme .05, ftd .05 (합 1.0) | scripts/calculate_exposure.py:L21-L30 |
| 2 | 치명 입력 집합 | CRITICAL = {regime, top_risk, breadth} | scripts/calculate_exposure.py:L33 |
| 3 | 결합식 | composite = sum(score_i*w_i)/sum(w_i) (제공된 입력만, 가중치 재정규화). 전부 결측이면 50.0 반환 | scripts/calculate_exposure.py:L366-L399 |
| 4 | 결측 치명 입력 감점 | composite = max(0, composite - 10*결측 치명 입력 수). 재정규화 후 적용. 단, 전부 결측이면 감점 없이 50.0 | scripts/calculate_exposure.py:L390-L399 |
| 5 | 노출 상한 구간(구간별 선형) | >=80: min(100, 90+(c-80)); 65-80: 70+(c-65)*1.3; 50-65: 50+(c-50)*1.3; 35-50: 30+(c-35)*1.3; 20-35: 10+(c-20)*1.3; <20: int(c/2). int 절사 | scripts/calculate_exposure.py:L402-L415 |
| 6 | 권고 결정표 | CASH_PRIORITY: c<30 또는 top_risk<25. REDUCE_ONLY: c<50 또는 top_risk<40 또는 결측 치명 >=2. 나머지 NEW_ENTRY_ALLOWED (top_risk 결측이면 top_risk 조건은 건너뜀) | scripts/calculate_exposure.py:L418-L436 |
| 7 | 신뢰도 | n_provided>=6 이고 결측 치명 0 -> HIGH; n_provided>=4 또는 결측 치명<=1 -> MEDIUM; 그 외 LOW (신뢰도는 입력 완결성만, 품질 아님) | scripts/calculate_exposure.py:L504-L514 |
| 8 | regime 점수 | broadening 80, concentration 60, transitional 50, inflationary 40, contraction 20; 모르는 이름은 50; regime_score 필드 있으면 우선 | scripts/calculate_exposure.py:L36-L42, L170-L190 |
| 9 | regime 입력 fail-closed | 중첩형이면 confidence 필수·{high,moderate,low,very_low} 아니면 무효, very_low 무효, composite.data_quality(available_count, total_components 정수, 0<avail<=total) 필수. 무효 -> 점수 None(결측 취급, 라벨 Unknown) | scripts/calculate_exposure.py:L45-L92 |
| 10 | breadth 점수 | breadth_score/composite_score/composite.composite_score 그대로(높을수록 건강). 폴백: ad_ratio>1.5 & nh_nl>3 ->90; ad>=1 & nhnl>=1 ->65; ad>=.7 & nhnl>=.5 ->40; 아니면 20 | scripts/calculate_exposure.py:L107-L132 |
| 11 | uptrend 점수 | uptrend_score 또는 composite.composite_score 그대로. 비율(%)만 있으면: pct>50: min(100,50+pct); 35-50: 35+pct; 20-35: 20+pct; <20: pct | scripts/calculate_exposure.py:L135-L167 |
| 12 | top_risk 점수(반전) | top_risk_score 그대로; 또는 100-composite_score(탑 감지기 점수, 높을수록 위험); 또는 100-top_probability; 또는 분배일수 <=2 ->90, <=4 ->65, <=6 ->40, 그 외 15 | scripts/calculate_exposure.py:L214-L240 |
| 13 | ftd 점수 | ftd_score 또는 quality_score.total_score(0-100, 반전 없음); anomaly_level 폴백 none90/low80/moderate55/elevated35/critical15 | scripts/calculate_exposure.py:L243-L262 |
| 14 | theme 점수 | round(50 + mean(부호 있는 heat)/2), bullish +heat, bearish -heat; 한 행이라도 무효면 None; theme_strength 폴백 strong85/stable65/rotating40/collapsing20 | scripts/calculate_exposure.py:L274-L314 |
| 15 | sector/institutional 폴백 | sector: dispersion<.1 & 선도=기술/경기소비 85; dispersion<.2 65; 선도=유틸/필수/헬스 35; 그 외 50. institutional: net_flow>.5 90, >0 70, >-.5 40, 그 외 20; flow_direction 매핑 90/70/50/30/15 | scripts/calculate_exposure.py:L317-L363 |
| 16 | 참여도 | uptrend>=50 AND breadth>=50 AND 섹터 dispersion<0.15(없으면 통과) -> BROAD; (둘 중 하나) AND 저분산 -> MODERATE; 그 외 NARROW | scripts/calculate_exposure.py:L483-L501 |
| 17 | 편향(bias) | regime=inflationary VALUE, contraction DEFENSIVE; theme>60 & (broadening/concentration) GROWTH; 섹터 선도 기술계열 GROWTH/금융·에너지·소재·산업 VALUE/방어 DEFENSIVE; 자금흐름 growth-value 차이 >0.2; 나머지 NEUTRAL | scripts/calculate_exposure.py:L439-L480 |
| 18 | 엄격 출처 게이트(선택) | --require-provenance: breadth·uptrend 필수, data_provenance의 run_id 일치, retrieved_at UTC·평가시각 이전, as_of 미래 금지, 나이>max_age_days면 "stale"로 거부(parser.error=실행 중단). top_risk 등 나머지 입력은 게이트 밖 | scripts/provenance_contract.py:L145-L204; scripts/calculate_exposure.py:L689-L701 |

**점수·등급**: 노출 상한 6구간(위 5). 구간 문서표(80-100 -> 90-100% 등)는 코드와 일치(references/exposure_framework.md:L30-L35 근처). 권고 3단계, 신뢰도 3단계, 참여도 3단계, 편향 4종.

**출력 형식**: JSON `exposure_posture_<ts>.json` + 마크다운. 필드 schema_version, exposure_ceiling_pct, bias, participation, recommendation, confidence, composite_score, component_scores, inputs_provided, inputs_missing, rationale, (inputs_unparseable, input_warnings, input_lineage) (scripts/calculate_exposure.py:L761-L790 근처, L766-L780).

**SKILL.md와 코드 차이**
- [차이] references/regime_exposure_map.md는 레짐 기준선(80-100% 등)에 +5/-10/-15% 가감을 더하는 방식으로 서술(L70-L113)하나, 코드는 가중평균 + 구간 선형 매핑이며 가감식은 구현 없음.
- [차이] 문서 신뢰도 "충돌 있으면 낮춤"(exposure_framework.md:L198-L200)이나 코드는 충돌 판정 없이 개수만 봄.
- [차이] 문서 "Reduce confidence proportionally"(framework L134-L136) vs 코드의 신뢰도는 3단 이산값. 입력 전부 결측이면 감점 없이 composite 50, 상한 50%이나 권고는 REDUCE_ONLY(결측 치명 3>=2), 신뢰도 LOW.
- fail-closed 여부: 부분적. regime 무효 입력만 명시적 fail-closed(결측 취급+감점). 나머지 입력 결측은 "제외+재정규화"(관대). top_risk 결측 시 top_risk 하드 게이트(<25/<40)도 사라짐. 즉 치명 입력 2개 이상 없으면 REDUCE_ONLY로 보수적 폴백.

**한국 시장 적용**: 입력 점수를 (breadth=KRX 전 종목 200일선 위 비율 기반, uptrend=상승추세 비율, regime=원/달러·금리차·외국인 순매수 기반 레짐, top_risk=KOSPI/KOSDAQ 분배일 수, institutional=외국인·기관 순매수 [추정]) 로 대체. 코스피·코스닥 각각 계산해 두 값 중 낮은 쪽(또는 시총가중)을 쓰는 방식 [추정]. 가중치 .25/.20/.15/.15/.10/.05x3는 미검증 휴리스틱이므로 한국 백테스트로 재보정. 상한을 포지션 사이징의 총노출 상한(리스크 게이트)으로 연결.

### market-breadth-analyzer — Market Breadth Analyzer
| 항목 | 내용 |
|---|---|
| 기법·출처 | S&P500 구성종목 중 200일선 위 비율(Breadth_Index_Raw, 0-1)의 8일/200일 EMA, 피크/트로프, 약세 신호를 6개 구성요소 점수화. 원 데이터·정의는 같은 저자의 tradermonty/market-breadth-analysis 저장소(공개 CSV) |
| 분류 | (c) 시장 폭. 단 지수 자체는 KRX 전 종목 일봉으로 직접 계산 가능 -> (a)로 이식 가능 |
| 필요 데이터 | 공개 CSV 2개(키 불필요): detail https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv , summary .../market_breadth_summary.csv (scripts/csv_client.py:L9-L24). detail 컬럼: Date, S&P500_Price, Breadth_Index_Raw, Breadth_Index_200MA, Breadth_Index_8MA, Breadth_200MA_Trend(+1/-1), Bearish_Signal, Is_Peak, Is_Trough, Is_Trough_8MA_Below_04 (csv_client.py:L27-L38). summary: Metric/Value, 필수 "Average Peaks (200MA)", "Average Troughs (8MA < 0.4)" (L42-L43) |
| 주요 파일 | skills/market-breadth-analyzer/scripts/scorer.py, scripts/calculators/*.py, references/breadth_analysis_methodology.md |
| 라이선스 | MIT. 단 데이터 CSV는 별도 저장소 산출물(라이선스 미확인) |
| 이식 판단 | 부분 채택: 6개 점수식을 KRX 직접계산 breadth(200일선 위 비율)에 적용해 위원회 점수기 + 레짐 필터. 피크/트로프(scipy find_peaks)는 일봉 직접 계산 가능 |

**규칙·계산식** (breadth 값 b는 0-1 비율; 모든 구성요소 0-100, 높을수록 건강)
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 지표 정의 | Raw=200일선 위 종목 비율; 8MA=8일 EMA(빠른 신호); 200MA=200일 EMA(추세 필터); 200MA_Trend는 히스테리시스 threshold 0.001; Is_Peak/Trough는 scipy find_peaks(200MA, distance=50, prominence=0.015); Is_Trough_8MA_Below_04는 8MA<0.4 반전 prominence 0.02 | references/breadth_analysis_methodology.md:L14-L35 |
| 2 | 가중치 | C1 level&trend .25, C2 8MA-200MA 교차 .20, C3 사이클 위치 .20, C4 약세 신호 .15, C5 역사적 백분위 .10, C6 가격-폭 다이버전스 .10 | scripts/scorer.py:L31-L38 |
| 3 | 결측 처리 | data_available=False 구성요소의 가중치를 나머지에 비례 재분배. 전부 결측이면 50.0·Neutral(참고용). 품질 라벨: 6/6 Complete, >=4 Partial, 그 외 Limited | scripts/scorer.py:L56-L113 |
| 4 | C1 level 점수 | 8MA >=.70 95; >=.60 80; >=.50 65; >=.40 50; >=.30 35; >=.20 20; <.20 5 | scripts/calculators/trend_level_calculator.py:L117-L131 |
| 5 | C1 결합 | score = clamp(round(0.7*level + 0.3*trend) + mod). trend: +1 -> 80, -1 -> 20. mod(5일 전 8MA 대비): 하락 & 8MA>.60 -> -10; 하락 & <.40 -> +5; 상승 & <.60 -> +5; 그 외 0 | trend_level_calculator.py:L42-L43,L87-L112 |
| 6 | C2 gap 점수 | gap=8MA-200MA. >=+.15 95; >=+.10 80; >=+.05 65; >=0 50; >=-.05 35; >=-.10 20; 미만 5. mod: gap<0 & 8MA(5일) 상승 +10; gap>0 & 하락 -10. 데이터<6행이면 결측 | scripts/calculators/ma_crossover_calculator.py:L33-L46,L71-L82,L91-L104 |
| 7 | C3 사이클 | 최근 120행에서 가장 최근 마커. TROUGH: <=20일 상승 85/비상승 30; 21-60일 상승 75/아니면 35; >60일 상승 65/아니면 40; 극단 트로프(8MA<0.4) +10. PEAK: <=20일 하락 20/상승 60; 21-60일 하락 15/상승 45; >60일 하락 10/상승 50. 마커 없음 50 (data_available=False 처리됨) | scripts/calculators/cycle_calculator.py:L99-L135, L74 |
| 8 | C4 약세 신호 | 기본: Signal=F&Trend=1 85; F&-1 50; T&1 30; T&-1 10. 보정: Signal=T & 8MA>.50 +15; T & 8MA<.25 -5; Pink Zone(Trend==-1 & 8MA<200MA) & Signal=F -> -10 | scripts/calculators/bearish_signal_calculator.py:L11-L24,L63-L78 |
| 9 | C5 백분위 | 현재 8MA의 전체 이력 내 백분위(작은 값 비율). >=80 90; >=60 70; >=40 50; >=20 30; 미만 10. 보정: 8MA >= 평균피크*0.95 -> -10; (else) <= 평균트로프*1.05 -> +10 | scripts/calculators/historical_context_calculator.py:L9-L17,L40-L58 |
| 10 | C6 다이버전스 | 60일(0.6) + 20일(0.4) 윈도우. 윈도우별: 가격+3% & 폭변화<-0.05 -> 10; 가격+1% & 폭<-0.03 -> 25; 가격-3% & 폭>+0.05 -> 80; -1% & >+0.03 -> 65; |가격|<0.5% & |폭|<0.01 -> 50; 둘 다 상승 70; 둘 다 하락 30; 그 외 50. Early warning: 20일<=25 & 60일>=50. 행<20이면 결측 | scripts/calculators/divergence_calculator.py:L45-L52,L135-L158 |
| 11 | 신선도 | 최신 행이 5 달력일 초과면 경고(차단 안 함) | scripts/csv_client.py:L170-L207 |

**점수·등급** (scorer._interpret_zone, scripts/scorer.py:L167-L248): >=80 Strong(노출 90-100%); 60-79 Healthy(75-90%); 40-59 Neutral(60-75%, 신규 사이즈 25-50% 축소); 20-39 Weakening(40-60%, 약한 25-40% 익절·신규 모멘텀 금지); <20 Critical(25-40%, 현금 60-75%).

**출력 형식**: JSON(composite_score, zone, exposure_guidance, actions, strongest/weakest_health, component_scores[score, weight, effective_weight, weighted_contribution], data_quality, data_freshness) + 마크다운 (scripts/market_breadth_analyzer.py:L240 근처, scorer.py:L127-L165). 이력 추적 history_tracker.py.

**SKILL.md와 코드 차이**: [차이] cycle_calculator docstring(L9-L22)에 없는 분기가 코드에 있음(PEAK 21-60일 상승 45, TROUGH 21-60일 비상승 35, >60일 비상승 40). exposure-coach의 breadth 입력은 이 composite_score를 그대로 사용(exposure-coach calculate_exposure.py:L116-L120). 결측 "마커 없음"은 점수 50이지만 data_available=False라 가중치에서 제외됨(cycle_calculator.py:L76).

**한국 시장 적용**: Raw = KRX 전 종목(코스피/코스닥 분리, 우선주·ETF·ETN·스팩 제외 [추정]) 종가 > SMA200 비율을 일별 계산 -> 8·200 EMA, 5일 방향, 피크/트로프(find_peaks와 동일 파라미터 distance=50, prominence=0.015 사용 가능), 가격 계열은 KOSPI/KOSDAQ 지수. 외부 CSV 불필요. 역사적 백분위는 최소 수년 이력 필요(상장 종목 일봉 전체). KRX는 가격제한 +-30%라 극단값 영향은 미국과 유사 수준 [추정]. 임계값(.70/.60/.40/.20)은 미국 기준이므로 코스피/코스닥 분포로 재보정.

### uptrend-analyzer — Uptrend Ratio Analyzer
| 항목 | 내용 |
|---|---|
| 기법·출처 | tradermonty/uptrend-dashboard가 매일 계산해 공개하는 "상승 추세 종목 비율"(전체+11 GICS 섹터)을 5개 구성요소로 점수화 |
| 분류 | (c) 시장 폭. 정의가 일봉 지표(SMA20/50/200, 52주 고저, 4주 수익률)뿐이라 KRX 전 종목 일봉으로 직접 구현 가능 -> (a) |
| 필요 데이터 | 공개 CSV(키 불필요): https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/uptrend_ratio_timeseries.csv (컬럼 worksheet,date,count,total,ratio,ma_10,slope,trend), .../data/sector_summary.csv (Sector,Ratio,10MA,Trend,Slope,Status) (scripts/data_fetcher.py:L21-L30) |
| 주요 파일 | skills/uptrend-analyzer/scripts/scorer.py, scripts/calculators/*.py, references/uptrend_methodology.md |
| 라이선스 | MIT (CSV 원 저장소 라이선스는 미확인) |
| 이식 판단 | 채택: "상승 추세" 정의와 비율 점수 밴드 -> KRX breadth 점수기. 섹터 회전은 KRX 업종/WICS로 대체 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 상승 추세 종목 정의(원 정의, 코드 아님: Finviz 스크리너 문서) | 가격>$10, 평균거래량>100K, 시총>$50M(기본 필터) AND 가격>SMA20 AND 가격>SMA200 AND SMA50>SMA200 AND 52주 저점 대비 +30% 초과 AND 4주 수익률 상승. 비율 = 조건 충족 수 / 기본 필터 통과 수. 약 2,800 종목, 11 섹터 | references/uptrend_methodology.md:L9-L23 |
| 2 | 파생 지표 | ratio=count/total; ma_10=ratio 10일 SMA; slope=ma_10.diff(); trend=slope>0 up else down; 피크/트로프 scipy find_peaks(distance=20, prominence=.015) | references/uptrend_methodology.md:L55-L74 |
| 3 | 대시보드 임계값 | 과열(Overbought) 0.37, 침체(Oversold) 0.097 | scripts/data_fetcher.py:L41-L43 |
| 4 | 가중치 | market_breadth .30, sector_participation .25, sector_rotation .15, momentum .20, historical_context .10 | scripts/scorer.py:L35-L41 |
| 5 | C1 비율->점수 선형보간 | r>=.50: 90+(r-.5)/.1*10 (최대 100); .37-.50: 70+(r-.37)/.13*19; .25-.37: 40+(r-.25)/.12*29; .097-.25: 10+(r-.097)/.153*29; <.097: r/.097*9. 보정: trend=up & slope>0 +5; down & slope<0 -5 | scripts/calculators/market_breadth_calculator.py:L89-L117, L61-L67 |
| 6 | C2 섹터 참여 | 0.6*개수점수 + 0.4*스프레드점수. 개수(상승 섹터 수): >=10 100; >=8 80; >=6 60; >=4 40; >=2 20; else 0. 스프레드(max-min ratio): <.15 100; .15-.25 100->80; .25-.35 80->60; .35-.45 60->30; >.45 30->0 선형 | scripts/calculators/sector_participation_calculator.py:L88-L90,L140-L184 |
| 7 | C3 섹터 로테이션 | 순환(기술·경기소비·통신·금융·산업) 평균 - 방어(유틸·필수·헬스·리츠) 평균 차이 d: >+.15 90-100; +.05~.15 70-89; -.05~.05 45-69; -.15~-.05 20-44; <-.15 0-19. 원자재(에너지·소재) 평균이 둘 다 초과 -> late_cycle: 초과폭>0.10 -10 else -5. 그룹 내 분산(std>0.08 또는 max-min>0.20 또는 추세 이탈) -> -5 | scripts/calculators/sector_rotation_calculator.py:L24-L45,L104-L118,L171-L189,L209-L230 |
| 8 | C4 모멘텀 | 0.5 slope점수(EMA3 평활 slope: >=.02 95+; >=.01 75-94; >=0 55-74; >=-.01 35-54; >=-.02 10-34; 아래 0-9) + 0.3 가속도(10일 vs 10일, 폴백 5v5) + 0.2 상승 slope 섹터 비율(선형 0-100) | scripts/calculators/momentum_calculator.py:L4-L13,L177-L188,L205 |
| 9 | C5 역사 맥락 | 점수 = 현재 ratio의 전체 이력 백분위 | scripts/calculators/historical_context_calculator.py:L5-L10 |
| 10 | 종합 | composite_raw = sum(score*weight) (결측 구성요소는 점수 50 기본값으로 포함, 가중치 재분배 없음 -> breadth-analyzer와 다름). 경고 감점: late_cycle -5, high_spread(섹터 스프레드>0.40) -3, divergence -3, 2개 이상이면 +1 완화. composite=clamp(raw+penalty,0,100) | scripts/scorer.py:L49-L55, L89-L100, L190-L206; scripts/uptrend_analyzer.py:L185-L189 |

**점수·등급**: scorer.py 헤더(L17-L21)와 _interpret_zone: 80-100 Strong Bull(노출 100%); 60-79 Bull(80-100%); 40-59 Neutral(60-80%, 포지션 20-30% 축소); 20-39 Cautious(30-60%, 현금 40-70%); 0-19 Bear(0-30%). 세부 7단계: >=80, 70, 60, 40, 30, 20 경계(scorer.py:L210-L227). 경계 10점 이내면 at_boundary 표시(L230-L255). 경고가 활성이면 Strong Bull은 "90-100% with caution", Bull은 "80-90% 하단"으로 상한 하향(L328-L336).

**출력 형식**: JSON(composite_score, zone, zone_detail, exposure_guidance, warnings, component breakdown, data_quality) + 마크다운. exposure-coach는 composite.composite_score 또는 uptrend_pct 비율에서 점수화(exposure-coach calculate_exposure.py:L135-L167).

**SKILL.md와 코드 차이**: [차이] 문서 정의의 "52W High/Low > 30% above Low"는 원 대시보드(Finviz)의 정의이며 이 저장소 코드는 계산하지 않고 CSV만 소비(data_fetcher.py). 가중치 재분배: 여기선 없음(결측=50 중립)이고 breadth-analyzer에는 있음.

**한국 시장 적용**: 정의를 KRX에 이식: 종가>SMA20, 종가>SMA200, SMA50>SMA200, 52주 저가 대비 +30% 초과, 20거래일(4주) 수익률>0. 기본 필터는 주가>$10 -> 종목별 최소 주가(예: 1,000원 이상 [추정]), 평균 거래대금 하한, 시총 하한 [추정]. 섹터는 KRX 업종지수 또는 WICS 10대 섹터 [추정]로 순환/방어/원자재(에너지·소재) 그룹 재분류. 임계값 0.37/0.097/0.25/0.50은 미국 기반이므로 KOSPI/KOSDAQ 별도 분포로 재보정(KOSDAQ은 변동성이 커 비율 분포가 다를 가능성 [추정]).

### macro-regime-detector — Macro Regime Detector
| 항목 | 내용 |
|---|---|
| 기법·출처 | 월봉 교차자산 비율(RSP/SPY, IWM/SPY, HYG/LQD, SPY/TLT, XLY/XLP, 10Y-2Y 금리차)의 6M/12M SMA 교차+ROC로 "전환 신호 강도"를 점수화하고 5개 레짐(Concentration/Broadening/Contraction/Inflationary/Transitional)을 규칙 점수제로 분류. 저자 자체 휴리스틱 [추정] |
| 분류 | (c) 거시. 가격 기반 비율 위주라 한국은 ETF로 대체하면 (a)에 가깝게 구현 가능 |
| 필요 데이터 | [차이] yfinance가 아니라 Financial Modeling Prep(FMP) API(유료/무료 키 FMP_API_KEY). ETF 9종 REQUIRED_ETFS = RSP, SPY, IWM, TLT, SHY, HYG, LQD, XLY, XLP (scripts/macro_regime_detector.py:L70) + FMP treasury rates(10Y-2Y). 600일 일봉(HISTORY_DAYS) -> 월봉 다운샘플. 엔드포인트 stable/historical-price-eod/full, 폴백 api/v3/historical-price-full (scripts/fmp_client.py:L96-L97) |
| 주요 파일 | skills/macro-regime-detector/scripts/scorer.py, scripts/calculators/{utils,concentration,yield_curve,credit_conditions,size_factor,equity_bond,sector_rotation}_calculator.py |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: 레짐 점수제(분류표)와 전환 신호 점수식(utils.score_transition_signal)은 가격 비율만 있으면 재사용. 입력 비율을 한국 대체지표로 교체. 위원회 점수기 + 레짐 필터 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 구성요소 가중치(전환 신호 점수 가중평균) | concentration(RSP/SPY) .25, yield_curve(10Y-2Y) .20, credit(HYG/LQD) .15, size(IWM/SPY) .15, equity_bond(SPY/TLT+상관) .15, sector_rotation(XLY/XLP) .10. 결측은 가중치 재분배 없이 점수 0으로 합산(품질 라벨만 표시) | scripts/scorer.py:L29-L47, L56-L66 |
| 2 | 전환 신호 점수(0-100) 3층 | L1 교차(0-40): 골든/데스크로스 bars_ago<=2 +40, <=5 +30, 그 외 +20; converging은 int(max(0,1-|gap%|)*25). L2 모멘텀(0-30): 장기ROC와 단기ROC 반대부호면 min(|roc_short|,5)/5*30; 같은 방향이고 |roc_short|>3 이면 +10. L3 확인(0-30): (교차 존재, 단기ROC가 교차방향 확인, SMA 간격>0.5%) 각 +10 | scripts/calculators/utils.py:L289-L358 |
| 3 | 교차 정의 | 월봉 비율의 6개월 SMA vs 12개월 SMA; |gap|<1.0%면 converging; bars_ago는 개월 | scripts/calculators/utils.py:L85-L155; concentration_calculator.py:L63-L69 |
| 4 | 방향 판정 | 교차 방향 우선; 교차가 3개월 이상 오래됐고 3M ROC가 반대면 모멘텀 방향("reversing") | scripts/calculators/utils.py:L223-L286 |
| 5 | 구성요소별 방향 라벨 | concentration: broadening/concentrating; size: small_cap_leading/large_cap_leading; credit: easing/tightening; sector(XLY/XLP): risk_on/risk_off; equity_bond: risk_on/off + 상관 레짐; yield_curve: 3M ROC>0 steepening, <0 flattening | scripts/calculators/yield_curve_calculator.py:L134-L143; credit_conditions_calculator.py:L75-L76; size_factor_calculator.py:L75-L76; sector_rotation_calculator.py:L74-L75 |
| 6 | 금리차 상태 | spread<-0.5 deeply_inverted; <0 inverted; <0.5 flat(3M ROC>0이면 normalizing); <1.5 normal; 이상 steep. 금리 데이터 없으면 SHY/TLT 비율 프록시(상승=flattening) | scripts/calculators/yield_curve_calculator.py:L244-L257, L189-L219 |
| 7 | 주식-채권 상관 레짐 | SPY·TLT 월수익률 6M 롤링 상관: <-0.3 negative_strong; <0 negative_mild; <0.3 near_zero; 이상 positive(인플레). 6M·12M 상관 부호 반전 또는 차이>0.3이면 레짐 전환 가산 | scripts/calculators/equity_bond_calculator.py:L85-L100, L147-L159 |
| 8 | 레짐별 규칙 점수 | Concentration: conc=concentrating +2, size=large_cap_leading +2, credit stable/easing +1. Broadening: conc=broadening +2, small_cap +2, credit stable/easing +1, sector risk_on +1, curve steepening +1. Contraction: credit tightening +2, sector risk_off +2, eq-bond risk_off +1, curve flattening +1, small_cap_leading -1(하한 0). Inflationary: 상관 positive +3, near_zero +1, eq-bond risk_off +1. unknown(결측)은 중립 | scripts/scorer.py:L322-L392 |
| 9 | 레짐 선택 | 비 transitional 4개 중 최고점. 상위 2개 점수차<=1(동점)이고 quick_composite<50 -> Transitional. signaling(구성요소 점수>=40) >=3 이고 best_score<3 -> Transitional | scripts/scorer.py:L202-L221 |
| 10 | 신뢰도 | best_score>=4 high; 3 moderate; 2 low; else very_low. 동점이면 high->moderate. 가용 구성요소<=3 -> very_low; 4개 -> low 상한 | scripts/scorer.py:L222-L242 |
| 11 | 전환 확률 | signaling>=4 & 평균점수>=50 high(70-90%); >=3 & >=40 moderate(40-60%); >=2 & >=30 low(20-40%); else minimal(<20%) | scripts/scorer.py:L407-L419 |

**점수·등급**: 종합 전환 점수(높을수록 전환 진행) 구간 <=20 Stable, <=40 Early Signal, <=60 Transition Zone, <=80 Active Transition, >80 Confirmed Transition (scripts/scorer.py:L545-L607 _interpret_zone). 이 점수는 "레짐 건강도"가 아님에 주의.

**출력 형식**: JSON(regime{current_regime, regime_label, confidence}, composite{composite_score, zone, data_quality{available_count,total_components}}, component_results, transition probability, evidence) + 마크다운. exposure-coach는 regime.current_regime 문자열을 REGIME_SCORES(broadening 80/concentration 60/transitional 50/inflationary 40/contraction 20)로 환산하고 confidence=very_low나 data_quality 결함은 fail-closed 처리(exposure-coach calculate_exposure.py:L45-L92).

**SKILL.md와 코드 차이**: [차이] 요청서의 "yfinance"와 달리 FMP API 사용. 구성요소 결측은 composite에서 점수 0으로 합산되어(재분배 없음) 전환 점수가 낮게 나오고 data_quality에만 반영됨(scorer.py:L56-L66). exposure-coach는 이 점수 대신 레짐 이름 매핑만 사용.

**한국 시장 적용** [추정, 모두 대체 제안]: RSP/SPY -> KOSPI200 동일가중 vs 시총가중 비율(또는 코스피 중소형/대형 ETF 비율); IWM/SPY -> KOSDAQ150 / KOSPI200(또는 코스닥/코스피 지수 비율); HYG/LQD -> 회사채 AA- 3년물 vs 국고채 3년물 스프레드(한국은행 ECOS 또는 KOFIA BIS) 변화; 10Y-2Y -> 국고채 10년-3년(또는 2년) 금리차(ECOS); SPY/TLT -> KOSPI vs 국고채 10년 선물 ETF 또는 KOSPI-채권 수익률 상관; XLY/XLP -> KRX 경기소비재/필수소비재 업종지수 비율; 추가로 원/달러 환율 3M ROC, 외국인 순매수 누적을 위험선호 보조 입력으로 [추정]. 월봉 6M/12M 교차는 일봉 시스템에는 느려 일봉 대응(120/250일 SMA)으로 환산 가능 [추정].

### us-market-bubble-detector — US Market Bubble Detector (v2.1)
- 기법: 정량 6지표(각 0-2, 합 0-12) + 정성 3보정(각 0-1, 합 0-3), 총 0-15. 입력은 사용자·웹에서 수집한 측정값(코드는 점수 검증·합산·분류만 수행). 분류: (c) 시장 폭·거시·심리, 일부(가격 가속, 신고가 시 50일선 위 비율)만 일봉으로 구현 가능. 라이선스 MIT. 근거 skills/us-market-bubble-detector/scripts/bubble_scorer.py:L5-L7, L28-L70, L163-L188, L238-L247.
- 점수표: 풋콜비율 <0.70 -> 2, 0.70-0.85 -> 1, >0.85 -> 0 / 변동성 억제: VIX<12 & 지수가 고점 5% 이내 2, VIX 12-15 & 고점 근처 1 / 레버리지: 신용잔고 YoY +20% & 사상 최고 2, +10-20% 1 / IPO 과열: 건수>5년 평균 2배 & 첫날 수익 +20% 2, 건수>1.5배 1 / 폭 이상: 신고가인데 50일선 위 비율 <45% 2, 45-60% 1 / 가격 가속: 3개월 수익률이 10년 분포 95백분위 초과 2, 85-95 1. 정성: 사회적 침투, 검색·미디어 5배 이상, 밸류에이션 괴리 각 +1(엄격 조건).
- 구간: 총점 <=4 Normal(위험예산 100%), 5-7 Caution(70-80%), 8-9 Elevated Risk(50-70%), 10-12 Euphoria(40-50%), 13-15 Critical(20-30%, 신규 진입 중단) (bubble_scorer.py:L163-L188). 입력 누락 시 점수 입력 거부(ValueError, 검증 L146-L161).
- 이식 판단: 부분. 한국판은 [추정] 신용융자잔고(금융투자협회) 증가율, 신고가 종목 중 50일선 위 비율, 지수 3개월 수익률 백분위, VKOSPI<12 등 4개 지표를 일봉/공개 통계로 계산. 위치: 리스크 게이트(노출 상한 20-100%). IPO·소셜 지표는 보류.

### breadth-chart-analyst — Breadth Chart Analyst
- 기법: 위 두 폭 지표(S&P500 200일선 기반 폭 지수, 상승 추세 종목 비율)를 차트 이미지 또는 동일 공개 CSV(https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv, uptrend-dashboard CSV; scripts/fetch_breadth_csv.py:L25-L31)로 읽어 해석하는 LLM 절차. 점수식 코드 없음, 해석 규칙은 SKILL.md에만 있음. 분류 (d)에 가까운 정성 해석 + (c). 라이선스 MIT.
- 판정 기준(SKILL.md): 200MA 폭 지수 평균 피크 73% 과열선; 200MA가 피크 형성 시 SELL(L70), 8MA 트로프 후 연속 2-3회 상승이면 진입 확인, 8MA가 다시 꺾이면 FAILED(L250-L260). 상승 추세 비율 차트: 약 40%(문서 35-40%) 이상 과열·천장권, 10-15% 미만 극단 침체, 색 전환(적->녹)이 <10-15%에서 나오면 ENTER LONG, 녹->적이 >35-40%에서 나오면 EXIT LONG(L82-L86, L314-L333). 임계값은 uptrend-analyzer의 0.37/0.097과 유사하나 같지 않음 [차이].
- 이식 판단: 보류(중복). 시그널 규칙(트로프 후 상승 확인, 극단 침체 반등 진입)은 market-breadth-analyzer C3 점수에 이미 수치화됨.

### market-environment-analysis — Market Environment Analysis
- 기법: 웹 검색으로 주요 지수·환율·금리·VIX·원자재를 모아 리스크온/오프 서술 보고서 작성. 정량 규칙은 VIX 구간뿐: <12 Low&Stable, <20 Normal, <30 Elevated, <40 High, >=40 Extreme (skills/market-environment-analysis/scripts/market_utils.py:L117-L128). 분류 (d) 정성 요약 + (c). 라이선스 MIT. 이식 판단: 보류. VKOSPI 구간 매핑 정도만 참고 [추정].

### crypto-regime-analyzer — Crypto Regime Analyzer
- 6요소 가중(BTC 추세 .25, 알트 폭 .20, BTC 도미넌스 .15, 펀딩 .15, 드로다운·변동성 .15, 모멘텀 .10), 구간 >=80 RISK_ON, 40-79 NEUTRAL, <40 RISK_OFF(skills/crypto-regime-analyzer/scripts/scorer.py:L11-L33, L44-L52). 데이터: CoinGecko, Binance 선물 공개 API(data_client.py:L62-L63). 주목할 설계: 결측 시 가중치 재분배는 가용 요소 >=4개이고 가중 합 >=0.65일 때만, 미달이면 UNKNOWN으로 fail-closed(scorer.py:L46-L47, L68-L86). 한국 주식과 무관해 보류하나, 이 fail-closed 규칙은 위원회 결합 규칙에 채택 가치 높음(exposure-coach의 관대한 재정규화와 대비).

#### 그룹 소결
1. exposure-coach 결합 구조 채택: composite = 가용 입력 가중평균(regime .25, top_risk .20, breadth .15, uptrend .15, institutional .10, sector/theme/ftd 각 .05) - 10*결측 치명입력 수; 노출 상한은 구간 선형(>=80 -> 90+; 65-80 -> 70+1.3*(c-65); 50-65 -> 50+1.3*(c-50); 35-50 -> 30+...; 20-35 -> 10+...; <20 -> c/2) (calculate_exposure.py:L21-L30, L402-L415). 권고: c<30 또는 top_risk<25 CASH_PRIORITY, c<50 또는 top_risk<40 또는 치명 결측>=2 REDUCE_ONLY (L418-L436). 신뢰도는 입력 개수(>=6 & 치명 결측 0 HIGH).
2. fail-closed 보강: exposure-coach는 regime만 무효 처리하고 나머지는 재정규화로 관대 -> 크립토 스코어러의 "가용 >=4개 & 가중>=65% 아니면 UNKNOWN"(scorer.py:L46-L47)을 합쳐 쓰는 것을 권장.
3. KRX breadth 직접 계산: 코스피/코스닥 각각 200일선 위 비율 -> 8일 EMA·200일 EMA, 6점수식(.25/.20/.20/.15/.10/.10), 구간 80/60/40/20 -> 노출 90-100/75-90/60-75/40-60/25-40%(market-breadth-analyzer scorer.py:L31-L38, L167-L248). 핵심 임계: 8MA .70/.60/.50/.40/.30/.20 -> 95/80/65/50/35/20/5, 극단 트로프 8MA<0.4 +10.
4. 상승 추세 비율 정의 이식: 종가>SMA20, >SMA200, SMA50>SMA200, 52주 저가 대비 +30%, 4주 수익률>0; 비율 점수 .097/.25/.37/.50 밴드 선형(uptrend-analyzer market_breadth_calculator.py:L89-L117), 경고 감점 late_cycle -5/high_spread -3/divergence -3.
5. 가격-폭 다이버전스: 60일(0.6)+20일(0.4), 가격 +3%인데 폭 -0.05 이하면 10점(divergence_calculator.py:L45-L52, L135-L158) -> 위원회 점수기.
6. 거시 레짐은 점수제 분류표(Concentration/Broadening/Contraction/Inflationary/Transitional, 최고점 선택, 동점&composite<50이면 Transitional, 신뢰도 best>=4/3/2) 구조를 한국 입력(원/달러, 국고채 10Y-3Y, 코스닥/코스피 비율, 업종 경기소비/필수소비)으로 교체해 레짐 필터에 사용(scorer.py:L202-L242, L322-L392).


---

## 14. Stockbee(Pradeep Bonde) 계열 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (fdfff01, MIT) · 범위: stockbee 5개 스킬

### stockbee-momentum-burst-screener — Stockbee 모멘텀 버스트 스크리너
경로 약칭: `MB` = `skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py`

| 항목 | 내용 |
|---|---|
| 기법·출처 | Stockbee(Pradeep Bonde) "Momentum Burst": 4% 돌파 + 거래량 증가, 3~5일 단기 스윙. 저장소가 규칙을 자체 구현(원저작 인용·코드 이식 아님) (`skills/stockbee-momentum-burst-screener/SKILL.md:L3-L8`) |
| 분류 | (a) 일봉만으로 구현 가능 — 주. 시장 게이트는 CLI 입력값(외부 레짐 스킬 결과) 즉 (c) 보조 |
| 필요 데이터 | 일봉 OHLCV(기본 80봉, `MB:L927`), FMP 유니버스(시총 5억달러 하한, `MB:L934`) 또는 `--prices-json` 오프라인. 재무·뉴스 불필요 |
| 주요 파일 | `MB`(1240줄), `references/scoring_system.md`, `references/entry_exit_rules.md`, `scripts/_market_calendar.py` |
| 라이선스 | 저장소 루트 MIT |
| 이식 판단 | 부분 채택: 트리거·점수식은 위원회 점수기/진입 트리거, 손절·청산 템플릿은 청산, 신선도 게이트는 데이터 품질 |

**TI65**: `grep -ri TI65` 결과 스킬 전체에 없음. TI65(65일 추세강도)류 지표는 이 스킬에 구현돼 있지 않다 [확인함: 부재]. 추세 필터는 사실상 "직전 베이스 폭/평균 레인지"뿐.

**데이터 배열 규약**: bars[0]=트리거일(최신), bars[1]=전일, 내림차순 (`MB:L579-L581`).

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 4% 돌파 | day_gain_pct=(close/prev_close-1)*100 >= 4.0 AND volume > prev volume AND volume >= min_volume(100,000) | `MB:L582,L594-L598`, 기본값 `MB:L938,L932` |
| 2 | 달러 돌파 | close-open >= 0.90 AND volume>=100,000 (거래량 증가 불요) | `MB:L599-L600`, `MB:L939` |
| 3 | 레인지 확장 | (high-low) > 직전 3일 max(high-low) AND 전일 등락률(prev_day_gain) <= 2.0% AND volume>전일 AND 최소거래량 | `MB:L586-L588,L601-L607`, `MB:L941` |
| 4 | 9M 거래량 태그 | volume >= 9,000,000 (점수 가산용 태그, 단독 트리거 불가) | `MB:L608-L609,L800`, `MB:L940` |
| 5 | 주 트리거 우선순위 | 4pct_breakout > range_expansion > dollar_breakout > 9m_volume | `MB:L611-L612` |
| 6 | 거래량 비율 | ratio_1d=vol/전일vol, ratio_20d=vol/avg(bars[1:21] 거래량) | `MB:L589-L591` |
| 7 | 종가 위치 | close_loc=(close-low)/(high-low)*100, 레인지 0이면 50 | `MB:L494-L498` |
| 8 | 직전 베이스(수축) | window=3..20일(bars[1:1+w]); base_width=(max high-min low)/prior[0].close*100 <= 15 AND 평균 일레인지%(=(H-L)/C 평균) <= 5.0 이면 후보; 가장 긴 window 우선, 동률이면 폭 작은 쪽. 없으면 prior_base_days=0 | `MB:L523-L560`, 기본값 `MB:L944-L947` |
| 9 | 거래량 건조 | 베이스 평균거래량 <= 그 직전 동일길이 구간 평균 *0.85 | `MB:L547-L550` |
| 10 | 직전 연속 상승 | 트리거 직전 최대 5일 연속 종가 상승 일수(up_streak) | `MB:L501-L509` |
| 11 | 최근 4% 하락 | 직전 5일(lookback=5) 중 일간 -4% 이하 종가하락 존재 | `MB:L512-L520`, `MB:L949-L950` |
| 12 | 진입 기준가/손절 | entry=트리거일 종가, stop=트리거일 저가, risk%=(entry-stop)/entry*100 | `MB:L818-L820`, `references/entry_exit_rules.md:L3-L16` |
| 13 | 하드 리젝트 | close<5.0(min_price); volume<100,000; 트리거 없음(9m 제외); entry<=stop; risk%>10.0; 가격일 무효/미확보/오래됨; 봉 < max(25, min_base_days+3)=25 | `MB:L780,L794-L802,L821-L824`, `MB:L930-L931,L951` |
| 14 | 사이징 인계 | position_size = 계좌위험$ / (entry-stop); 스크리너는 수량 결정 안 함 | `references/entry_exit_rules.md:L24-L28` |
| 15 | 청산 템플릿 | 트리거일 저가 이탈 시 손절; 3~5세션 후 점검; 하루 10%+ 급등 시 이익보호; 수 세션 후속 부재=실패. 코드에는 문자열 `"3_to_5_day_or_abnormal_profit_protection"`만 있고 실제 청산 로직은 없음 | `references/entry_exit_rules.md:L30-L37`, `MB:L880` |
| 16 | 신선도 게이트 | 기본 마지막 완료 NYSE 세션; bar_age_sessions > max-bar-age(기본 0)이면 stale_price_data로 REJECT; 허용 시 ACTIONABLE_DAY1 -> MANUAL_REVIEW 강등 | `MB:L314-L347,L842-L845`, `SKILL.md:L58-L92` |

**점수·등급** (합계 100: 트리거20+거래량15+셋업25+종가10+리스크15+실패필터10+시장게이트5)
| 구성요소 | 점수식 | 근거 |
|---|---|---|
| trigger(max20) | 4pct +14 (day_gain>=7이면 추가 +3); range_expansion +10; dollar_breakout +8; 9m_volume +2; 합 min(20) | `MB:L628-L640` |
| volume(15) | best=max(ratio_1d, ratio_20d): >=3.0→15, >=2.0→12, >=1.5→9, >=1.0→6, else 0 | `MB:L643-L653` |
| setup(25) | 베이스일수 >=10:+10, >=5:+8, >=3:+6, >0:+3; 폭 <=8:+7, <=12:+5, <=15:+3; 전일 레인지% <=3.0:+5 (아니고 전일 음봉이면 +4); 거래량건조 +3; min(25) | `MB:L656-L685`, `MB:L948` |
| close_quality(10) | loc>=90:10, >=80:9, >=70:7, >=60:5, >=50:3, else 0 | `MB:L688-L699` |
| risk_distance(15) | risk% <=0:0; <=2.5:15; <=4:12; <=6:8; <=8:5; <=10:2; else 0 | `MB:L702-L715` |
| failure_filters(10) | 시작 10; 직전 3일+ 연속상승 -4; 최근 -4% 하락 -4; 베이스폭>15 -3; close_loc<50 -2; 하한 0 | `MB:L718-L739` |
| market_gate(5) | allowed 5, neutral 3, restrictive 0 (기본 neutral) | `MB:L742-L747`, `MB:L953-L957` |
- 등급: >=90 A, >=80 A-, >=70 B, >=55 Watch, else Reject (`MB:L750-L759`). 하드리젝트면 점수 0 취급.
- 상태: 리젝트→REJECTED; gate=restrictive & score>=70→MANUAL_REVIEW_ONLY; >=80 ACTIONABLE_DAY1; >=70 MANUAL_REVIEW; >=55 WATCH_ONLY; else REJECTED (`MB:L762-L773`).
- 하류: A/A- → technical-analyst→position-sizer; B → 관찰/소위험 (`SKILL.md:L131-L138`).

**출력 형식**: JSON(`stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json`: symbol, state, rating, setup_score, trigger_tags, day_gain_pct, volume_ratio_1d/20d, close_location_pct, prior_base_days, base_width_pct, entry/stop_reference, risk_pct_to_stop, components, soft_failure_tags, reject_reasons, downstream_action 등) + Markdown (`MB:L847-L885`, `SKILL.md:L140-L143`).

**SKILL.md와 코드 차이**
- [차이] SKILL.md Step 2는 4% 돌파를 "거래량이 전일 초과 + 유동성 하한"으로 적었고 코드와 일치. 다만 Range Expansion의 "전일 이미 확장되지 않음"은 코드에서 전일 상승률 <= 2.0%로 구현(`MB:L603`).
- [차이] "market gate alignment"는 코드가 시장을 직접 계산하지 않고 CLI 문자열(allowed/neutral/restrictive)만 받음(`MB:L953-L957`).
- [차이] 문서의 "exit"는 템플릿 문자열뿐, 보유일수 로직·트레일링 없음(`MB:L880`).
- 현금성 지표(거래대금)는 없음: 유동성은 주식수(volume>=100k) 기준이며 거래대금 필터 아님. 시총 5억 달러는 유니버스 조회 단계에서만 적용.

**한국 시장 적용** [추정 포함]
- 4% 임계: 상한 ±30%에서 4%는 흔함(코스닥 소형주 일 4% 이상 상승일이 많음) → 4%를 유지하되 거래대금 필터를 강화하고, 점수는 ATR%/20일 변동성으로 정규화 제안 [추정].
- 달러 돌파 $0.90은 가격 규모 고정치 → 원화에서 의미 없음. 호가단위 기준(예: 종가의 3~4% 이상) 또는 ATR 배수로 대체 [추정].
- 거래량 하한 100k주/9M주 → 거래대금(원) 기준으로 재정의(예: 20일 평균 거래대금 하한 + 당일 거래대금 배수) [추정].
- min_price 5달러 → 호가 5원/10원 구간 초저가 제외(예: 1,000~2,000원 미만) [추정].
- 상한가 잠김(+30%): 종가=상한가, 고가=종가이면 close_loc 100이 되고 risk_distance 점수가 높게 나옴 → 매수 불가이므로 "상한가 마감 제외(진입불가 플래그)" 필수 [추정]. 다음 날 갭 진입 시 entry 기준가를 종가가 아니라 시가로 재계산.
- 단일가(VI), 시장경보·관리종목·거래정지 종목 하드 리젝트 추가.
- 진입 기준가를 종가로 두는 설계는 한국 종가 동시호가(15:20~15:30) 특성상 "종가 베팅"과 충돌 가능 — 익일 시가 진입 가정으로 백테스트 [추정].

### stockbee-episodic-pivot-analyzer — Stockbee 에피소딕 피벗(EP) 분석기
경로 약칭: `EP` = `skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py`

| 항목 | 내용 |
|---|---|
| 기법·출처 | Stockbee EP: 실적·가이던스·M&A·FDA 등 촉매로 갭/거래량이 터진 Day 1. 촉매 품질 + 가격/거래량 확인을 합산(`skills/stockbee-episodic-pivot-analyzer/SKILL.md:L3-L8`) |
| 분류 | (c) 뉴스·촉매 필요 + (a) 일봉 확인. 촉매는 외부 입력(스킬이 뉴스 수집 안 함, `SKILL.md:L22-L24`) → 한국은 OpenDART로 대체 가능 [추정] |
| 필요 데이터 | 이벤트 JSON(symbol, event_date, catalyst_type/headline/summary), 일봉 OHLCV(50일 이상 권장; 없으면 FMP), 선택: earnings-trade-analyzer JSON(grade), momentum-burst JSON, market_cap |
| 주요 파일 | `EP`(1251줄), `references/{ep_methodology,catalyst_quality,handoff_rules}.md`(미정독) |
| 라이선스 | 루트 MIT |
| 이식 판단 | 부분 채택: 촉매 점수표·상태 판정은 위원회의 "이벤트 관점" 점수기 + 진입 트리거. 촉매 입력을 DART 공시 분류로 교체 |

**catalyst_events_json 형식**: 코드상 CLI 인자명은 `--events-json`(`EP:L1136-L1139`). 최상위는 리스트 또는 dict(`events|candidates|results|signals` 키, `as_of|date` 대체 날짜) (`EP:L339-L360`). 레코드 필드: symbol, event_date, catalyst_type(별칭 허용)/event_type/type/category, headline, summary/description/notes, source_grade/grade(A~D), market_cap/mktCap (`EP:L274-L300,L623-L645`, 예시 `SKILL.md:L36-L48`).

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 이벤트일 봉 선택 | event_date와 동일 날짜 봉; 없으면 그 이후 첫 봉(시간외 공시는 다음 거래일 봉); 날짜 없으면 마지막 봉 | `EP:L478-L493` |
| 2 | 갭% | (event_open/prev_close-1)*100 | `EP:L495-L520` (gap_pct 계산부 L520-L525 부근) |
| 3 | 일간 상승% | (close/prev_close-1)*100; range%=(H-L)/prev_close*100; close_loc=(C-L)/(H-L)*100; risk_pct_to_low=(close-low)/close*100 | `EP:L495-L545` |
| 4 | 거래량 배수 | volume/직전 20일 평균(vr20), volume/직전 최대50일 평균(vr50) — 이벤트일 제외 | `EP:L506-L508,L535-L536` |
| 5 | 거래대금 | close*volume (달러) | `EP:L541-L542` |
| 6 | 사전 수익률 | prior_5d, prior_20d = 전일종가/N봉전 종가-1 | `EP:L544-L551` |
| 7 | 촉매 분류 | 명시 타입 우선(별칭표), 없으면 headline/summary 정규식 키워드 순서대로 최초 매칭(guidance_raise → earnings → m_and_a → fda → ... → story_theme) | `EP:L50-L102,L281-L300` |
| 8 | 하드 필터 없음 | 갭 최소치·거래량 최소치는 하드 컷이 아니라 상태 판정(move_confirmed 등)에서만 사용 | `EP:L843-L884` |

**점수·등급** (합 100 = 촉매35 + 가격20 + 거래량20 + 재평가10 + 유동성10 + 리스크5; `EP:L623-L830,L944-L955`)
| 구성요소 | 식 | 근거 |
|---|---|---|
| catalyst_quality(0~35) | 기본점수표(guidance_raise 95, fda_approval 94, earnings 88, m_and_a 84, regulatory 82, major_contract 76, partnership 72, product_launch 66, short_squeeze 58, analyst_upgrade 54, story_theme 50, unknown 35) + 등급보너스(A+8,B+4,C0,D-4) + "first|record|accelerat|inflect|turnaround|transform|breakthrough" +6 − "secondary offering|dilution|investigation|downgrade|lawsuit|resignation" -12; clip 0~100 후 *0.35 | `EP:L105-L118,L135,L623-L646` |
| price_action(0~20) | move=day_gain(없으면 gap): >=12:+12, >=8:+10, >=4:+8, >=2:+4; gap>=4:+4(>=2:+2); close_loc>=80:+4, >=60:+2, <40:-4; range%>=6:+2; clip 0~20 | `EP:L649-L697` |
| volume_shock(0~20) | ratio=vr50→vr20→vol_ratio_1d 순 첫 값: >=10:20, >=5:17, >=3:14, >=1.5:8, else 2; 비율 없으면 절대거래량 >=9M:14, >=1M:8, >=300k:4; 거래량 >=9M & 점수<20이면 +3 | `EP:L700-L744` |
| neglect_revaluation(0~10) | 기본 5; prior_20d: <=5%:8, <=15:6, <=30:3, else 1; 시총<100억$ +2, >1000억$ -1 | `EP:L747-L774` |
| liquidity(0~10) | 거래대금 >=50M$:10, >=10M$:8, >=2M$:4, else 1 (없으면 거래량 >=1M:7, >=300k:5); 가격<5$면 상한 3 | `EP:L777-L815` |
| risk_distance(0~5) | risk_pct_to_low <=4:5, <=7:3.5, <=10:1.5, else 0; 없으면 2 | `EP:L818-L828` |
- 페이드 감점: close_loc<30 & 합계>=55면 -8 후 재판정 (`EP:L944-L953`). 등급: >=90 A, >=80 A-, >=70 B, >=55 C, else D (`EP:L831-L840`).
- 상태 판정(`EP:L843-L884`): move_confirmed = day_gain>=4 OR gap>=4; volume_confirmed = ratio 없음 OR ratio>=1.5 OR 거래량>=300,000; weak_close = close_loc<40; risk_too_wide = risk>max_risk_pct(기본 10, `EP:L1149-L1155`).
  - ACTIONABLE_DAY1: 점수>=85 & move & volume & !weak_close & !risk_too_wide
  - DAY1_WATCH: 점수>=75 & 같은 조건
  - DELAYED_EP_WATCH: 점수>=70 & (risk_too_wide OR weak_close)
  - CATALYST_WATCH: 촉매 known & move 미확인 & 점수>=55
  - 그 외 REJECT
- 핸드오프: pead_handoff = (earnings|guidance_raise) & 상태 in (ACTIONABLE_DAY1, DAY1_WATCH, DELAYED_EP_WATCH); momentum_handoff = day_gain>=4 & 상태≠REJECT (`EP:L955-L960`).
- 손절/진입: entry=종가, stop=EP일 저가 (`trade_plan_inputs.stop_basis="ep_day_low"`) (`EP:L1000-L1003 부근`).

**출력 형식**: JSON(`stockbee_episodic_pivot_*.json`: catalyst_type, ep_type, state, state_reasons, rating, composite_score, component_scores/reasons, gap_pct, day_gain_pct, volume_ratio_50, dollar_volume, risk_pct_to_low, pead_handoff, trade_plan_inputs 등) + Markdown (`EP:L961-L1003`, `SKILL.md:L108-L111`).

**SKILL.md와 코드 차이**
- [차이] SKILL.md가 말하는 "갭 크기/거래량 배수 기준"은 명시적 EP 정의(예: 갭>=8% 등)가 아니라 점수 구간·상태 조건(>=4%, 거래량 배수>=1.5)으로만 구현. Stockbee 원 EP의 "거래량 9M" 정도만 보너스로 남음 (`EP:L741-L743`).
- [차이] 점수에서 가격 20점이 갭에 의존하지 않고 day_gain 우선(`EP:L657`) — 갭다운 후 반등한 날도 인정.
- 촉매 키워드가 "ai|ev|space" 등 영어 단어 경계 정규식이라 한국어 공시에는 적용 불가.
- 지급된 코드에 가격 입력이 없으면 기본값 보정(+2~+5)이 들어가 점수가 부풀려짐(missing_* 분기).

**한국 시장 적용** [추정]
- 촉매를 OpenDART로 대체: 잠정실적(영업(잠정)실적), 단일판매·공급계약체결, 자기주식취득, 주요사항보고(M&A·유증 부정), 임상·허가는 공시/보도자료. 기본점수표의 guidance_raise≈매출·영업이익 전망 상향(공시), earnings≈잠정실적 서프라이즈, major_contract≈단일판매·공급계약(계약금액/최근 매출 비율을 점수에 추가 권장). 부정 키워드는 유상증자·전환사채·감사의견·횡령·거래정지로 확대.
- 갭 4%는 한국 장 시초 갭 기준으로 낮음. ±30% 제한과 시초 동시호가 때문에 EP 갭은 시가 갭 8~10%+, 거래대금 배수(20일 평균 대비) 5배+로 재보정 제안 [추정].
- 거래대금 하한(50M$/10M$/2M$)은 원화(예: 100억/30억/10억 원)로 재설정 [추정]. 시총 구간도 원화(1조 미만 가산 등).
- 장 마감 후 공시(15:30 이후)는 다음 거래일 봉이 EP일 — 코드의 "다음 봉 사용"(`EP:L488-L493`) 로직과 동일하게 처리.
- 상한가 잠김(+30%)은 close_loc=100, 낮은 risk_pct로 최고점 → 진입 불가 플래그 필요. 테마 급등주(뉴스 없는 순환매)는 story_theme(50점)로 낮게 평가되므로 한국에서는 테마주 과열(단기과열·투자경고) 필터와 함께 재가중 [추정].

### stockbee-exhaustion-hammer-screener — Stockbee 매도 소진 망치형(Exhaustion Hammer) 스크리너
경로 약칭: `EH` = `skills/stockbee-exhaustion-hammer-screener/scripts/screen_exhaustion_hammer.py`

| 항목 | 내용 |
|---|---|
| 기법·출처 | 급등 후 눌림에서 긴 아랫꼬리 망치형 + 직전 저점 하회 후 회복(undercut & reclaim)으로 매도 소진 포착. 종가 근처 매수 후보(`skills/stockbee-exhaustion-hammer-screener/SKILL.md:L70-L76`, `references/near_close_operations.md:L9-L12`) |
| 분류 | (a) 일봉만으로 구현 가능 — 주. 시총·보유기관 수는 선택 메타(없으면 중립 점수) |
| 필요 데이터 | 일봉 OHLCV 120봉(`EH:L1040`), 최소 61봉 있으면 60일 수익률 계산(`EH:L553-L554`), 선택 profile JSON(marketCap, 기관보유%, 펀드보유수), `--use-quote-latest`로 장중 근사 종가(`EH:L1043-L1048`) |
| 주요 파일 | `EH`(1361줄), `references/{exhaustion_hammer_methodology,near_close_operations,scoring_system}.md` |
| 라이선스 | 루트 MIT |
| 이식 판단 | 채택(부분): 망치형 기하·눌림 정의는 진입 트리거(역추세 반등 셋업), 점수는 위원회 "단기 반전" 관점. 종가 직전 스캔은 한국 종가 동시호가와 연결 |

**규칙·계산식** (bars[0]=판정일; 함수 범위로 인용)
| # | 규칙 | 계산식·임계값(기본값) | 근거 |
|---|---|---|---|
| 1 | 캔들 기하 | range=H-L; body=|C-O|; lower_wick=min(O,C)-L; upper_wick=H-max(O,C); lower%=lower/range, body%=body/range, upper%=upper/range; wick/body=lower/body(몸통0이면 999); recovery_from_low%=(C/L-1)*100 | `EH:L521-L548` |
| 2 | 망치형 하드조건 | lower_wick% >= 40; body% <= 35; close_loc >= 60; lower/body >= 1.5; recovery >= 2.0% — 하나라도 미달이면 REJECT | `EH:L1079-L1084`(기본값), 하드리젝트 `EH:L897-L910`(analyze_symbol 내부) |
| 3 | 보조 태그 | green_or_flat_close(C>=O), controlled_upper_wick(upper% <= 35); 3개(긴 아랫꼬리·작은 몸통·강한 종가위치) 모두 충족이면 primary=confirmed_exhaustion_hammer | `EH:L521-L561` |
| 4 | 직전 고점 눌림 | 직전 40봉(1..40) 중 최고 high; pullback%=(C/최고high-1)*100; 깊이 6%~35% 하드조건; 고점 후 경과일 3~30일 하드조건 | `EH:L581-L592,L1066-L1070` |
| 5 | 언더컷/리클레임 | 직전 5일(1..5) 최저 low를 오늘 low가 하회(undercut) AND 오늘 close > 그 저점(reclaim). 기본은 가점만, `--require-undercut-reclaim` 지정 시 하드조건 | `EH:L594-L601,L1071-L1076` |
| 6 | 하락 맥락 | down_days_10=직전 10봉 중 C<O 개수; lower_closes_5; 연속 하락마감(최대 7); ma10(직전10), ma50(오늘 포함 50) 대비 위치; return_20d, return_60d(전일 종가 기준) | `EH:L603-L631,L506-L519` |
| 7 | 유동성·품질 | 가격 >= 20; 거래량 >= 100,000; 20일 평균 거래대금(직전20봉 close*vol 평균) >= 20,000,000; 시총 >= 2,000,000,000(시총 0이면 미적용) | `EH:L1053-L1057,L633-L667,L880-L895` |
| 8 | 손절·리스크 | entry=종가; stop = 당일 저가*(1-0.10/100); risk%=(entry-stop)/entry*100; risk > 12.0이면 하드리젝트 | `EH:L1087-L1088,L920-L930` |
| 9 | 소프트 감점 태그 | no_undercut_reclaim; |pullback|>25 deep_pullback; 고점 경과>30 stale_high; vol_ratio_20d<0.8; close_loc<70; day_gain<-3; risk>=8 (태그만, 점수 영향 없음) | `EH:L835-L857` |
| 10 | 청산 템플릿 | "low_of_day_stop_then_3_to_5_day_follow_through_review" 문자열뿐(로직 없음). B급은 익일 망치 고가 돌파 확인 권고 | `EH:L995`(exit_template), `SKILL.md:L100-L106`, `EH:L1007-L1019` |

**점수·등급** (합 100 = 품질20 + 선행모멘텀15 + 눌림소진20 + 망치25 + 리스크15 + 시장5)
| 구성요소 | 식 | 근거 |
|---|---|---|
| quality(20) | 가격 >=40(min*2):4, >=20:3; 20일평균거래대금 >=60M:6, >=20M:5, (미달이나 당일량>=100k):2; 시총 >=100억$:5, >=20억$:4, 시총0:2; 기관/펀드보유 >=1000개:3, 기관보유율>=40%:2; 20일 평균거래량>=100k:+2; min(20) | `EH:L669-L697` |
| prior_momentum(15) | 고점 경과 3~30일:+5(40일내:+2); 60일수익 >=30%:5, >=15%:4, 20일수익>=10%:3; 종가>=50일선:+3; 고점 존재:+2 | `EH:L700-L718` |
| pullback_exhaustion(20) | 눌림 6~25%:+6(<=35%:+4); undercut&reclaim:+6(저가만 하회 low_undercut<0:+3); 10일중 음봉>=5:+3(>=3:+2); 5일중 하락마감>=3 또는 연속하락>=2:+2; 거래량/20일평균 >=1.5:+3(>=1.0:+2) | `EH:L721-L748` |
| hammer_geometry(25) | 아랫꼬리% >=60:8(>=40:6); 몸통% <=20:5(<=35:4); 종가위치 >=75:5(>=60:4); wick/body >=3:3(>=1.5:2); 저점회복 >=4%:2(>=2%:1); 양봉:+1; 윗꼬리<=35%:+1 | `EH:L751-L782` |
| risk_distance(15) | <=3:15, <=5:12, <=7.5:9, <=10:6, <=12:3, else 0 | `EH:L785-L798` |
| market_gate(5) | allowed 5, neutral 3, else 0 | `EH:L801-L806` |
- 등급: >=90 A, >=82 A-, >=70 B, >=55 Watch (`EH:L809-L818`). 상태: 하드리젝트 REJECTED; restrictive & >=70 MANUAL_REVIEW_ONLY; >=82 ACTIONABLE_CLOSE_BUY; >=70 MANUAL_REVIEW; >=55 WATCH_TOMORROW (`EH:L821-L832`).
- 점수 구조상 하드조건을 모두 통과해야 하므로 기본 하드게이트만 통과해도 망치형 15+ (대개 40점+)를 받는다.

**출력 형식**: JSON/Markdown(`stockbee_exhaustion_hammer_*`), 필드: trigger_tags, pullback_pct_from_high, days_since_recent_high, undercut_reclaim, lower/body/upper wick %, recovery_from_low_pct, avg_dollar_volume_20d, entry/stop_reference, components, soft_failure_tags, reject_reasons (`EH:L934-L1005`, `SKILL.md:L86-L96`).

**SKILL.md와 코드 차이**
- [차이] SKILL.md는 "undercut/reclaim"을 별도 셋업군처럼 기술하나 코드에서는 기본 가점이며 하드조건은 옵션 플래그(`EH:L1072-L1076`).
- [차이] 문서에 "하락 연속" 요건이 없고(코드에서도 연속하락은 +2 가점뿐) 사용자가 말한 "하락 연속"은 하드조건이 아님 (`EH:L745`).
- [차이] 문서의 "controlled pullback rather than a long-term downtrend"는 50일선 위 여부 가점(+3)으로만 구현, 하드 필터 아님 (`EH:L713`).
- 장중 `--use-quote-latest` 미사용 시 어제까지 완료봉 기준(종가 직전 근사는 옵션).

**한국 시장 적용** [추정]
- 거래대금 20M$/시총 2B$/가격 20$ 하한 → 원화(예: 20일 평균 거래대금 30~50억 원, 시총 3,000억+, 가격 2,000원+ 등)로 재설정.
- 한국은 상·하한 ±30%, 호가단위가 큰 저가주에서 꼬리 비율이 호가 틱에 좌우됨 → 가격대별 최소 레인지(틱 5개 이상 등) 조건 추가.
- 종가 동시호가(15:20~15:30) 때문에 "종가 직전 스캔(close-2min)" 방식은 15:20 이전 값으로 재정의해야 함: 15:20 시점 미확정 종가 vs 동시호가 체결가 차이를 감안, 장 마감 후 일봉 확정 후 익일 시가/망치 고가 돌파 진입으로 보수적으로 이식 [추정].
- 하한가 근접·VI 발동·거래정지 후 재개 일은 꼬리가 인위적 → 제외. 코스닥 소형 테마주는 아랫꼬리 후 급락 재개가 잦음: 직전 60일 +30% 가점이 과열주를 선호하게 하므로 단기과열/투자경고 지정 제외.

### stockbee-20pct-study — Stockbee 20% 무버 이벤트 스터디
경로 약칭: `ST` = `skills/stockbee-20pct-study/scripts/run_20pct_study.py`

| 항목 | 내용 |
|---|---|
| 기법·출처 | Stockbee 식 "N일 +-20% 급등락 종목 연구": 급등락 이벤트를 구조화 기록 → 이후 1/3/5/10/20일 성과 갱신 → 코호트 집계로 엣지 힌트. 신호·주문 생성 안 함(`skills/stockbee-20pct-study/SKILL.md:L6-L9`) |
| 분류 | (a) 일봉만으로 구현 가능(촉매는 선택 뉴스 JSON). 용도는 연구·사후 분석(검증 루프) |
| 필요 데이터 | 일봉 OHLCV(260봉 이상 권장; 미만이면 품질 플래그), 선택 뉴스/촉매 JSON, 상태 JSONL(`state/stockbee/20pct_study_events.jsonl`) |
| 주요 파일 | `ST`(1839줄): 하위명령 scan / enrich / update-outcomes / summarize / backfill (`ST:L1749-L1822`) |
| 라이선스 | 루트 MIT |
| 이식 판단 | 채택: 사후 분석·검증 모듈(이벤트-포워드 아웃컴 + 코호트 집계 + 후보 규칙 승격 기준). 점수식은 생존편향 플래그와 함께 참고만 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 이벤트 정의 | return_pct=(close[t]/close[t-lookback]-1)*100; lookback 기본 5거래일; UP: >= +20, DOWN(옵션): <= -20 (PCT_EPSILON 1e-9) | `ST:L483-L520`, 기본값 `ST:L1756-L1760` |
| 2 | 필터 | close >= 5; 당일 거래대금(close*volume) >= 20,000,000 (달러) | `ST:L520-L528`, `ST:L1758-L1759` |
| 3 | 보조 지표 | 20일 평균거래량/거래대금(직전20봉), volume_ratio_20; 52주 고/저 대비 거리; prior_20d/50d 수익률(전일 종가 기준); gap_pct=open/prev_close; range%=(H-L)/prev_close; close_loc | `ST:L530-L548` |
| 4 | 에피소드 묶음 | 같은 종목·방향 이벤트가 5일(episode_gap_days, 캘린더일) 이내이면 동일 episode_id | `ST:L454-L482`, `ST:L1761` |
| 5 | 종가 품질(UP) | close_loc >=80 STRONG, >=55 MID, else WEAK; DOWN: <=20 WEAK_CLOSE_DOWN, <=45 MID, else REVERSAL_CLOSE | `ST:L698-L710` |
| 6 | 과확장 위험 | 점수합: |ret|>=60:+2(>=35:+1); |prior20d|>=50:+2(>=25:+1); close_loc<45:+1; >=4 HIGH, >=2 MODERATE, else LOW | `ST:L712-L731` |
| 7 | 차트 패턴 라벨(UP) | GAP_AND_GO: gap>=8 & close_loc>=75 & vol_ratio>=2; BASE_BREAKOUT: 52주고가 -5% 이내 & close_loc>=70 & vol_ratio>=1.5; CLIMAX_EXTENSION: ret>=50 & close_loc<55; FAILED_BREAKOUT: close_loc<45; EXTENDED_MOMENTUM: prior20d>40; else MOMENTUM_EVENT. DOWN: close_loc>=65 DOWN_GAP_REVERSAL_CANDIDATE; |ret|>=35 & close_loc<=25 STRUCTURAL_BREAKDOWN; else BREAKDOWN_EVENT | `ST:L733-L761` |
| 8 | 베이스 추정 | base_length=이벤트일 이전 최대 80봉에서 종가가 현재가*0.75 이상인 연속 봉 수; base_depth=최근 50봉 (고-저)/고 | `ST:L764-L784` |
| 9 | 데이터 품질 플래그 | <260봉; 평균거래대금<5M$; 거래량<=0; |ret|>200%(분할/기업행위 의심); 시가가 전일종가의 4배 초과/0.25배 미만(분할 의심) | `ST:L795-L815` |
| 10 | 포워드 아웃컴 | entry=이벤트일 종가; 호라이즌 h in (1,3,5,10,20): close_return, MFE=max high(t+1..t+h)/entry-1, MAE=min low/entry-1; DOWN은 부호 반전; 미래 봉 부족하면 PENDING | `ST:L1077-L1160`, `ST:L49` |
| 11 | 아웃컴 분류(UP) | STRONG_CONTINUATION: 방향수익>=8 또는 MFE>=12; CONTINUED: >=4 또는 MFE>=6; FAILED_FADE: 수익<=-4; CHOPPY_FAILURE: MAE<=-8 & 수익<2; else NEUTRAL (DOWN은 대칭, REVERSAL_BOUNCE: 수익>=6) | `ST:L1167-L1195` |
| 12 | 코호트 집계 | 기본 그룹키 direction, catalyst.label, pattern_label, close_quality; horizon 기본 5d; 코호트당 n, 방향 승률(수익>0), 중앙값 방향수익·종가수익·MFE·MAE, 아웃컴 태그 카운트, 데이터품질 플래그 카운트 | `ST:L50-L52,L1207-L1283`, `ST:L1791-L1794` |
| 13 | 후보 규칙 승격 | n>=min_sample(기본 10) 이고 승률>=0.58 & 중앙값수익>=+2.0 → candidate_for_review; 승률<=0.42 & 중앙값<=-2.0 → avoid_or_fade_study. 연도별 안정성·레짐 분할·슬리피지 점검 필요 문구 포함 | `ST:L1292-L1333`, `ST:L1793` |

**점수·등급** (continuation_quality_score, 0~100; `ST:L818-L900`)
- catalyst_quality: EARNINGS_REVALUATION 24, GUIDANCE_RAISE 24, M&A 22, CONTRACT_ORDER 18, FDA_CLINICAL 14, ANALYST_UPGRADE 12, THEME_SYMPATHY 14, SHORT_SQUEEZE 8, NO_CLEAR_NEWS 3, LOW_FLOAT_SPECULATION 0, CAPITAL_STRUCTURE 0, 기타 5 (`ST:L829-L842`). 가격만 있으면 기본 NO_CLEAR_NEWS(3점) (`ST:L786-L792`).
- liquidity=min(15, int(거래대금/20M*10)); volume=min(10, int(vol_ratio_20*3)); close_score=UP: int(close_loc/100*15), DOWN: int((100-close_loc)/100*15); setup: BASE_BREAKOUT/GAP_AND_GO 12, "MOMENTUM" 포함 8, else 3; high_score: UP & 52주고가 -5% 이내 10, else 4 (DOWN 5); 과확장 감점 LOW 0/MODERATE -5/HIGH -12; 데이터품질=int(max(0,100-15*플래그수)/100*10) (`ST:L843-L876`). 합계 clip 0~100.
- reversal_risk_score: 촉매가 NO_CLEAR_NEWS/LOW_FLOAT/CAPITAL_STRUCTURE +25; 과확장 HIGH +25 (MODERATE +12); UP & close_loc<50 +25; 거래대금<20M$ +15; 품질 플래그 min(20, 8*개수) (`ST:L877-L888`).
- study_priority = clip(0..100, continuation + 20 - |50 - reversal_risk|//3) (`ST:L889-L891`).
- 라벨: continuation>=75 A, >=60 B, reversal>=65 D, else C (`ST:L902-L920`). 핸드오프: EP(GAP_AND_GO/BASE_BREAKOUT), PEAD, theme_detector(THEME_SYMPATHY 또는 priority>=80), edge_candidate(priority>=85), parabolic_short_watch(UP & reversal>=70) (`ST:L923-L934`).

**출력 형식**: 이벤트 JSONL 레코드(record_id, episode_id, price_snapshot, liquidity, technical_context, catalyst, theme_context, scores, labels, handoffs, outcomes{1d,3d,5d,10d,20d}, data_quality, human_review) + 일별/아웃컴/코호트 마크다운 리포트 (`ST:L584-L650`, `ST:L1347-L1473`).

**SKILL.md와 코드 차이**
- [차이] 촉매 분류(뉴스 JSON)는 영어 키워드 매칭, 신뢰도=min(0.95,0.45+0.15*매칭수) (`ST:L964-L995`). 뉴스 없으면 모든 이벤트 NO_CLEAR_NEWS.
- [차이] 문서가 "theme-cluster patterns"를 언급하나 scan 단계의 theme_context는 항상 UNKNOWN/0 (`ST:L590-L595`); 클러스터는 enrich 단계에 의존 (`ST:L1022`, 미정독).
- 아웃컴 진입가는 이벤트일 종가(이미 +20%인 종가) — 실제 매수 가능성 미반영; 슬리피지·갭 미적용 [한계].
- backfill은 현재 유니버스 기준이라 생존편향 플래그(`ST:L54`)를 붙임.

**한국 시장 적용** [추정]
- 20%/5일 조건은 한국에서 흔함(코스닥 급등주). 상한가(+30%) 연속(상따) 종목이 이벤트로 대량 포착됨 → "상한가 잠김 여부"와 "연속 상한가 일수"를 별도 라벨로 두고 코호트 분리. 포워드 진입가는 당일 종가가 아니라 다음 거래일 시가로 바꿔 미체결·갭 반영.
- 거래대금 20M$ → 원화(약 30~50억 원 이상)로 재설정; 가격 5$ → 호가단위 구간 고려한 최소 가격.
- 한국은 이벤트가 테마(정치·바이오·방산·2차전지 등) 동반 급등 비중이 큼 → theme_cluster(같은 날 동일 업종 이벤트 수) 계산을 scan에 필수화. 촉매는 OpenDART(단일판매·공급계약, 유증, 전환사채)로 대체.
- 승격 기준(n>=10, 승률>=58%, 중앙값>=+2%)은 거래세·농특세(왕복 약 0.2%대, 확인 필요)와 슬리피지 차감 후 평가하도록 조정.

### stockbee-setup-fluency-trainer — Stockbee 셋업 숙련 트레이너(모델북 + 블라인드 리플레이)
경로 약칭: `MBK` = `skills/stockbee-setup-fluency-trainer/scripts/build_model_book.py`, `DR` = `skills/stockbee-setup-fluency-trainer/scripts/decision_replay.py`

| 항목 | 내용 |
|---|---|
| 기법·출처 | 모멘텀 버스트 후보를 모델북(JSONL)에 적재 → 3/5일 포워드 성과(MFE/MAE/손절 터치) 갱신 → 태그별 코호트 통계로 승격/강등. 별도로 VCP 후보에 대한 enter/wait/pass 블라인드 리플레이(규칙 준수와 사후 경로 분리 채점) (`skills/stockbee-setup-fluency-trainer/SKILL.md:L6-L19`) |
| 분류 | (a) 일봉 기반, 용도는 검증·사후 분석(규칙 가중치 보정 루프). 셋업 판정 규칙 자체는 없음(판정은 momentum-burst 출력 재사용) |
| 필요 데이터 | momentum-burst JSON, 일봉(FMP 또는 오프라인), VCP 스크리너 JSON(리플레이용) |
| 라이선스 | 루트 MIT |
| 이식 판단 | 채택(부분): 포워드 아웃컴 분류·태그별 승격/강등 기준 → 검증/사후 분석 모듈. 리플레이는 사람 훈련용이라 보류 |

**규칙·계산식**
| # | 규칙 | 수치 | 근거 |
|---|---|---|---|
| 1 | 기본 호라이즌 | 3일, 5일; 주 호라이즌 5일 | `MBK:L54`, `MBK:L572-L577` |
| 2 | 포워드 계산 | entry=screener의 entry_reference(트리거일 종가), stop=stop_reference(트리거일 저가). 이후 N봉: fwd=(N일째 종가/entry-1)*100, MFE=(max high/entry-1), MAE=(min low/entry-1); 윈도 내 low<=stop이면 stop_hit(날짜 기록); 미래봉 부족 시 미성숙 | `MBK:L504-L556` |
| 3 | 결과 태그 | stop_hit→FAILED_STOP; MFE>=12 또는 fwd>=8→STRONG_WINNER; MFE>=6 또는 fwd>=4→WORKED; fwd<=-2→FAILED_FADE; MAE<=-5 & fwd<2→CHOPPY_FAILURE; else NEUTRAL | `MBK:L558-L569` |
| 4 | 셋업 태그 파생 | trigger_tags + soft_/reject_ 접두 + rating_*; close_loc>=85 close_near_high, <50 weak_close_location; vol_ratio_1d>=3 high_volume_expansion, (0,1.2) thin_volume_confirmation; base_width 0<w<=8 tight_base, >=15 wide_base; 베이스일수 3~20 controlled_3_to_20_day_base, >30 long_base; risk 0<r<=3 compact_risk, >=6 wide_risk; 거래량건조, 최근4%하락, 직전3일상승 태그 | `MBK:L368-L421` |
| 5 | 승격 후보 | 코호트 n>=5 & 승률>=60% & 평균 5일수익>=+2% & 평균 5일 MAE > -5% | `MBK:L743-L748` |
| 6 | 강등 후보 | n>=5 & (실패율>=50% 또는 평균 5일수익<=-1%) | `MBK:L751-L755` |
| 7 | 리젝트 적재 | 기본은 스킵, `--include-rejects`로 네거티브 세트 | `skills/stockbee-setup-fluency-trainer/SKILL.md:L36-L40` |
| 8 | 리플레이 체크리스트 vcp-checklist-v1 | market_gate==open; valid_vcp 참; execution_state가 Invalid/Damaged/Overextended/Extended/Early-post-breakout 아님; 피벗 거리 -8%~+3%; 리스크 0<r<=15%; dry_up_ratio<=1.0 → 전부 통과 시 expected=enter | `DR:L70-L86,L271-L305` |
| 9 | 리플레이 경로·사분면 | 호라이즌 5일, rally = 손절 미터치 & 포워드수익 >= 5.0%; 준수(followed/deviated) × 결과(favorable/adverse) 4사분면 | `DR:L51-L52,L309-L330,L1023-L1024` |

**점수·등급**: 점수 없음. 결과 태그 + 코호트 승격/강등 플래그만.
**출력 형식**: model_book.jsonl 레코드(setup_date, entry/stop_reference, setup_tags, outcomes{3d,5d}, overall_outcome) + 코호트 JSON/MD 리포트(그룹별 sample_size, win_rate_pct, failure_rate_pct, avg_5d_return_pct, avg_5d_mae_pct) (`MBK:L650-L741`).
**SKILL.md와 코드 차이**: [차이] SKILL.md 설명은 모멘텀 버스트 모델북 중심이지만 코드 `decision_replay.py`는 별도로 VCP(vcp-screener) 전용 규칙이며 Stockbee 규칙이 아님 (`DR:L45-L46`).
**한국 시장 적용** [추정]: 손절 터치 판정은 일봉 low<=stop으로 보수적(갭다운 시 실제 체결은 시가) → 갭 하회 시 시가 체결 가정과 거래세·슬리피지 반영. 호라이즌 3/5일은 유지, 상한가 잠김일은 체결 불가로 제외. 승격/강등 기준(n>=5)은 표본이 작아 한국 적용 시 n>=30 이상 권장 [추정].

#### 그룹 소결
이식 후보(우선순위):
1. 모멘텀 버스트 트리거+점수 골격(진입 트리거 + 위원회 "단기 돌파" 점수기): 4% 상승(+거래량>전일), 20일 평균 대비 거래량 배수 구간점수(>=3:15,>=2:12,>=1.5:9,>=1:6), 종가위치 구간점수(>=90:10 … >=50:3), 전일 레인지<=3% 또는 음봉 가점, 베이스 3~20일 폭<=15%·평균일레인지<=5%(`skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py:L577-L760`). 한국용으로 $0.90 달러돌파 → ATR/호가 기반, 최소거래량 → 거래대금(원)으로 재보정, 상한가 마감은 진입불가 플래그.
2. 손절=트리거일 저가, risk%=(종가-저가)/종가 구간점수(<=2.5:15 … <=10:2, >10 리젝트)와 3~5일 보유 청산 템플릿 (`screen_momentum_burst.py:L702-L715,L818-L824`, `references/entry_exit_rules.md:L30-L37`). 코드에 청산 로직 자체는 없으므로 엔진에서 구현 필요.
3. 완료봉 신선도 게이트(bar_age_sessions 0 허용, 기본 stale=리젝트, 허용 시 ACTIONABLE→MANUAL 강등) (`screen_momentum_burst.py:L314-L347,L842-L845`)를 데이터 품질 게이트로 이식(KRX 거래일 달력 필요).
4. EP: 촉매 기본점수표(guidance 95, FDA 94, earnings 88, M&A 84, 계약 76 …)×0.35 + 가격20 + 거래량20 + 재평가10 + 유동성10 + 리스크5, 상태 임계 85/75/70, move>=4%, 거래량배수>=1.5, 종가위치<40이면 약세 (`analyze_ep.py:L105-L118,L623-L884`). 촉매 입력은 OpenDART 공시 분류로 대체 [추정].
5. 눌림 반전(망치형): 아랫꼬리>=40%·몸통<=35%·종가위치>=60·꼬리/몸통>=1.5·저점회복>=2%, 직전40일 고점 대비 6~35% 눌림·3~30일 경과, 직전5일 저점 undercut&reclaim, 손절=당일저가-0.1%, 리스크<=12% (`screen_exhaustion_hammer.py:L521-L632,L860-L930`). 일봉만으로 가능, 한국에서는 호가틱 대비 꼬리 길이 보정 필요.
6. 검증 루프: 20% 스터디 코호트(승률>=58% & 중앙값>=+2%, n>=10 승격)와 모델북 승격/강등(n>=5, 승률>=60%, 5일 평균>=+2%, MAE>-5%) + 포워드 아웃컴 분류(STRONG>=MFE12/ret8 …) (`run_20pct_study.py:L1167-L1333`, `build_model_book.py:L558-L755`). 사후 분석·가중치 보정 모듈로 채택, 진입가는 익일 시가로 수정.
- 주의: TI65 등 추세강도 지표는 이 저장소에 구현돼 있지 않음. 한국 임계값(갭·거래대금 등)은 모두 [추정] 재보정 필요.


---

## 15. 이벤트·역발상 계열: 포물선 숏, PEAD, 실적 반응, 뉴스 반응 실패, COT (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, 2026-11-14, MIT) · 범위: parabolic-short-trade-planner, pead-screener, earnings-trade-analyzer, news-reaction-failure-analyzer, contrarian-setup-gate, cot-contrarian-detector

### parabolic-short-trade-planner — 포물선 숏 트레이드 플래너
| 항목 | 내용 |
|---|---|
| 기법·출처 | Qullamaggie의 3대 숏 셋업(ORL 이탈 / First Red 5분봉 / VWAP fail)을 각색 (`skills/parabolic-short-trade-planner/references/parabolic_short_methodology.md:L3`). 주문은 내지 않고 JSON/MD만 생성 (`SKILL.md:L8-L9` 근처) |
| 분류 | 주: (a) 일봉만 (1단계 스크리너·점수) / 보조: 분봉 필요(3단계 FSM), 공매도 인프라 필요(2단계) |
| 필요 데이터 | 1단계: FMP 일봉 OHLCV + profile(mktCap, 상장일) + earnings calendar, `FMP_API_KEY` 필수. 2단계: Alpaca 대여가능(ETB) 조회(선택). 3단계: Alpaca 5분봉 (`SKILL.md:L52`) |
| 주요 파일 | `scripts/screen_parabolic.py`, `scripts/calculators/*.py`, `scripts/parabolic_scorer.py`, `scripts/invalidation_rules.py`, `scripts/state_caps.py`, `scripts/size_recipe_builder.py`, `scripts/intraday_evaluators/*.py` |
| 라이선스 | MIT (저장소 루트) |
| 이식 판단 | 부분 채택: 1단계 "과열 점수"를 위원회의 역발상 과열 관점(보유분 청산·신규 진입 금지)으로. 숏 트리거·SSR·대여 로직은 보류(한국 개인 숏 제한) |

**규칙·계산식** (P = `skills/parabolic-short-trade-planner/scripts/`)
| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 사전 필터: 이력 | 일봉 21개 미만이면 제외 | P`screen_parabolic.py:L257-L259` |
| 2 | 하드 게이트 A: 5일 수익률 | `return_5d = (close[-1]-close[-6])/close[-6]*100`; safe_largecap >= 30, classic_qm >= 100 (CLI `--min-roc-5d`로 덮어씀) | P`screen_parabolic.py:L52`, `L304-L313`; P`calculators/acceleration_calculator.py:L19-L34` |
| 3 | 하드 게이트 B: 20일선 이격 % | `(close-SMA20)/SMA20*100 >= 25.0` (`--min-ma20-extension-pct` 기본 25) | P`screen_parabolic.py:L76`, `L314-L322`; P`calculators/ma_extension_calculator.py:L59-L62` |
| 4 | 하드 게이트 C: 20일선 이격 ATR | `(close-SMA20)/ATR14 >= 4.0`; ATR14 = 최근 14개 TR의 단순평균(Wilder 아님), TR=max(H-L,|H-pC|,|L-pC|) | P`screen_parabolic.py:L77`, `L323-L331`; P`calculators/ma_extension_calculator.py:L66-L70`; P`calculators/atr_calculator.py:L11-L43` |
| 5 | 무효화(하드 제외) safe_largecap | 시총 < 20억달러, 20일 평균 거래대금(ADV) < 2천만달러, 종가 < 5달러, 상장 < 60일, 실적 발표까지 <= 2일 | P`invalidation_rules.py:L15-L22`, `L58-L78` |
| 6 | 무효화 classic_qm | 시총 < 3억달러, ADV < 500만달러, 나머지 동일 | P`invalidation_rules.py:L23-L29` |
| 7 | 성분1 MA 이격 점수(가중 30%) | `0.5*linear(ext20_pct,20,120) + 0.5*linear(ext20_atr,3,10)`; linear는 [lo,hi]->[0,100] 클램프 | P`calculators/parabolic_score_calculator.py:L27-L45` |
| 8 | 성분2 가속(25%) | `0.4*linear(ret5d,20,100) + 0.2*linear(연속양봉수,2,5) + 0.2*linear(가속비,1.0,2.0) + 0.2*linear(ret3d,10,50)` | 위 파일 `L48-L58` |
| 9 | 연속 양봉 정의 | 최근봉부터 거꾸로 `close > open`인 봉 수(전일 대비 상승 아님) | P`calculators/acceleration_calculator.py:L37-L47` |
| 10 | 가속비 | `평균일수익률(최근3일)/평균일수익률(최근10일)`, 10일 평균 <= 0이면 None(점수 0) | P`calculators/acceleration_calculator.py:L50-L81` |
| 11 | 성분3 거래량 클라이맥스(20%) | `linear(최신거래량/직전20일평균거래량, 1.5, 5.0)` (직전 20일, 당일 제외) | P`parabolic_score_calculator.py:L61-L62`; P`calculators/liquidity_metrics_calculator.py:L24-L31` |
| 12 | 성분4 레인지 확장(15%) | `linear(최근5일 평균TR / 그 앞 20일 평균TR, 1.2, 3.0)`, 비중첩 윈도우, 최소 26봉 | P`parabolic_score_calculator.py:L65-L66`; P`calculators/range_expansion_calculator.py:L31-L47` |
| 13 | 성분5 유동성(10%) | `log10(ADV20)`을 7.0(1천만달러)->0, 8.5(약 3.16억달러)->10으로 선형, x10 하여 0-100 | P`calculators/liquidity_metrics_calculator.py:L34-L46`; P`math_helpers.py:L69-L86`; P`parabolic_score_calculator.py:L69-L71` |
| 14 | state cap `still_in_markup` | 종가가 당일 범위 상단 80% 이상(`(c-L)/(H-L)>=0.80`) AND 252봉 최고가의 99.9% 이상 -> 차단성 상태 | P`state_caps.py:L24`, `L43-L50`; P`screen_parabolic.py:L340` |
| 15 | 경고 `too_early_to_short` | 위 상단마감 AND 거래량비 >= 2.0 (still_in_markup 아닐 때만) | P`state_caps.py:L25`, `L52-L60` |
| 16 | 경고 `wait_for_first_crack` | 프리마켓 갭 >= +5% | P`state_caps.py:L26`, `L62-L64` |
| 17 | 최근 실적 경고 | 마지막 실적 후 거래일 <= 10(기본)이면 `recent_earnings_catalyst` (참고용) | P`screen_parabolic.py:L88-L92`, `L350-L353` |
| 18 | 차단/참고 사유 분리 | 차단: 대여불가, HTB 수수료 불명, SSR 당일/이월, `state_cap:*`, 프리마켓 고저 없음. 참고: 수동 locate, `warning:*` | P`manual_reasons.py:L28-L54` |
| 19 | 진입 트리거 ORL | 첫 5분봉 저가(ORL) 아래 종가 AND 거래량 >= 1.2 x 첫봉 거래량 -> 진입가 = 종가-0.05, 손절 = 당일 고가 + 0.25 x ATR14 | P`intraday_evaluators/orl_evaluator.py:L37`, `L129-L133` |
| 20 | ORL 사후 무효 | 트리거 후 종가 > ORL 저가 AND 종가 > 현재 VWAP (둘 다) | P`intraday_evaluators/orl_evaluator.py:L139-L142` |
| 21 | First Red | 첫 `close<open` 5분봉 저/고 기록 -> 이후 봉 저가 < red_low면 진입(red_low-0.05), 손절 = red_high; 같은 봉에 둘 다면 무효 우선 | P`intraday_evaluators/first_red_evaluator.py:L79-L103` |
| 22 | VWAP fail | 5상태: 첫 균열(종가<VWAP, 고점에서 내려옴) -> 재시험(종가>=VWAP) -> 거부확인(고가<재시험봉 고가 AND 종가<VWAP) -> 거부봉 저가 이탈 시 진입(저가-0.05), 손절 = 재시험봉 고가; 트리거 후 종가>VWAP면 무효 | P`intraday_evaluators/vwap_fail_evaluator.py:L108-L153` |
| 23 | 사이징(고정비율) | `risk_usd = 계좌 x risk_bps/10000`(기본 50bp=0.5%), 종목 한도 5%, 숏 총노출 한도 20%; `shares=floor(min(risk_usd/(stop-entry), max_position_value/entry))`; 잔여 숏 한도가 종목 한도보다 작으면 한도를 잔여로 축소, 0 이하면 0 | P`generate_pre_market_plan.py:L71-L77`; P`size_recipe_builder.py:L48-L64`; P`intraday_size_resolver.py:L47-L50` |
| 24 | 목표 | 구조적 목표 10일선·20일선, 참고 R배수 1R/2R/3R (코드가 청산을 집행하지는 않음) | P`plan_builders/orl_plan_builder.py:L17`, `L27-L28` |
| 25 | SSR(미국 Rule 201) | 정규장 중 전일 종가 대비 -10% 이상 하락 시 당일+익일 숏 제한 | P`ssr_state_tracker.py:L29`, `L51` |

**점수·등급**
- 총점 = sum(성분점수 x 가중치), 소수 1자리 반올림. 가중치 MA이격 0.30 / 가속 0.25 / 거래량 0.20 / 레인지 0.15 / 유동성 0.10 (P`parabolic_scorer.py:L10-L16`, `L46-L51`).
- 등급 컷: A >= 85, B >= 70, C >= 50, 그 아래 D. 매매 가능 기본 B 이상, 관찰 C 이상 (P`parabolic_scorer.py:L18-L35`).
- 지침: A "트리거 대기, 대여 확인", B "깨끗한 트리거 + 차단사유 없을 때만", C 모니터링, D 제외 (P`parabolic_scorer.py:L25-L30`).

**출력 형식**: 1단계 JSON+MD (후보별 score/grade/components/raw_metrics/state_caps/warnings/key_levels, 상위 25개 기본, `--watch-min-grade C`) (P`screen_parabolic.py:L52`, `L94-L99`, `L365-L378`). 2단계 사전장 계획 JSON(트리거별 plan, size_recipe), 3단계 `intraday_monitor` JSON(state, entry_actual, stop_actual, shares_actual) (`SKILL.md:L22-L29`).

**SKILL.md와 코드 차이**
- [차이] 방법론 문서는 "3연속 양봉 AND 가속비>1.0 AND 거래량비>=1.5 AND ADV 하한이 모두 참"이라 쓰지만 (`references/parabolic_short_methodology.md:L11-L20`), 코드의 하드 게이트는 5일 수익률·MA20 이격%·MA20 이격 ATR 세 개뿐이며(P`screen_parabolic.py:L304-L331`) 연속 양봉·가속·거래량·레인지는 점수에만 반영된다. ADV는 무효화 규칙으로 하드 적용.
- [차이] state_caps 주석은 "52주 고점을 최근 2세션 내 달성"이라 하나, 호출부는 당일 종가가 252봉 최고가 x 0.999 이상인지만 본다 (P`state_caps.py:L32`, P`screen_parabolic.py:L340`).
- [차이] 문서는 "실적 N 거래일 이내 제외" (`references/short_invalidation_rules.md:L11`), 코드 주석은 달력일 기준 (P`screen_parabolic.py:L248-L250`).
- 문서에 보이는 일일 손실 한도는 미구현 (`references/short_risk_management.md:L122-L127`).

**한국 시장 적용**
- 일봉 계산부(규칙 2-4, 7-13)는 OHLCV만으로 그대로 이식 가능. 단 달러 임계값(ADV 2천만달러, 가격 5달러, 시총 20억달러)은 원화로 재산정 필요: ADV는 [추정] 약 20~50억원 이상, 가격하한은 호가단위 구간(예 2천원 미만 1원 호가)을 고려해 별도 정의.
- 가격제한 +-30%이므로 5일 +30%/+100% 임계는 한국에서 상한가 연속 구간에 몰림. 상한가 잠김(거래량 급감, 종가=상한가) 구간은 거래량 클라이맥스 점수가 왜곡되므로 [추정] 상한가 종가 봉은 별도 플래그 처리.
- 개인 공매도 제약이 커서 3단계(ORL/First Red/VWAP fail 숏 진입)와 SSR·ETB 대여 로직은 이식 불가. 1단계 과열 판정을 "보유분 부분 청산·신규 진입 금지" 신호로 재해석(이식 판단: 위원회의 역발상 점수기 + 진입 리스크 게이트). 규칙 14(상단마감+신고가 = 아직 상승 중이면 차단)는 롱 관점에서는 "과열이지만 추세 지속 중이므로 즉시 청산하지 말고 약세 첫 신호(예: 일봉 음봉 + 20일선 이격 축소) 대기"로 뒤집어 쓸 수 있음 [추정].
- VI(변동성완화장치)·시간외 단일가가 있어 5분봉 FSM을 일봉 FSM으로 단순화해야 함. 분봉 데이터가 일봉 엔진 범위 밖이므로 보류.
- 청산 연계: 트리거 후 "종가가 ORL 저가·VWAP 위로 회복 시 무효"(규칙 20) 개념은 일봉으로 "과열 경고 후 N일 내 신고가 갱신 시 경고 해제"로 번안 가능 [추정].

### pead-screener — PEAD(실적 후 표류) 스크리너
| 항목 | 내용 |
|---|---|
| 기법·출처 | 실적 갭상승 후 주봉 "빨간 봉 눌림 -> 그 봉 고가 돌파" 패턴. 이론 근거로 Ball & Brown(1968), Bernard & Thomas(1989) 인용 (`skills/pead-screener/references/pead_strategy.md:L9-L13`). 주봉 패턴 자체는 저자 고유 규칙(원전 명시 없음) |
| 분류 | 주: (b) 재무(실적 일정·시점) 필요하나, 갭 계산 자체는 일봉만으로 가능 -> 한국은 (a)+공시일 캘린더 |
| 필요 데이터 | FMP earnings calendar(일자별 호출, bmo/amc 시점), profile(시총), 일봉 90일(후보당 1콜), 무료 250콜/일 (`SKILL.md:L20-L25`; P2`screen_pead.py:L486-L487` 근처). Mode B는 earnings-trade-analyzer JSON 입력 |
| 주요 파일 | P2=`skills/pead-screener/scripts/`: `screen_pead.py`, `scorer.py`, `calculators/{weekly_candle,breakout,liquidity,risk_reward}_calculator.py` |
| 라이선스 | MIT |
| 이식 판단 | 채택(부분): 실적 갭 -> 주봉 눌림 -> 돌파 상태머신(MONITORING/SIGNAL_READY/BREAKOUT/EXPIRED)과 갭 점수표. R:R 성분은 코드상 상수라 폐기. 엔진 위치: 진입 트리거 + 위원회 "실적 모멘텀" 점수기 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 갭 계산 | BMO: `open[실적일]/close[전일]-1`; AMC/미상: `open[다음날]/close[실적일]-1` (%, 소수 2자리) | P2`screen_pead.py:L47-L91` |
| 2 | 후보 필터(Mode A) | 최소 갭 3.0% (`abs(gap)` 비교 -> 음의 갭도 통과), 시총 >= 5억달러, 실적 조회 기간 14일 | P2`screen_pead.py:L137`, `L143`, `L131`, `L512-L514` |
| 3 | 후보 필터(Mode B) | earnings-trade-analyzer 등급 >= B(기본) | P2`screen_pead.py:L154`, `L844-L851`(grep 상 줄 근처) |
| 4 | 주봉 변환 | ISO주(월 시작), 실적 주는 실적일 이전 일자 제외, 주 OHLC = 첫날 시가/최고/최저/마지막날 종가, 거래량 합, `is_green = close >= open`, 마지막 거래일이 금요일 전이면 partial | `calculators/weekly_candle_calculator.py:L58-L139` (P2 기준) |
| 5 | 빨간 봉 탐색 | 가장 최근(인덱스 0부터) `close<open` 주봉, 단 실적 주 자체는 제외(range 끝이 실적 주 인덱스 미포함); 아랫꼬리% = `(min(o,c)-low)/(high-low)*100`; 거래량비 = 해당 주/주변 4주 평균 | P2`calculators/weekly_candle_calculator.py:L142-L201` |
| 6 | 단계 판정 | 실적 후 경과 주 > watch_weeks(5) -> EXPIRED; 빨간 봉 없음 -> MONITORING; 최신 주봉이 양봉 AND 종가 > 빨간 봉 고가 -> BREAKOUT(돌파폭 % = `(close-red_high)/red_high*100`); 그 외 SIGNAL_READY | P2`calculators/weekly_candle_calculator.py:L262-L287` |
| 7 | 성분1 Setup Quality(30%) | 갭 점수: >=10%:50, >=7:40, >=5:30, >=3:20, 그 외 10. 패턴 점수: BREAKOUT 50 / SIGNAL_READY 40(+5 if 아랫꼬리 > 30%) / MONITORING 25(경과 <= 2주) 또는 15 / EXPIRED 0. 상한 100 | P2`screen_pead.py:L240-L285` |
| 8 | 성분2 Breakout(25%) | 돌파 없음 0; 돌파폭 >= 3% AND 거래량확인 100; >= 2% AND 거래량확인 85; >= 1% 70; 그 외 양수 55. 거래량확인 = 현재 주 거래량 > 직전 4주(양수 거래량만) 평균 | P2`calculators/breakout_calculator.py:L53-L76`, `L81-L105` |
| 9 | 성분3 Liquidity(25%) | 3조건: ADV20 >= 2,500만달러, 20일 평균거래량 >= 100만주, 가격 >= 10달러. 3개 통과: ADV > 1억달러 100 / > 5천만 85 / 그 외 70; 2개 40; 0-1개 15 | P2`calculators/liquidity_calculator.py:L74-L93` |
| 10 | 성분4 Risk/Reward(20%) | 진입 = 현재가, 손절 = 빨간 봉 저가, 목표 = 진입 + 2 x 위험; 점수 R:R>=3 100, >=2.5 85, >=2 70, >=1.5 50, 그 외 25. 빨간 봉 없음/손절>=현재가이면 25 | P2`calculators/risk_reward_calculator.py:L57-L90` |
| 11 | 종합 점수 | `0.30*setup + 0.25*breakout + 0.25*liquidity + 0.20*rr`, 소수 1자리 | P2`scorer.py:L21-L26`, `L61-L66` |
| 12 | 등급 | >=85 Strong Setup(풀 사이즈), >=70 Good(표준), >=55 Developing(관찰), 미만 Weak | P2`scorer.py:L96-L121` |
| 13 | 정렬 | 단계 우선(BREAKOUT>SIGNAL_READY>MONITORING>EXPIRED) 후 종합점수 내림차순, 상위 20 | P2`screen_pead.py:L566-L570`, `L118` 근처 |
| 14 | 문서상 청산(코드 미집행) | 2R 목표, 1R 도달 시 손절 본전, 1.5R 시 1R 아래 추적, 4주 내 목표 미도달 시 정리, 포지션 <= ADV20의 1%, 동시 3-5종목 | `skills/pead-screener/references/entry_exit_rules.md:L31-L62` |

**점수·등급**: 위 규칙 11-12. 단, 규칙 10의 R:R은 `reward = risk * 2.0` 고정이므로 `rr_ratio`는 항상 2.0 -> 성분4가 사실상 70점(가중 14점) 상수 (P2`calculators/risk_reward_calculator.py:L23`, `L63`, `L70`, `L84-L85`; 호출은 기본값 P2`screen_pead.py:L343`). 손절>=현재가인 경우만 25점.

**출력 형식**: `pead_screener_<날짜>.json/.md`, 단계별 그룹; 후보별 stage, gap_pct, weeks_since_earnings, red_candle, entry/stop/target, risk_pct, adv20_dollar, composite_score, rating, components (P2`screen_pead.py:L363-L383`; `SKILL.md:L82-L85`).

**SKILL.md와 코드 차이**
- [차이] 문서 체크리스트는 "빨간 봉이 도지·인사이드바가 아닐 것"(`references/entry_exit_rules.md:L18`)이나 코드는 `close<open`만 확인, 몸통 크기 검증 없음 (P2`calculators/weekly_candle_calculator.py:L170`).
- [차이] 문서는 "ADV20의 1% 이내 포지션"을 규칙으로 제시하나 코드에 사이징 없음; 트레일링·시간청산도 코드 없음.
- [차이] 최소 갭 필터가 `abs(gap)`라 하락 갭(악재)도 PEAD 후보로 통과, 갭 점수는 `<3%`에 10점을 줌 (P2`screen_pead.py:L513`, `L261-L262`).
- [차이] R:R 점수 상수화(위). 문서상 "전략은 R:R로 후보를 변별"하나 실제로는 변별력 없음.
- 갭 시점 미상(unknown)은 AMC로 가정 (`SKILL.md:L87-L95`).

**한국 시장 적용**
- 실적 이벤트: FMP 캘린더 대신 OpenDART 잠정실적 공시(영업(잠정)실적(공정공시)·연결재무제표기준영업실적 등)의 접수일시로 이벤트일을 잡음. 접수시각이 있으므로 장중/장후 구분이 FMP unknown보다 정확 [추정]. 시간외 단일가(16:00~18:00)에서 반응이 먼저 나오므로 "공시 접수 시각이 15:30 이후면 다음 거래일 시가 갭" 규칙으로 AMC 대응, 08:00~09:00 공시는 BMO 대응 [추정].
- 갭 계산식(규칙 1)은 일봉 시가/종가만으로 그대로 이식. 가격제한 +-30%이므로 +10% 이상 갭 구간(점수 50) 내 변별은 약해지고, 임계값을 한국 변동성에 맞게 재보정 필요 [추정].
- 주봉 눌림 -> 고가 돌파(규칙 4-6)와 5주 감시창은 일봉에서 파생되는 순수 가격 규칙이라 그대로 이식 가능. 한국은 주 5일이므로 ISO주 처리 호환. 공휴일 주(4일 미만)는 partial 오탐 가능 -> `trading_days<5` 대신 달력 기준 필요 [추정].
- 유동성 임계(2,500만달러 ADV, 100만주, 10달러)는 원화 재산정(예: ADV 30억원 이상, 가격 호가단위 변동 감안) 필요 [추정].
- 컨센서스(서프라이즈) 없이도 "갭 크기"가 서프라이즈 대용으로 동작하는 것이 이 스킬의 장점. 규칙 3(Mode B 등급 연동)은 earnings-trade-analyzer 이식 시 연결.
- 엔진 위치: 진입 트리거(BREAKOUT 단계), 위원회 "이벤트 모멘텀" 관점(갭 점수 + 단계 점수), 청산(빨간 봉 저가 손절·2R).

### earnings-trade-analyzer — 실적 반응 트레이드 분석기
| 항목 | 내용 |
|---|---|
| 기법·출처 | 최근 실적 발표 종목의 반응을 5요인 점수(0-100)로 평가해 A-D 등급. 학술 출처는 없고 "지지선·거래량·추세 확인형 PEAD 모멘텀" 휴리스틱 (`skills/earnings-trade-analyzer/references/scoring_methodology.md:L93-L98`). 필터는 저자의 517거래 백테스트에서 도출됐다고 코드 주석에 기록 (E=`skills/earnings-trade-analyzer/scripts/`, E`analyze_earnings_trades.py:L322-L324`) — 백테스트 원자료는 저장소에서 확인 못 함 |
| 분류 | 주: (a) 일봉만 (이벤트 일자만 외부) / 보조: (b) 실적 일정·시점 |
| 필요 데이터 | FMP earnings calendar(bmo/amc), 프로필(시총·거래소), 일봉 250일 (E`analyze_earnings_trades.py:L15-L18`). 컨센서스·EPS 서프라이즈 미사용 — 가격 반응만 사용 |
| 주요 파일 | E`scorer.py`, E`calculators/{gap_size,pre_earnings_trend,volume_trend,ma200,ma50}_calculator.py`, E`analyze_earnings_trades.py` |
| 라이선스 | MIT |
| 이식 판단 | 채택: 5요인 점수식(순수 일봉) -> 위원회 "실적 반응" 관점. 단 갭 절대값 점수·거래량 앵커 결함은 보정 필요. 엔진 위치: 위원회 점수기 + 사후 분석(백테스트 필터 규칙은 자체 데이터로 재검증) |

**규칙·계산식** (E = `skills/earnings-trade-analyzer/scripts/`)
| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 갭 계산 | BMO: `open[실적일]/close[전일]-1`; AMC/미상(AMC 가정): `open[다음거래일]/close[실적일]-1`; 거래일 인덱스 기반 | E`calculators/gap_size_calculator.py:L97-L128`, `L141-L143` |
| 2 | 성분1 갭 점수(25%) | `abs(gap)`: >=10% 100, >=7 85, >=5 70, >=3 55, >=1 35, 그 외 15 (부호 무시) | E`calculators/gap_size_calculator.py:L41-L52`, `L142-L144` |
| 3 | 성분2 실적 전 20일 추세(30%) | `close[실적일]/close[실적일 20거래일 전]-1`: >=15% 100, >=10 85, >=5 70, >=0 50, >=-5 30, 그 외 15 | E`calculators/pre_earnings_trend_calculator.py:L39-L50`, `L80-L101` |
| 4 | 성분3 거래량 추세(20%) | `최근20일 평균거래량 / 최근60일 평균거래량`(인덱스 0부터, 실적일 기준이 아니라 최신 봉 기준): >=2.0 100, >=1.5 80, >=1.2 60, >=1.0 40, 그 외 20; 최소 20봉 필요 | E`calculators/volume_trend_calculator.py:L40-L49`, `L86-L127`, 주석 `L78-L85` |
| 5 | 성분4 MA200 위치(15%) | `(최신종가/SMA200-1)*100`: >=20% 100, >=10 85, >=5 70, >=0 55, >=-5 35, 그 외 15; 200봉 미만이면 0점 | E`calculators/ma200_calculator.py:L27-L38`, `L57-L83` |
| 6 | 성분5 MA50 위치(10%) | 같은 식, >=10% 100, >=5 80, >=0 60, >=-5 35, 그 외 15; 50봉 미만 0점 | E`calculators/ma50_calculator.py:L26-L35`, `L53-L79` |
| 7 | 종합 | `0.25*gap + 0.30*trend + 0.20*volume + 0.15*ma200 + 0.10*ma50`, 소수 1자리 | E`scorer.py:L22-L28`, `L85-L86` |
| 8 | 등급 | A >= 85, B >= 70, C >= 55, D 미만 | E`scorer.py:L30-L35`, `L89-L95` |
| 9 | 후보 선정 | 시총 >= 5억달러(기본), 미국 거래소, 조회 2일(기본), 최소 갭 0, 호출예산 200 | E`analyze_earnings_trades.py:L255-L265`, `L369`, `L388`, `L391`, `L395` |
| 10 | 진입 필터(옵션 `--apply-entry-filter`) | 현재가 < 30달러 제외(승률 40.6% vs 기준 54.5% 주석), `abs(gap)>=10% AND 종합>=85` 제외(승률 33.3% "역설 패턴" 주석) | E`analyze_earnings_trades.py:L319-L341` |

**점수·등급**: 규칙 7-8. 최하점 성분/최고점 성분과 가이던스 문구를 함께 출력 (E`scorer.py:L37-L42`, `L99-L121`). 가이던스: A "눌림 또는 돌파 지속 진입 고려", B "눌림/거래량 확인 대기", C "추가 분석", D "회피".

**출력 형식**: JSON + MD 보고서(상위 20), 후보별 gap/trend/volume/ma200/ma50 세부와 composite{grade, guidance, weakest/strongest, component_breakdown}. pead-screener Mode B가 이 JSON(schema_version "1.0")을 입력으로 사용 (E`analyze_earnings_trades.py:L309-L316`; `skills/pead-screener/SKILL.md:L25`).

**SKILL.md와 코드 차이**
- [차이] 문서의 진입 필터는 "가격 < 10달러 제외"뿐 (`references/scoring_methodology.md:L86-L89`)이나 코드는 < 30달러 + (갭>=10 AND 점수>=85) 두 규칙 (E`analyze_earnings_trades.py:L333-L338`).
- [차이/결함] 갭 점수가 절대값이라 -10% 하락 갭도 100점. 하락 갭은 추세·MA 성분에서만 감점되므로 악재 반응 종목이 B 이상이 될 수 있음. 이식 시 갭 방향을 부호로 반영해야 함.
- [차이/결함] 거래량 성분은 실적일이 아니라 "가장 최근 20일/60일"을 사용(주석에 과거 버그 수정 기록, E`calculators/volume_trend_calculator.py:L78-L85`). 조회 2일 기본이라 후행 창이 실적 반응을 포함하지만 오래된 이벤트에는 부정확.
- 문서는 이 점수를 "이미 오른 종목의 지속성 점수"로 설명하지만, 코드는 pre-trend/MA 위치(과열)까지 가점해 "이미 강한 종목 선호" 편향 + 갭 10%+ 과열 구간을 페널티로 별도 필터링하는 이중 구조.

**한국 시장 적용**
- 일봉 OHLCV와 이벤트일만 있으면 5요인 모두 계산 가능(MA200이 200봉 필요하므로 신규상장·단기 이력 종목 제외). 이벤트일은 OpenDART 잠정실적 공시 접수일/시각으로 대체, 시각에 따라 BMO(장 시작 전, 8시대)/AMC(15:30 이후, 시간외 단일가 반응) 분기 [추정]. 컨센서스 없음 -> 서프라이즈 대신 갭이 "시장이 평가한 서프라이즈"의 대용치. 영업이익 YoY 같은 DART 재무 수치를 보조 요인으로 추가하는 것은 가능하나 본 스킬에는 없음.
- 한국은 정규장 갭 + 가격제한 +-30%로 갭 점수 구간(1/3/5/7/10%)은 그대로 쓸 수 있으나 코스닥 소형주는 10%+가 흔하므로 구간 재보정 [추정].
- 가격 하한 30달러 필터는 달러 가격 기준이라 이식 불가. 한국은 호가단위 대비 저가주(2천원 미만 등) 별도 필터로 대체 [추정].
- 필터 규칙 10(갭>=10 & 고점수 제외)은 "이미 과열된 갭은 진입 보류" 역발상 게이트로 유용하나 517건 근거 데이터가 저장소에 없어 임계값은 자체 검증 후 사용.

### news-reaction-failure-analyzer — 뉴스 반응 실패 분석기
| 항목 | 내용 |
|---|---|
| 기법·출처 | Jason Shapiro의 COT 역발상 프로세스 2단계("쏠린 시장이 호재/악재에 반응하지 않는가") (`skills/news-reaction-failure-analyzer/SKILL.md:L3`, `L11-L14`). 단순 실패비율(절반 미만 반응) 대신 "표류 유의성 검정"으로 설계, 순수 잡음에서 CONFIRMED가 48-83% 나오는 문제를 회피 (`SKILL.md:L22-L28`) |
| 분류 | 주: (c) 뉴스 필요(이벤트는 WebSearch로 사람이/Claude가 수집한 JSON) / 계산부는 (a) 일봉 종가만 |
| 필요 데이터 | 가격: FMP `stable/historical-price-eod/light` 종가 시계열(130일 전~10일 후), 선물 심볼 -> ETF 프록시 폴백. 이벤트: `event`, `event_time`(UTC 오프셋 필수), `source_url`, `source_tier`(primary/official/wire/portal), `expected_impact`(BULLISH/BEARISH). 선택: cot-contrarian-detector 보고서(방향) (`SKILL.md:L47-L52`, `L82-L88`; N=`skills/news-reaction-failure-analyzer/scripts/` N`analyze_news_reaction.py:L84-L98`, `L587-L590`) |
| 주요 파일 | N`reaction_math.py`(순수 계산), N`analyze_news_reaction.py`(CLI, 이벤트 검증, 보고서) |
| 라이선스 | MIT |
| 이식 판단 | 채택(핵심 수식): 이벤트 효과일 정렬 -> 변동성 정규화 z -> 클러스터링 -> 표류 통계 -> 3값 판정. 한국에서는 이벤트를 공시/뉴스 피드로 자동 공급. 엔진 위치: 사후 분석 + 위원회 "재료 소멸/둔감" 관점 + 청산 가속 신호 |

**규칙·계산식** (N=`skills/news-reaction-failure-analyzer/scripts/`)
| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 관련 이벤트 | 군중 방향이 CROWDED_LONG이면 BULLISH 뉴스만, CROWDED_SHORT이면 BEARISH만 판정에 사용; 반대 방향 뉴스는 증거표에만 표시 | N`reaction_math.py:L248-L251`; N`analyze_news_reaction.py:L1170-L1183` |
| 2 | 이벤트 유효 | `event_time`은 tz 포함 ISO8601, 평가 창 = as-of 기준 10일(`--window-days`), 필수필드 없으면 `dropped_events` | N`reaction_math.py:L141-L145`; N`analyze_news_reaction.py:L86`, `L627-L628` |
| 3 | 효과일(effective date) | ET 변환 후 16시 이후(시장 마감 후) 이벤트는 다음 날로 이월, 거래일 아니면 다음 거래일 | N`reaction_math.py:L86`, `L146-L152` |
| 4 | 수익률 | k=1: `close(eff)/close(eff-1)-1`; k=3: `close(eff+2)/close(eff-1)-1` (효과일 당일 포함 3세션) | N`reaction_math.py:L158-L181` |
| 5 | 변동성 | 효과일 직전까지 60거래일 일수익률의 표본 표준편차(n-1), 20개 미만이면 사용 불가 | N`reaction_math.py:L72-L73`, `L184-L211` |
| 6 | z 점수 | `z1 = r1/sd`, `z3 = r3/(sd*sqrt(3))` | N`reaction_math.py:L217-L233` |
| 7 | 방향 보정 | CROWDED_LONG은 부호 유지, CROWDED_SHORT는 부호 반전 -> 양수 = 군중에게 유리한 방향 | N`reaction_math.py:L236-L245` |
| 8 | 이벤트 분류 | 보정 z3 >= +0.5 RESPONDED(호재 먹힘), <= -0.5 OPPOSITE(역행), 그 사이 FAILED_TO_RESPOND | N`reaction_math.py:L34`, `L257-L269` |
| 9 | 독립성 가드(클러스터링) | 효과일 인덱스 기준 3거래일 창이 겹치는 이벤트는 구간 병합(전이적)하여 1건으로 셈; 클러스터 z3 = 가장 이른 멤버의 z3(평균 아님) | N`reaction_math.py:L82`, `L275-L332` |
| 10 | 집계 | `n`=클러스터 수, `mean_z3 = 평균(보정 z3)`, `drift_stat = sqrt(n) * mean_z3`, `responded_ratio = RESPONDED 클러스터 수 / n` | N`reaction_math.py:L427-L433` |
| 11 | 판정 | n < 3 -> INSUFFICIENT_EVIDENCE; `drift_stat <= -1.45` AND `responded_ratio <= 0.25` -> CONFIRMED; `drift_stat >= +1.45` OR `responded_ratio >= 0.5` -> NOT_CONFIRMED(market_rewarded_crowd); 그 외 NOT_CONFIRMED(mixed) | N`reaction_math.py:L57`, `L61`, `L355-L361` |
| 12 | 신뢰도 | CONFIRMED AND `drift_stat <= -1.645` AND n >= 4 AND OPPOSITE 클러스터 >= 1이면 HIGH, 아니면 MEDIUM (LOW는 미사용) | N`reaction_math.py:L65`, `L364-L376` |
| 13 | 임계값 근거 | drift_z 1.45는 iid 잡음 하에서 CONFIRMED 오탐률 < 8%(n=3,4,5,8; 최악 약 7.3%), ρ=0.1 AR(1)에서 < 10%, ρ=0.3에서 10.8-13.1%; 엄격히는 `--drift-z 1.75` | N`reaction_math.py:L36-L56` |
| 14 | 실패 종료(fail-closed) 조건 | 감지기 보고서 NEUTRAL, 심볼 누락, 데이터 vintage 10일 초과/미래/누락, 가격 소스 없음, 이벤트 없음 -> INSUFFICIENT_EVIDENCE (예외 대신 항상 종료코드 0) | `SKILL.md:L53-L62`, `L130-L138` |

**점수·등급**: 점수 없음. 3값 판정(CONFIRMED/NOT_CONFIRMED/INSUFFICIENT_EVIDENCE) + 신뢰도 MEDIUM/HIGH. 상위 `actual_reaction` 라벨: FAILED_TO_RALLY/FAILED_TO_SELL_OFF/RALLIED/SOLD_OFF/MIXED_REACTION/NO_DATA (N`reaction_math.py:L379-L394`).

**출력 형식**: `nrf_<symbol>_<as-of>.json/.md` (verdict, confidence, aggregate{mean_z3, drift_stat, responded_ratio}, evidence[], dropped_events[], run_context). 게이트용 핸드오프 블록 `{"news_failure": {"verdict", "confidence", "report_path"}}` (`SKILL.md:L121-L126`, `L136-L145`).

**SKILL.md와 코드 차이**: 큰 불일치 없음. 수식은 코드와 일치(rationale 주석까지 확인). 다만 [차이] 문서는 "contrarian-setup-gate(#241, not yet built)"라 하나 저장소에 해당 스킬이 있음(아래 절). 가장 큰 구조적 약점은 이벤트 자체가 Claude의 웹검색 수작업 큐레이션이라 코드로 재현 불가한 비결정 입력이라는 점.

**한국 시장 적용**
- 핵심 계산(규칙 3-12)은 종목 일봉 종가만 있으면 결정론적. 이벤트 소스를 OpenDART 공시 목록(공급계약, 잠정실적, 자사주 취득 등)의 `rcept_dt`/접수시각 + 공시 유형 -> BULLISH/BEARISH 분류표(룰 기반)로 자동화하면 "정성 큐레이션" 약점을 제거 [추정].
- 효과일 규칙(16시 이후 -> 다음 날)을 한국에 맞추면 15:30 이후 공시는 다음 거래일로 이월(시간외 단일가 16:00~18:00 반응은 종가 기준 일봉에는 잡히지 않음) [추정].
- 사용자가 원한 "호재에도 안 오름"은 `표류 통계 <= -1.45 AND 반응비율 <= 25%`로 구현. 롱 보유 종목에서 호재 공시 3건 이상(클러스터 후)인데 확정되면 신규 진입 금지/부분 청산 신호로 사용. "악재에도 안 빠짐"은 CROWDED_SHORT 측으로 대칭 적용(역방향 부호 반전)해 하방 경직(바닥 신호) 판정에 사용 가능 [추정].
- 한국 개별 종목의 일일 변동성이 크고 가격제한이 있으므로 60일 표준편차 정규화는 그대로 유효. 상한가/하한가 날은 변동성 왜곡 -> 해당일 z 계산에서 제외 또는 클립 필요 [추정].
- 표본 부족 문제: 개별 종목은 10일 내 독립 이벤트 3건(클러스터 후)을 채우기 어려움. 지수/업종 단위(예: KOSPI200, 반도체 업종 지수 + 시장 전체 뉴스)에서 쓰거나 창을 확대(20~30일)하고 n 하한 완화는 오탐률 재산정 필요 [추정].

### contrarian-setup-gate — 역발상 셋업 게이트 (fail-closed 상태 머신)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Jason Shapiro의 3단계 역발상 프로세스(COT 쏠림 -> 뉴스 반응 실패 -> 주봉 가격행동 확인)의 결과를 하나의 `setup_status`로 합성하는 순수 오프라인 게이트 (`skills/contrarian-setup-gate/SKILL.md:L3`, `L8-L10`) |
| 분류 | 주: 게이트/상태머신 설계 참고(자체 계산 없음, 검증과 우선순위만). 입력 3종은 각각 (c) 시장 폭·거시(COT), (c) 뉴스, (a) 주봉 |
| 필요 데이터 | 없음(네트워크·API 키 불필요). 입력 = cot-contrarian-detector JSON(필수), news-reaction-failure JSON(선택), technical-analyst 가격행동 JSON(선택) |
| 주요 파일 | G=`skills/contrarian-setup-gate/`: G`references/gate-decision-table.md`(권위 명세), G`scripts/gate_logic.py`, G`scripts/run_contrarian_setup_gate.py` |
| 라이선스 | MIT |
| 이식 판단 | 채택(설계 패턴): "단계별 선(先)확정" 우선순위 + 입력별 INVALID 격리 + 신선도 검증 + 신뢰도 최약 연결. 엔진 위치: 리스크 게이트 / 위원회 합의 단계(관점별 상태 -> 최종 상태). 코드 그대로는 COT 전용이므로 상태 모델만 이식 |

**규칙·계산식(상태·전이)**
| # | 규칙 | 내용 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 입력 상태 5종 | CONFIRMED / NOT_CONFIRMED / INSUFFICIENT / PENDING(보고서 미제공) / INVALID(제공됐으나 사용불가). 쏠림(C)은 PENDING 불가(항상 필수) | G`references/gate-decision-table.md:L5`; G`scripts/gate_logic.py:L86-L90` |
| 2 | 출력 상태 6종 | INSUFFICIENT_EVIDENCE, REJECTED, CROWDED, WATCHING_PRICE, READY_FOR_PLAN (+ 코드상 진행 단계) | G`scripts/gate_logic.py:L921-L990` |
| 3 | 1단계(쏠림, 단독·최우선) | C가 INVALID/INSUFFICIENT -> INSUFFICIENT_EVIDENCE; NOT_CONFIRMED(NEUTRAL) -> REJECTED (N/P는 열어보지도 않음); CONFIRMED -> 계속 | G`scripts/gate_logic.py:L921-L932` |
| 4 | 2단계(뉴스) | PENDING이 아니면 4방향 정산: INVALID -> INSUFFICIENT_EVIDENCE, NOT_CONFIRMED -> REJECTED, INSUFFICIENT -> INSUFFICIENT_EVIDENCE, CONFIRMED -> 3단계. 뉴스가 CONFIRMED가 되기 전엔 가격행동을 아예 검사하지 않음 | G`scripts/gate_logic.py:L935-L962` |
| 5 | 3단계(가격행동) | 뉴스 CONFIRMED 후: PENDING -> WATCHING_PRICE; 같은 4방향 정산; CONFIRMED -> READY_FOR_PLAN | G`scripts/gate_logic.py:L963-L973` |
| 6 | 순서 이탈 사용 | 뉴스 PENDING + 가격행동 제공: 가격행동 CONFIRMED여도 CROWDED로 상한(경고 `out_of_order_price_action`); INVALID/NOT_CONFIRMED/INSUFFICIENT는 정상 정산; 둘 다 PENDING이면 CROWDED | G`scripts/gate_logic.py:L975-L990` |
| 7 | "연화 금지" 원칙 | 앞 단계가 확정(REJECTED/INSUFFICIENT)이면 뒤 단계의 문제(손상 파일 등)가 그 결과를 완화하지 못함. 예: C=CONFIRMED, N=NOT_CONFIRMED, P=INVALID -> REJECTED(INSUFFICIENT 아님). v3의 "N,P 묶음 평가" 오류를 v4에서 수정 | G`references/gate-decision-table.md:L9-L11`, `L57` |
| 8 | 입력 일관성(입력 단위 INVALID) | 심볼 불일치, 방향 불일치(보고서 `direction` != 감지기 분류, 단 null은 불일치 아님), 스키마 major != 1 -> 그 입력만 INVALID (전역 오버라이드 아님) | G`references/gate-decision-table.md:L62-L70` |
| 9 | 신선도 | 감지기 `data_date` 최대 10일, 뉴스/가격행동 `run_context.as_of` 최대 7일; 미래 날짜/누락/비문자/파싱불가는 INVALID; 만료 2일 이내 접근 시 `<input>_near_stale` 경고(상태 불변) | G`scripts/run_contrarian_setup_gate.py:L186-L187`; G`scripts/gate_logic.py:L116`, `L221-L250` |
| 10 | 신뢰도 | `gate_confidence` = 뉴스·가격행동 신뢰도 중 약한 쪽(HIGH 3 > MEDIUM 2 > LOW 1); MEDIUM이면 경고만 추가 | G`scripts/gate_logic.py:L111-L112`, `L993-L997`, `L1019-L1021`, `L1043-L1047` |
| 11 | 실행 가능 조건(불변식) | READY_FOR_PLAN이면 `entry_trigger`는 비어 있지 않은 문자열, `invalidation_level`은 유한 양수(손절 기준)여야 함, 아니면 INVALID(`price_action_missing/invalid_stop_reference`), 이중 assert | G`scripts/gate_logic.py:L1019-L1037`; G`references/gate-decision-table.md:L114-L118` |
| 12 | 가격행동 근거 허용목록 | CONFIRMED 사유는 {key_reversal, failed_extreme, failed_breakout}만 허용(주봉 키리버설/실패한 극단/실패한 돌파) | G`scripts/gate_logic.py:L120-L137` |
| 13 | 방향 매핑 | CROWDED_LONG -> 역발상 SHORT, CROWDED_SHORT -> 역발상 LONG (거부돼도 감사용으로 방향 유지) | G`scripts/gate_logic.py:L99`, `L1014` |
| 14 | 견고성 | 전체 파일 비유한수(inf/nan) 스캔, 반복형 탐색, 항상 종료코드 0 + 보고서 작성 | G`references/gate-decision-table.md:L120-L128` |

**점수·등급**: 점수 없음. 상태 5종 + 신뢰도(HIGH/MEDIUM/LOW) + 경고 목록. 125개 조합 전수 단위테스트가 명세 (G`references/gate-decision-table.md:L26`).

**출력 형식**: JSON `{schema_version, symbol, setup_status, direction, gate_confidence, entry_trigger, invalidation_level, missing_confirmations[{step,state,reason}], warnings[], inputs{crowding,news_failure,price_action}(감사), run_context}` (G`scripts/gate_logic.py:L1049-L1072`).

**SKILL.md와 코드 차이**: 큰 불일치 없음. 상태표(문서 L28-L44)와 `decide_setup_status`(코드 L921-L990)는 줄 단위로 일치. 단 상태 이름이 문서 "Precedence Rules"와 코드에서 모두 쓰이는 `CROWDED`는 외부에 나가는 "REJECTED/INSUFFICIENT"와 달리 단계 진행 중 상태(= 대기)로 사실상 "진행 중" 표현.

**한국 시장 적용**
- 상태머신 자체는 시장 중립적. 한국판 매핑 [추정]: C(쏠림) -> 위원회의 "과열/쏠림" 관점(과열 점수, 외국인·기관·개인 수급 극단), N(뉴스 실패) -> "재료 반응 실패" 관점, P(가격행동) -> "일/주봉 반전 확인" 관점. 단계별 선확정 규칙으로 앞 관점이 REJECTED면 뒤 관점을 평가하지 않음(연산 절약 + 감사 용이).
- 가져갈 핵심 4가지: (1) INSUFFICIENT/INVALID와 NOT_CONFIRMED를 구분(데이터 부족 시 매매 안 함, 반대 증거와 구별), (2) 입력 신선도(일수) 제한 + near-stale 경고, (3) 신뢰도는 최약 고리, (4) 실행 가능 상태는 반드시 `entry_trigger`+`invalidation_level`을 동반(손절 없는 신호는 무효).
- 한국 롱 온리 엔진에는 "REJECTED/INSUFFICIENT_EVIDENCE -> 신규 진입 금지, READY_FOR_PLAN(역방향=롱 반전 확인)일 때만 진입 후보"로 번안. 입력이 모두 결정론적 일봉/수급 지표이면 PENDING 상태는 불필요(항상 계산 가능).

### cot-contrarian-detector — COT 역발상 쏠림 탐지기
| 항목 | 내용 |
|---|---|
| 기법·출처 | Jason Shapiro 5단계 중 1단계(투기 세력 순포지션의 3년 극단 탐지). 출처: Schwager, Unknown Market Wizards(2020) 2장, crowdedmarketreport.com (`skills/cot-contrarian-detector/references/shapiro-methodology.md:L144-L149`). COT Index는 "포지셔닝의 스토캐스틱" 정규 공식 (`references/cot-index-calculation.md:L5-L20`) |
| 분류 | 주: (c) 시장 폭·거시(선물 투자자별 포지션). 일봉 불필요 |
| 필요 데이터 | FMP `stable/commitment-of-traders-*`(CFTC Legacy 비상업 롱/숏, 건수, 미결제약정), `FMP_API_KEY` 필수, 매주 화요일 기준, 금요일 약 15:30 ET 공표 (`references/shapiro-methodology.md:L119-L125`; C=`skills/cot-contrarian-detector/scripts/` C`screen_cot_crowding.py:L66-L79`) |
| 주요 파일 | C`cot_index.py`(순수 계산 100줄), C`screen_cot_crowding.py`, `references/{cot-index-calculation,shapiro-methodology,output-contract}.md` |
| 라이선스 | MIT. 단 CFTC 데이터는 FMP 경유 |
| 이식 판단 | 부분 채택(수식만): COT Index와 90/10 임계 구조를 KRX 투자자별 순매수/선물 포지션 시계열에 적용. 엔진 위치: 위원회 "수급 쏠림" 관점 / 레짐 필터. 미국 COT 자체는 보류 |

**규칙·계산식** (C = `skills/cot-contrarian-detector/scripts/`)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 순포지션 | `net = noncommPositionsLongAll - noncommPositionsShortAll` (결측 0) | C`cot_index.py:L13-L21` |
| 2 | COT Index | `(현재 net - 창 최소) / (창 최대 - 창 최소) * 100`, 창 = 최근 156주(현재 주 포함); 이력 < 156주 또는 max == min이면 None(스킵) | C`cot_index.py:L24-L39`; C`screen_cot_crowding.py:L572-L574` |
| 3 | 보조 지수 | 같은 식, 26주 창(문맥용). 26주 미만 이력이면 스킵 | C`screen_cot_crowding.py:L224-L233`, `L252`, `L575-L579` |
| 4 | 분류 | index >= 90 -> CROWDED_LONG, <= 10 -> CROWDED_SHORT, 그 외 NEUTRAL (경계 포함, None -> NEUTRAL) | C`cot_index.py:L57-L73`; C`screen_cot_crowding.py:L581-L586` |
| 5 | 극단도 | `extremity = abs(index - 50)` 로 정렬 | C`screen_cot_crowding.py:L275`, `L665` |
| 6 | 부가 지표 | OI 정규화 순포지션 `net/openInterest`, 전주 대비 변화 `net[-1]-net[-2]`, 롱/숏 트레이더 수, 상위 10 주간 급변동 | C`cot_index.py:L42-L54`, `L93-L100`; C`screen_cot_crowding.py:L86`, `L264-L273` |
| 7 | 임계 민감도(문서) | 80/20로 완화하면 표시 시장 수 약 2배·거짓양성 증가, 95/5는 고신뢰·소수 | `references/cot-index-calculation.md:L56-L65` |
| 8 | 데이터 정리 | 날짜 오름차순, 중복일은 마지막 행 우선, 날짜 없는 행 제외; 모든 시장은 결과 또는 skipped 사유 중 하나로 반드시 기록 | C`cot_index.py:L76-L90`; C`screen_cot_crowding.py:L202-L204` |
| 9 | 기본 유니버스 | 핵심 23종목(ES, NQ, YM, QR, VX, ZT/ZF/ZN/ZB, DX, 주요 FX, GC/SI/HG/PL, CL/NG, BT) | C`screen_cot_crowding.py:L72-L79` |
| 10 | 공표 지연 | 화요일 기준 데이터가 금요일 공표 -> 최소 3일, 최대 9일 지연; 뉴스 확인은 화요일 전후를 봐야 함 | `references/shapiro-methodology.md:L119-L132` |
| 11 | Shapiro 3-5단계(수동, 문서) | 3: 주봉 가격행동 확인(신고/신저 실패, 주봉 반전 캔들, 추세선·이평 이탈). 4: 쏠림 방향 반대로 진입, 손절은 군중이 만든 스윙 극단. 5: COT Index가 50 쪽으로 정상화 또는 손절 시 청산, 고정 목표 없음 | `references/shapiro-methodology.md:L73-L107` |

**점수·등급**: 점수 없음. 3분류(CROWDED_LONG/CROWDED_SHORT/NEUTRAL) + `extremity`. (게이트에서 최약 연결 신뢰도는 뉴스/가격행동 쪽에서만 산출.)

**출력 형식**: `cot_crowding_<날짜>.json/.md` — `markets[]`(심볼별 cot_index_3y/short, classification, extremity, net_position, oi_normalized_net, data_date, 트레이더 수), `skipped[]`(사유), `run_context`(data_date), `data_provenance`(시장별 vintage) (C`screen_cot_crowding.py:L304-L390`; `SKILL.md:L117`).

**SKILL.md와 코드 차이**: 큰 불일치 없음(수식과 임계 일치). 문서가 인정하듯 2-5단계는 자동화 안 됨(`references/shapiro-methodology.md:L15-L17`).

**한국 시장 적용 [추정 포함]**
- 한국 대체 데이터:
  - KRX 정보데이터시스템의 투자자별 매매동향(코스피/코스닥 외국인·기관·개인 일별 순매수 금액·수량) — 일 단위 공표, 약 20분~익일 이내로 CFTC보다 지연이 훨씬 짧음 [추정].
  - KOSPI200 선물·옵션 투자자별 거래 및 미결제약정 통계(외국인/기관/개인 선물 순매수 누적 포지션) — COT의 "비상업 순포지션"에 가장 가까운 대응. 정확한 공표 지표(순매수 거래량 vs 미결제약정 잔량)는 KRX 통계 화면에서 확인 필요 [추정].
  - 종목 단위: 외국인 보유 비중(지분율) 시계열, 공매도 잔고 비중, 신용잔고율(금융투자협회/KRX) [추정].
- 이식 수식: `index = (현재 - 창 최소) / (창 최대 - 창 최소) * 100`(스토캐스틱형)을 외국인 누적 순매수 또는 선물 순포지션에 적용. 한국에서 3년(156주)=약 750거래일 창 가능. 임계 90/10은 그대로 두고 시장별 거짓양성률을 백테스트로 재측정 [추정]. 거래량·미결제약정으로 정규화(규칙 6)하면 시장 크기 변화 보정.
- 역발상 번안: 롱 전용이므로 CROWDED_LONG(외국인/기관 쏠림 정점)은 "신규 매수 금지·분할 청산" 신호, CROWDED_SHORT(공매도 잔고/선물 순매도 극단)은 "저가 매수 후보 대기" 신호 [추정].
- 주의: 한국은 외국인 매매를 투기 세력으로 단정하기 어렵고(패시브 자금, 지수 추종 포함), 연기금·기관 구조가 달라 "비상업=투기" 가정이 약함 [추정]. 일별 시계열은 월/분기말·옵션 만기(둘째 목요일)·MSCI 리밸런싱에 왜곡되므로 해당 일 플래그 필요.

#### 그룹 소결
이식할 규칙 6개(우선순위순). 근거는 위 각 절의 줄 참조.
1. **과열(포물선) 점수식** — 일봉만으로 계산: 5일 수익률 `linear(20%,100%)`, 20일선 이격 `0.5*linear(pct,20,120)+0.5*linear(ATR단위,3,10)`, 거래량비 `linear(1.5,5.0)`, 5일/직전20일 TR비 `linear(1.2,3.0)`, 유동성 로그척도; 가중 30/25/20/15/10, 등급 A>=85/B>=70/C>=50. 하드 게이트 5일 >= +30%, 20일선 이격 >= 25% 및 >= 4 ATR (`skills/parabolic-short-trade-planner/scripts/parabolic_scorer.py:L10-L35`, `calculators/parabolic_score_calculator.py:L27-L71`, `screen_parabolic.py:L304-L331`). 한국에서는 "보유분 청산·신규 진입 금지" 역발상 과열 관점으로 번안, +-30% 가격제한·상한가 잠김 보정 필요. 위원회 역발상 점수기 + 진입 리스크 게이트.
2. **실적 이벤트 -> 주봉 눌림 돌파 상태머신** — 갭 >= 3%(5/7/10% 단계 점수), 실적 후 5주 감시, 첫 `close<open` 주봉 고가 돌파(양봉 종가 > 빨간 봉 고가, 거래량 > 직전 4주 평균) 진입, 손절 빨간 봉 저가, 목표 2R. 단 R:R 성분은 상수라 폐기, 갭은 부호 포함으로 수정 (`skills/pead-screener/scripts/calculators/weekly_candle_calculator.py:L262-L287`, `screen_pead.py:L240-L285`, `risk_reward_calculator.py:L63`). OpenDART 잠정실적 접수일을 이벤트일로. 진입 트리거 + 위원회 이벤트 모멘텀.
3. **실적 반응 5요인 점수** — 갭 25%(1/3/5/7/10% -> 35/55/70/85/100) + 실적 전 20일 수익률 30% + 20/60일 거래량비 20% + MA200 15% + MA50 10%, 등급 A>=85/B>=70/C>=55 (`skills/earnings-trade-analyzer/scripts/scorer.py:L22-L35`). 갭 방향 부호 반영 필수. 필터 "갭>=10% AND 점수>=85 제외"(자체 데이터로 재검증). 위원회 점수기 + 사후 분석.
4. **뉴스 무반응 판정(표류 통계)** — 이벤트 효과일 정렬(마감 후는 다음 거래일), 3일 수익률 `z3 = r3/(sd60*sqrt(3))`, 3거래일 겹침 이벤트 클러스터링, `drift_stat = sqrt(n)*mean(z3_adj)`; CONFIRMED는 `drift_stat <= -1.45 AND 반응비율 <= 25%`, n >= 3 미만은 INSUFFICIENT (`skills/news-reaction-failure-analyzer/scripts/reaction_math.py:L34-L65`, `L355-L361`). 오탐률 < 8% 몬테카를로 검증이 근거. 공시 이벤트 자동화로 사후 분석/청산 가속에 사용.
5. **fail-closed 순차 게이트** — 단계별 선확정(C -> N -> P), 앞 단계 REJECTED/INSUFFICIENT는 뒤 단계 오류로 완화 불가, INVALID는 입력 단위 격리, 신선도 10일/7일 + 만료 임박 2일 경고, 신뢰도 최약 고리, 실행 가능 상태엔 `entry_trigger`+양의 `invalidation_level` 필수 (`skills/contrarian-setup-gate/scripts/gate_logic.py:L921-L990`, `L1019-L1037`; `references/gate-decision-table.md:L9-L22`). 위원회 합의 -> 리스크 게이트 구조에 이식.
6. **COT 스토캐스틱 지수 + 90/10 분류** — `(현재-최소)/(최대-최소)*100`, 156주, >= 90 쏠림 롱 / <= 10 쏠림 숏 (`skills/cot-contrarian-detector/scripts/cot_index.py:L24-L73`). KRX 투자자별 순매수·KOSPI200 선물 미결제약정에 적용(데이터 가용성 확인 필요 [추정]).


---

## 16. 리스크 관리·매매 규율·기록 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, MIT) · 범위: position-sizer, drawdown-circuit-breaker, pre-trade-discipline-gate, data-quality-checker, portfolio-manager, trade-performance-coach, signal-postmortem, weekly-performance-digest, trader-memory-core, futures-position-sizer

### position-sizer — 포지션 사이저
| 항목 | 내용 |
|---|---|
| 기법·출처 | Fixed Fractional(Minervini 권장 범위 0.5~1% 인용), ATR 스톱 사이징, Kelly(J.L. Kelly 1956, half-Kelly) — skills/position-sizer/references/sizing_methodologies.md:L31-L37, L145-L190 |
| 분류 | (a) 계좌·체결 기록만 필요 (순수 계산, 시세 불필요; ATR 값은 입력으로 받음) |
| 필요 데이터 | 계좌 평가액, 진입가, 손절가 또는 ATR, (Kelly) 승률·평균손익, 섹터·현재 섹터 노출. API 키 불필요, 표준 라이브러리만 |
| 주요 파일 | skills/position-sizer/scripts/position_sizer.py (581줄), SKILL.md, references/sizing_methodologies.md |
| 라이선스 | MIT (저장소 루트) |
| 이식 판단 | 채택 — 사이징 모듈의 핵심. 단 반올림·호가·세금 보정 추가 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 고정비율 위험 | risk_per_share = entry - stop; dollar_risk = equity * risk_pct/100; shares = floor(dollar_risk / risk_per_share) | skills/position-sizer/scripts/position_sizer.py:L108-L126 |
| 2 | ATR 사이징 | stop_distance = ATR * mult (기본 mult 2.0); stop = entry - stop_distance; shares = floor(equity*risk%/stop_distance) | position_sizer.py:L128-L148, L444 |
| 3 | Kelly | R = avg_win/avg_loss; kelly = W - (1-W)/R; 음수면 0 하한; half = kelly/2 | position_sizer.py:L151-L168 |
| 4 | Kelly 예산 모드 (진입가 없음) | risk_budget = equity * half_kelly_pct/100, 주식 수 미산출 | position_sizer.py:L254-L267 |
| 5 | Kelly 주식 모드 | budget = equity*half_kelly%; stop 있으면 shares=floor(budget/(entry-stop)), 없으면 floor(budget/entry) (전액 투입, 위험 미정의 -> risk 필드 None) | position_sizer.py:L286-L297, L329-L346 |
| 6 | 최대 종목 비중 | max_by_pos = floor(equity*max_position_pct/100/entry) | position_sizer.py:L171-L202 |
| 7 | 최대 섹터 비중 | remaining = (max_sector_pct - current_sector_exposure)/100*equity; max_by_sector = max(0, floor(remaining/entry)) | position_sizer.py:L204-L221 |
| 8 | 최종 = 가장 엄격한 제약 | final = max(0, min(risk_shares, max_by_pos, max_by_sector)); final<risk_shares인 제약이 binding | position_sizer.py:L223-L229 |
| 9 | 반올림 | 정수 주식은 항상 내림(int), 소수 주식은 지정 자릿수(기본 4, 0~8)로 ROUND_FLOOR; 위험 금액 보고만 ROUND_HALF_UP | position_sizer.py:L96-L105, L328-L346 |
| 10 | 입력 검증 | 비유한값 거부, stop<entry 필수(롱 전용), win_rate는 0<W<1 열린구간, risk-pct와 Kelly 동시 지정 금지 | position_sizer.py:L56-L88, L504-L520 |
| 11 | 문서상 가이드 | 위험 0.25~0.5 보수, 0.5~1 숙련 스윙, 1~1.5 검증된 시스템, 1.5~2 상한, >2 위험; 총 오픈리스크(포트폴리오 히트) 6~8% 상한; 종목 5~10%, 섹터 25~30%; 연패 후 0.5%로 축소; 하드 손절 7~8% | references/sizing_methodologies.md:L31-L37, L82-L89, L232-L233, L293-L299 |
| 12 | 손실-회복 표 | 손실 10/20/30/50% -> 필요 이익 11.1/25/42.9/100% | references/sizing_methodologies.md:L332-L335 |

**출력 형식**: JSON(schema_version 1.0; mode=shares|budget, calculations{fixed_fractional,atr_based,kelly}, constraints_applied[], final_recommended_shares, final_position_value, final_risk_dollars, final_risk_pct, binding_constraint)와 동명 .md 리포트. SKILL.md:L108-L140 부근.

**SKILL.md와 코드 차이**: [차이] SKILL.md는 "기본 1% 위험"이라 하나 코드에서 --risk-pct는 기본값이 없고 필수(risk-pct 또는 win-rate 중 하나 필수; position_sizer.py:L509-L520). [차이] "포트폴리오 히트 6~8%"는 문서 원칙뿐이고 코드에 계산·검사 없음(단일 종목 계산만). ATR과 --stop 동시 지정 시 stop은 무시(ATR 우선, SKILL.md Output Format 절 명시).

**한국 시장 적용**: 정수 주식(1주 최소)·내림 그대로 적합. 추가 필요: (1) 수수료·거래세(매도 약 0.2% [추정, 확인 필요])를 손실에 포함해 risk_per_share = (entry - stop) + 왕복 비용/주; (2) 호가단위로 stop·entry 정렬; (3) 갭 하락 최악 손실은 stop이 아니라 전일 종가*(1-0.30) 또는 시초 갭 가정으로 별도 상한 [추정]; (4) 롱 전용이므로 공매도 불가 시장과 일치; (5) 현금 계좌라 레버리지 없음 -> 포지션 가치 <= 가용현금 제약 추가.

### drawdown-circuit-breaker — 드로다운 서킷브레이커
| 항목 | 내용 |
|---|---|
| 기법·출처 | 계좌 수준 실현손익 한도(일·주·월) + 연속 손실 쿨다운. 특정 원저자 인용 없음(자체 설계). market-side exposure-coach의 짝 — skills/drawdown-circuit-breaker/references/circuit_breaker_framework.md:L5-L7 |
| 분류 | (a) 계좌·체결 기록만 필요 (시세·유료 API 불필요) |
| 필요 데이터 | trader-memory-core의 thesis YAML(status_history[].realized_pnl/at, status, exit.actual_date, outcome.pnl_dollars) + account_size(CLI 입력, 고정값). _index.json은 P&L에 사용 금지 — framework.md:L11-L21 |
| 주요 파일 | skills/drawdown-circuit-breaker/scripts/check_circuit_breaker.py (858줄), scripts/_market_calendar.py(XNYS 세션 계산), references/circuit_breaker_framework.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 리스크 게이트(신규 진입 차단). 단 아래 약점 보완 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 설정 기본값 | max_daily_loss_pct=2.0, losing_streak_n=2, cooldown_hours=24.0, weekly_drawdown_pct=5.0, monthly_drawdown_pct=8.0 (CLI 또는 JSON config, CLI 우선) | scripts/check_circuit_breaker.py:L52-L57; framework.md:L65-L77 |
| 2 | 임계값 금액화 | threshold = account_size * pct/100 (양의 유한값 아니면 예외). account_size는 고정 입력이라 자기자본 곡선 연동 없음 | check_circuit_breaker.py:L157-L162 |
| 3 | 일 손실 한도 | realized_today <= -(account*2.0%) -> HALTED, active_until = 다음 거래일 0시(ET) | check_circuit_breaker.py:L610-L627 |
| 4 | 연속 손실 쿨다운 | 최근 종결 건을 역순으로 pnl>=0 만나면 중단, 연속 음수 개수 >= N(2)이고 now < 마지막 손실 청산시각+24h -> COOLDOWN. 본전(0)은 승으로 취급 | check_circuit_breaker.py:L547-L556, L630-L644; framework.md:L48-L50 |
| 5 | 주간 한도 | week-to-date(월요일 ET~as_of) 실현손익 <= -(account*5.0%) -> HALTED, 다음 주 첫 거래일까지 | check_circuit_breaker.py:L586-L587, L647-L663 |
| 6 | 월간 한도 | month-to-date(1일~as_of) <= -(account*8.0%) -> HALTED, 다음 달 첫 거래일까지 | check_circuit_breaker.py:L588, L666-L682 |
| 7 | 합성 | 여러 규칙 발동 시 최엄격 상태(HALTED > COOLDOWN > TRADING_ALLOWED), 발동 규칙은 전부 JSON에 기록 | check_circuit_breaker.py:L42, L696-L700; framework.md:L52-L58 |
| 8 | 해제(재개) 조건 | 시간 경과로만 해제(active_until 이후 자동 재평가). 상태 저장 없이 매 호출 전체 재계산(stateless). 수동 해제·단계적 노출 축소/재개 개념 없음 | check_circuit_breaker.py:L559-L738 (저장 로직 없음, write_reports는 리포트만 L788) |
| 9 | 데이터 불완전 시 fail-closed | 중복 thesis_id, 깨진 ledger, 비유한 P&L, ledger-outcome 불일치 등 -> data_quality=PARTIAL + incomplete_state_data 규칙(HALTED, active_until=null: 수리 후 재실행까지). 상태 디렉터리 없음/비어있음은 EMPTY_STATE -> TRADING_ALLOWED | check_circuit_breaker.py:L118-L121, L683-L695; framework.md:L60-L63 |
| 10 | 손익 원천 | 실현손익 ledger(부분 청산 포함, status_history[].realized_pnl)를 일/주/월 집계에 사용; 종결 승패는 outcome.pnl_dollars. 불일치 허용오차 $0.01, 불일치 시 ledger 우선 | check_circuit_breaker.py:L499-L513, L353-L438(특히 L411-L417) |
| 11 | 달력 | 모든 집계는 America/New_York 날짜. 휴장일은 XNYS 캘린더(pandas_market_calendars류 공급자)로 건너뜀. 의존성 없으면 exit 2 | check_circuit_breaker.py:L38, L516-L536, L836-L840; _market_calendar.py:L102-L125 |
| 12 | 워크플로 계약 | circuit_breaker_decision.recommendation == TRADING_ALLOWED 일 때만 후보 생성 진행. COOLDOWN/HALTED는 신규 진입만 막고 기존 포지션 청산·브로커 조치는 강제 안 함 | framework.md:L90-L99 |

**출력 형식**: JSON(schema_version 1.0, as_of_date, recommendation, triggered_rules[{rule, threshold, observed, active_until, detail}], metrics{realized_pnl_today/wtd/mtd, consecutive_losses, last_loss_exit_at, theses_scanned}, account_size, config, data_quality, warnings, rationale) + Markdown. check_circuit_breaker.py:L719-L738. 종료코드 0/1/2.

**SKILL.md와 코드 차이**: 큰 차이 없음(SKILL은 "권고 도구이며 브로커 차단 아님"이라 명시, SKILL.md:L9-L11). [차이 아님, 한계] 실현손익만 집계하므로 미실현 손실(보유 중 급락)은 한도에 반영되지 않음; account_size가 고정 입력이라 드로다운이 고점 대비 낙폭이 아니라 기준 자본 대비 일/주/월 합계; "노출 단계적 축소"(예: 50%로 축소 후 재개) 기능은 없고 이진(허용/차단) 게이트.

**한국 시장 적용**: 엔진 이식 시 (1) 일 경계를 Asia/Seoul·KRX 거래일로 교체, XNYS 캘린더 대체(KRX 휴장일); (2) 손익에 거래세·수수료 반영한 순실현손익 사용; (3) 미실현손익 포함 일중 평가손(mark-to-market, 일봉 종가 기준) 한도 추가 권장 [추정]; (4) 상태는 DB(SQLite 등)로 영속, 파일 YAML 스캔 대신 거래 원장 테이블 집계; (5) 단계적 규칙 제안: 일 -2% 신규 진입 중단 / 2연패 24h 쿨다운(일봉 엔진에서는 "다음 거래일 1회 건너뜀"으로 환산) / 주 -5% / 월 -8% 중단 후 사이즈 50% 재개 [추정, 원 코드엔 없음]; (6) 하한가 잠김으로 손절 미체결이면 실현손익이 나중에 한꺼번에 반영되므로 평가손익 기준 보조 한도 필요 [추정].

### pre-trade-discipline-gate — 진입 전 규율 게이트
| 항목 | 내용 |
|---|---|
| 기법·출처 | 수동 주문 직전 체크리스트(계획 내 진입·사전 손절·계획 내 사이즈·위험 초과 금지) + 복수매매(revenge) 방지 + 상위 게이트(시장 국면·서킷브레이커) 결과 종합. 원저자 인용 없음 |
| 분류 | (a) 계좌·체결 기록만 필요 (체크리스트 답변 + 상위 게이트 결과 JSON + thesis 손익 기록) |
| 필요 데이터 | answers-file(후보별 order_intent, entry_in_written_plan, stop_predefined, size_within_plan, planned/actual_risk_dollars), trader-memory-core 손실 기록, market_regime(exposure_decision) JSON, circuit_breaker_decision JSON |
| 주요 파일 | skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py (718줄), references/discipline_gate_framework.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 주문 직전 최종 리스크 게이트(결정론적 부분만). 체크리스트 항목은 자동매매에서 코드 불변식으로 치환 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 결정 등급 | GO(0) < NO_ACTIONABLE_ORDERS(1) < REVIEW_REQUIRED(2) < NO_GO(3); 후보 간 최댓값 | scripts/check_pre_trade_discipline.py:L44-L50, L385-L403 |
| 2 | 주문 대상 의도 | ENTRY_READY, ACTIONABLE, ACTIONABLE_DAY1, MANUAL_ORDER만 검사. WATCHLIST/DELAYED_EP_WATCH/PEAD_HANDOFF/IGNORE/REJECTED는 기록만(NO_ACTIONABLE_ORDERS); 알 수 없는 의도는 REVIEW_REQUIRED | check_pre_trade_discipline.py:L32-L33, L318-L346 |
| 3 | 계획 내 진입 | entry_in_written_plan is True 가 아니면 NO_GO (불리언 true만 인정, 문자열 "true"는 불인정) | check_pre_trade_discipline.py:L156-L157, L356-L357 |
| 4 | 사전 손절 | stop_predefined is True 아니면 NO_GO | check_pre_trade_discipline.py:L358-L359 |
| 5 | 계획 내 사이즈 | size_within_plan is True 아니면 NO_GO | check_pre_trade_discipline.py:L360-L361 |
| 6 | 위험 초과 | actual_risk_dollars > planned_risk_dollars -> NO_GO; 둘 중 하나가 없거나 음수/비유한/불리언이면 REVIEW_REQUIRED (0은 허용). Decimal 비교 | check_pre_trade_discipline.py:L363-L382, L160-L174 |
| 7 | 복수매매 창 | 최근 revenge_window_hours(기본 24.0) 내 음수 realized_pnl 이벤트(부분 청산 포함) 또는 종결 thesis의 outcome.pnl_dollars<0 가 있으면 모든 주문 후보 NO_GO | check_pre_trade_discipline.py:L220-L276, L664, L526-L533 |
| 8 | 시장 국면 | NEW_ENTRY_ALLOWED=통과; REDUCE_ONLY/CASH_PRIORITY=NO_GO; 그 외·누락·파일오류=REVIEW_REQUIRED (fail-safe) | check_pre_trade_discipline.py:L296-L305 |
| 9 | 서킷브레이커 | TRADING_ALLOWED=통과; COOLDOWN/HALTED/TRADING_HALTED=NO_GO; 그 외·누락=REVIEW_REQUIRED | check_pre_trade_discipline.py:L307-L316 |
| 10 | 감사 기록 | 모든 후보의 체크리스트 답변을 JSON·JSONL 저널에 보존(GO도 포함); --fail-on-non-go 시 종료코드 2 | framework.md:L52-L56; check_pre_trade_discipline.py:L641-L676 |

**출력 형식**: JSON(overall_decision, candidate_results[{symbol, thesis_id, intent, actionable, decision, reasons[], checklist_answers}], metrics, inputs, warnings, rationale) + Markdown + JSONL 저널. check_pre_trade_discipline.py:L536-L561.

**SKILL.md와 코드 차이**: 큰 차이 없음. 주의: 복수매매 창이 24h 고정이고 서킷브레이커의 24h 쿨다운과 사실상 중복(2연패 미만 1패만으로도 NO_GO가 됨 — 서킷브레이커보다 엄격).

**한국 시장 적용**: 일봉 엔진에서는 (1) 체크리스트 3종은 "주문 객체에 손절가·계획 위험액이 반드시 첨부" 불변식으로 대체; (2) actual_risk > planned_risk 검사는 호가단위 반올림·수수료·거래세 반영 후의 실제 위험으로 재계산 [추정]; (3) 복수매매 창은 "손절 청산 후 N 거래일 재진입 금지(동일 종목 쿨다운)"로 변환 가능 [추정]; (4) 상위 게이트 결과 미수신 시 REVIEW_REQUIRED=주문 보류 원칙(fail-safe)은 그대로 이식 가치 높음.

### data-quality-checker — 데이터 품질 검사기 (문서용)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 시장 분석 문서(마크다운 블로그·리포트)의 정적 텍스트 린트. 가격 스케일, 종목 표기, 날짜-요일, 배분 합계, 단위 5종. 영문·일문 지원 — skills/data-quality-checker/SKILL.md:L2-L12 |
| 분류 | 우리 용도에는 부적합 — 시계열 OHLCV 품질 검사가 아님. (d)에 가까움(문서 린트). 일부 발상만 차용 가능 |
| 필요 데이터 | 마크다운 파일 한 개. API 불필요, 표준 라이브러리만 |
| 주요 파일 | skills/data-quality-checker/scripts/check_data_quality.py (906줄), references/common_data_errors.md |
| 라이선스 | MIT |
| 이식 판단 | 보류(코드 이식 불필요). 일봉 데이터 품질(결측·이상치·분할 조정)은 이 스킬에 없음 -> 자체 설계 필요 |

**규칙·계산식** (문서 린트 규칙; 엔진 직접 가치는 낮음)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 가격 자릿수 휴리스틱 | 종목별 정수부 자릿수 허용범위(GLD 2-3, GC 3-4, SPY 2-3, SPX 4-5, VIX 1-2, TLT 2-3, SLV 2-2, SI 2-2, USO 2-2, CL 2-3) 벗어나면 WARNING | scripts/check_data_quality.py:L38-L49, L98-L115 |
| 2 | ETF/선물 비율 교차검증 | 기대 비율 futures/ETF: GLD-GC 15, SLV-SI 2.3, USO-CL 0.85, SPY-SPX 10; abs(실제-기대)/기대 > 0.5 이면 WARNING | check_data_quality.py:L53-L58, L117-L139 |
| 3 | 날짜-요일 불일치 | 영문/일문 표기 날짜의 명시 요일이 실제 weekday와 다르면 ERROR (연도 없으면 --as-of 로 추정) | check_data_quality.py:L306-L360, L257-L297 |
| 4 | 배분 합계 | 고정값 합계가 100%에서 0.5%p 초과 이탈 시 WARNING; 범위 표기는 [합 min, 합 max]가 [99.5,100.5]와 안 겹치면 WARNING; 값 2개 미만 섹션은 무시 | check_data_quality.py:L667-L700 |
| 5 | 단위 | bp와 % 혼용 INFO; 종목어+등락어가 있는 줄에 단위($,%,bp) 없는 숫자만 있으면 WARNING | check_data_quality.py:L724-L760 |
| 6 | 종료코드 | 항상 0(advisory), 스크립트 오류만 1 | check_data_quality.py:L888-L893 부근 (main 하단 주석 "Always exit 0 (advisory mode)") |

**출력 형식**: Finding(severity ERROR/WARNING/INFO, category, message, line_number, context) 목록을 심각도·줄 순으로 정렬한 마크다운 리포트(+JSON). check_data_quality.py:L22-L35, L799-L826.

**SKILL.md와 코드 차이**: 큰 차이 없음. 단 SKILL 이름·설명이 "데이터 품질"이지만 실제는 문서 텍스트 린트. 분할·배당 조정, 결측, 가격 이상치(급등락 점프) 검사는 코드에 없음 (grep 결과 해당 로직 없음).

**한국 시장 적용**: 코드 이식 가치 없음. 대신 자체 구현 권장 [추정]: (1) 일봉 결측 거래일(KRX 캘린더 대비), (2) 전일 대비 |수익률|>30% 초과(가격제한 위반=조정 누락 또는 오류 의심; 신규상장·정리매매 제외), (3) 고가>=max(시가,종가), 저가<=min(...), 거래량 0 + 가격 변동, (4) 액면분할·병합·유상증자 권리락 조정계수 연속성. 유일하게 이식 가능한 발상: "교차 출처 가격 비율 검증"과 "경고(advisory) vs 차단 등급 분리".

### portfolio-manager — 포트폴리오 매니저
| 항목 | 내용 |
|---|---|
| 기법·출처 | LLM 주도 서술형 포트폴리오 리뷰(자산배분·집중도·리스크·리밸런싱). 일반 포트폴리오 이론(HHI, 편차 밴드). 자동 계산 코드는 CSV 리뷰·포지션 대조 두 스크립트뿐 |
| 분류 | (a) 계좌·체결 기록만 필요 (집중도·대조) / 일부 (b)(베타·섹터 데이터) / 대부분 서술형이라 엔진 직접 이식 가치 낮음 |
| 필요 데이터 | Alpaca MCP(mcp__alpaca__get_account_info/get_positions/get_portfolio_history; 폴백 REST /v2/account, /v2/positions, /v2/account/portfolio/history) — references/alpaca-data-fetch.md:L7-L48. 오프라인 모드는 CSV(symbol, asset_type, quantity, direction, price, currency) — scripts/review_csv.py:L18-L19 |
| 주요 파일 | skills/portfolio-manager/SKILL.md(436줄), scripts/review_csv.py, scripts/reconcile_positions.py, references/*.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 — 집중도 한도(종목/섹터)와 브로커-내부 포지션 대조(reconcile)만 채택. 나머지는 보류 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 단일 종목 집중도 | 포트폴리오 10~15% 초과 시 플래그; 리밸런싱 단계에서는 15~20% 초과 시 trim 대상; 단일 종목 >15% 즉시 리밸런스 | skills/portfolio-manager/SKILL.md:L173, L302; references/rebalancing-strategies.md:L106 |
| 2 | 섹터 집중도 | 30~40% 초과 플래그; 섹터 >35% 즉시 리밸런스 | SKILL.md:L178; rebalancing-strategies.md:L107 |
| 3 | HHI | HHI = sum((w_i*100)^2); 체크리스트 목표 HHI < 1800; 예: 비중 30/25/20/15/10% -> 2250 (고집중) | references/diversification-principles.md:L209-L237, L370 |
| 4 | 종목 수 | 적정 15~30, <10 과소분산, >50 과다분산 | SKILL.md:L186-L188 |
| 5 | 드리프트 | 절대 편차 목표 대비 >5%p 면 리밸런스(예 60% 주식 -> <55% 또는 >65%); 상대 편차 10~20%; 월·분기 점검 + 임계 초과 때만 실행(하이브리드) | rebalancing-strategies.md:L73-L117 |
| 6 | 우선순위 | Immediate=집중 포지션 축소, High=목표 대비 >10% 드리프트, Medium=5~10%, Low=미세조정; 현금 >10%면 투입 제안 | SKILL.md:L311-L318 |
| 7 | 레버리지 | 노출을 equity 분모로 계산: gross_long_exposure = long_market_value/equity, cash_pct = cash/equity; 총노출이 100% 초과 또는 현금 음수면 마진 플래그 | SKILL.md:L88 |
| 8 | 위험 지표 | 가중평균 베타, 최대낙폭·현재 낙폭(portfolio history), beta>1.5 비중 | SKILL.md:L198-L210 |
| 9 | 대조 상태 | 브로커 스냅샷 vs 내부 기록: MATCH / MEMORY_ONLY / BROKER_ONLY / DIRECTION_MISMATCH / QUANTITY_MISMATCH (계좌·시각 불일치면 INVALID_INPUT) | scripts/reconcile_positions.py:L82-L141 |
| 10 | CSV 계산 | gross_weight_pct = 종목 총가치 / 총 gross * 100 (소수 6자리); unrealized_pnl = sign*qty*(price - basis) | scripts/review_csv.py:L118, L126-L127 |

**출력 형식**: 마크다운 포트폴리오 리포트(템플릿 references/report-section-templates.md), CSV 모드는 JSON(schema assets/holdings-review.schema.json) + 마크다운 표.

**SKILL.md와 코드 차이**: 집중도·HHI·리밸런싱 임계값은 모두 문서(LLM 지침)이고 코드로 강제되는 것은 없음. 코드 계산은 gross weight·미실현손익·대조 상태뿐 [차이: 문서가 코드보다 훨씬 넓음].

**한국 시장 적용**: Alpaca 대신 증권사 잔고 API(국내 증권사 API는 종목별 평가·수량 제공 [추정]). 포지션 대조(reconcile)는 자동매매에서 필수 안전장치로 채택(주문 체결 누락·부분체결 불일치 탐지). 섹터는 KRX 업종 분류 사용. 한도 값(종목 15%, 섹터 35%, HHI<1800)은 사이저의 max_position_pct·max_sector_pct 입력으로 이식.

### trade-performance-coach — 트레이드 성과 코치
| 항목 | 내용 |
|---|---|
| 기법·출처 | 거래 1건의 "과정 품질" 점검(5축: 논거·절차 준수·리스크 규율·실행·행동 패턴). 손익이 아니라 규칙 준수 평가 — references/review-framework.md:L3-L8. 기대값·승률 계산 없음(그건 weekly-digest) |
| 분류 | (a) 계좌·체결 기록만 필요 (거래 기록 JSON/YAML + 사용자 리스크 계획) |
| 필요 데이터 | 거래 기록(planned/actual/risk_plan/monthly/journal 필드). 시세·API 불필요 |
| 주요 파일 | skills/trade-performance-coach/scripts/review_trade_performance.py (849줄), references/review-framework.md, risk-review-checklist.md, behavior-tags.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 — 심각도 체계·verdict 합성·실제위험>계획위험 검사만 채택(사후 분석/리스크 게이트 입력). 저널 텍스트 정규식 태깅(fomo/revenge)은 자동매매에 해당 없음(보류) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 거래당 위험 | reference = max_risk_per_trade_r (없으면 planned.risk_r); actual > ref*1.25 -> critical; ref < actual <= ref*1.25 -> warning; 이하 info; 값 없으면 warning(unclear) | scripts/review_trade_performance.py:L275-L316 |
| 2 | 포트폴리오 히트 | heat > max_portfolio_heat_r -> critical; heat > max*0.9 -> warning | review_trade_performance.py:L318-L338 |
| 3 | 연속 손실 | monthly.consecutive_losses >= 3 -> warning, >= 4 -> critical ("review-only 모드 고려") | review_trade_performance.py:L340-L350 |
| 4 | 점수 | 100에서 critical -30, warning -15, info 0 차감, [0,100] 클램프 (문서 범위 권고는 info 0-5/warn 10-20/crit 25-40/누락 10-20) | review_trade_performance.py:L522-L532; review-framework.md:L67-L75 |
| 5 | verdict | critical 2개 이상 OR (revenge 태그 AND 연패>=2) OR 연패>=4 -> COOL_DOWN; critical 1개 -> RULE_VIOLATION; warning 있음 -> REVIEW_REQUIRED; 그 외 OK | review_trade_performance.py:L535-L556 |
| 6 | 절차 critical 조건 | setup 미확인 진입(entry_before_confirmation 또는 setup_confirmed==False), 제한 국면(restrictive/cash_priority)에서 거래, 사전 계획 없는 손절 이동(stop_moved & !stop_move_planned) -> critical; 사전 논거 기록 없음/불명 -> warning | review_trade_performance.py:L201-L274 |
| 7 | 근본 원인 | 입력 root_cause 우선; position_size warning/critical -> risk_sizing; setup_confirmation/stop_change_rule critical -> execution; regime critical -> market_environment; 그 외 unknown (문서 범주: thesis_quality/execution/risk_sizing/market_environment/rule_violation/randomness/unknown) | review_trade_performance.py:L558-L572; review-framework.md:L23-L40 |
| 8 | 리뷰 품질 점수 | 필수 5필드(planned.risk_r, actual.risk_r, risk_plan.max_risk_per_trade_r, postmortem.root_cause, journal.reflection) 존재 수 n -> int(40 + 60*n/5); <60 이면 신뢰도 low, >=85 이면 high | review_trade_performance.py:L687-L718 |
| 9 | 다음 세션 규칙 | size_creep -> 다음 2거래 위험 0.5R 상한; revenge/COOL_DOWN -> review-only; stop_moved -> 사전 기재 필수 등 | review_trade_performance.py:L574-L631; behavior-tags.md:L9-L18 |
| 10 | 체크리스트(문서) | 주간 손실 한도 근접(한도의 10% 이내) warning, 초과 critical; 동일 클러스터 증가 시 critical | references/risk-review-checklist.md:L9-L18 (코드 구현은 확인 못 함 — 코드에 weekly loss 검사 없음) |

**출력 형식**: JSON(performance_coach_report.schema.json: verdict, scores{process,risk,execution,review_quality}, findings, risk_notes, behavior_tags[{tag,confidence,evidence,question}], root_cause, next_session_rules[{rule,duration,trigger,reason}]) + Markdown. ALLOWED_ACTIONS = accept_rules/modify_rules/defer/journal_only (review_trade_performance.py:L29).

**SKILL.md와 코드 차이**: [차이] 체크리스트 문서의 "주간 손실 한도"·"상관 클러스터"·"추가/축소 규칙" 검사는 코드에 구현이 없음(grep로 evaluate_risk_discipline가 position_size/portfolio_heat/consecutive_losses 3종만 확인). 연속손실 임계도 문서(threshold 입력)와 달리 코드는 3/4 고정.

**한국 시장 적용**: 거래 기록 스키마가 R 단위(위험 대비)라 시장 무관. 자동매매에서는 "실제 위험 R > 계획 R*1.25 = critical" 같은 체결 후 감사(slippage·갭으로 초과된 위험 감지)로 쓸모 있음. 한국 갭 하락·하한가 잠김으로 실현 R이 -1R을 크게 넘는 경우를 별도 태그(gap_loss)로 구분 권장 [추정].

### signal-postmortem — 시그널 사후 분석
| 항목 | 내용 |
|---|---|
| 기법·출처 | 시그널의 방향 예측 vs 5일 실현수익으로 TP/FP 분류 + 스킬별 정확도로 가중치 피드백(edge-signal-aggregator용) |
| 분류 | (a) 일봉만으로 구현 가능 (시그널 로그 + 일봉 종가. 원본은 FMP API로 가격 조회, 수동 청산가 입력도 지원) |
| 필요 데이터 | 시그널 JSON(ticker, signal_date, entry_price, direction, source_skill, regime_at_signal/exit), FMP API 키(선택) |
| 주요 파일 | skills/signal-postmortem/scripts/postmortem_recorder.py(567줄), postmortem_analyzer.py(557줄), references/outcome-classification.md, feedback-integration.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(사후 분석/위원회 가중치 보정) — 분류기와 가중치 보정식이 위원회 "관점별 점수->합의"의 관점 가중 자동 보정에 직접 대응 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 수익률 | (exit - entry)/entry, entry<=0이면 0 | scripts/postmortem_recorder.py:L113-L117 |
| 2 | 분류 순서 | (1) 국면이 바뀌고(exit 국면이 UNKNOWN 아님) LONG이 -2% 미만 또는 SHORT이 +2% 초과 -> REGIME_MISMATCH; (2) abs(ret) < 0.005 -> NEUTRAL; (3) 방향 일치 -> TRUE_POSITIVE; (4) 불일치 중 abs(ret) > 0.02 -> FALSE_POSITIVE_SEVERE, 아니면 FALSE_POSITIVE | postmortem_recorder.py:L120-L155 |
| 3 | 평가 시점 | 보유기간별 수익률은 신호일+N 달력일에서 이후 최대 4일(offset 0-4) 내 첫 유효 종가 사용; 5d 값이 없으면 시그널 스킵(20d는 보조) | postmortem_recorder.py:L327-L343 |
| 4 | 정확도 | accuracy = TP/(TP+FP) (NEUTRAL·REGIME_MISMATCH 제외); fp_rate = FP/전체; avg_return_5d = 관측된 5d 평균 | postmortem_analyzer.py:L82-L145 (L125-L128) |
| 5 | 가중치 보정 | 표본 >= 20(min_sample_size); factor = (accuracy - 0.55)*0.5; new_weight = clamp(1.0 + factor, 0.3, 2.0); |1.0-new_weight| >= 0.05 일 때만 제안 | postmortem_analyzer.py:L148-L190 (L151-L152, L164-L170) |
| 6 | 보정 신뢰도 | 전체 표본 >=100 HIGH, >=50 MEDIUM, 그 외 LOW | postmortem_analyzer.py:L193-L200 |
| 7 | 개선 백로그 | fp_rate > 0.15 -> medium(>0.25 high), score = fp_rate*n*100; regime_mismatch_rate > 0.25 -> medium; severe_fp_rate > 0.10 -> high ("과신" 이슈) | postmortem_analyzer.py:L212-L300 |
| 8 | 국면 상관 | 국면별 실패율 최댓값이 0.2 초과인 국면을 지목 | postmortem_analyzer.py:L304-L333 |
| 9 | 문서상 추가 규칙 | MISSED_OPPORTUNITY(미체결+방향 수익 >= 2%), 신뢰도 보정(고거래량 +10%, 저거래량 -10%, 실적 -20%, VIX +5 급등 -15%, 갭 >3% -15%, 범위 [0.5,1.0]), RISK_ON VIX<20 breadth>60% / RISK_OFF VIX>25 breadth<40% | references/outcome-classification.md (Classification Categories 3, Confidence Adjustment Factors, Regime Detection 절) |

**출력 형식**: postmortem 레코드 JSON(outcome_category, realized_returns{5d,20d,actual}, holding_days, regime_*, early_exit, gap_event...), 분석기는 skill_metrics, weight_feedback_*.json({skill_adjustments[{current_weight,suggested_weight,reason,accuracy}], confidence, min_sample_threshold}), 개선 백로그.

**SKILL.md와 코드 차이**: [차이] 문서의 MISSED_OPPORTUNITY 분류와 거래량/실적/VIX/갭 기반 신뢰도 보정은 코드에 없음(grep: MISSED/trade_taken 미구현, confidence는 표본수 기반만). [차이] 문서의 "min 임계 0.5%"는 코드 기본 threshold=0.005로 일치. 보유기간이 거래일이 아닌 달력일.

**한국 시장 적용**: 일봉 종가 기준 5거래일 수익률로 바꿔(달력일->KRX 거래일) 위원회 각 관점(모멘텀/가치 등)의 적중률을 계산 -> w = clamp(1 + (acc-0.55)*0.5, 0.3, 2.0) 보정. 수수료·거래세(약 0.2% [추정]) 때문에 NEUTRAL 임계 0.5%를 왕복비용 이상으로 상향 검토. 표본 20건 미만은 보정 금지(그대로 이식 권장). 하한가·거래정지로 평가가격이 없으면 5d 미관측 -> 스킵 규칙을 그대로 따름.

### weekly-performance-digest — 주간 성과 다이제스트
| 항목 | 내용 |
|---|---|
| 기법·출처 | 주간 종결 거래의 표준 성과 통계(승률·기대값·profit factor·R-multiple·MAE/MFE) + 패턴 버킷 |
| 분류 | (a) 계좌·체결 기록만 필요 (순수 계산) |
| 필요 데이터 | trader-memory-core thesis YAML(CLOSED, exit.actual_date가 주 범위; outcome.pnl_dollars/pnl_pct/holding_days/mae_pct/mfe_pct, entry.actual_price, exit.stop_loss, position.shares) |
| 주요 파일 | skills/weekly-performance-digest/scripts/generate_weekly_digest.py (607줄), references/weekly-digest-metrics.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 사후 분석/검증 지표 모듈(공식이 단순·명확) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 승/패/무 | pnl_dollars>0 승, <0 패, ==0 무(없으면 pnl_pct로 대체) | scripts/generate_weekly_digest.py:L203-L252 |
| 2 | 승률 | winners/total_trades (무승부가 분모에 포함) | generate_weekly_digest.py:L255 |
| 3 | 기대값 | mean(pnl_dollars) 전 거래 (= avg_win*win_rate + avg_loss*loss_rate와 동치) | generate_weekly_digest.py:L257; references/weekly-digest-metrics.md:L18-L25 |
| 4 | Profit factor | gross_profit / abs(gross_loss); 손실 0이면 null | generate_weekly_digest.py:L258-L263 |
| 5 | R-multiple | R = pnl_dollars / ((entry.actual_price - exit.stop_loss)*shares); risk<=0 이면 null; 소수 4자리; 평균·표본표준편차(1건이면 0.0) | generate_weekly_digest.py:L175-L195, L282-L288 |
| 6 | MAE/MFE | MAE=min(mae_pct,0), MFE=max(mfe_pct,0)로 클램프 후 평균 | generate_weekly_digest.py:L240-L249, L289-L292 |
| 7 | 보유일 | outcome.holding_days, 없으면 (exit - entry) 달력일; 승/패 따로 평균 | generate_weekly_digest.py:L160-L172 |
| 8 | 패턴 버킷 | 소스 스킬·청산 사유·thesis 유형·섹터·메커니즘·스크리닝 등급별 {wins, losses, win_rate=wins/(wins+losses)}; 값 없으면 unknown | weekly-digest-metrics.md:L52-L66; generate_weekly_digest.py:L306-L341 |
| 9 | 개선 힌트 | 스킬별 loss>=2 이고 win_rate<0.5, stop_hit 청산 >=2건 이면 경고 문구 | generate_weekly_digest.py:L372-L383 |
| 10 | 부분청산 | 헤드라인 통계에서 제외(중복 방지), 별도 보고 | weekly-digest-metrics.md:L68-L74 |

**출력 형식**: JSON(schema_version 1.0, report_type weekly_performance_digest; summary{total_trades, winners, losers, breakeven, win_rate, expectancy, profit_factor, total_realized_pnl}, metrics{...}, patterns, lessons{top_wins, top_losses, process_improvements}) + Markdown.

**SKILL.md와 코드 차이**: [차이] 기대값 계산 시 pnl_dollars가 없고 pnl_pct만 있으면 0.0으로 넣어(L238-L240 부근 `dollars if dollars is not None else 0.0`) 기대값이 희석됨. R의 initial_risk는 "exit.stop_loss"(이동했을 수 있는 최종 손절가)를 쓰므로 진입 시점 초기 손절이 아님 — 문서 자체도 인정(L175-L180). 승률 분모가 두 곳에서 다름(summary는 전체, 패턴은 decided).

**한국 시장 적용**: 순수 계산이라 그대로 이식. 이식 시: pnl은 수수료·세금 차감 후 순손익; R 분모는 진입 시점 초기 손절(고정 저장) 사용; 보유일은 KRX 거래일; MAE/MFE는 일봉 고저가로 계산(일봉 엔진이라 장중 극값 해상도 한계) [추정]. 표본 작을 때(주간 몇 건) 통계 신뢰도 낮다는 문서 경고도 반영: 최소 N 이후에만 판단.

### trader-memory-core — 트레이더 메모리 코어 (짧게, 구조만)
- 기법·출처: 아이디어(thesis)를 YAML 파일 1개씩(state/theses/th_*.yaml)으로 저장하고 `_index.json` 조회 인덱스를 두는 파일 기반 원장. 분류 (a) 계좌·체결 기록만 필요. MIT. 코드 약 5,500줄(thesis_store.py 670 + thesis_store_parts/*.py 약 3,500 + ingest/review) — skills/trader-memory-core/scripts/.
- 수명주기: IDEA -> ENTRY_READY -> ACTIVE -> PARTIALLY_CLOSED -> CLOSED, 어느 비종결 상태에서든 INVALIDATED. 역방향 금지, 종결 상태는 최종. 전이는 transition()은 IDEA->ENTRY_READY만, ACTIVE는 open_position()만, PARTIALLY_CLOSED는 trim()만 — references/thesis_lifecycle.md:L5-L33, L65-L77.
- 손익 원장: position.shares는 최초 수량(불변), shares_remaining은 잔량; trim/close마다 status_history에 {shares_sold, price, proceeds, realized_pnl} 기록; outcome.pnl_dollars = sum(realized_pnl), pnl_pct = pnl_dollars/(entry_price*원수량)*100(소수 2자리) — thesis_lifecycle.md:L33-L43; scripts/thesis_store_parts/positions_equity.py:L281-L294. 선물 실현손익 = (exit-entry)*multiplier*qty*sign — positions_futures.py:L248.
- 안전장치: 원자적 쓰기(tempfile + os.replace) — persistence.py:L109-L131; 손익·보유기간은 update()로 직접 수정 불가(수명주기 함수만 계산) — lifecycle.py:L221-L248; 주식은 롱 전용(SHORT 거부); 초기 손절 > 진입가 거부; 모니터링 review_interval_days 기본 30, 상태 사다리 OK -> WARN -> REVIEW — lifecycle.py:L136, L475-L493.
- MAE/MFE 계산: 보유 기간 일별 종가의 최저/최고(FMP EOD)로 mae_pct = (min_close-entry)/entry*100, mfe_pct = (max_close-entry)/entry*100 (장중 고저 미사용) — thesis_review.py:L25-L75.
- 한국 적용·이식 판단: 부분 채택 — 파일 YAML 대신 DB 원장 테이블로 바꾸되 (1) 상태 머신(전이 제한), (2) 실현손익 원장 + 파생 지표는 원장 합으로만 계산, (3) 수량 불변/잔량 분리 불변식을 그대로 이식. 서킷브레이커·사전게이트·주간 다이제스트가 모두 이 원장을 읽는 구조라 "단일 진실 원천"으로서 가치가 큼.

### futures-position-sizer — 선물 포지션 사이저 (짧게)
- 기법·출처: 선물 위험 기반 사이징(승수·틱·환율 반영); 증거금 기반이 아님. 분류 (a) 계좌·체결 기록만 필요(순수 계산, 오프라인). MIT. 파일: skills/futures-position-sizer/scripts/futures_sizing.py(1,221줄), futures_position_sizer.py, references/sizing-methodology.md.
- 계산식: stop_distance=|entry-stop|; risk_per_contract = stop_distance*multiplier*fx_rate; risk_budget = account*risk_pct/100; contracts = floor(risk_budget/risk_per_contract) — Fraction 정확 유리수 나눗셈으로 "절대 올림 없음"을 구성적으로 보장(엡실론 방식은 폐기) — references/sizing-methodology.md Core Formula·Floor Algorithm 절; scripts/futures_sizing.py:L604-L676. 1계약 위험이 예산 초과면 NO_TRADE(risk_below_one_contract).
- 가드: risk_pct 범위 (0,10], 2.0 초과 경고(RISK_PCT_WARNING_THRESHOLD=2.0, futures_sizing.py:L93); 손절이 1틱 미만이면 거부; 방향-손절 기하 검증; 계약 수 상한 CONTRACTS_SANITY_MAX=1e12 (L108); 증거금은 계산하지 않고 고정 안내문만 출력(MARGIN_NOTE, L400-L403). 23개 핵심 종목 사양표(미국 CME 계열; 코드·문서에서 KOSPI/KRX 검색 결과 없음).
- 한국 적용 [추정]: KOSPI200 선물 승수 25만원(미니 5만원) -> multiplier만 교체하면 동일 공식 적용(원화 단일통화라 fx_rate=1), 틱 0.05pt(=12,500원)·미니 0.02pt [확인 필요]. 이 스킬은 증거금을 계산하지 않으므로 증거금·마진콜 한도(총 증거금 <= 계좌 X%)는 별도 구현. 일봉 엔진의 선물 사용 가능성이 낮으면 보류; 계약 수 내림·NO_TRADE 처리 패턴은 주식 사이저에도 그대로 이식 가능("1주도 못 사면 매매 안 함").
- 이식 판단: 보류(선물 미사용 시). 채택 시 사이징 모듈의 파생상품 분기.

#### 그룹 소결
이식할 규칙(우선순위 순):
1. 사이징(position-sizer): shares = floor(equity*risk%/(entry-stop)), risk% 0.5~1% 기본 상한 2%; 최종 = min(위험 기반, 종목 한도, 섹터 한도(남은 한도=max_sector-현재노출)); 정수 내림만, 위험 보고만 half-up (position_sizer.py:L108-L229, L96-L105). 한국판은 위험/주 = (entry-stop) + 왕복 비용(수수료+매도세 약 0.2% [추정]) 으로 보정, 호가단위 정렬, 현금 한도 추가. Kelly는 표본 100건 이상에서 상한 점검용(half-Kelly, 음수면 0).
2. 서킷브레이커(리스크 게이트): 일 -2% 즉시 중단(다음 거래일까지), 주 -5%(다음 주 첫 거래일까지), 월 -8%(다음 달 첫 거래일까지), 2연패 시 24시간 쿨다운; 최엄격 상태 승리(HALTED>COOLDOWN>ALLOWED); 상태 파일 불완전하면 fail-closed(check_circuit_breaker.py:L52-L57, L610-L700). 보완 필요: 미실현손익 포함, 고점 대비 낙폭 연동, 단계적 사이즈 축소·재개(원본에 없음).
3. 사전 게이트(주문 직전): 손절·계획 위험액 없는 주문 거부, 실제 위험 > 계획 위험이면 NO_GO, 상위 게이트 결과 누락·미상이면 REVIEW_REQUIRED(보류), 최근 24h 손실 청산 있으면 NO_GO (check_pre_trade_discipline.py:L353-L382, L296-L316, L220-L276). 판정 등급 GO<NO_ACTIONABLE<REVIEW_REQUIRED<NO_GO.
4. 성과 지표(검증·사후): 기대값=평균 손익, profit factor=총이익/|총손실|(손실 0이면 정의 안 함), R=손익/((진입-손절)*수량)로 초기 손절 고정 저장 필요, MAE/MFE는 종가 기준 (진입 대비 %) (generate_weekly_digest.py:L175-L195, L255-L292; thesis_review.py:L67-L75).
5. 사후 분류 및 위원회 가중치 보정: 5거래일 수익률로 TP/FP/NEUTRAL(|r|<0.5%)/FP_SEVERE(>2%)/REGIME_MISMATCH, w=clamp(1+(accuracy-0.55)*0.5, 0.3, 2.0), 표본>=20일 때만, 변화 5% 미만은 무시 (postmortem_recorder.py:L120-L155; postmortem_analyzer.py:L148-L190).
6. 포지션 대조(reconcile)와 원장 설계: 브로커-내부 상태 MATCH/MEMORY_ONLY/BROKER_ONLY/QUANTITY_MISMATCH 점검, 수명주기 상태 머신 + 실현손익 원장 합산 원칙 (reconcile_positions.py:L82-L141; thesis_lifecycle.md:L5-L43).
보류: data-quality-checker(문서 린트라 일봉 품질 검사 아님), portfolio-manager의 서술형 리밸런싱, 저널 텍스트 정규식 행동 태깅.


---

## 17. 재무·가치·배당·거시 투자자 계열 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, 2026-11-14, MIT) · 범위: stanley-druckenmiller-investment, value-dividend-screener, dividend-growth-pullback-screener, institutional-flow-tracker, us-undervalued-growth-screener, kanchi-dividend-*, finviz-screener

### stanley-druckenmiller-investment — Druckenmiller 전략 합성기 (확신도 점수 -> 노출/배분)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Druckenmiller 식 "오리 정렬(signals aligned)" 확신도. 자체 스킬 8개의 JSON 보고서를 읽어 합성하는 메타 스킬. 원저자 언급 외 독자 구현 (SKILL.md:3) |
| 분류 | (c) 시장 폭·거시 필요 (주). 입력 5개는 다른 스킬 산출물이라 단독 구현 불가. 일봉 지수/폭 지표로 대체하면 (a) 근사 가능 |
| 필요 데이터 | 필수 5: market_breadth, uptrend_analysis, market_top, macro_regime, ftd_detector. 선택 3: vcp_screener, theme_detector, canslim_screener (skills/stanley-druckenmiller-investment/scripts/report_loader.py:L22-L39). 보고서 최대 나이 기본 72시간 (scripts/strategy_synthesizer.py:L45-L48) |
| 주요 파일 | scripts/scorer.py(532줄), allocation_engine.py(165줄), report_loader.py |
| 라이선스 | MIT (저장소 루트) |
| 이식 판단 | 부분 채택: 위원회 합의 점수 -> 레짐/노출 상한(리스크 게이트·사이징). 구조(가중합+분산 기반 수렴도+구간별 노출표)만 이식, 입력은 우리 관점 점수로 교체 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 7개 구성요소 가중치 | market_structure .18, distribution_risk .18, bottom_confirmation .12, macro_alignment .18, theme_quality .12, setup_availability .10, signal_convergence .12 (합 1.00) | scorer.py:L28-L36 |
| 2 | 시장구조 | base = 0.5*breadth + 0.5*uptrend; 두 점수 차 divergence>30이면 base -= (divergence-30)*0.3; 0~100 클램프 | scorer.py:L54-L69 |
| 3 | 분배 위험(반전) | 100 - market_top.composite (기본 top=0) | scorer.py:L72-L76 |
| 4 | 바닥 확인(FTD) | 상태점수 FTD_CONFIRMED 80, FTD_WINDOW 60, RALLY_ATTEMPT 55, NO_SIGNAL 40, CORRECTION 35, FTD_INVALIDATED 15, RALLY_FAILED 10, DATA_GAP 10. 확정이면 +(quality-50)*0.2, dual_confirmation +5, 이후 분배일 수*5 차감 | scorer.py:L79-L111 |
| 5 | 거시 정합 | 레짐 기본 broadening 85, concentration 65, transitional 50, inflationary 35, contraction 20; +(composite-50)*0.2; 신뢰도 곱 high 1.1/medium 1.0/low 0.9 | scorer.py:L114-L139 |
| 6 | 테마 품질 | upstream derived_score 그대로. derive: avg_heat(강세 테마)*0.7 + early수*5 + hot(heat>=70)수*3 - exhaustion수*8 | scorer.py:L142-L146, report_loader.py:L276-L328 |
| 7 | 셋업 가용성 | VCP·CANSLIM derived 평균 + fat pitch 보너스(VCP textbook>=2개 +10, CANSLIM 90점이상>=3개 +10); 데이터 없으면 50 | scorer.py:L149-L174 |
| 8 | VCP derive | quality = min(textbook*25+strong*15+good*10+developing*3,100); funnel = min(trend_template통과/유니버스 /0.20*100,100); derived = 0.6*quality+0.4*funnel | report_loader.py:L223-L275 |
| 9 | CANSLIM derive | min(상위5 평균*0.7 + (90+ 개수*3 + 80~90 개수*1.5) + M_score*0.15, 100) | report_loader.py:L329-L364 |
| 10 | 신호 수렴도 | 5개(breadth, uptrend, 100-top, macro, FTD quality) 모집단 표준편차 sd; convergence = max(0,100 - sd*3.33); 전부 >55면 +15, 전부 <45면 -15; 입력 3개 미만이면 50 | scorer.py:L177-L231 |
| 11 | 결측 가중치 재분배 | theme/setup 없으면 해당 가중치 0, 나머지를 비례 정규화 | scorer.py:L272-L292 |

**점수·등급 (확신도 -> 노출)**: >=80 Maximum(주식 90-100%), 60-79 High(70-90), 40-59 Moderate(50-70, 포지션 절반, A등급 셋업만), 20-39 Low(20-50, 신규진입 거의 없음), <20 Capital Preservation(0-20) (scorer.py:L342-L415). 배분 기본표 equity/bonds/alt/cash: Max 90/0/5/5, High 75/5/5/15, Moderate 55/10/10/25, Low 30/15/15/40, Preservation 10/20/20/50 (allocation_engine.py:L17-L48). 레짐 가감 broadening eq+5/cash-5, concentration +3/-3, inflationary eq-5 bonds-5 alt+10, contraction eq-10 bonds+5 cash+5 (L54-L60). 패턴 가감 unsustainable_distortion eq-10, extreme_sentiment_contrarian eq+10, wait_and_observe eq-5 등 (L66-L71); 음수 클램프 후 100으로 재정규화 (L103-L122).
**사이징**: 구간별 max_single_position/daily_vol_target/max_positions = Max 25%/0.4%/8, High 15%/0.3%/12, Moderate 10%/0.25%/15, Low 5%/0.15%/20, Preservation 3%/0.1%/25 (allocation_engine.py:L137-L165). 즉 확신도가 낮을수록 종목 수 상한은 늘고 단일 비중은 줄어듦.
**패턴 분류** 4종(policy_pivot_anticipation, unsustainable_distortion, extreme_sentiment_contrarian, wait_and_observe)을 규칙 점수(예: p2 = top>=60 +35, 레짐 contraction/inflationary +30, 테마 exhaustion>=2 +20, breadth<40 +15)로 매기고 40점 미만이면 wait_and_observe (scorer.py:L418-L532).
**보조 문서 매트릭스**: Market Top 구간 x 레짐별 권고 주식비중표(예: broadening+Green 95-100%, contraction+Critical 0-10%) (references/conviction_matrix.md:L5-L14), 폭 구간 x VCP 등급별 신규진입 크기(Full/75%/50%/없음) (L18-L25). 코드에는 없고 문서에만 있음.
**출력 형식**: 마크다운+JSON 보고서(conviction_score, zone, components 가중 기여, pattern, 배분, 사이징) (scripts/report_generator.py).
**SKILL.md와 코드 차이**: 확인한 범위에서 가중치·구간 일치. conviction_matrix.md의 Top x Regime 노출표는 코드(scorer/allocation_engine)에 미구현 [차이: 문서 전용].
**한국 시장 적용**: S&P 계열 입력(breadth, FTD, theme)을 KOSPI/KOSDAQ 일봉 기반 폭(20/50일선 상회 종목 비율, 신고가-신저가), FTD(지수 저점 후 4~7일째 +1.25%~1.5% 이상 거래량 증가) 로직으로 자체 계산해야 함 [추정]. 거시 레짐은 금리·환율·반도체 수출 등 별도 소스 필요. 규칙 2/4/10 및 확신도->노출 구간표는 소스 없이 그대로 이식 가능.

### value-dividend-screener — 가치+배당 성장 스크리너 (PER<=20, PBR<=2, 수익률>=3%)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 가치(PER·PBR) + 배당수익률 + 3년 성장(배당·매출·EPS) 복합 스크린, 마지막에 RSI<=40 눌림 필터. 원저자 미명시 자체 구현 |
| 분류 | (b) 재무 데이터 필요 (주). RSI 부분만 (a) |
| 필요 데이터 | FMP API(필수): income-statement, balance-sheet, cash-flow, key-metrics, stock_dividend 이력, 일봉 30일, profile. FINVIZ Elite 유료(선택, 월 약 $40 문서 기준) 사전 필터 (skills/value-dividend-screener/SKILL.md:L12-L32, scripts/screen_dividend_stocks.py:L204-L234) |
| 주요 파일 | scripts/screen_dividend_stocks.py(1376줄), references/screening_methodology.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: 배당 지속가능성(FCF 배당성향<100%, 배당성향<80%), 배당 TTM-CAGR+무삭감(95%) 일관성, 안정성 점수, 재무건전성(D/E<2, 유동비율>1)을 위원회 "가치/배당" 관점 점수기로. 종목 선별 필터는 일봉 규칙의 유니버스 사전필터로 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 1차 게이트 (FMP-only 경로) | 추정수익률=lastAnnualDividend/price*100 >= 3.0, ETF·펀드 제외, 시총 상위 max_candidates(300)만 /ratios 조회, 0<PE<=20, 0<PB<=2 | scripts/screen_dividend_stocks.py:L121-L202, L973-L981 |
| 2 | FINVIZ 필터 문자열 | cap_midover, fa_div_o3, fa_divgrowth_3yo5, fa_eps3years_pos, fa_pb_u2, fa_pe_u20, fa_sales3years_pos, geo_usa | screen_dividend_stocks.py:L54-L75 |
| 3 | 배당 TTM CAGR | 365일 롤링 합 4개 창(현재~3년 전), CAGR=(끝/시작)^(1/3)-1; 3년 미만 이력이면 탈락; 일관성=각 창 >= 직전 창의 95% | screen_dividend_stocks.py:L390-L448 |
| 4 | 탈락: 배당 CAGR | div_cagr < 4.0% 이면 탈락 | screen_dividend_stocks.py:L1063-L1067 |
| 5 | 탈락: 실제 수익률 | 최근 TTM 배당/현재가*100 < 3.0% 탈락 | screen_dividend_stocks.py:L1069-L1084 |
| 6 | 탈락: 매출·EPS 추세 | 손익계산서 4개년 미만 탈락; 매출 3년 추세 양(+)·EPS 3년 추세 양 아니면 탈락 (check_positive_trend: 하락 횟수<=1) | screen_dividend_stocks.py:L376-L387, L451-L482, L1056-L1095 |
| 7 | 탈락: 배당 변동성 | 변동성>100% 이고 (성장 아님 또는 성장연수<3) 이면 탈락 | screen_dividend_stocks.py:L1097-L1107 |
| 8 | 지속가능성 | 비REIT: 배당/순이익*100 <80 AND FCF(영업CF-|CAPEX|)가 배당을 초과(COVERED) AND FCF배당성향<100. REIT: 배당/FFO<80 (FFO=순이익+감가상각 류) | screen_dividend_stocks.py:L485-L630 |
| 9 | 재무건전성 | healthy = (총부채/자기자본 < 2.0) AND (유동자산/유동부채 > 1.0) | screen_dividend_stocks.py:L633-L660 |
| 10 | 안정성 점수(0-100) | 변동성<50이면 안정 +40, 아니면 변동성<100일 때 max(0, 40-0.4*vol); 성장(성장연수>=2 & 전체상승) +30; 성장연수*10 (최대 30). 연간 배당이 전년 95% 이상이면 성장연수로 계산 | screen_dividend_stocks.py:L727, L736, L746, L844-L873 |
| 11 | 품질 점수(0-100) | min(ROE%/20*50,50) + min(순이익률%/15*50,50) | screen_dividend_stocks.py:L876-L906 |
| 12 | RSI | 14일 RSI(Wilder류), 최종 RSI<=40 종목만 우선; 없으면 RSI 낮은 순 | screen_dividend_stocks.py:L236-L277, L1195-L1214 |

**점수·등급 (코드 기준 복합점수 100점)**: min(배당CAGR/10*15,15) + 안정성점수*0.2(최대20) + min(매출CAGR/10*10,10) + min(EPS CAGR/15*10,10) + 지속가능 10 + 재무건전 10 + 품질*0.25(최대25) (screen_dividend_stocks.py:L1120-L1135). 등급 라벨 없음, 상위 top_n(기본 20) 정렬.
**출력 형식**: JSON(종목별 수치 전부)과 마크다운 리포트 (references/report_template.md).
**SKILL.md와 코드 차이**: [차이] (1) 모듈 docstring은 수익률 3.5%/배당 CAGR 5%(L10-L13) 이지만 실제 코드는 3.0%/4.0% (L1065, L1081). (2) references/screening_methodology.md의 점수 배분(배당성장 20, 매출 15, EPS 15, 품질 30, L192-L218)은 코드(15/10/10/25 + 안정성 20)와 다름. 코드 기준 사용.
**한국 시장 적용**: OpenDART로 매출·영업이익·순이익·자본·부채·유동자산/부채·영업CF/CAPEX(현금흐름표) 모두 연간/분기 대체 가능. 배당 이력은 DART "배당에 관한 사항"(주당배당금·배당성향·시가배당률) 사용. PER·PBR·배당수익률은 KRX 정보데이터시스템 제공 값 사용 가능 [추정]. 한국은 배당 연 1회(12월 결산)가 다수라 TTM 365일 창은 연 단위 DPS 비교로 단순화, 분기·반기 배당 기업은 합산. 배당기준일이 결산 후 이사회 결의 이후로 바뀐 제도 변경 [추정] 때문에 연말 수익률 계산은 직전 확정 DPS 기준. 미국식 PER<=20은 한국 저평가 구조 때문에 PER<=12, PBR<=1.0~1.5 등 재보정 필요 [추정]. 배당소득세 15.4% 가정 [추정].

### dividend-growth-pullback-screener — 배당성장주 RSI 눌림목
| 항목 | 내용 |
|---|---|
| 기법·출처 | 배당 CAGR 12%+ 우량 성장주가 RSI(14)<=40으로 눌릴 때 분할 진입. 원저자 미명시, 자체 구현 |
| 분류 | (b) 재무 필요 + 진입 타이밍은 (a) 일봉 RSI. 주=(b) |
| 필요 데이터 | FMP(배당이력, 손익, 재무상태, 현금흐름, key-metrics, 일봉 최소 20일), FINVIZ Elite 선택 (skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py:L118-L165) |
| 주요 파일 | scripts/screen_dividend_growth_rsi.py(1344줄), references/rsi_oversold_strategy.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(부분): RSI 구간별 점수·분할진입·손절 규칙은 진입 트리거/사이징으로 일봉 엔진에 바로 이식. 배당성장 점수는 DART 배당 이력 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 기본 파라미터 | min_yield 1.5%, min_div_growth(3Y CAGR) 12.0%, rsi_max 40.0 | screen_dividend_growth_rsi.py:L695-L702 |
| 2 | FINVIZ 사전필터 | 수익률 0.5-3%, 3Y 배당성장 10%+, EPS 3Y 5%+, 매출 3Y 5%+, RSI<40, 중형주 이상, 미국 | screen_dividend_growth_rsi.py:L47-L77 |
| 3 | 배당 CAGR | 달력연도 합산, 올해(부분연도) 제외, 최근 4개 연도 CAGR(3년); 일관성=연간 >= 전년*0.95; 연속 성장연수는 0.95 허용으로 역산 | screen_dividend_growth_rsi.py:L262-L319 |
| 4 | 탈락 순서 | CAGR<12 -> 수익률(최근 연 배당/가격)<1.5 -> 일봉 20개 미만 -> RSI>40 -> 매출 CAGR<0 -> EPS CAGR<0 -> 재무건전성 불량 | screen_dividend_growth_rsi.py:L800-L893 (분기 위치 L780-L893) |
| 5 | RSI 14 | Wilder 평활: 첫 14개 단순평균, 이후 (avg*(13)+x)/14; 가격 15개 미만이면 None | screen_dividend_growth_rsi.py:L205-L250 |
| 6 | 재무건전성 | D/E<2.0 AND 유동비율>1.0 (값이 None이면 통과로 처리) | screen_dividend_growth_rsi.py:L564-L588 |
| 7 | 지속가능성(표시용) | 비REIT 배당성향<80 & FCF배당성향<100; REIT FFO<80 | screen_dividend_growth_rsi.py:L407-L540 |
| 8 | 진입 가이드(문서) | RSI<30: 50% 선진입 후 RSI>30 확인 시 추가, 손절 8-10%; RSI 31-35: 전량, 손절 5-8%; RSI 36-40: 전량, 손절 3-5% | references/rsi_oversold_strategy.md:L35-L36, L100, L205-L209 |

**점수·등급 (100점 상한)**: 배당성장 40(CAGR>=20:40, >=15:35, >=12:30, 그 외 20) + 일관성 +5; 품질 30(ROE>=20:12, >=15:10, >=10:7, 그 외 3 / 순이익률>=20:10, >=15:8, >=10:6, 그 외 3 / D/E<0.5:8, <1.0:6, <2.0:3); 기술 20(RSI<=25:20, <=30:18, <=35:15, <=40:12, 그 외 5); 밸류 10(PER<15:5, <25:3 / PBR<3:5, <5:3). 합이 105까지 가능해 min(,100) (screen_dividend_growth_rsi.py:L610-L692). 등급 없음, 점수 내림차순.
**출력 형식**: 마크다운 리포트(RSI 구역별 진입 권고, 손절 표) + JSON (screen_dividend_growth_rsi.py:L971-L1195).
**SKILL.md와 코드 차이**: 기본값(1.5%, 12%, RSI 40)은 일치. docstring의 가중치 40/30/20/10과 코드 배점은 일치하나 일관성 +5 때문에 최대 105 -> 캡 100 [미세 차이]. 위 value-dividend 스크리너는 달력연도가 아닌 TTM 창을 쓰는 반면 이쪽은 달력연도 [두 스킬 간 차이].
**한국 시장 적용**: RSI·분할진입은 일봉만으로 이식. 한국은 배당 12% 연성장 기업이 드물어 임계값 완화(예 CAGR 8~10%) 필요 [추정]. 배당 이력은 DART 배당 공시, 연 1회 결산배당 위주라 달력연도 방식이 더 자연스러움. 일봉만으로 RSI<=30 눌림 + 위원회 가치 점수 결합을 권장.

### institutional-flow-tracker — 13F 기관 수급 추적
| 항목 | 내용 |
|---|---|
| 기법·출처 | SEC 13F 분기 보유 변화로 "스마트머니" 축적/분배 식별. FMP의 13F 집계 요약(ownership summary) 사용 |
| 분류 | (c) 수급·거시류 (주). 일봉만으로는 불가, KRX 투자자별 순매수로 대체 시 일 단위로 오히려 정밀 |
| 필요 데이터 | FMP API(13F 집계: investorsHolding, numberOf13Fshares 및 전분기 값, increased/reduced/new/closedPositions, top holders). 13F는 분기말 +45일 지연 (skills/institutional-flow-tracker/SKILL.md:L31, L56-L57; scripts/track_institutional_flow.py:L68-L131) |
| 주요 파일 | scripts/track_institutional_flow.py, data_quality.py, analyze_single_stock.py, references/interpretation_framework.md, institutional_investor_types.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: 점수식 구조(변화율 임계값·breadth 등급·티어 가중)를 KRX 외국인/기관 순매수 기반 "수급 관점" 위원회 점수기로 재설계 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 보유주식 변화율 | percent_change = (현재 13F 주식수 - 전분기) / 전분기 * 100 | track_institutional_flow.py:L125-L131 |
| 2 | 신뢰도 등급 | A: 전분기 존재 & 보유기관 >=50; B: 전분기 존재 & >=10; C: 전분기 없음 또는 <10 -> 제외 | data_quality.py:L39-L70 |
| 3 | 스크린 필터 | |변화율| >= 10% (기본), 기관수 >= 10, 시총 >= $1B | track_institutional_flow.py:L170-L175, L232-L233 |
| 4 | 정렬 | |변화율| 또는 |기관수 변화| 내림차순 | track_institutional_flow.py:L240-L246 |
| 5 | 단일종목 신호(8분기) | shares_trend>15 & holders_trend>5: STRONG ACCUMULATION; shares_trend>7 & holders_trend>0: MODERATE ACCUMULATION; shares_trend<-15 또는 holders_trend<-5: STRONG DISTRIBUTION; shares_trend<-7: 중간 분배 | analyze_single_stock.py:L287-L300 |
| 6 | 상위10 보유 집중도 | >60 높음, >40 보통, 그 외 낮음 | analyze_single_stock.py:L415-L425 |
| 7 | 신호 강도(문서) | >15% QoQ 강, 5-15% 중, <5% 노이즈; 3분기 연속 가속은 고품질 | references/interpretation_framework.md:L11-L45 |
| 8 | 티어 가중 점수(문서) | Quality = T1*3.5 + T2*2.5 + T3*1.0 + T4*0.3; Flow = (T1 매수-매도)*3.5 + (T2)*2.5 + (T3)*1.0; Combined = 합 | references/institutional_investor_types.md:L505-L520 |

**점수·등급**: 코드의 등급은 데이터 신뢰도 A/B/C뿐이고 방향성 점수는 임계값 분류(규칙 5). 티어 가중 점수식은 문서에만 있고 코드 미구현 [차이]. 문서에 적힌 "과거 성공률 75-80%" (interpretation_framework.md:L115) 는 검증 근거 없는 주장으로 이식 가치 없음.
**출력 형식**: 마크다운 리포트(상위 매집 10, 분배 10, 종목별 변화·신뢰도 등급)와 콘솔 표.
**한국 시장 적용 (KRX 대체 계산식 제안)** [추정]: KRX 투자자별 일별 순매수(외국인, 기관 세부, 개인)를 사용. 제안:
- 순매수 강도 NB_k(N) = (최근 N일 투자자 k 순매수 대금 합) / (N일 거래대금 합) * 100, N=5, 20, 60.
- 보유 변화: 외국인 보유 비중(%) 의 20일 변화량 Δfor20 (13F 주식수 변화율 대응).
- 지속성: 최근 20일 중 순매수 일수 비율(0~1) 및 NB 가속(NB_5 > NB_20 > NB_60).
- 점수: S = clip(50 + 2.0*NB_foreign(20) + 1.5*NB_inst(20) + 10*Δfor20 + 20*(순매수일수비율-0.5), 0, 100) — 계수는 [추정] 초안이고 백테스트 보정 필요. 개인 순매수 NB_retail은 역지표(음의 가중) 후보.
- 신뢰 등급: 13F 보유기관 수 대응으로 거래대금·시총 최소선(예: 20일 평균 거래대금 하한)을 두고 미달 시 제외(등급 C).
- 13F 대비 장점: 지연 45일 -> 당일/익영업일, 단점: 투자자 구분이 유형(외국인/기관)이라 개별 운용사 티어 가중은 불가.

### us-undervalued-growth-screener — 미국 저평가 성장(GARP) 스크리너 v3.6.1
| 항목 | 내용 |
|---|---|
| 기법·출처 | 포워드 PER·FCF 수익률 대비 주당 성장 GARP, 가정 "멀티플 확장 없이" 2~3년 수익률, SBC·희석 통제. 자체 설계 |
| 분류 | (b) 재무 + 컨센서스 추정 필요 (주), 일부 (d) 정성: 최종 점수 7개 구성요소 원점수는 LLM/분석가가 후보 JSON에 입력 |
| 필요 데이터 | FMP 직접 호출(약 1.7만 줄 코드: 유니버스·추정치 스냅샷·캐시·체크포인트), 애널리스트 추정(FY1), SEC 재무 검증, 시장 컨텍스트(금리·물가·GDP) (skills/us-undervalued-growth-screener/SKILL.md:L6-L9, assets/screening-config.example.json:L1-L91) |
| 주요 파일 | scripts/screen_universe.py(2032줄, 광역 스크린), evaluation_candidate.py(점수·상태), evaluation_common.py(가중·패널티), evaluation_ranking.py(최종 3종 선별), research_contract.py(1898줄 계약 검증)·manage_run_state.py 등은 파이프라인 구조 |
| 라이선스 | MIT |
| 이식 판단 | 부분: 광역 스크린 점수식(broad_score)과 패널티 표만 위원회 "가치/성장" 점수기 참고. 파이프라인/계약 코드는 이식 불필요. 컨센서스가 한국 무료 데이터로 불가해 전체 이식은 보류 |

**규칙·계산식: 광역 스크린 (screen_universe.py)**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 유니버스 | 시총 $0.5B~$20B, 가격>=$5, 20일 평균 거래대금 >=$5M(하드 $1M), NYSE/Nasdaq/NYSE American만 | assets/screening-config.example.json:L2-L6; screen_universe.py:L73 |
| 2 | 주당 성장 | per_share_growth = max(EPS 성장, FCF/주 성장, 명시 값) | screen_universe.py:L362-L369 |
| 3 | normal_value | 포워드PER<=20 OR EV/FCF<=20 OR FCF수익률>=5% | screen_universe.py:L558-L562; config:L66-L69 |
| 4 | 통과 | economic_pass = normal_value AND 주당성장>=12%; (매출성장>=8, ROIC>=8, 순부채/EBITDA<=2.5는 가이드라인 미달 표시만) | screen_universe.py:L516-L528, L586-L589 |
| 5 | 고성장 예외 | PER<=30 AND 주당성장>=20% (추정치 모드); 정식 모드는 추가로 ROIC>=10, FCF>0, 희석<=3%, 레버리지<=2.5 | screen_universe.py:L563-L584 |
| 6 | near miss | normal_value AND PER<=22 AND 주당성장>=8% AND 매출성장>=0 (또는 결측) | screen_universe.py:L586-L598; config:L42-L43 |
| 7 | 광역 탈락 | FCF<=0 -> negative_forward_growth; PER가 있고 normal_value도 고성장 예외도 아니면 valuation_not_supported_by_growth; 포워드PER>60은 경제 스크린 탈락 | screen_universe.py:L545-L551, L553-L556, L600-L601 |
| 8 | 광역 점수(broad_score) | 밸류 = (35 - min(PER,100))+ min(20, FCF수익률*2) ; 성장 = clip(주당성장,0,35) + clip(매출성장,0,15); 품질 = clip(ROIC,0,20); 희석 = max(0, 10 - 희석%*2); 레버리지 = max(0, 10 - 순부채/EBITDA*2); 커버리지 = min(10, 애널리스트수*2); 최대 약 145 | screen_universe.py:L647-L665 |
| 9 | 감점 | 순환성(cyclicality 1-5) (c-2)*2; 누락 딥다이브 항목당 1.5; 섹터 검토 -5; near miss -4; 주당성장>100% -10 | screen_universe.py:L666-L680 |

**규칙·계산식: 정밀 평가 (evaluation_*.py)**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 10 | 원점수 상한(합 100) | growth_sustainability 20, valuation_attractiveness 20, financial_quality 15, fcf_earnings_quality 15, competitive_advantage 10, capital_allocation 10, catalyst_risk_balance 10 | evaluation_common.py:L169-L177 |
| 11 | 최종점수 | clip(원점수 합 - 패널티 합, 0, 100) | evaluation_candidate.py:L429 |
| 12 | 패널티: 데이터품질 | >=85:0, >=70:2, >=55:5, 그 외 10 | evaluation_common.py:L415-L422 |
| 13 | 패널티: 순환성 | 1:0, 2:0, 3:2, 4:5, 5:8 | evaluation_common.py:L425-L426 |
| 14 | 패널티: 추정 breadth | 애널리스트 >=5:0, >=3:2, >=1:4, 없음 5 | evaluation_common.py:L391-L400 |
| 15 | 패널티: 추정 분산 | (고-저)/중앙값 >50%:4, >30:2, >15:1 | evaluation_common.py:L403-L412 |
| 16 | 패널티: SBC/매출 | >25%:8, >15:5, >10:3, >5:1, 결측 2 | evaluation_common.py:L429-L440 |
| 17 | 패널티: 연 희석 | <=3%:0, <=5:2, <=10:5, 초과 8, 결측 2 | evaluation_common.py:L443-L452 |
| 18 | 시나리오 | 상수배수 상승여력 >=30% 필요, 멀티플 20% 수축 스트레스 >=0%(선택), 컨센서스 저점 상승 >=15% | config:L9-L11, L82 |
| 19 | 정식 eligible 게이트 | 최종점수>=70; SBC조정 FCF수익률>=3% 또는 EV/FCF<=30; ROIC>=8; 순부채/EBITDA<=3.0; 희석<=5%; 저점상승>=15; 신약특허만료 스트레스 <-25% 이면 심각 | evaluation_candidate.py:L109-L175; config:L76-L84 |
| 20 | 상태 | hard 있으면 excluded; review 있으면 review_required; 심각 게이트 실패 review_required; 게이트 실패 <=2개면 conditional, 초과 review_required; 전부 통과 eligible | evaluation_candidate.py:L443-L460 |
| 21 | 최종 3종 | 점수>=75, 데이터품질>=80, SBC조정 FCF수익률>=5, EV/FCF<=20, 저점상승>=20; 레인 쿼터 core 2/고성장 1/near-miss 1/순환 1, 섹터당 최대 2 | config:L61-L65, L85-L90; evaluation_ranking.py:L61-L160 |
| 22 | 데이터 검증 가중(합 100 근처) | forecast_bridge 15, sec_financials 10, latest_earnings 7, guidance 8, diluted_shares 8, sbc 8, peer_set 8, gaap_nongaap 8, quote 5, cyclical 5, cash 5, sector_risk 5, corp_actions 4, roic_ebitda 4 | evaluation_common.py:L180-L195 |

**출력 형식**: 광역 스크린 감사 JSON, 평가 JSON, 마크다운 보고서(eligible/conditional/review/excluded 그룹, 최종 3종) (evaluation_report.py, evaluation_ranking.py:L257-L425).
**SKILL.md와 코드 차이**: 코드 확인 범위에서 config 임계값과 screen_universe 기본값 일치(L133-L146). 상세 문서(methodology.md 622줄)는 읽지 않음 [미확인].
**한국 시장 적용**: 포워드 PER/컨센서스는 FnGuide 유료 필요 [추정]. 대체: 후행 PER, OpenDART 연간 EPS 성장 3년 CAGR, 영업CF-CAPEX 기반 FCF 수익률. 유용한 이식 요소는 (i) normal_value OR 규칙(PER<=20 / EV/FCF<=20 / FCF수익률>=5% 중 하나), (ii) 희석·레버리지 점수식 max(0,10-x*2), (iii) 패널티 표. SBC는 한국 기업 공시가 빈약해 생략, 대신 유상증자·CB/BW 희석률 사용 [추정]. 섹터 프로파일(bank/insurance/reit 등)은 한국 금융·리츠에 별도 규칙 필요.

### kanchi-dividend-sop — Kanchi 배당 SOP (Step 1~5 + 판정 합성)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 일본 배당 투자자 Kanchi(カンチ)의 5단계 SOP(수익률 필터 -> 성장·안전 -> 밸류 -> 일회성 이익 제거 -> 약세 매수)를 미국 주식용으로 변환 (references/valuation-and-one-off-checks.md:L14-L16 "Japan-style PER x PBR" 언급) |
| 분류 | (b) 재무 필요 (주) + 진입 타이밍 규칙은 (a)류(5년 평균 수익률 대비 가격). 일부 (d) 정성(일회성 이익 체크리스트 YES/NO) |
| 필요 데이터 | FMP(배당 이력, key-metrics 연간 배당수익률 5년, ratios, 재무제표), 공시 이벤트 스캔 입력(JSON) (skills/kanchi-dividend-sop/SKILL.md:L21-L90, scripts/build_entry_signals.py:L87-L100, L254-L263) |
| 주요 파일 | references/default-thresholds.md, scripts/thresholds.py(SSOT), payout_safety.py, dividend_basis.py, verdict.py, build_entry_signals.py |
| 라이선스 | MIT |
| 이식 판단 | 채택(핵심): "5년 평균 배당수익률 + alpha(0.5%p)" 매수 목표가 = 연 DPS / (평균수익률+alpha) 를 진입 트리거로, 안전 3중 검사(배당성향·FCF성향·이자보상)를 위원회 가치 관점/리스크 게이트로, 40/30/30 분할을 사이징으로 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | Step1 수익률 하한 | 프로파일별 income-now 4.0%, balanced 3.0%, growth-first 1.5%; 기본 문서값 3.5%; 극단 수익률(>=8.0%) 함정 플래그는 심층 검사 강제 | scripts/thresholds.py:L21-L25; references/default-thresholds.md:L9-L10, L35-L39 |
| 2 | 수익률 산식 | 정기 선행수익률 = 최근 선언 정기배당 x 주기 추정 빈도 / 가격 (TTM·특별배당 제외) | SKILL.md:L117-L123 |
| 3 | 특별배당 판별 | 직전 정기 중앙값의 1.5배 초과, 3.0배 이상은 즉시 특별, 1.5~3배는 이후 1.2배 이내로 복귀하면 특별 | thresholds.py:L37-L45 |
| 4 | 변동배당 정책 | 12개월 정규화 잔차 변동계수(CoV)>0.35 이면 variable_policy -> FAIL | thresholds.py:L50; SKILL.md:L126-L128 |
| 5 | 삭감·중단·동결 | cut/suspension -> FAIL, freeze(주기+45일 유예 후 동일액) -> HOLD-REVIEW; 정기배당 4회 미만이면 판정 불가 | thresholds.py:L54-L63; SKILL.md:L126-L129 |
| 6 | 데이터 신선도 | 정기수익률이 하한 +-0.20%p 이내이고 최신 선언 미확인이면 STEP1-RECHECK(하드 FAIL 금지) | thresholds.py:L32; SKILL.md:L130-L136 |
| 7 | Step2 안전(소비재/일반) | FCF 배당성향>100% FAIL; 조정EPS 배당성향>85% FAIL; >70% 주의; FCF성향>80% 주의; 조정EPS 없으면 HOLD-REVIEW | payout_safety.py:L173-L190; thresholds.py:L66-L69 |
| 8 | 기타 기준 | 매출·EPS 5년 CAGR>0, 배당 5년 비하락, 순부채 3기 연속 상승 시 경고, 이자보상배율>=3.0 (<2.5 주의), GAAP-조정EPS 괴리>25% 일회성 플래그 | default-thresholds.md:L11-L17; thresholds.py:L78 |
| 9 | 섹터 분기 | 은행: 예금 beta>0.50, NPL/NCO 악화, CET1·CRE 집중도 필수; 유틸: FFO/Debt<0.13 주의, 요금 케이스 불리 시 HOLD-REVIEW; 보험: 영업EPS 성향>0.85 | thresholds.py:L72-L74; payout_safety.py:L192-L252 |
| 10 | Step3 밸류 | 은행·보험 P/TBV(과거 밴드 초과 시 거절), REIT P/FFO(5년 중앙값 이하), 성장 경량 PER/PFCF 5년 범위 하단 절반, 성숙 PFCF/수익률>5년 평균; 지표 불일치는 HOLD-FOR-REVIEW | references/valuation-and-one-off-checks.md:L5-L18 |
| 11 | Step4 일회성 | 자산매각 이익, 소송·세금 일회성, 매출 대비 마진 확대, 경영진 반복 "비경상" 표기, 부채 증가·자산 매각으로 배당 지탱 중 2개 이상 YES면 강등/거절 | valuation-and-one-off-checks.md:L20-L28 |
| 12 | Step4b 구조 이벤트 | 합병 거래가>시총 10%, 신주 발행>10%, 레버리지 변화>0.5x EBITDA이면 구조 이벤트; 최근 4분기 내 완료 합병은 GAAP EPS 왜곡 간주 | thresholds.py:L81-L86 |
| 13 | Step5 진입 목표가 | 목표수익률 = 5년 평균 수익률 + alpha(기본 0.5%p; 안정 대형 0.3, 고변동 0.8~1.0); buy_target = 연 배당/(목표수익률/100); 가격<=목표면 TRIGGERED, 아니면 WAIT, drop_needed = max(0,(가격-목표)/가격*100) | build_entry_signals.py:L254-L275; default-thresholds.md:L41-L62 |
| 14 | 분할매수 | 40%->30%->30%; pre_order_blockers 또는 t1_blocked 이면 1차는 보류하거나 20% 이하 추적 물량 | SKILL.md:L205-L212 |
| 15 | 포트폴리오 제약 | 종목수 15~30, 단일<=8%(원가), 섹터<=25%, 고수익 버킷(리츠·통신·유틸 합)<=35%, 동일 섹터 PASS 4개 이상이면 CLUSTER-RISK | default-thresholds.md:L66-L70; thresholds.py:L89-L93 |
| 16 | 최종 판정 합성 | FAIL > STEP1-RECHECK > HOLD-REVIEW > PASS-CAUTION > CONDITIONAL-PASS > CLEAN-PASS; Step1 FAIL이나 안전 FAIL 즉시 FAIL, 안전 미평가면 PASS 불가 | scripts/verdict.py:L29-L99; thresholds.py:L96-L103 |

**점수·등급**: 수치 점수 없이 규칙 기반 티어(CLEAN-PASS 등 6단계)만 존재(thresholds.py:L96-L103).
**출력 형식**: 종목별 JSON(schema_version=2: dividend flags, payout, 진입 신호, run_context, evidence), CSV, 마크다운 (build_entry_signals.py:L452-L560, thresholds.py:L15).
**SKILL.md와 코드 차이**: 임계값은 thresholds.py가 단일 출처(주석 thresholds.py:L3-L5)이며 default-thresholds.md는 미러. 문서 기본 yield 3.5% vs 코드 balanced 3.0% [차이: 문서는 기본 3.5, 코드 balanced 프로파일 3.0].
**한국 시장 적용**: 5년 평균 시가배당률은 KRX/DART 연도별 시가배당률로 계산 가능. 한국은 연 1회 결산배당 비중이 높아(분기배당 일부 대형주) 선언 주기 추정 대신 직전 확정 DPS 사용, 배당기준일 제도 변경 이후 배당금 확정 시점 불확실 [추정]. 특별배당 판별(1.5x/3x), CoV>0.35 변동배당, 삭감 FAIL은 DPS 연간 이력만으로 이식 가능. FCF=영업CF-CAPEX는 DART 현금흐름표로 계산. 이자보상배율(영업이익/이자비용)도 DART 가능. 한국 은행·보험·금융지주는 CET1·BIS비율 별도 항목 필요, 섹터는 GICS가 아닌 KRX/WICS 업종이라 매핑표 필요. 거래세·배당소득세(15.4%) 반영 시 수익률 하한 상향 검토 [추정].

### kanchi-dividend-review-monitor — 보유 배당주 리뷰 트리거 T1~T6
| 항목 | 내용 |
|---|---|
| 기법·출처 | 보유 종목 점검 큐. 입력은 보유 현황 JSON, SOP의 dividend flags(T6) 소비 |
| 분류 | (b) 재무 / 사후 모니터링 (리스크 게이트·청산 검토) |
| 필요 데이터 | 배당 이력, 현금흐름, 순부채·이자보상 이력, 공시 텍스트(Item 4.02 등), 영업지표 추세 (skills/kanchi-dividend-review-monitor/references/input-schema.md; scripts/build_review_queue.py:L67-L330) |
| 라이선스 | MIT |
| 이식 판단 | 채택: T1(삭감)·T2(커버리지)·T3(신용)·T5(구조 쇠퇴)를 보유 종목 사후 점검/청산 후보 플래그로 |

| # | 트리거 | 규칙 | 근거 |
|---|---|---|---|
| 1 | T1 배당 삭감·중단 -> REVIEW | latest_regular < prior_regular*0.99 또는 <=0 또는 피드 없음 (일 단위) | references/trigger-matrix.md:L15; build_review_queue.py:L67-L98 (L89) |
| 2 | T2 커버리지 악화 | 분모(FCF, REIT는 FFO/AFFO, BDC는 NII)<=0이고 배당>0, 또는 커버리지 비율>1.0이 2기 연속이면 REVIEW, 1기면 WARN (분기) | trigger-matrix.md:L16, L28-L42; build_review_queue.py:L100-L168 |
| 3 | T3 신용 스트레스 | 순부채 3기 연속 상승 AND (이자보상 하락 또는 <2.5 또는 (자사주+배당) > FCF*1.10) -> REVIEW; 부채 상승만, 또는 이자보상 하락&약함 -> WARN | build_review_queue.py:L171-L232 |
| 4 | T4 거버넌스·회계 | Item 4.02, 비신뢰 통보, 재작성, 중대한 결함, SEC 조사 -> REVIEW | trigger-matrix.md:L18; build_review_queue.py:L235-L260 |
| 5 | T5 구조적 쇠퇴 | 점수 = [5년 매출 CAGR<0] + [마진 하락] + [가이던스 하락] + [배당성장 정체]; >=3 REVIEW, 2 WARN | build_review_queue.py:L262-L310 |
| 6 | T6 배당정책 변경 | cut/variable -> REVIEW, freeze/special -> WARN | trigger-matrix.md:L20; build_review_queue.py:L312-L370 |
| 7 | 에스컬레이션 | OK < WARN < REVIEW, 복수 발동 시 최고 심각도. WARN=다음 체크포인트·추가매수 보류, REVIEW=즉시 검토·추가매수 보류 | trigger-matrix.md:L5-L9, L37-L39 |

**한국 적용**: T1·T2·T3·T5는 DART 연·분기 데이터로 계산 가능(분기 지연 45일, 사업보고서 90일). T4는 DART 공시 키워드(감사의견 비적정/한정, 횡령·배임, 관리종목 지정, 불성실공시)로 대체 가능 [추정]. 일봉 엔진에서는 T1/T4를 "보유 종목 청산·신규진입 차단 게이트"로 쓰는 것이 현실적.

### kanchi-dividend-us-tax-accounting — 요약
미국 배당세(적격/일반 배당, 1099-DIV, 보유 기간, 계좌 위치) 워크플로. 입력 ticker, instrument_type, account_type, hold_days_in_window (skills/kanchi-dividend-us-tax-accounting/SKILL.md:L14-L28). 미국 세제 전용이라 한국 이식 대상 아님(분류 d). 한국은 배당소득세 15.4%, 금융소득 연 2천만 원 초과 시 종합과세 [추정]. 보류.

### finviz-screener — 요약
자연어를 FinViz 필터 코드로 바꿔 URL을 만들어 브라우저로 여는 도구. 공개 스크리너는 키 불필요, Elite는 $FINVIZ_API_KEY 자동 감지, 필터 검증으로 URL 주입 방지 (skills/finviz-screener/SKILL.md:L8-L19, scripts/open_finviz_screener.py:L107-L240; 필터 목록 references/finviz_screener_filters.md 1988줄). 규칙·점수 없음, 외부 서비스 의존 UI 도구. 분류 (d)(도구), 이식 보류. 스크리너 필터 문자열은 value-dividend/dividend-growth 스킬의 FINVIZ 필터(`fa_div_o3`, `fa_pe_u20`, `ta_rsi_os40` 등)에서 임계값 참고용으로만 가치.

#### 그룹 소결
이식 추천(우선순위):
1. 배당 진입 목표가: 목표수익률 = 5년 평균 시가배당률 + 0.5%p(안정 0.3, 고변동 0.8~1.0), buy_target = 연 DPS/목표수익률, 분할 40/30/30, 차단 시 20% 추적물량 (kanchi-dividend-sop/scripts/build_entry_signals.py:L254-L275; SKILL.md:L205-L212). 일봉+DART DPS만으로 구현 가능, 진입 트리거+사이징.
2. 배당 안전 게이트: 배당성향 70% 주의/85% FAIL, FCF 성향 80% 주의/100% FAIL, 이자보상 <2.5 주의, 순부채 3기 상승 경고 (payout_safety.py:L173-L190; build_review_queue.py:L195-L232). 위원회 가치/배당 관점의 점수기·리스크 게이트.
3. 확신도 -> 노출/사이징 표: 80/60/40/20 구간 -> 주식비중 90-100/70-90/50-70/20-50/0-20, 단일종목 25/15/10/5/3%, 종목수 8/12/15/20/25, 수렴도 = 100 - 3.33*표준편차 (+-15 보정) (stanley-druckenmiller-investment/scripts/scorer.py:L177-L231, L342-L415; allocation_engine.py:L137-L165). 위원회 합의 점수 -> 레짐 노출 상한에 직접 대응. 가중치 18/18/12/18/12/10/12도 참고.
4. RSI 눌림 점수·분할진입: RSI<=25 20점, <=30 18, <=35 15, <=40 12; RSI<30은 50% 선진입 후 >30 확인 추가, 손절 3-5/5-8/8-10% (dividend-growth-pullback-screener/scripts/screen_dividend_growth_rsi.py:L665-L676; references/rsi_oversold_strategy.md:L205-L209). 일봉만으로 가능.
5. 가치 지속성 필터 묶음: 배당 TTM CAGR>=4%(가치형)/12%(성장형), 연도별 95% 무삭감, D/E<2.0, 유동비율>1.0, 매출·EPS 3년 추세 양, 안정성 점수 (value-dividend-screener/scripts/screen_dividend_stocks.py:L390-L448, L633-L660, L844-L873). DART로 대체 가능.
6. 수급 점수(KRX 대체): 기관 13F 변화 신호(>15% 강, 5-15% 중, 신뢰도 A/B/C)를 외국인/기관 순매수 강도·보유비중 변화로 치환(제안식은 institutional-flow-tracker 절). 보류: us-undervalued-growth는 컨센서스 의존으로 패널티 표만 참고, 그 외 Kanchi 세무·FinViz 보류.


---

## 18. 기술적 분석·테마·페어·전략 연구 파이프라인 (tradermonty)
> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, MIT) · 범위: pair-trade-screener, edge-*, theme-detector, technical-analyst, backtest-expert, residual-edge-analyzer 외 짧게 10개

### pair-trade-screener — 페어 트레이드 스크리너
| 항목 | 내용 |
|---|---|
| 기법·출처 | 상관 필터 → OLS 헤지비율 → ADF 공적분(Engle-Granger 단순형) → AR(1) 반감기 → 90일 롤링 z-score. 원저자 표기는 저장소 오너(tradermonty), 학술 출처 명시 없음 [추정: 고전 통계차익] |
| 분류 | (a) 일봉(종가)만으로 구현 가능. 단 공매도 가능 전제 |
| 필요 데이터 | FMP API 키 필수(유료/무료 플랜 의존): 섹터 스크리너(시총>=20억달러, limit 1000)와 일봉 종가(adjClose 우선, 없으면 close). 거래량은 코드에서 안 씀 |
| 주요 파일 | skills/pair-trade-screener/scripts/find_pairs.py, analyze_spread.py, references/trade_rules_and_reporting.md |
| 라이선스 | 저장소 MIT. 외부 의존 statsmodels(BSD), FMP API 약관 |
| 이식 판단 | 부분 채택: 공적분·반감기·z-score 계산식은 연구/검증 도구로. 매매는 KRX 공매도 제약으로 보류(우선주-보통주 등 한정 후보만) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 유니버스 | 섹터별 시총 >= 2,000,000,000 USD, isActivelyTrading, 조회 limit 1000 | scripts/find_pairs.py:L74-L104 |
| 2 | 데이터 기간 | lookback 기본 730일, 최소 250일 강제(parser.error) | scripts/find_pairs.py:L548-L572 |
| 3 | 상관 | 가격 수준(레벨) Pearson, 정렬 후 관측 >= 100 아니면 None, 기본 min_corr 0.70 (수익률 상관 아님: 이는 약점) | scripts/find_pairs.py:L218-L226, L314-L322 |
| 4 | 헤지비율 | scipy linregress(B→A): A = a + beta*B; spread = A - beta*B (절편 제외) | scripts/find_pairs.py:L229-L239, L242-L250 |
| 5 | 공적분 | adfuller(spread, maxlag=1, regression='c'), p<0.05면 cointegrated (Engle-Granger 임계값이 아닌 표준 ADF p값 사용 [추정: 잔차 기반 검정은 p값이 낙관적]) | scripts/find_pairs.py:L242-L265 |
| 6 | 반감기 | AutoReg(spread, lags=1)의 phi; phi>=1 또는 phi<=0이면 None; HL = -ln2/ln(phi) | scripts/find_pairs.py:L268-L289 |
| 7 | z-score | 최근 90관측(부족하면 전체) 평균·표준편차(표본), z=(마지막 spread-평균)/std | scripts/find_pairs.py:L292-L306 |
| 8 | 신호 | z>2.0 → SHORT(A 매도, B 매수); z<-2.0 → LONG; 그 외 NONE | scripts/find_pairs.py:L343-L349 |
| 9 | 강도 | p<0.01 ★★★, p<0.05 ★★, 그 외 ☆ | scripts/find_pairs.py:L351-L355 |
| 10 | 순위 | (p값 오름차순, -abs(z)) 정렬. 반감기는 순위에 미반영, 결과 필터에도 미사용(공적분 pair만 보관) | scripts/find_pairs.py:L410-L418, L402 |
| 11 | 분석기 진입/청산 | entry |z|>=2.0(기본), exit 기본 0.0, exit<entry 강제; 공적분 아니면 NO TRADE | scripts/analyze_spread.py:L391-L409, L313-L316 |
| 12 | 분석기 롤링 z | window 90 롤링 평균/표준편차 | scripts/analyze_spread.py:L156-L162 |
| 13 | 반감기 등급 | <30일 Fast, <60일 Moderate, 그 외 Slow | scripts/analyze_spread.py:L279-L284 |
| 14 | 사이징 예시 | 배분액/2를 A에, B는 A금액*beta (달러 기준 beta 헤지; 주의: 가격레벨 beta는 수량 비율이지 금액 비율이 아님 → [차이/오류 가능]) | scripts/analyze_spread.py:L336-L357 |
| 15 | 문서 규칙: 청산 | z=0 청산, ±1.0에서 50% 분할청산, 손절 |z|>3.0, 90일 시간청산 | references/trade_rules_and_reporting.md:L31-L51 |
| 16 | 문서 규칙: 리스크 | 페어당 포트폴리오 10-20%, 동시 5-8쌍, 페어당 최대손실 2-3%, 스프레드 -5% 손절, 총 페어리스크 <=10% | references/trade_rules_and_reporting.md:L74-L81 |
| 17 | 문서 품질 기준 | 상관>=0.70, p<0.05, 반감기<90일(진입규칙은 <60일), 최근 6개월 상관 0.15~0.20 하락 시 제외, 평균거래량 500K주 미만 제외 | SKILL.md:L297-L306, L168-L169 |
| 18 | 거래비용 가정 | 레그당 왕복 0.1%, 페어 총 0.4%; z 임계값은 비용 초과해야 | SKILL.md:L312-L315 |

**점수·등급**: 종합 점수 없음. 등급은 p값 별(규칙 9)과 반감기 3단계(규칙 13)뿐.
**출력 형식**: JSON {metadata, pairs[]} (pair, correlation, beta, p값, adf_statistic, half_life_days, current_zscore, signal, strength, timestamp) (scripts/find_pairs.py:L357-L372, L438-L470); analyze_spread는 콘솔 리포트+ASCII z 차트.
**SKILL.md와 코드 차이**
- [차이] 문서 "반감기<60일/90일 필터"와 "롤링 상관 안정성 검사", "구조적 변화 없음 확인"은 find_pairs.py에 구현 없음(상관 단일 값, 반감기는 표시만). 분할청산·시간청산·리스크 한도도 분석기 출력 문구일 뿐 백테스트 코드 없음 (scripts/analyze_spread.py:L359-L362는 텍스트 출력).
- [차이] 문서 "Supports spread backtesting"이나 백테스트 로직 미확인(grep 결과 해당 함수 없음).
- 레벨 상관+레벨 ADF는 과적합/허위상관 위험 [추정].
**한국 시장 적용**: 후보 [추정]: 우선주-보통주(삼성전자/삼성전자우, 현대차/현대차2우B 등), 지주-자회사, 동일업종 대형주(KOSPI 업종 분류). 일봉 종가+수정주가 필요(KRX 배당·액면분할 보정 필수; 코드도 adjClose 사용). 공매도: 2025-03-31 재개되었으나 개인 대주 제약이 커서 한쪽 숏 레그 실현이 어려움 [추정] → 롱온리 변형(저평가 레그만 매수, 지수선물/ETF 인버스로 헤지) 또는 페어 신호를 "상대강도 필터"로만 사용. 비용: 매도 레그마다 거래세+농특세(약 0.20% 확인필요)+수수료+호가단위 슬리피지 → 문서 0.4% 가정은 한국에서 최소 0.5~0.8% 수준으로 상향 [추정]. 가격제한 ±30% 때문에 z>3 갭 손절이 슬립할 수 있음.

### edge-signal-aggregator — 엣지 신호 통합기
| 항목 | 내용 |
|---|---|
| 기법·출처 | 여러 스킬 출력(JSON/YAML)을 정규화 → 중복 병합 → 모순 처리 → 가중평균+합의 보너스×최신성 계수 → 순위. 자체 설계(학술 출처 없음) |
| 분류 | (a) 연구 도구 겸 위원회 결합 규칙 참고용: 입력은 다른 스킬 산출물이라 자체 데이터 요구 없음 |
| 필요 데이터 | 없음(로컬 JSON/YAML 산출물). 외부 API 없음 |
| 주요 파일 | skills/edge-signal-aggregator/scripts/aggregate_signals.py, assets/default_weights.yaml, references/signal-weighting-framework.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(결합 규칙): 위원회 결합 단계에 "독립 증거 수 기반 합의 보너스 + 같은 관점 반대신호 제외 + 최신성 감쇠" 이식 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 스킬 가중치 | edge_candidate_agent 0.25, concept_synthesizer 0.20, theme_detector 0.15, sector_analyst 0.15, institutional_flow_tracker 0.15, hint_extractor 0.10 (합 1.0); 미등록 스킬 기본 0.10 | assets/default_weights.yaml:L6-L13; scripts/aggregate_signals.py:L33-L40, L1243 |
| 2 | 점수 정규화 | 0-1은 그대로, 0-100은 /100, 선언 없으면 1<값<=100을 0-100으로 가정(assumed 플래그), 음수/NaN/범위초과는 무효 처리(점수 안 만듦); 등급 A=1.0 B=0.8 C=0.6 D=0.4 F=0.2 | scripts/aggregate_signals.py:L199-L250 |
| 3 | 방향 | LONG/SHORT/NEUTRAL. 섹터는 rotation_phase accumulation/markup→LONG, distribution/markdown→SHORT, trend up/down 폴백 | scripts/aggregate_signals.py:L604-L624 |
| 4 | 완전 중복(1단계) | (skill, evidence_id) 동일 재유입은 무보너스 병합, 최신 타임스탬프 우선, 동률이면 raw_score 최고 | scripts/aggregate_signals.py:L944-L975 |
| 5 | 유사 중복(2단계) | 방향 같아야 함; 티커 Jaccard >= 0.30 또는 제목 단어 Jaccard >= 0.60이면 병합(OR 조건). 함수 내부 폴백값은 0.50/0.80로 yaml과 다름 | scripts/aggregate_signals.py:L822-L837, L42-L48 |
| 6 | 모순 감지 | 같은 티커에 LONG과 SHORT: 같은 스킬=HIGH(양쪽 제외), 호라이즌 불겹침=LOW(로그만, 페널티 0), 그 외 MEDIUM(양쪽 점수 x(1-0.10)) | scripts/aggregate_signals.py:L1040-L1111, L1114-L1188; default_weights.yaml:L33-L36 |
| 7 | 호라이즌 버킷 | 일/<=12주/<=3개월=short, 12주 초과/<=6개월=medium, 그 이상=long; unknown은 겹침으로 간주 | scripts/aggregate_signals.py:L330-L366 |
| 8 | 기본 점수 | base = Σ(raw_i x w_i)/Σ w_i (기여 스킬 한정, 가중 평균) | scripts/aggregate_signals.py:L1239-L1250 |
| 9 | 합의 보너스 | 티어 = min(고유 evidence, 고유 event_fingerprint, 고유 skill 수); 티어2 +0.10, 티어>=3 +0.20, 아니면 0 (같은 증거 복사로 부풀리기 방지) | scripts/aggregate_signals.py:L1254-L1266; default_weights.yaml:L22-L25 |
| 10 | 최신성 | <1일 1.00, <=3일 0.95, <=7일 0.90, 그 이상·타임스탬프 없음 0.85 | scripts/aggregate_signals.py:L391-L407; default_weights.yaml:L28-L31 |
| 11 | 종합 | composite = clip((base + 합의보너스) x 최신성, 0, 1.0) | scripts/aggregate_signals.py:L1273-L1278 |
| 12 | 신뢰도 분해 | 합의 0.35 x (보너스/0.20) + 강도 0.40 x 평균 raw + 최신성 0.25 x 계수 (표시용) | scripts/aggregate_signals.py:L1280-L1292; default_weights.yaml:L39-L42 |
| 13 | 필터 | min_conviction 0.50 이상만 상위 목록; 순위는 composite 내림차순 | scripts/aggregate_signals.py:L1401-L1415; default_weights.yaml:L45 |

**점수·등급**: 0~1 conviction. 등급 라벨은 없음, 임계 0.50 컷만.
**출력 형식**: JSON(ranked_signals, dedup_log, contradictions, adjustment_log, 무효 입력 목록) + Markdown 대시보드 (scripts/aggregate_signals.py:L1299-L1520).
**SKILL.md와 코드 차이**: [차이] references/signal-weighting-framework.md:L87,L114는 병합 1건당 +0.05 보너스를 서술하나 코드는 Issue #510으로 제거(deprecated, 무시) (scripts/aggregate_signals.py:L1268). 유사 중복 로그의 similarity_score는 0.90 고정 (L1021-L1027).
**한국 시장 적용**: 입력 스킬을 우리 관점(추세·수급·테마·밸류 등)으로 치환하면 그대로 결합기로 사용 가능. 가중치는 관점 신뢰도에 따라 백테스트로 재추정 필요(문서 L213 자체도 분기 재조정 권고). 고유 증거/이벤트/관점 수의 min으로 합의 티어를 정하는 방식은 상관된 관점(같은 지표 파생)의 이중 계산 방지에 유용.

### edge-strategy-reviewer — 전략 초안 검토기
| 항목 | 내용 |
|---|---|
| 기법·출처 | 전략 초안(YAML)을 8개 기준(C1-C8) 규칙으로 채점하고 PASS/REVISE/REJECT 판정 + 13항목 편향 체크리스트 게이트. 자체 설계 |
| 분류 | (a) 연구 도구: 매매 신호 아님(검증 게이트로 적합) |
| 필요 데이터 | 없음(초안 YAML만). 가격 데이터 불필요 |
| 주요 파일 | skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py, references/review_criteria.md, assets/bias_checklist.yaml |
| 라이선스 | MIT |
| 이식 판단 | 채택(검증 단계): 전략 등록 전 정적 점검(조건 수, 예상 연간 기회, 손절·손익비, 위험 한도, 편향 체크리스트) |

**규칙·계산식 (코드 기준)**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 가중치 | C1 20, C2 20, C3 15, C4 10, C5 10, C6 10, C7 10, C8 5 (합 100) | scripts/review_strategy_drafts.py:L32-L41 |
| 2 | 심각도 | 점수 <30 fail, 30-59 warn, >=60 pass | scripts/review_strategy_drafts.py:L115-L120 |
| 3 | 판정 | C1/C2 fail → REJECT; 가중평균 confidence>=70 이고 fail 없음 → PASS; <35 → REJECT; 그 외 REVISE | scripts/review_strategy_drafts.py:L456-L480 |
| 4 | C2 과적합(코드) | 조건수=entry.conditions+trend_filter: >=13→10, 11-12→40, 8-10→60, 5-7→80, <5→90; 소수점 정밀 임계값(예 33.5, 1.73) 1개당 -10 | scripts/review_strategy_drafts.py:L164-L190, L79 |
| 5 | C3 표본 | 연간 기회 추정 = 252 (섹터 조건이면 //3, 레짐이 Neutral/Unknown 아니면 //2) x 0.8^조건수 x 0.85^추세필터수, 최소 1 | scripts/review_strategy_drafts.py:L219-L236 |
| 6 | C3 점수 | <10→10; 10-29→30~59 선형; 30-49→65~74; 50-99→75~85; >=100→85~95(200에서 캡) | scripts/review_strategy_drafts.py:L239-L254 |
| 7 | C5 청산 | stop_loss_pct>0.15 또는 take_profit_rr<1.5 → fail(10) | scripts/review_strategy_drafts.py:L311-L327 |
| 8 | C6 위험 | risk_per_trade>0.02 fail, >0.015 warn(40), max_positions>10 fail | scripts/review_strategy_drafts.py:L342-L364 |
| 9 | C7/C8/C1/C4 | 거래량 필터 없음 warn(50); invalidation 0개 fail, 1개 warn; thesis 5단어 미만 fail; 단일 레짐+레짐 검증계획 없음 warn (표는 review_criteria.md) | references/review_criteria.md:L17-L25, L77-L117 |
| 10 | 편향 게이트 | 13개 필수 항목(look-ahead, 생존편향, 유니버스 선정, 상장폐지, 실적발표 시점, 분할·배당 조정, 거래비용·슬리피지, 공매도 차입 가능성, 유동성·용량, 파라미터 다중성, walk-forward/OOS, 벤치마크 귀속, 레짐 의존성) 중 초안이 미선언이면 PASS→REVISE 강등(점수 불변) | assets/bias_checklist.yaml:L1-L54; scripts/review_strategy_drafts.py:L597-L617 |
| 11 | 내보내기 | PASS + export_ready_v1 + entry_family가 {pivot_breakout, gap_up_continuation, panic_reversal, news_reaction} | scripts/review_strategy_drafts.py:L25-L30, L483-L494 |

**점수·등급**: 항목 0-100, 종합 confidence 정수, 판정 3단계.
**출력 형식**: JSON/Markdown 리뷰(draft별 findings, verdict, revision_instructions, export_eligible, bias 결과) (scripts/review_strategy_drafts.py:L710-).
**SKILL.md와 코드 차이**: [차이] review_criteria.md는 C2를 >12 fail/>10 warn(3단계)로, C3를 3단계(<10/<30/>=30)로, 내보내기 가능군을 2개로 적었으나 코드는 C2 5단계(>=13 fail, 11-12 warn), C3 연속 보간, 내보내기군 4개. 코드 기준을 따른다. 편향 체크리스트는 SKILL 쪽 문서에 약술(assets 파일이 실체).
**한국 시장 적용**: 임계값(조건 12개 초과 과적합, 연 30회 미만 표본 부족, 손절 15%, 손익비 1.5, 거래당 위험 1.5-2%, 동시 10종목)을 그대로 검증 규칙으로 이식 가능. 체크리스트에 KRX 항목 추가: 상장폐지·관리종목, 공매도 가능 종목/대주, 가격제한폭 ±30%, 호가단위 슬리피지, 거래세, 수정주가.

### edge-candidate-agent — 엣지 후보 탐지기
| 항목 | 내용 |
|---|---|
| 기법·출처 | 일봉 OHLCV 전체 유니버스에서 피처(MA, 상대거래량, 갭, ATR%, 120일 RS) 계산 → 시장 레짐(RiskOn/Neutral/RiskOff) 점수화 → 패밀리별 마스크+0~100 우선순위 점수 → 리서치 티켓/전략 YAML 내보내기. 자체 설계 |
| 분류 | (a) 일봉만으로 구현 가능(연구 도구 겸 후보 스캐너; 일부 탐지기는 뉴스·선물 표 선택 입력) |
| 필요 데이터 | parquet 일봉 OHLCV(symbol,timestamp,open,high,low,close,volume) 필수, SPY 행이 있으면 레짐에 사용; 선택: 힌트 YAML, 뉴스 반응 표(symbol,timestamp,reaction_1d), 선물 맵. 외부 유료 API 없음 |
| 주요 파일 | skills/edge-candidate-agent/scripts/auto_detect_candidates.py, references/signal_mapping.md |
| 라이선스 | MIT (pandas/pyarrow 필요) |
| 이식 판단 | 채택(진입 트리거 + 레짐 필터): 패밀리 마스크와 점수식, 레짐 점수식을 KOSPI/KOSDAQ 폭으로 대체 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 피처 | ma20/50/200, 거래량 20일 평균→rel_volume, high20_prev(전일까지 20일 고가), close_pos=(C-L)/(H-L), gap=O/전일C-1, rs_120=C/C[-120]-1, ATR14 단순평균(TR)/C=atr_pct, 60일 롤링 z(ret_1d, rel_volume, gap, atr_pct; min 30) | scripts/auto_detect_candidates.py:L636-L685 |
| 2 | 거래 가능 유니버스 | close>=5(USD), 20일 평균거래량>=1,000,000, ma50·ma200 존재 | scripts/auto_detect_candidates.py:L693-L707, L1643-L1648 |
| 3 | RS 순위 | rs_120의 유니버스 내 백분위 (rs_rank_pct) | scripts/auto_detect_candidates.py:L709 |
| 4 | 레짐 점수 | risk_on = (SPY>MA200 ? 25:5) + clamp((%>MA50-0.35)/0.45)*35 + clamp((0.8-평균쌍상관20)/0.6)*20 + clamp((1.4-vol_trend)/0.8)*20; risk_off = (SPY<=MA200 ? 20:5) + clamp((상관-0.35)/0.45)*30 + clamp((vol_trend-0.95)/0.8)*30 + clamp((0.55-%>MA50)/0.45)*20; vol_trend=rv20/rv60 | scripts/auto_detect_candidates.py:L777-L790 |
| 5 | 레짐 라벨 | risk_off>=65 이고 (risk_off-risk_on)>=5 → RiskOff; risk_on>=65 이고 >=risk_off → RiskOn; 그 외 Neutral | scripts/auto_detect_candidates.py:L792-L797 |
| 6 | 피벗 돌파 마스크 | close>MA50>MA200, close>high20_prev, rel_volume>=1.5, close_pos>=0.55, rs_rank>=0.70 | scripts/auto_detect_candidates.py:L919-L926 |
| 7 | 피벗 돌파 점수 | rs_rank*40 + clamp(rel_vol/3)*20 + clamp(돌파폭/0.08)*20 + close_pos*10 + 레짐(RiskOn +10, Neutral +5, RiskOff -5) + 힌트부스트 - clamp((atr_pct-0.08)/0.07)*15 | scripts/auto_detect_candidates.py:L204-L231 |
| 8 | 갭상승 마스크 | gap>=0.04, rel_volume>=2.0, close_pos>=0.50, close>MA50 | scripts/auto_detect_candidates.py:L928-L933 |
| 9 | 갭상승 점수 | clamp(gap/0.12)*35 + clamp(rel_vol/4)*25 + close_pos*20 + 추세(C>MA50 +10, C>MA200 +10) + 레짐(+8/+4/-8) + 힌트 - clamp((atr_pct-0.10)/0.08)*10 | scripts/auto_detect_candidates.py:L234-L264 |
| 10 | 패닉 반전 마스크 | ret_1d<=-0.07, rel_volume>=1.8, close>0.85*MA200 | scripts/auto_detect_candidates.py:L1005-L1009 |
| 11 | 패닉 반전 점수 | clamp(|하락률|/0.18)*45 + clamp(rel_vol/4)*20 + (C>MA200 ? 15:5) + 레짐(RiskOff +12, Neutral +7, RiskOn +2) + 힌트x0.6 - clamp((atr_pct-0.14)/0.10)*12 | scripts/auto_detect_candidates.py:L267-L291 |
| 12 | 이상치 | 4개 지표 z 절대값>=2.0 기록; 시장 콤보: 쌍상관>=0.65 & vol_trend>=1.15 & %>MA50<=0.40 → riskoff_combo; %>MA50<=0.35 & SPY 일수익>0.003 → breadth_divergence | scripts/auto_detect_candidates.py:L821-L909 |
| 13 | 레짐전환(연구용) | 폭 변화>=+0.08 & 5일수익>0 & vol_trend<=1.05 → risk_on_transition; <=-0.08 & 5일수익<0 & vol_trend>=1.10 → risk_off; 점수 55+clamp((|Δ|-0.08)/0.12)*25 | scripts/auto_detect_candidates.py:L1092-L1101 |
| 14 | 상관 체인(리더-팔로워) | 리더 |ret_1d|>=4.5%(상위 6), 팔로워는 리더 1일 래그 상관>=0.25(상위 5) & 오늘 |수익|<1.5%; 점수=clamp(|리더수익|/0.12)*40 + clamp(래그상관/0.60)*35 + clamp(rel_vol/3)*15 + (C>MA50 ? 10:4); 보유 20D | scripts/auto_detect_candidates.py:L1165-L1205 |
| 15 | 달력 이상 | 같은 월 표본>=6, 평균 월수익>=2.5%, 승률>=60%; 점수=clamp(평균/0.10)*45 + 승률*30 + rs_rank*15 + clamp(rel_vol/2.5)*10 | scripts/auto_detect_candidates.py:L1265-L1286 |
| 16 | 뉴스 반응 | 점수=clamp(|reaction_1d|/0.12)*70+20 (표 입력 필요; 조건 |반응|>=6%, rel_vol>=2.0, close_pos>=0.4) | scripts/auto_detect_candidates.py:L1366-L1383 |
| 17 | 선물 트리거 | 매핑된 선물 수익 z>=2.0인 날 연동 종목; 점수=clamp(|z|/4)*60+20 | scripts/auto_detect_candidates.py:L1429-L1445 |
| 18 | 내보내기 가능군 | pivot_breakout→breakout, gap_up_continuation→earnings_drift만 export 가능(문서 기준; 코드 매핑에는 panic_reversal/news_reaction도 있음); regime_shift·sector_x_stock·calendar_anomaly·futures_trigger는 research-only | scripts/auto_detect_candidates.py:L29-L41; references/signal_mapping.md:L7-L19 |
| 19 | 힌트 부스트 | 종목 지정 힌트 +12, 종목 미지정 +6, 합계 상한 20 | scripts/auto_detect_candidates.py:L180-L201 |

**점수·등급**: 0-100 priority_score, 등급 없음(상위 N=10 티켓).
**출력 형식**: 일일 리포트(Markdown), 티켓 YAML, 워치리스트, 이상치 목록 (scripts/auto_detect_candidates.py:L454-L527, L1496-L1625).
**SKILL.md와 코드 차이**: [차이] signal_mapping.md는 panic_reversal을 research-only로 표기하나 코드의 ENTRY_FAMILY_TO_HYPOTHESIS에는 포함(L29-L34). 로컬 파일이라 판단 보류.
**한국 시장 적용**: 최소가격 5달러·거래량 100만주 기준은 KRX에서 가격(예: 1,000원 이상)·거래대금(예: 일평균 10억원 이상) [추정]으로 치환. 피벗 돌파(20일 고가 돌파+거래량 1.5배+RS 상위 30%+MA50>MA200)와 레짐 점수식은 일봉만으로 이식 가능(SPY 대신 KOSPI 지수 행). 가격제한 ±30%·호가단위가 큰 저가주에서 갭·ATR% 점수 왜곡 주의. 패닉 반전 -7%는 KOSDAQ 변동성 고려해 상향 조정 필요 [추정].

### theme-detector — 테마 탐지기
| 항목 | 내용 |
|---|---|
| 기법·출처 | FINVIZ 산업(약 145개) 다중기간 수익률 → 모멘텀 순위 → 키워드 템플릿으로 산업을 교차섹터 테마로 묶음 → 열기(Heat) + 생애주기 성숙도 + 신뢰도 3축 점수. 자체 설계 |
| 분류 | (c) 시장 폭·테마·ETF 필요(일봉만으로는 부족; 산업 분류+종목 RSI·PER까지 사용) |
| 필요 데이터 | FINVIZ(Elite API 키 권장, 공개 스크래핑 가능: 산업별 1W/1M/3M/6M/1Y 수익률), FMP(종목 지표·ETF 거래량 20일/60일), uptrend-dashboard 섹터 업트렌드 비율(외부 스킬), 선택: scan-hits 파일, 내러티브 점수, 히스토리 파일. WebSearch로 내러티브 확인(High 신뢰도 승격) |
| 주요 파일 | skills/theme-detector/scripts/calculators/{heat_calculator,lifecycle_calculator,industry_ranker,theme_classifier}.py, scorer.py, leadership.py, theme_matcher.py, theme_detector.py, theme_history.py |
| 라이선스 | MIT. FINVIZ/FMP 약관 별도(스크래핑 제약 가능) |
| 이식 판단 | 부분 채택: 점수 구조(열기 4요소 가중합+성숙도 5요소)와 divergence 규칙은 한국 테마/업종 지수에 이식(위원회 점수기 + 레짐/테마 필터). 데이터는 KRX 업종지수·테마 구성 종목 일봉으로 자체 계산 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 산업 가중수익 | 1W 0.10, 1M 0.25, 3M 0.35, 6M 0.30 가중합 → weighted_return; >0 bullish, 아니면 bearish; 순위 정렬은 강도(절대값) 기준 | scripts/calculators/industry_ranker.py:L17-L22, L53-L83 |
| 2 | 산업 모멘텀(순위용) | 100/(1+exp(-0.15*(|wr|-5))) | scripts/calculators/industry_ranker.py:L33-L36 |
| 3 | 테마 열기 | Heat = 0.35*모멘텀 + 0.20*거래량강도 + 0.25*업트렌드 + 0.20*폭; 없는 요소는 분모에서 제외(coverage 기록) | scripts/calculators/heat_calculator.py:L1-L9, L18-L23, L160-L200 |
| 4 | 열기용 모멘텀 | 100/(1+exp(-2.0*(ln(1+|wr|)-ln16))) → |wr|=15%에서 50, 5%→27, 30%→73, 50%→86 (theme_detector는 이 함수를 사용) | scripts/calculators/heat_calculator.py:L26-L43; scripts/theme_detector.py:L30-L33, L881 |
| 5 | 거래량 강도 | ratio=ETF 20일/60일 거래량 평균; min(100, sqrt(max(0, ratio-0.8))/sqrt(1.2)*100) (1.0→37, 1.5→76, 2.0→100) | scripts/calculators/heat_calculator.py:L46-L64 |
| 6 | 업트렌드 | 섹터별 min(80, ratio*100) + 10(ratio>MA10) + 10(slope>0), 가중평균; 하락 테마는 100-값 | scripts/calculators/heat_calculator.py:L67-L108 |
| 7 | 폭 | 방향과 같은 산업 비율 r: min(100, r^2.5*80 + min(20, 산업수*2)) | scripts/calculators/heat_calculator.py:L111-L130; scripts/theme_detector.py:L434-L450 |
| 8 | 열기 라벨 | >=80 Hot, >=60 Warm, >=40 Neutral, >=20 Cool, 그 외 Cold | scripts/scorer.py:L26-L37 |
| 9 | 성숙도 | 0.25*지속기간 + 0.25*극단성 + 0.25*가격극단포화 + 0.15*밸류에이션 + 0.10*ETF확산 | scripts/calculators/lifecycle_calculator.py:L1-L10, L15-L21 |
| 10 | 지속기간 | 1M/3M/6M/1Y 중 수익률 >+2%(하락은 <-2%)인 구간당 25점; 히스토리 있으면 min(100, 연속 횟수*10) | scripts/calculators/lifecycle_calculator.py:L24-L45; scripts/theme_history.py:L67-L68 |
| 11 | 극단성 | RSI>70 종목 비율(하락 테마 RSI<30)*200, 상한 100 | scripts/calculators/lifecycle_calculator.py:L47-L66 |
| 12 | 가격극단 포화 | 52주 고가와의 거리<=5% 종목 비율*200 (하락은 저가) | scripts/calculators/lifecycle_calculator.py:L69-L89 |
| 13 | 밸류에이션 | 중앙값 PER/22 = premium; min(100, max(0, (premium-0.5)*32)); PER 유효 3개 미만이면 제외 | scripts/calculators/lifecycle_calculator.py:L92-L108 |
| 14 | ETF 확산 | ETF 0개 0, 1개 20, <=3개 40, <=6개 60, <=10개 80, 초과 100 | scripts/calculators/lifecycle_calculator.py:L111-L126 |
| 15 | 생애주기 단계 | <20 Emerging, <40 Accelerating, <60 Trending, <80 Mature, 그 이상 Exhausting | scripts/calculators/lifecycle_calculator.py:L143-L158 |
| 16 | 신뢰도 | quant=모멘텀점수>50, breadth=업트렌드>55, narrative=스크립트에서는 False(웹검색 후 승격); 확인층 3→High, 2→Medium, 그 외 Low; 데이터 stale이면 1단계 강등; 커버리지 페널티(열기 coverage<0.75, 성숙도 coverage<0.60, scan-hits 없음) 최대 2단계 추가 강등 | scripts/theme_detector.py:L990-L1002, L503-L513; scripts/scorer.py:L40-L69 |
| 17 | 괴리 감지 | momentum-uptrend 차이 >=25: 양수면 narrow_rally(소수 주도, 취약), 음수면 internal_recovery(폭이 가격 선행) | scripts/theme_detector.py:L406-L433 |
| 18 | 테마 매칭 | 키워드(산업명) 매칭 수>=cross_sector_min(2) → 교차섹터 테마; 같은 섹터 상/하위 N=30 산업이 >=3개면 "섹터 집중" 테마; 후보 산업은 상위 N+하위 N만 | scripts/calculators/theme_classifier.py:L28-L100 |
| 19 | 주도주 스캔 규칙 | 5일 수익>=20%; EP9M: 거래량>=9,000,000 & rel_vol>=2 & 등락>=4%; 레인지 확장: 등락>=4%, ATR확장>=1.5, 종가위치>=0.75; 신고가: 종가>=52주고가(또는 거리<=1%); 고RS: >=90 | scripts/leadership.py:L297-L345 |
| 20 | 주도 점수 | 스캔유형 가중 5일20% 0.30, EP9M 0.25, 범위확장 0.20, 신고가 0.15, 고RS 0.10; 히스토리 있으면 50+z*15; Heat 블렌드 = max(base, 0.70*base + 0.30*leadership) | scripts/leadership.py:L17-L22, L145-L162, L488-L498 |
| 21 | 매칭 품질·최종 순위 | match 가중 산업 0.40, 고정 종목 hit 0.30(hit당 40), ETF 모멘텀 0.20(50+(비율-1)*50, 확인 비율>=1.2), 내러티브 0.10; rank_score = 0.75*heat + 0.25*match | scripts/theme_matcher.py:L13-L17, L126, L164; scripts/theme_detector.py:L923-L926 |

**점수·등급**: Heat 0-100 + 5라벨; 성숙도 0-100 + 5단계; 신뢰도 Low/Medium/High(스크립트 최대 Medium).
**출력 형식**: JSON 리포트 + Markdown(상위 N 상세, 강세/약세 테마, ETF·대표종목, 히스토리 가속도) (scripts/theme_detector.py:L1083-L1100; scripts/report_generator.py).
**SKILL.md와 코드 차이**: 모멘텀 함수가 두 개(산업 순위용 시그모이드 0.15/5 vs 열기용 로그-시그모이드); 문서 요약만 보면 하나로 읽힘 [차이 주의]. 신뢰도는 문서대로 코드상 High 불가(L16-L18 주석).
**한국 시장 적용 [추정]**: FINVIZ 산업=KRX 업종(WICS/KRX 업종지수) 또는 네이버 테마. 열기 4요소를 (테마 구성종목 가중수익, 구성종목 거래대금 20일/60일, 구성종목 중 20일선 위 비율, 상승 종목 비율)로 일봉에서 직접 계산 가능. EP9M 거래량 900만주는 한국에서 거래대금 기준으로 재정의. PER 22 기준은 KOSPI 평균 PER로 대체 필요. ETF 확산은 국내 테마 ETF 개수로 대체(데이터 구성 필요). 한국 테마주는 상한가·단기 과열이 잦아 성숙도(RSI>70 비율, 52주 고가 근접 비율)를 단기 과열 필터로 재활용할 만함.

### technical-analyst — 주봉 차트 기술적 분석
| 항목 | 내용 |
|---|---|
| 기법·출처 | 핵심은 사용자가 준 주봉 차트 이미지를 LLM이 읽고 추세·지지저항·MA(20/50/200주)·거래량·패턴·시나리오 2-4개를 서술(정성). 별도 보조 스크립트 하나: COT 역발상 확인용 주봉 가격행동 검사(Jason Shapiro의 COT contrarian 3단계 중 3단계라고 스크립트 docstring에 기재) |
| 분류 | 차트 분석 본체는 (d) 자동매매 부적합(정성·이미지). 보조 스크립트는 (a) 일봉→주봉 리샘플만으로 구현 가능 |
| 필요 데이터 | 본체: 차트 이미지, API 불필요. 스크립트: FMP 일봉(주봉 리샘플), 선택 입력으로 cot-contrarian-detector 리포트(JSON) |
| 주요 파일 | skills/technical-analyst/SKILL.md, references/technical_analysis_framework.md, scripts/weekly_price_action.py, scripts/check_weekly_price_action.py |
| 라이선스 | MIT |
| 이식 판단 | 본체 보류. 주봉 가격행동 감지기 3종(키 리버설, 실패 극단, 실패 돌파)+연속성 거부권은 부분 채택(진입/청산 트리거 또는 위원회 반전 관점) |

**규칙·계산식 (scripts/weekly_price_action.py, 코드 확인)**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 파라미터 | swing 13주, 극단 52주, 신호 최근성 4주, 최소 30주 | scripts/weekly_price_action.py:L31-L34 |
| 2 | 주간 키 리버설(과열 롱 쪽) | 해당 주 고가 > 이전 13주 최고가 AND 해당 주 종가 < 직전 주 저가(엄격 부등호); 숏 쪽은 대칭. 최근 4주 중 가장 최근 1건만 보고 | scripts/weekly_price_action.py:L153-L232 |
| 3 | 실패 극단 | 주중 고가가 이전 52주 최고가를 상향 돌파했으나 종가는 그 수준 아래 | scripts/weekly_price_action.py:L235-L281 |
| 4 | 실패 돌파 | 종가가 이전 52주 고가 상향 돌파(주 B) 후 3주 이내 종가가 그 수준 아래로 복귀; 첫 복귀만 인정 | scripts/weekly_price_action.py:L284-L365 |
| 5 | 연속성 거부권 | 신호 이후(없으면 최근 4주) 52주 종가 기준 새 종가 극단이 크라우드 방향으로 나오면 NOT_CONFIRMED(continuation_intact) | scripts/weekly_price_action.py:L368-L418, L512-L533 |
| 6 | 판정 | 거부권 없고 3개 감지기 중 하나라도 발동 → CONFIRMED; 아니면 NOT_CONFIRMED(no_reversal_evidence). 증거 부재는 확인으로 치지 않는 fail-closed | scripts/weekly_price_action.py:L512-L533 |
| 7 | 신뢰도 | 서로 다른 감지기 >=2개 발동 또는 (키 리버설 발동 & 52주 이상 윈도우의 극단) → HIGH, 아니면 MEDIUM (LOW는 미발행) | scripts/weekly_price_action.py:L536-L557 |
| 8 | 스윙 레벨 | 5주 프랙탈(양쪽 2주보다 엄격히 높은/낮은 주); 손절 기준은 역추세 방향의 가장 가까운 스윙 고/저 | scripts/weekly_price_action.py:L421-L489 |
| 9 | 차트 MA 해석 | 20/50/200주 MA, 골든/데드 크로스 20주 vs 50주(정성 기준) | references/technical_analysis_framework.md:L104-L117 |

**점수·등급**: 지표 계산기·점수 없음(본체). 스크립트는 CONFIRMED/NOT_CONFIRMED + HIGH/MEDIUM.
**출력 형식**: 본체는 reports/[SYMBOL]_technical_analysis_[날짜].md (SKILL.md:L26-L30); 스크립트는 JSON 판정.
**SKILL.md와 코드 차이**: 본체에 RSI/ATR/패턴 계산 코드는 없음(grep으로 확인한 지표 계산 함수 없음). 스크립트는 COT 파이프라인 확인용이라 SKILL.md 앞부분 설명(차트 이미지)과 용도가 다름.
**한국 시장 적용**: 이미지 기반 본체는 이식 불가. 주봉 3감지기는 KOSPI/KOSDAQ 종목 일봉→주봉 리샘플로 구현 가능(수정주가 필수). COT(선물 포지셔닝)는 한국에 직접 대응 없음; 대응 관점으로 KRX 투자자별 순매수 과열을 "크라우드"로 쓰는 변형 [추정].

### backtest-expert — 백테스트 방법론·평가기
| 항목 | 내용 |
|---|---|
| 기법·출처 | "아이디어를 두들겨 패라(20% 발상 / 80% 파괴 테스트)" 방법론 문서 + 요약 통계 5개 입력으로 0-100 품질점수와 게이트 판정을 내는 평가 스크립트. 백테스트 엔진 자체는 없음 |
| 분류 | (a) 연구 도구: 매매 신호 아님(검증 게이트) |
| 필요 데이터 | 없음. 입력은 사용자가 준 요약치(총 거래수, 승률, 평균 이익/손실 %, 최대낙폭, 테스트 연수, 파라미터 수, 슬리피지 테스트 여부) |
| 주요 파일 | skills/backtest-expert/scripts/evaluate_backtest.py, references/methodology.md, SKILL.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(검증 단계 게이트): 점수표와 차단 사유 우선순위를 우리 백테스트 리포트 합격 기준으로 이식 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 표본 점수(0-20) | <30거래 0; 30-99는 8~14 선형; 100-199는 15~19 선형; 200+ 20 | scripts/evaluate_backtest.py:L30-L51 |
| 2 | 기대값 | E = 승률*평균이익 - 패률*평균손실 (%); PF = (승률*평균이익)/(패률*평균손실); 부호는 Decimal 정밀 계산 | scripts/evaluate_backtest.py:L68-L96 |
| 3 | 기대값 점수(0-20) | <=0이면 0; 0-0.5%는 5~10; 0.5-1.5%는 10~18; >=1.5% 20 | scripts/evaluate_backtest.py:L99-L114 |
| 4 | 리스크 점수(0-20) | 낙폭 <20% 12점; 20-50% 선형 12→0; >=50% 전체 0 (override). PF 1.0→3.0을 0→8점 선형, 3.0+ 8점 | scripts/evaluate_backtest.py:L117-L156 |
| 5 | 견고성 점수(0-20) | 연수 <5 0; 5-9년 5~14; 10년+ 15. 파라미터 <=4 5점, 5-6 3점, 7 1점, 8+ 0점 | scripts/evaluate_backtest.py:L159-L191 |
| 6 | 실행 현실성(0-20) | 슬리피지/마찰 테스트 했으면 20, 아니면 0 | scripts/evaluate_backtest.py:L194-L199 |
| 7 | 점수 판정 | >=70 Deploy, >=40 Refine, 그 외 Abandon | scripts/evaluate_backtest.py:L208-L215 |
| 8 | 레드 플래그 | <30거래 high; 슬리피지 미검증 high; 낙폭>=50% high; 음의 기대값 high; 파라미터>=7 medium; 연수<5 medium; 승률>90% & 낙폭<5% medium(too_good, look-ahead 의심) | scripts/evaluate_backtest.py:L222-L304 |
| 9 | 차단 게이트 우선순위 | NOT_EVALUABLE(거래<30 또는 PF 오버플로) > REJECT(음/0 기대값, 낙폭>=50%) > RISK_LIMIT_EXCEEDED(사용자 낙폭 한도 초과) > VALIDATION_REQUIRED(슬리피지 미검증, <5년, too_good); 게이트 없을 때만 점수 판정 적용 | scripts/evaluate_backtest.py:L412-L436; SKILL.md:L190 |
| 10 | 슬리피지 가정 | 시총별: 초대형(>2000억달러) 0.01-0.02%, 대형 0.02-0.05%, 중형(20-100억달러) 0.05-0.10%, 소형(3-20억) 0.10-0.20%, 초소형 0.20-0.50%+; 스트레스는 1.5-2배; 최악 체결 호가±1-2틱 | references/methodology.md:L110-L125, L37-L40 |
| 11 | 민감도 | 손절 거리 기준의 50/75/100/125/150%, 목표가 80/90/100/110/120%로 격자; "고원"이면 견고, "스파이크/절벽"이면 취약 | references/methodology.md:L48-L49, L74-L83 |
| 12 | 워크포워드 | 학습 1-2년 → 검증 3년차 → 롤링; OOS 성과 <IS의 50%, 잦은 재최적화, 파라미터 급변은 경고 | references/methodology.md:L85-L95 |
| 13 | 표본/기간 문서 | 최소 30, 권장 100, 고신뢰 200+ 거래; 최소 5년, 권장 10년+, 전 사이클·다중 변동성 레짐 포함; 연도별 기대값 양(+)이 다수여야 함 | references/methodology.md:L134-L148, L58, L67 |

**점수·등급**: 5개 차원 각 0-20 합계 0-100, Deploy/Refine/Abandon + 최종 decision 7종.
**출력 형식**: JSON + Markdown 리포트 (scripts/evaluate_backtest.py:L507-L592).
**SKILL.md와 코드 차이**: 큰 차이 없음. 문서는 점수가 "진단용"이고 decision이 권위라고 명시(SKILL.md:L190); 이는 코드와 일치. 수수료는 "실제 브로커 요율"로만 서술되고 수치 기준 없음.
**한국 시장 적용**: 슬리피지 시총 구간을 원화 호가단위로 치환: 호가단위(2023-01-25~: 2천원 미만 1원, 5천 미만 5원, 2만 미만 10원, 5만 미만 50원, 20만 미만 100원, 50만 미만 500원, 이상 1,000원)로 "호가 ±1-2틱" 최악 체결을 직접 계산 가능. 매도 거래세+농특세(2026년 합계 약 0.20% 확인 필요)+수수료를 별도 비용으로 반영. 소형 KOSDAQ은 0.2-0.5%+ 구간 적용 [추정]. 이 평가기 점수표는 그대로 이식 가능.

### residual-edge-analyzer — 잔차 엣지(알파) 분석기
| 항목 | 내용 |
|---|---|
| 기법·출처 | 전략 수익률을 사전 선언한 기준(시장, 동일가중, 모멘텀, 섹터 등) 수익률에 절편 포함 OLS 회귀, Newey-West HAC t값, 롤링 안정성, 대체 기준 민감도, 레짐별 active return 분해. 순수 파이썬 직접 구현(statsmodels 불사용으로 보임) |
| 분류 | (a) 연구 도구: 매매 신호 아님(백테스트 사후 검증 게이트) |
| 필요 데이터 | 날짜 있는 전략 수익률 CSV + 기준 수익률 열 + JSON 명세. 요약 지표(CAGR, 샤프)만으로는 불가 |
| 주요 파일 | skills/residual-edge-analyzer/scripts/analyze_residual_edge.py, references/methodology.md, references/input-contract.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(사후 분석/검증): 우리 전략 수익률을 KOSPI·동일가중·모멘텀 기준에 회귀해 "시장 베타 아닌 알파" 확인 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 모형 | r_t = alpha + beta'f_t + e_t; 연율화 252(일)/52(주)/12(월); alpha 연율 = 절편 x 연율화계수(산술) | references/methodology.md:L5-L16; scripts/analyze_residual_edge.py:L26, L903 |
| 2 | 잔차 엣지 비율 | 연율 alpha / 연율 잔차 변동성(잔차 평균 샤프 금지: 절편이 있으면 평균 0) | references/methodology.md:L17-L23; scripts/analyze_residual_edge.py:L901-L903 |
| 3 | HAC 래그 | 자동 = floor(4(n/100)^(2/9)) | references/methodology.md:L27-L29; scripts/analyze_residual_edge.py:L180 |
| 4 | 기본 임계값 | R² 기준설명 >=0.75; 약한 엣지 비율 <=0.50; 잔차 엣지 비율 >=0.75; alpha t >=2.0; 롤링 양(+) alpha 비율 >=0.60 | scripts/analyze_residual_edge.py:L27-L33 |
| 5 | 표본 | minimum_observations 60, regime 최소 20, 롤링 창 기본 일 63/주 52/월 24, 롤링 창 개수 최소 12 | scripts/analyze_residual_edge.py:L513-L518 |
| 6 | 롤링 창 최소 | max(20, 5*(요인수+1)) 이상이어야 사용 | scripts/analyze_residual_edge.py:L761-L766 |
| 7 | 분류 | 롤링 불가/실패창 있으면 RESIDUAL_FRAGILE; 비율>=0.75 & t>=2 & 롤링 양 비율>=0.6 → RESIDUAL_EDGE; R²>=0.75 & |비율|<=0.5 & |t|<2 → BASELINE_EXPLAINED; 그 외 FRAGILE; 표본 미달 INSUFFICIENT_EVIDENCE | scripts/analyze_residual_edge.py:L845-L880; SKILL.md:L84-L91 |
| 8 | 다중공선성 | VIF ~1 양호, >5 점검, >10 또는 정의 불가면 계수 불안정 | references/methodology.md:L39-L47 |
| 9 | 의사결정 자격 | 기준 사전선언, gross/net 동일, 분석 범위(OOS/live/in-sample), 유니버스 point-in-time 중 하나라도 미선언이면 REVIEW_REQUIRED; 대체 기준 없으면 REVIEW_REQUIRED | SKILL.md:L36-L51, L90-L95 |

**점수·등급**: 4상태(RESIDUAL_EDGE, BASELINE_EXPLAINED, RESIDUAL_FRAGILE, INSUFFICIENT_EVIDENCE) + decision_eligibility.
**출력 형식**: JSON(모델별 alpha/t/R²/VIF/롤링/레짐) + Markdown (scripts/analyze_residual_edge.py:L1-).
**SKILL.md와 코드 차이**: 큰 차이 없음(문서 임계값이 DEFAULT_THRESHOLDS와 일치).
**한국 시장 적용**: 기준을 KOSPI/KOSDAQ 수익률, 동일가중 KRX 유니버스(상장폐지 포함 point-in-time), 모멘텀(12-1개월) 팩터로 구성. 일별 63일 롤링·표본 60일 기준은 그대로 사용 가능. 비용 gross/net 일치 요건은 거래세·수수료 반영 후 net으로 통일.

### 짧게 다루는 스킬 10개
- **sector-analyst** — TraderMonty 공개 CSV의 섹터 업트렌드 비율(키 불필요, 차트 이미지는 선택)로 섹터 로테이션·사이클 국면 판정. 과매수 비율>0.37, 과매도<0.097, 데이터 신선도 5일(skills/sector-analyst/scripts/analyze_sector_rotation.py:L61-L66); 경기민감(기술·경기소비·통신·금융·산업)/방어(유틸·필수소비·헬스·부동산)/원자재 분류와 early/mid/late/recession 국면별 주도·후행 섹터 표(L43-L108), 국면 적합도 = 주도 0.4 + 후행 0.3 + 추세정렬 0.3(L331-L374). 분류 (c) 시장 폭. 이식: 부분(업종지수 상승종목 비율로 대체, 레짐 필터). MIT.
- **options-strategy-advisor** — Black-Scholes 이론가·그릭스·전략 손익 시뮬레이션(scripts/black_scholes.py), FMP API로 가격·변동성·배당·실적일. 분류 (d)에 가까움(옵션·이론가, 일봉 규칙엔진과 무관). 이식: 보류(KRX 개별종목 옵션 유동성 낮음, 다만 KOSPI200 옵션은 [추정] 별도 검토). MIT.
- **edge-concept-synthesizer** — 탐지 티켓·힌트를 thesis, 무효화 신호, 플레이북을 가진 재사용 엣지 개념으로 추상화(scripts/synthesize_edge_concepts.py). 분류 (a) 연구 도구, LLM 보조 포함. 이식: 보류(우리 규칙엔진엔 개념 문서화 단계 불필요, 관점 메타데이터 구조만 참고). MIT.
- **edge-hint-extractor** — 일일 시장 요약·이상치·뉴스 반응을 hints.yaml로 변환(선택적 LLM 아이디어). 파이프라인 1단계(observe→abstract→design→pipeline). 분류 (c) 뉴스 필요. 이식: 보류. MIT.
- **edge-pipeline-orchestrator** — 후보 탐지→개념→설계→리뷰→수정→내보내기를 서브프로세스로 연결, 리뷰-수정 반복 최대 2회(skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py:L47). 분류 (a) 연구 도구. 이식: 워크플로 구조만 참고(검증 게이트 반복 2회 한도). MIT.
- **edge-strategy-designer** — 엣지 개념을 전략 초안 변형으로 변환. 리스크 프로필: conservative(거래당 위험 0.5%, 동시 3종목, 손절 5%, RR 2.2), balanced(1.0%, 5종목, 7%, 3.0), aggressive(1.5%, 7종목, 9%, 3.5) (skills/edge-strategy-designer/scripts/design_strategy_drafts.py:L71-L90). 분류 (a). 이식: 부분(리스크 프로필 3단계 수치는 리스크 게이트·사이징 기본값 후보; reviewer의 한도 1.5%/10종목/손절 15% 안에 들어감). MIT.
- **strategy-pivot-designer** — 백테스트 반복이 정체(국소 최적)일 때 구조가 다른 전략 피벗 제안. 감지: 기대값 점수>=15 & 리스크>=15 & 견고성<10 & (과최적화 or 단기 테스트) → 과적합 프록시; expectancy<0.3 & PF<1.3 & 슬리피지 테스트됨 → 비용에 패배; 낙폭>35% 또는 리스크 점수<=5 → 꼬리 위험; 반복>=3 & 최신 점수<30 & 단조 하락 → 포기(skills/strategy-pivot-designer/scripts/detect_stagnation.py:L120-L255). backtest-expert 점수표에 의존. 분류 (a). 이식: 사후 분석 규칙으로 채택 가능. MIT.
- **trade-hypothesis-ideator** — 시장 데이터·매매 로그에서 반증 가능한 가설 생성(순수 계산, 키 불필요; scripts/run_hypothesis_ideator.py, schemas/). 분류 (d)에 가까움(LLM 발상). 이식: 보류. MIT.
- **manifoldbt-backtester** — 선언형 전략 스펙을 OHLCV에 manifoldbt Rust 엔진으로 실행, 체결 로그를 라운드트립으로 묶어 backtest-expert 입력 8개를 산출. 수수료/슬리피지는 bps 입력(기본 0.0, 미지정이면 경고)(skills/manifoldbt-backtester/scripts/spec.py:L64, L132-L133, L168). 라이선스 주의: 파이썬 패키지 Apache 2.0, 컴파일된 엔진은 무료 Manifold-BT Engine License(무료 티어)(SKILL.md:L30-L32) → 외부 도구 제약. 이식: 보류(우리는 자체 파이썬 엔진 사용; 라운드트립→통계 변환 로직만 참고).
- **mt5-robot-tester** — MetaTrader 5 Strategy Tester CLI로 EA(로봇)를 3라운드(5개 이상 심볼 수익 & 최고 심볼 >=3x 예치금 → 최적 페어 백테스트 → 입력 5-6개를 ±50% 5% 스텝으로 순차 최적화), 최종 후보 조건: 개선 & 수익>=4x 예치금 & 최대낙폭<=12%(skills/mt5-robot-tester/SKILL.md:L18-L27). Windows+MT5 필수, 외부 터미널 의존. 분류 (d) 부적합(FX/CFD EA 선별). 이식: 보류.

#### 그룹 소결
이식할 규칙 6개(코드 확인 수치):
1. **검증 게이트(backtest-expert)**: 거래수<30 평가불가, 5년 미만 또는 슬리피지 미검증이면 VALIDATION_REQUIRED, 낙폭>=50% 거부, 승률>90% & 낙폭<5%는 too_good로 look-ahead 감사. 점수표(표본 20/기대값 20/리스크 20/견고성 20/실행 20; >=70 Deploy, >=40 Refine). (skills/backtest-expert/scripts/evaluate_backtest.py:L30-L215, L412-L436)
2. **전략 정적 검토(edge-strategy-reviewer)**: 조건 수 11개 이상 경고·13개 이상 실패, 소수점 임계값당 -10, 연간 기회 추정 252x0.8^조건수x0.85^추세필터수가 30 미만이면 표본 부족, 손절>15% 또는 RR<1.5 실패, 거래당 위험>2% 실패, 동시종목>10 실패, 가중 70 이상 PASS/35 미만 REJECT, 13항목 편향 체크리스트 게이트. (skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py:L164-L254, L456-L480; assets/bias_checklist.yaml)
3. **위원회 결합 규칙(edge-signal-aggregator)**: 가중평균(0.25/0.20/0.15/0.15/0.15/0.10) + 독립 증거·이벤트·관점 수의 최솟값으로 합의 티어(2개 +0.10, 3개 이상 +0.20) x 최신성(1.0/0.95/0.90/0.85), 같은 관점의 반대 신호는 양쪽 제외, 서로 다른 관점의 같은 호라이즌 충돌은 -10%, 컷 0.50. (skills/edge-signal-aggregator/scripts/aggregate_signals.py:L1040-L1292)
4. **레짐 점수 + 진입 트리거(edge-candidate-agent)**: RiskOn/RiskOff 점수식(지수 200일선, 20일 평균 쌍상관, 변동성 비율 rv20/rv60, 50일선 위 비율)과 65점·5점차 라벨링; 피벗 돌파 마스크(20일 고가 돌파, 거래량 1.5배, close_pos>=0.55, RS 상위 30%, MA50>MA200)와 0-100 점수식. (skills/edge-candidate-agent/scripts/auto_detect_candidates.py:L204-L231, L777-L797, L919-L926)
5. **테마 열기 점수(theme-detector)**: Heat = 0.35 모멘텀 + 0.20 거래량 + 0.25 업트렌드 + 0.20 폭, 폭 = r^2.5*80+보너스, 괴리(모멘텀-업트렌드 >=25) 경고, 성숙도 = 지속기간·RSI>70 비율·52주 고가 5% 이내 비율 등으로 과열 판정(20/40/60/80 단계). 한국은 업종/테마 구성종목 일봉으로 자체 계산. (skills/theme-detector/scripts/calculators/heat_calculator.py, lifecycle_calculator.py)
6. **사후 알파 검증(residual-edge-analyzer) + 페어 통계 도구(pair-trade-screener)**: alpha t>=2.0, 잔차 엣지 비율>=0.75, R²>=0.75면 기준설명, 롤링 양 알파 비율>=0.60, 표본>=60; 페어는 ADF p<0.05, 반감기 -ln2/ln(phi), 90일 z-score |z|>=2 진입/0 청산/3 손절/90일 시간청산을 연구 도구로(공매도 제약으로 매매는 롱온리 변형 또는 보류). (skills/residual-edge-analyzer/scripts/analyze_residual_edge.py:L27-L33, L845-L880; skills/pair-trade-screener/scripts/find_pairs.py:L242-L306)


---

## 19. 메타·일정·정성 분석 스킬과 워크플로 정의 (tradermonty)

> 저장소: tradermonty/claude-trading-skills (커밋 fdfff01, MIT) · 범위: skill-designer, skill-idea-miner, skill-integration-tester, dual-axis-skill-reviewer, trading-skills-navigator, earnings-calendar, economic-calendar-fetcher, fxmacrodata-calendar, market-news-analyst, scenario-analyzer, us-stock-analysis + workflows/*.yaml
>
> 이 묶음은 매매 기법이 아니라 스킬 개발 도구, 일정 수집기, LLM 서술형 분석이다. 그래서 SKILL.md 앞부분과 skills-index.yaml 항목, 코드 규모만 확인했다. 계산 규칙을 깊게 읽지는 않았다.

### 스킬 한 줄 표

| 스킬 | 하는 일(소스 확인) | 데이터 | 분류 | 이식 판단 |
|---|---|---|---|---|
| skill-designer | 아이디어 명세를 받아 새 스킬 폴더(SKILL.md·scripts·tests)를 만드는 Claude CLI 프롬프트 생성 (`skills/skill-designer/SKILL.md:L3`) | 로컬 | (d) 메타 | 해당 없음 |
| skill-idea-miner | Claude Code 세션 로그에서 스킬 아이디어를 뽑아 점수화·백로그 (`skills/skill-idea-miner/SKILL.md:L3`) | 로컬 로그 | (d) 메타 | 해당 없음 |
| skill-integration-tester | 다중 스킬 워크플로의 스킬 존재, JSON 계약, 파일명, 핸드오프 검증 (`skills/skill-integration-tester/SKILL.md:L3`) | 로컬 | (d) 메타 | 구조만 참고: 위원회 입력 JSON의 계약 검사 아이디어 |
| dual-axis-skill-reviewer | 결정론 검사 + LLM 리뷰 2축 점수로 스킬 품질 게이트(예: 90점 이상) (`skills/dual-axis-skill-reviewer/SKILL.md:L3`) | 로컬 | (d) 메타 | 해당 없음 |
| trading-skills-navigator | 자연어 목표를 받아 워크플로·스킬셋·API 프로필 추천 (`skills/trading-skills-navigator/SKILL.md:L2-L6`). 파이썬 약 2,400줄 | 로컬 | (d) 메타 | 해당 없음 |
| earnings-calendar | FMP로 다음 주 미국 실적 발표 일정 수집, 시가총액 20억 달러 초과만, 날짜·BMO/AMC로 정리 (`skills/earnings-calendar/SKILL.md:L3`, `L14`) | FMP | (c) 이벤트 일정 | 개념 채택: 실적 발표 전후 신규 진입 제한 필터. 한국은 DART 영업(잠정)실적 공정공시·IR 일정 공시로 대체 [추정] |
| economic-calendar-fetcher | FMP 경제 일정(중앙은행, 고용, CPI/PPI, GDP 등), 기본 7일. 스크립트는 원자료만 내고 영향도 판정은 어시스턴트가 함 (`skills/economic-calendar-fetcher/SKILL.md:L3`, `L12`, `L17`) | FMP | (c) | 개념 채택: 매크로 이벤트 당일 신규 진입 축소. 한국은 금통위 일정, 통계청 CPI, 미국 FOMC·CPI 일정을 직접 관리 [추정] |
| fxmacrodata-calendar | FXMacroData 공식 매크로 발표 일정(CPI, NFP, GDP, PCE, 소매판매, PMI, 중앙은행) (`skills/fxmacrodata-calendar/SKILL.md:L3`). 파이썬 약 280줄 | FXMacroData(키 선택) | (c) | 위와 같음 |
| market-news-analyst | 지난 10일 시장 뉴스의 영향 분석, 파이썬 코드 없음 (`skills/market-news-analyst/SKILL.md:L3`) | 웹 검색 | (d) | 보류 |
| scenario-analyzer | 뉴스 헤드라인 하나로 18개월 시나리오 작성, scenario-analyst 에이전트가 1차 분석하고 strategy-reviewer 에이전트가 2차 의견 (`skills/scenario-analyzer/SKILL.md:L2-L6`, `agents/scenario-analyst.md`, `agents/strategy-reviewer.md`). 파이썬 없음 | 웹 검색 | (d) | 보류. "1차 분석 + 독립 반론" 2단 구조만 위원회 설계 참고 |
| us-stock-analysis | 미국 종목 기본·기술 분석 보고서, 파이썬 없음 (`skills/us-stock-analysis/SKILL.md:L3`) | 사용자 입력·웹 검색 | (d) | 보류 |

### workflows/*.yaml — 스킬 연결 순서와 결정 게이트

저장소는 스킬을 어떤 순서로 묶고 어디서 멈출지를 `workflows/` 아래 15개 YAML로 정의한다(README는 이 파일들을 정본이라 부른다). 우리 엔진의 일일 파이프라인 순서를 정할 때 직접 참고할 만하다.

| 워크플로 | 단계(소스 확인) | 결정 게이트 |
|---|---|---|
| market-regime-daily | 1 market-breadth-analyzer → 2 uptrend-analyzer → 3 market-top-detector → 4 exposure-coach (`workflows/market-regime-daily.yaml:L54-L89`) | 4단계 exposure-coach 결과에서 판단(`L89`) |
| swing-opportunity-daily | 1 drawdown-circuit-breaker → 2 vcp-screener → 3 stockbee-momentum-burst-screener → 4 stockbee-exhaustion-hammer-screener → 5 canslim-screener → 6 theme-detector → 7 technical-analyst → 8 position-sizer → 9 breakout-trade-planner → 10 trader-memory-core → 11 pre-trade-discipline-gate (`workflows/swing-opportunity-daily.yaml:L92-L227`) | 1단계(서킷브레이커가 TRADING_ALLOWED인지, `L98-L101`), 7단계, 10단계, 11단계(`L162`, `L206`, `L227`) |
| 그 밖 | core-portfolio-weekly, earnings-weekly, kanchi-dividend-weekly, monthly-performance-review, multi-asset-opportunity-daily, portfolio-holdings-review, shapiro-contrarian, stockbee-20pct-study-daily, stockbee-ep-daily, stockbee-fluency-loop, strategy-research-pipeline, trade-memory-loop (`workflows/` 목록) | 각 파일의 decision_gate 항목 |

엔진 설계에 주는 시사점:
- 계좌 리스크 게이트(서킷브레이커)를 종목 탐색보다 먼저 둔다. 막히면 스크리너를 돌리지 않는다.
- 시장 레짐 판정(폭 → 추세 참여 → 천장 위험 → 노출 결합)을 종목 선별과 분리된 하루 1회 파이프라인으로 둔다.
- 여러 스크리너(VCP, 모멘텀 버스트, 망치형, CANSLIM, 테마)를 병렬 후보 생성기로 두고, 그 뒤에 사이징 → 매매계획 → 기록 → 주문 직전 규율 게이트를 직렬로 둔다. 다관점 위원회는 "후보 생성기 출력 → 점수 결합" 자리에 들어간다.

#### 그룹 소결
1. 워크플로 순서(계좌 게이트 → 레짐 → 후보 생성 → 사이징 → 계획 → 기록 → 주문 전 게이트)를 엔진의 일일 배치 순서로 채택한다.
2. 실적·매크로 일정 스킬은 "이벤트 리스크 필터" 개념만 채택한다. 한국 일정 데이터(DART 공시, 금통위, 통계청, 미국 지표)는 직접 수집해야 한다 [추정].
3. 나머지 메타·정성 스킬은 자동매매 엔진에 넣지 않는다.


---

## 20. 기타 주식 기법 스킬: A주 전략 · finance-skills(SEPA 등) · quant-skills
> 저장소들: shouldnotappearcalm-a-share-skill(8874bd1, MIT), himself65-finance-skills(a085078, MIT), shakeebshaan-claude-code-quant-skills(6b39f8f, MIT)

### a-share/macd-second-golden-cross — MACD 영하 2차 골든크로스(저점 다이버전스)
| 항목 | 내용 |
|---|---|
| 기법·출처 | MACD 바닥 다이버전스 + 0축 아래 2차 골든크로스(第一脚/第二脚). 저자 개인 실전 프레임(출처 인용 없음) |
| 분류 | (a) 일봉만으로 구현 가능(단, 문서뿐 코드 없음) / 일부 (c) 시장 필터 |
| 필요 데이터 | 일봉 OHLC, MACD(12,26,9), MA5/MA10 |
| 주요 파일 | shouldnotappearcalm-a-share-skill/macd-second-golden-cross/SKILL.md (140줄, 코드 없음) |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: 진입 트리거(위원회 점수기 1개 관점). 임계값이 거의 없어 직접 수치화 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 구조 | 선행 하락 존재 -> 1st foot(반등) -> 2nd foot(저점 재시험). "변허(虛)" = DIF 저점 상승 or 녹주 단축 or 2차 GC 위치가 1차보다 높음 | macd-second-golden-cross/SKILL.md:L21-L32 |
| 2 | 시험매수(B) | 2nd foot 변허 + DIF가 DEA 상향돌파(0축 아래) + 확인(단기선 회복/미세 박스 돌파/저점 미이탈 중 하나) | SKILL.md:L48-L55 |
| 3 | 포지션/손절 | 초기 10~30%(예시), 손절=2nd foot 저점 하회, 실패형 물타기 금지 | SKILL.md:L56-L59 |
| 4 | 포기(C) 조건 | 선행 하락 없음 / 2nd foot에서 MACD가 더 약함(녹주 더 길거나 저점 더 낮음) / 두 GC 사이 0축 상향 돌파 후 재하락 / GC 후 즉시 DC 또는 1~2일 내 2nd foot 저점 이탈 / 위 매물대 근접 / 지수·업종 주하락 | SKILL.md:L61-L69 |
| 5 | 10항목 체크리스트 | 항목 10개 중 7개 이상=시험매수 평가, 5~6=관찰, <=4=포기 | SKILL.md:L71-L89 |
| 6 | 파라미터 | 일봉 위주, MACD 12/26/9, 확인 MA5/MA10 | SKILL.md:L125-L129 |

**점수·등급**: 3단(관찰/시험/포기), 체크리스트 개수 기반(L86-L89). 수치 가중 없음.
**출력 형식**: 【형태결론】【구조증거】【실행계획】【리스크】 텍스트 템플릿(L93-L116).
**SKILL.md와 코드 차이**: 코드 없음. 윈도 길이, 저점 판별(pivot 폭), "상당한 하락"의 % 기준이 정의되지 않음 -> 이식 시 직접 정해야 함 [추정: 예 -20% from 60d high, pivot 5봉].
**한국 시장 적용**: 가격제한 폭 무관한 지표 규칙이라 그대로 가능. 거래대금 최소 필터(L133 "유동성 극히 나쁜 종목 제외")를 호가단위·거래대금 기준으로 수치화 필요.

### a-share/macd-trend-resonance-stock-picker — MA60 방향 + MACD 타이밍 공명 선별
| 항목 | 내용 |
|---|---|
| 기법·출처 | "균선이 방향, MACD가 리듬". 저자 프레임. 코드 없음 |
| 분류 | (a) 일봉(60분봉 항목 제외) + (c) 업종/지수 15점 |
| 필요 데이터 | 일봉, MA20/MA60, MACD, (60분 MACD), 업종/지수 상태, 이벤트 |
| 주요 파일 | macd-trend-resonance-stock-picker/SKILL.md (189줄, 코드 없음) |
| 라이선스 | MIT |
| 이식 판단 | 채택(점수식 그대로 위원회 "추세+모멘텀" 관점). 60분 10점은 일봉 대체 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 방향 하드필터 | MA60 상향 & 종가>MA60 = 통과; MA60 횡보/밀집 = 관찰만; MA60 하향 & 종가<MA60 = 제외 | SKILL.md:L38-L49 |
| 2 | MACD 우선순위 | 0축 위 GC > 적주 축소 후 재확대 > DIF/DEA 동반 상승 > 60분 동조. 일봉 MACD가 0축 아래면 관찰만 | SKILL.md:L51-L61 |
| 3 | A/B/C/D 등급 | A: MA60상향+종가>MA60+MACD 0축 위+최근 GC/적주 재확대. B: 0축 근처 복귀+적주 회복. C: 추세 OK/MACD 모순. D: MA60 하향·MA60 아래 지속·DC 후 약화·섹터 약세 | SKILL.md:L63-L104 |
| 4 | 진입 트리거 | 최근 5~10일 박스 고점 돌파 / MA20·MA60 눌림 후 재상승 / 60분 MACD GC / 전일고가·구간고점 거래량 돌파 | SKILL.md:L109-L113 |
| 5 | 무효화 | 종가 MA60 하회, 트리거봉 저점 이탈, DIF가 DEA 하향 + 거래량 약화 | SKILL.md:L120-L123 |
| 6 | 청산 | 감축: MACD 상단 다이버전스/적주 연속 축소/60분 선 DC. 전량: MA60 유효 이탈, 일봉 MACD 0축 하향, 돌파 실패 후 거래량 동반 하락 | SKILL.md:L125-L134 |
| 7 | 시장 필터 | 업종·지수 역풍이면 등급 최소 1단계 하향, 큰 비중 금지 | SKILL.md:L136-L144 |

**점수·등급 (100점)**: 추세 40(MA60 방향 20, 종가-MA60 위치 10, MA20/60 정배열 10) + MACD 35(0축 위 15, GC/적주 재확대 10, 60분 동조 10) + 업종·시장 15 + 리스크·이벤트 10. 매핑 85-100 EXECUTE, 70-84 LIGHT, 55-69 OBSERVE, <55 AVOID (SKILL.md:L146-L162). 세부 소항목 배점의 내부 기준(예: 방향 20점을 어떻게 부분점수)은 미정의.
**출력 형식**: 표본풀/시각 -> A·B 후보(추세근거, MACD근거, 트리거, 무효화) -> 회피 특징 -> 결론(L171-L183).
**SKILL.md와 코드 차이**: 코드 없음. 데이터 스크립트는 `../a-share-skill/scripts/`(fetch_technical.py 등)로 위임하고 이 저장소 a-share-data에 대응(L17-L24).
**한국 시장 적용**: 지표 규칙은 그대로. 60분봉이 없으므로 일봉 MACD+주봉 MACD로 대체 권장 [추정]. 업종·지수 15점은 KOSPI/KOSDAQ MA 상태+업종지수로 대체.

### a-share/a-share-strategy-allmarket-multi-swing-defensive · mainboard-multi-swing-defensive — 추세 눌림목(trend_pullback) 일봉 신호
> 두 스킬은 거의 동일(diff: 이름/설명, 유니버스 함수 `get_all_market_universe`(+창업판 300/301·과창판 688/689 포함) vs `get_mainboard_universe`(600/601/603/605/000/001/002)만 다름. 파라미터 파일도 STRATEGY_NAME 한 줄만 다름). 아래는 allmarket 기준.
| 항목 | 내용 |
|---|---|
| 기법·출처 | 이동평균 눌림목 + RSI 대역 + 비용·파라미터 이웃 합의 필터. 저자 자체 "strategy_lab" 구현(출처 인용 없음) |
| 분류 | (a) 일봉만으로 구현 가능. 코드 있음(pandas), 실행은 하지 않음 |
| 필요 데이터 | 일봉 close/high/low, 120봉(`--history-count` 기본 120), 거래대금 상위 N(기본 120) 유니버스(akshare 스팟) |
| 주요 파일 | a-share-strategy-allmarket-multi-swing-defensive/scripts/strategy_lab/{strategies.py,strategy_params.py,indicators.py}, scripts/daily_decisions.py, scripts/paper_trading/market_data.py |
| 라이선스 | MIT |
| 이식 판단 | 채택: trend_pullback 진입/청산(진입 트리거), "비용 차감 후 엣지>0" 게이트와 "파라미터 이웃 합의율>=0.67" 필터(리스크 게이트). 유니버스=거래대금 상위 N은 데이터 수집 단계 |

**규칙·계산식 (코드 기준)**
| # | 규칙 | 계산식·임계값·가중치 | 근거 |
|---|---|---|---|
| 1 | 파라미터 | fast=8, slow=20, pullback_ceiling=1.008, bull RSI [42,72], bear RSI [30,60], exit_rsi=74, rsi_period=14 | allmarket.../strategy_lab/strategy_params.py:L7-L19 |
| 2 | 진입(entry) | MA8>MA20 AND close>MA20 AND close<MA8*1.008 AND RSI14가 [42,72] | strategy_lab/strategies.py:L36-L49 |
| 3 | 청산(exit) | close<MA20 OR RSI14>74 (params 없을 때 기본 72, 실제 파라미터는 74) | strategies.py:L50 ; params:L17 |
| 4 | 점수 | score = MA8/MA20 - 1 (이평 이격, 클수록 상위) | strategies.py:L51 |
| 5 | RSI 정의 | 단순 롤링평균(SMA) 기반 RSI(Wilder 평활 아님) | strategy_lab/indicators.py:L15-L22 |
| 6 | 비용 필터 | edge_after_cost = max(score,0) - roundtrip_bps/10000, 기본 45bps => MA8/MA20 > 1.0045 이어야 통과 | daily_decisions.py:L97-L104 ; params:L30 |
| 7 | 파라미터 이웃 합의율 | grid {fast:[8,10], slow:[20,30], bull_rsi_low:[40,42], bull_rsi_high:[70,72]} 16개 조합에서 신호봉 entry 비율 >= 0.67 | params:L21-L28 ; daily_decisions.py:L58-L94 |
| 8 | 신호봉 | from_previous_day_close(전일 종가 봉, index -2, 사전계획형) / from_last_close(최신 봉, 표시용) | daily_decisions.py:L72-L94 ; SKILL.md:L31-L34 |
| 9 | 상위 N 제한 | score 내림차순, 목록당 최대 5개 | params:L39 ; SKILL.md:L36 |
| 10 | 유니버스 | 거래대금(成交额) 내림차순 상위 120, ST·退 제외, 보드 접두사 화이트리스트 | market_data.py:L158-L179 ; params:L37 |
| 11 | 참고 일중 손절 | REFERENCE_INTRADAY_STOP_PCT=0.07 (문서용, 스크립트가 감시하지 않음) | params:L41 ; SKILL.md:L41-L42 |
| 12 | 제도 처리 | 가격제한 비율 추정: 300/301/688/689=20%, ST=5%, 북교소(43/83/87계열 등)=30%, 그 외 10%. 단 ST 판정이 20% 판정보다 뒤(창업판 ST는 20%로 처리) | market_data.py:L182-L200 |

> 같은 파일에 미사용 변형 전략 9개가 있음(STRATEGY_BUILDERS, strategies.py:L215-L226): breakout_momentum(20일 고점 돌파+MA10>MA30), event_rotation(5일 수익률>4%), mean_revert(RSI6<18 & MA20 이격<-6%, 청산 RSI6>55 or close>=MA5), low_vol_breakout(ATR% 20일 백분위<0.35 & 15일 돌파), mainboard_leader_trend(MA5>20>60, 20일수익률>15%, 20일 돌파; 청산 close<MA20 or 이격<-4%), event_rotation_defensive(ret5>3.5%, ret10>6%, ATR%<8.5%; 청산 ret5<-1% or ATR%>10%), main_event_swing(ret10>8%, ret20>15%, RSI10<78; 청산 RSI10>84), leader_rotation(ret20>10%, ret60>25%, RSI14 52~82; 청산 RSI14>88; 점수=0.5*ret20+0.5*ret60+이격), adaptive_rotation(돌파 OR 눌림). 모두 daily_decisions에서는 trend_pullback만 호출(daily_decisions.py:L19-L20, L119).

**점수·등급**: 등급 없음. score=MA8/MA20-1 한 개로 정렬 후 상위 5.
**출력 형식**: 사람 읽기 목록 또는 `--json`(from_*_raw / 필터 후 목록 / entry_consensus_ratio / edge_after_cost / cost_filter_passed / consensus_filter_passed / sell 목록 / todo_confirm_items) (SKILL.md:L74-L79).
**SKILL.md와 코드 차이**
- [차이] bear RSI 대역[30,60]은 entry에서 사실상 쓰이지 않음: entry 조건이 MA8>MA20을 이미 요구해 bull_mask가 항상 참 (strategies.py:L12-L22 vs L44).
- [차이] SKILL.md는 "RSI 구간 42~72"로 서술하나 함수 기본값(params 누락 시)은 rsi_high 68, exit_rsi 72 (strategies.py:L15, L50); 실제 params 파일 값이 우선.
- [차이] 문서의 "횡보 시장 필터/시장 레짐"은 이 스킬에 없음. 개별 종목 신호만 계산.
- 합의율 계산은 grid 16조합 전부에 대해 "해당 봉 entry"만 비교(수익률 검증이 아님). edge_after_cost는 사실상 "이평 이격>0.45%" 필터.
**한국 시장 적용**
- 거래비용: 45bps 왕복은 A주(인지세 0.05%+수수료 등) 기준 [추정]. 한국은 2026년 거래세 합계 약 0.20%(확인 필요)+수수료이므로 왕복 약 25~35bps 수준이 될 수 있어 파라미터화 필요.
- 가격제한은 단일 ±30%로 단순화(코드 L182-L191의 ST/보드별 분기 불필요). T+1 제약 제거: 청산을 당일 종가 동시호가(15:20~15:30) 기준으로 평가 가능.
- 유니버스: 거래대금 상위 N에 호가단위 기반 최소 가격(예: 1,000원 미만 제외) 및 관리종목·투자주의 제외를 추가 [추정]. 100주 단위 사이징 없음(1주).
- SMA 기반 RSI는 Wilder RSI와 값이 달라 임계값(42/72/74) 이식 시 같은 정의 사용 필수.

### a-share/tuige-shortline-trading — "退哥" 단기매매 규칙(시장 레짐 -> 종목 -> 시나리오 -> 청산 -> 포지션)
| 항목 | 내용 |
|---|---|
| 기법·출처 | "퇴(退)형" 단타 체계(涨停 후 조정, 연판 릴레이, 황금구덩이 등) 정성 문서화. 원저자 개인 체계 |
| 분류 | (d) 자동매매 부적합(정성 위주) + 일부 (c) 시장·테마 레짐 |
| 필요 데이터 | 상한가/연판 정보, 테마·업종 강도, 호가 봉단(封单), 경매(竞价) = 일봉 외 데이터 필수 |
| 주요 파일 | tuige-shortline-trading/SKILL.md (124줄), api-reference/*.md 9개(합 1,022줄) |
| 라이선스 | MIT |
| 이식 판단 | 보류(상한가 릴레이 접근은 한국 ±30%/테마 구조에 맞지 않고 수치 없음). 구조만 차용: 레짐 라벨 5단계(레짐 필터)와 포지션 등급 4단계(사이징) |

**확인 결과**: api-reference 9개 문서 전체에서 숫자 임계값이 사실상 없음(grep으로 %, 일수, 배수 패턴 0건). 규칙은 "~가 깨지지 않음", "거래량 축소"처럼 정성 서술.
| # | 규칙 | 내용 | 근거 |
|---|---|---|---|
| 1 | 레짐 라벨 | aggressive / rotation / pullback_only / defensive / no_trade. 판단 순서 대시장->업종->개별 | tuige-shortline-trading/api-reference/market-regime.md:L8-L28 |
| 2 | 시나리오 허용 매트릭스 | relay는 aggressive 또는 강한 rotation만; trend는 no_trade만 아니면 + 缩量 조정; washout는 극단 퇴조만 아니면 | market-regime.md:L70-L93 |
| 3 | 강등 | 지수·업종·개별 불일치, 테마 약한데 위치 높음, 구조 좋은데 환경 역풍 -> 관찰만 | market-regime.md:L95-L101 |
| 4 | 시나리오 | 추세(5일선 불파, 눌림, 缩量 후 재상승), 涨停 후 조정(三阴不破阳 등), 릴레이(一进二/二进三/2+2), 洗盘(黄金坑/가짜 이탈) | SKILL.md:L36-L53 ; trend-setups.md:L10-L75 |
| 5 | 청산 4분류 | 止盈兑现 / trend_broken(5일선 유효 이탈) / structure_failed / risk_off(고위 거래량 정체, 고위 고회전 무상승, 익일 약세, 거래량 동반 하락) | exit-failure-rules.md:L10-L60 |
| 6 | 포지션 등급 | light/standard/defensive/no_trade; 릴레이=기본 light; 연속 실패 시 降频(등급 하향·릴레이 중단) | position-discipline.md:L8-L62 |
| 7 | 엔지니어링 주장 | `tuige_shortline_v1`, 최대 8종목(`--max-holdings` 기본 8), `--max-buys` 8 | SKILL.md:L96, L114-L115, L123 |
**점수·등급**: 없음(문자 라벨만).
**출력 형식**: 시장환경/허용모듈/후보등급/구조/trigger/invalidation/卖出观察点/position_grade (SKILL.md:L55-L79).
**SKILL.md와 코드 차이**: [차이] SKILL.md L88-L102는 `scripts/daily_decisions.py`, `strategy_lab/` 등이 있다고 쓰나 이 폴더에는 api-reference/와 SKILL.md뿐(find 결과: md 10개, 코드 없음). 즉 실행 스크립트는 실제로 없음(문서뿐).
**한국 시장 적용**: 상한가(10%) 기반 릴레이/涨停 후 조정 시나리오는 한국의 상한가 30%와 거래 구조가 달라 직접 이식 불가. 레짐 5라벨과 "시장이 총스위치" 원칙만 위원회 레짐 필터로 차용.

### a-share/a-share-paper-trading — A주 모의투자 엔진(SQLite)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 규칙 검증형 모의계좌(가격제한·T+1·100주·수수료·세금). 매매 기법 아님 |
| 분류 | 실행/시뮬 인프라(데이터 도구에 준함). 전략 아님 |
| 필요 데이터 | 실시간 시세(텐센트/신랑), 분봉 |
| 주요 파일 | a-share-paper-trading/scripts/paper_trading/engine.py(728줄), SKILL.md(208줄) |
| 라이선스 | MIT |
| 이식 판단 | 부분: 한국용 모의/백테스트 체결 규칙 레퍼런스로만. 제도 상수는 전부 교체 |

| # | 규칙 | 값 | 근거 |
|---|---|---|---|
| 1 | 수수료 | max(5원, 거래대금*0.03%) + 상해(6xxxxx)만 이전비 0.001% | a-share-paper-trading/scripts/paper_trading/engine.py:L66-L74 |
| 2 | 인지세 | 매도만 0.1% | engine.py:L77-L78 |
| 3 | 호가단위 | 0.01 고정 검증(소수 둘째자리 정렬) | engine.py:L81-L90 |
| 4 | 매수 수량 | 100주 배수. 매도는 100주 배수 or 잔량 전량 | engine.py:L281-L282, L316-L318 |
| 5 | T+1 | 매도 가능 수량 = acquired_date < 오늘인 lot 합 - 미체결 매도 | engine.py:L716-L728 |
| 6 | 가격제한 검증 | 지정가가 limit_up/limit_down 밖이면 거부 | engine.py:L574-L584 |
| 7 | 장 단계 | 9:15-9:25 시초 동시호가, 9:30-11:30, 13:00-14:57 연속, 14:57-15:00 종가 동시호가 | engine.py:L28-L45 |
| 8 | 제한가 계산 | prev_close*(1±ratio) 2자리 반올림, ratio=10/20/5/30% | market_data.py:L194-L200 |
**한국 시장 적용**: 호가단위 0.01 고정 -> KRX 가격대별 호가단위 표(1/5/10/50/100/500/1,000원); 100주 -> 1주; T+1 sellable lot 로직 삭제(당일 매도 가능); 장 단계 15:20-15:30 종가 동시호가(KRX)로 교체(A주 14:57-15:00); 수수료/세금 상수 교체(0.1% 인지세 -> 거래세 합계 약 0.20%, 확인 필요); 가격제한 ±30%, 기준가 라운딩은 호가단위로.

### a-share/a-share-data — A주 데이터 조회(akshare/MyTT 기반)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 데이터 도구. 지표 라이브러리 MyTT, akshare, 텐센트·신랑·동방재부·DangInvest |
| 분류 | 데이터 도구 |
| 필요 데이터 | 무료 공개 API(키 불필요 추정), 일부 외부 사이트 스크래핑 |
| 주요 파일 | a-share-data/SKILL.md(94줄), scripts/fetch_technical.py(215줄), fetch_realtime.py(1,278줄), fetch_history_fallback.py(1,396줄) |
| 라이선스 | MIT |
| 이식 판단 | 보류(한국은 KRX/OpenDART 사용). 참고: `status/meta/data` 응답 계약, stale 플래그, 재무 as-of 공고일 기준(공시일 이후만 사용) 설계는 데이터 수집 계층에 차용 가치 |
- 지표 해석 임계(코드): MA5>MA10>MA20 정배열, MACD DIF/DEA 교차 + 0축 위/아래, KDJ K,D>80 과매수/<20 과매도, RSI>80/<20, 볼린저 상하단 이탈 (a-share-data/scripts/fetch_technical.py:L115-L172). MyTT MACD 기본(12,26,9) [추정: MyTT 기본값].
- 데이터 정책: 기본 `--adjust raw`, 재무는 공고일 필터, 업종 성분은 현재 시점(과거 성분 아님) 경고, 북향 전부 0이면 자리표시 가능성 (a-share-data/SKILL.md:L45-L46, L80-L88).
- 제약: 데이터 소스 신뢰성은 코드 실행 없이 확인 불가. docs/*health*.json은 저자 자체 헬스체크 결과.

### finance-skills/sepa-strategy — Minervini SEPA(스테이지 + 8조건 트렌드 템플릿 + VCP + 리스크 기반 사이징)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Mark Minervini SEPA, Stan Weinstein 4-Stage(1988) (stage-analysis.md:L3). 프롬프트 지시문 |
| 분류 | (a) 일봉 규칙 대부분(트렌드 템플릿·VCP·피벗·사이징) + (b) 재무(EPS/매출, 등급 A-D) + (c) 시장환경(지수 200MA, 신고가/신저가) |
| 필요 데이터 | 일봉 OHLCV 2년(200MA 5개월 기울기), 분기 EPS/매출/마진, RS 레이팅(12개월 상대수익률), 지수·breadth |
| 주요 파일 | himself65-finance-skills/plugins/market-analysis/skills/sepa-strategy/SKILL.md(253줄) + references/*.md 7개 + README.md |
| 라이선스 | MIT |
| 이식 판단 | 채택(핵심). 트렌드 템플릿 8조건=진입 게이트, 시장환경 3상태=레짐 필터+리스크율, 포지션 사이징 공식=사이징, 3단계 스탑=청산, VCP/피벗/거래량 1.5x=진입 트리거 |

**코드 여부**: 문서뿐(코드 없음). sepa-strategy 폴더는 .md 9개만(find 결과). 계산은 "코드로 직접 계산하라"는 지시만 있음(SKILL.md:L46). 파라미터 해석 여지가 있는 곳은 명시.

**규칙·계산식**
| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 스테이지 | Stage2만 매수. Stage1(200MA 평탄/하락, MA 엉킴), 3(고점 넓은 변동·거짓 돌파), 4(전 MA 아래). 정량 판정식은 없음 | sepa-strategy/SKILL.md:L56-L65 ; references/stage-analysis.md:L5-L51 |
| 2 | 베이스 카운트 | Base1-2 풀사이즈, 3-4 소폭 축소, 5-6 최대 절반, 7+ 회피 | SKILL.md:L67-L71 ; stage-analysis.md:L29-L36 |
| 3 | 트렌드 템플릿 8조건(전부 충족) | (1) 종가>MA150 & MA200 (2) MA150>MA200 (3) MA200 상승 >=1개월(이상 4-5개월; 오늘 vs 1개월 전/4-5개월 전 비교) (4) MA50>MA150 & MA200 (5) 종가>MA50 (6) 종가 >= 52주저점*1.30 (7) 종가 >= 52주고점*0.75, 즉 (1-종가/고점)<=25% (8) RS>70백분위(선호 85-90+) | SKILL.md:L83-L90 ; references/trend-template.md:L11-L43 |
| 4 | EPS | 분기 EPS 성장 >=20% 미달 시 탈락(선호 25-50%+); 가속(이번 분기 성장률>직전); 연간 3년 각 >=25% | SKILL.md:L102-L104 ; references/fundamentals.md:L11-L26 |
| 5 | 매출 | 연 >=15%, 분기 20-25%+ 선호. EPS만 늘고 매출 정체=비용절감으로 간주 | SKILL.md:L105 ; fundamentals.md:L34-L38 |
| 6 | 재무 등급 | A: EPS>30% & 양수 & 매출 성장; B 15-30%; C 0-15%; D 음수(제외) | SKILL.md:L110 ; fundamentals.md:L85-L87 |
| 7 | VCP 7규칙 | Stage2 전제; 풀백 깊이 순차 감소(예 20->12->6->3%, 각 수축은 직전의 약 20-30% 작아짐); 최소 3회 수축(4-5 이상적); 수축마다 거래량 감소+최종 VDU; 저점 상승; 명확한 피벗; RS>70; 시장 강세/중립 | SKILL.md:L120-L128 ; references/patterns.md:L9-L30 |
| 8 | 기타 베이스 | 컵핸들: 컵 12-35%, 핸들<=12%(컵 깊이의 1/3 이하), 7-65주 / 플랫: <=15%, 5-10주 / 불플래그: 깃대 25%+, 풀백<=깃대 50%, 1-5주 / HTF: 4-8주에 100%+ 상승 후 <=25% 조정, 1-4주 | SKILL.md:L132-L137 ; patterns.md:L65-L107 |
| 9 | 진입 | 피벗=기본 고점. 매수구간 피벗~+5%. +5% 초과 추격 금지. 돌파일 거래량>=20일 평균*1.5(>=2.0x 강함; 1.2-1.5x 한계; <1.2x 회피) | SKILL.md:L147-L153 ; references/entry-rules.md:L11-L24 |
| 10 | 실거래 돌파 품질 | 종가가 일중 고점 근처, VDU 선행, 익일 후속 상승, 긴 윗꼬리 없음. 실패: 피벗 아래 마감, 약한 거래량 | SKILL.md:L155-L162 ; entry-rules.md:L26-L40 |
| 11 | 포켓 피벗(대안) | 상승일 거래량 > 직전 10거래일 하락일 최대 거래량; 진입 10/20MA 근처; 손절 해당일 저점 -1~2% | entry-rules.md:L42-L52 |
| 12 | 어닝 | 실적 발표 2주 이내 진입 회피 | SKILL.md:L153 ; entry-rules.md:L60 |
| 13 | R/R 검증 | 손절거리 <=7-8%; 보상/위험 >=2:1(선호 3:1), 미달 시 스킵 | SKILL.md:L167-L169 ; entry-rules.md:L62-L72 |
| 14 | 시장환경 | Bull(S&P·나스닥>200MA, breadth 확대, 신고가>신저가): 리스크 1-2%, 최대 6-8종목, S급 10-15%/A급 5-10% / Choppy: 0.5-1%, 2-3종목, A+만 절반 크기 / Bear(지수<200MA, 종목의 >50%가 200MA 아래): 0%, 전량 현금. VIX 지속 25-30 이상은 공포 신호 | SKILL.md:L179-L183 ; references/market-environment.md:L7-L65 |
| 15 | 사이징 | Shares = (계좌*리스크%) / (진입가-손절가). 예: 100k, 1%, 50->46.5 => 285주(14.25%) | SKILL.md:L195-L202 ; references/position-sizing.md:L88-L101 |
| 16 | 스탑 3단계 | 초기 -7~8% 하드스탑; +8% 도달 시 절반 매도+스탑=진입가; +15% 시 추가 25% 매도+잔여는 20MA 추적(종가<20MA 시 전량, 주 1회 20MA의 1-2% 아래로 갱신); +20-25% 급등이면 10MA로 조임; 종가<50MA는 전량 청산 고려 | SKILL.md:L204-L210 ; position-sizing.md:L103-L138 |
| 17 | 철칙 | 스탑은 상향만; 물타기 금지; 3-4연패 시 리스크 0.5%로; 평균 손실 4-5%, 상한 10% | SKILL.md:L212 ; position-sizing.md:L140-L145 |
| 18 | 피라미딩 | 50%(돌파) -> 30%(+8% & 20MA 눌림) -> 20%(다음 베이스 돌파) | SKILL.md:L216 ; position-sizing.md:L147-L158 |
**점수·등급**: 가중점수 없음. 8조건 전부 통과 필요(이진). 재무 A-D(위 #6). 종합 판정 3단 Strong Buy Setup / Watch List / Pass (SKILL.md:L236-L239). 피벗 정량 정의는 "컨솔리데이션 범위 최고가"뿐이라 윈도 길이는 구현자가 정해야 함.
**출력 형식**: 9단 리포트(종목·스테이지, 8조건 체크리스트, 재무 등급, 패턴, 진입, 시장환경, 사이징, 판정) + 교육용 면책 (SKILL.md:L222-L241).
**SKILL.md와 코드 차이**: 코드 없음. 문서 내부 불일치 [차이]: SKILL.md는 손절 7-8% 고정, patterns.md는 패턴별 "진입가 아래 5-10%"(patterns.md:L116); 시장환경 표의 종목 수(6-8)는 SKILL.md와 market-environment.md 일치, 포지션 비중 S 10-15%/A 5-10%는 market-environment.md에만 있음(L17).
**한국 시장 적용**
- 트렌드 템플릿: MA50/150/200 일봉 그대로 적용 가능. 한국은 ±30%이므로 52주 저점 +30% 조건은 변동성 큰 소형 테마주에 너무 쉽게 충족됨 -> 유동성 하한(거래대금)과 병행 [추정].
- RS: 12개월 수익률의 코스피+코스닥 전종목 백분위로 자체 계산(IBD 의존 불가). 70/85 임계 유지.
- 재무: EPS 분기 >=20%, 매출 >=15%는 OpenDART 분기 재무(연결, 공시일 기준 as-of)로 계산 가능. 한국 분기보고서 공시 시차(분기 종료 후 45일 이내) 반영 필요 [추정]. 재무 없는 종목은 점수만 삭제하지 말고 "Unknown" 처리.
- 시장환경: 코스피/코스닥 vs 200MA + 200MA 아래 종목 비율(>50% 베어) + 신고가/신저가 수는 일봉만으로 계산 가능. 레짐별 리스크율 1-2% / 0.5-1% / 0% 는 바로 이식 가능.
- 어닝 2주 회피: DART 정기보고서 예정일은 확정 공시가 없어 추정 필요. 사이징 시 1주 단위(100주 제약 없음), 호가단위 라운딩(손절가는 호가단위로 정렬).
- T+2는 결제일 기준이므로 당일 매도 가능: 손절 장중 감시 가능(자동매매 엔진은 일봉 기반이므로 종가 동시호가 15:20-15:30 청산 또는 다음 날 시가).

### finance-skills/stock-liquidity — 유동성 지표(스프레드·거래대금·Amihud·충격비용·회전율)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Amihud(2002) 비유동성 비율, 제곱근 시장충격 모델(기관 관행). SKILL.md 안에 파이썬 코드 템플릿 포함(저장소에 독립 .py 없음) |
| 분류 | (a) 일봉 OHLCV 기반 지표 + 일부 호가(스프레드)는 별도 데이터 |
| 필요 데이터 | 일봉(3개월), 상장주식수·유통주식수, bid/ask(옵션). yfinance(무료) |
| 주요 파일 | himself65-finance-skills/plugins/market-analysis/skills/stock-liquidity/SKILL.md(496줄), references/liquidity_reference.md(438줄) |
| 라이선스 | MIT |
| 이식 판단 | 채택(리스크 게이트·유니버스 필터·사이징 상한): 일평균 거래대금 등급, Amihud, 충격비용 추정 |

| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 평균 거래대금 | mean(Close*Volume) 3개월 | stock-liquidity/SKILL.md:L104 |
| 2 | 거래량 변동계수 | std(Volume)/mean(Volume) | SKILL.md:L105-L106 |
| 3 | 회전율 | mean(Volume)/ (유통주식수 or 상장주식수) | SKILL.md:L108-L112 |
| 4 | Amihud | mean(abs(일수익률)/일거래대금), 표시 시 *1e9 | SKILL.md:L114-L118, L153 |
| 5 | 제곱근 충격 | impact_bps = sigma_일 * sqrt(주문/ADV) * 10000 (상수 계수 없음); 1% ADV 기본; 곡선 0.1,0.5,1,2,5,10,20,50% ADV | SKILL.md:L120-L126, L323-L360 |
| 6 | 충격 경고 | 충격 > 약 25bps = 주문이 크다, > 약 50bps 강한 경고 | SKILL.md:L394-L395, L483 |
| 7 | 유동성 등급 | 거래대금/스프레드/Amihud(*1e9): Very High >$500M/<0.03%/<0.01; High $50-500M/0.03-0.10%/0.01-0.1; Moderate $5-50M/0.10-0.50%/0.1-1.0; Low $0.5-5M/0.5-2%/1-10; Very Low <$0.5M/>2%/>10 (미국주식 기준) | SKILL.md:L155-L163 |
| 8 | RVOL | 오늘 거래량 / 기간 평균; >1.5 상승, <0.5 한산 | SKILL.md:L225-L274 |
| 9 | 연환산 회전율 해석 | >500% 투기적, 100-500% 활발, 30-100% 보통, <30% 한산 | SKILL.md:L457-L460 |
| 10 | 소형주 경고 | 일 거래대금 <$1M 은 주의. 왕복 스프레드 비용 = 2*스프레드 | SKILL.md:L484-L485 |
**점수·등급**: 5등급(Very High ~ Very Low), 세 지표를 합산하는 식은 없음(표로 병기).
**출력 형식**: 요약 카드/비교표/충격 곡선, 조회 기간·타임스탬프·15분 지연 주의문 (SKILL.md:L466-L481).
**SKILL.md와 코드 차이**: 문서 내 코드 일관. [주의] 충격 모델에 Y 계수가 없어 보수/낙관 편향 가능(실무는 0.5~1.0 가중 [추정]).
**한국 시장 적용**: 달러 기준 등급표는 원화로 재보정 필요: 한국 소형주는 일 거래대금 수억 원대가 흔하므로 임계값을 자체 분포(KRX 일별 거래대금 백분위)로 재설정. 호가단위가 가격대별로 달라 "스프레드%"는 호가단위/가격(예 2천원 미만 1원=최대 약 0.05-0.1%)으로 하한이 결정됨. 예: 1주 단위 사이징이므로 주문 크기를 일 거래대금의 0.5~1% 이하로 제한하는 룰이 가장 단순 [추정].

### finance-skills/stock-correlation — 상관·베타·롤링상관·레짐별 상관
| 항목 | 내용 |
|---|---|
| 기법·출처 | 수익률 피어슨 상관, 베타, 계층 군집(scipy linkage), 롤링/조건부 상관. 표준 통계. SKILL.md 내 코드 템플릿 |
| 분류 | (a) 일봉 종가만으로 계산 가능 (포트폴리오 리스크 게이트·군집 집중도 제한에 사용) |
| 필요 데이터 | 일봉 종가 1~2년(yfinance), 후보 피어 15~30개 |
| 주요 파일 | himself65-finance-skills/plugins/market-analysis/skills/stock-correlation/SKILL.md(365줄), references/sector_universes.md(100줄) |
| 라이선스 | MIT |
| 이식 판단 | 채택(리스크 게이트): 보유 종목 간 상관 상한, 하락일 상관 상승 감시. 피어 발굴은 필요 없음 |

| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 기본값 | 1년, 일봉, 피어슨, 최소 상관 0.60, 상위 10, 일 로그수익률, 롤링 60일 | stock-correlation/SKILL.md:L58-L67 |
| 2 | 베타 | cov(B,A)/var(A) ; R^2 = corr^2 | SKILL.md:L139-L151 |
| 3 | 해석 | >0.80 강, 0.50-0.80 보통, <0.50 약, 롤링 표준편차 크면 불안정 | SKILL.md:L189-L192 |
| 4 | 군집 | 거리 = 1 - |corr|, scipy hierarchical ordering; scipy 없으면 평균 상관 정렬 | SKILL.md:L216-L233 |
| 5 | 롤링 창 | 20/60/120일 | SKILL.md:L262-L270 |
| 6 | 레짐 상관 | 상승일, 하락일, 변동 상위25%(|r|>q75), 하위25%, 큰 하락(<-2%) 별 상관, 표본 >=20일일 때만 | SKILL.md:L278-L296 |
**점수·등급**: 없음. **출력 형식**: 순위표, 매트릭스+군집, 롤링 표, 레짐 표, "위기에 상관이 1로 수렴" 인사이트 (SKILL.md:L318-L330).
**SKILL.md와 코드 차이**: 기본값 표는 "로그수익률"이나 Sub-Skill A/B 코드의 returns 계산 방식은 템플릿별로 다를 수 있음(일부 pct_change, 확인 못 함).
**한국 시장 적용**: 일봉 종가 기반이라 그대로 가능(한국 종목은 수정주가 사용). 한국은 테마주 동조가 강하므로 포트폴리오 상위 N 중 쌍별 상관>0.8 종목은 하나만 허용 같은 룰 [추정]. 레짐 -2% 기준은 코스닥 변동성에 맞춰 재보정.

### finance-skills/estimate-analysis · earnings-preview · earnings-recap · company-valuation · etf-premium · saas-valuation-compression · options-payoff · yfinance-data
| 스킬 | 기법/계산 | 데이터 | 분류 | 이식 판단 |
|---|---|---|---|---|
| estimate-analysis | 컨센서스 범위폭, EPS 추정치 7/30/60/90일 추이, 리비전 비율 Up/(Up+Down) >0.7 강세 <0.3 약세, 최근 4분기 서프라이즈. 범위폭 >15% 불확실, 애널 <5명 얇은 커버리지 (estimate-analysis/SKILL.md:L99-L129) | yfinance 컨센서스(미국 중심) | (b) 재무+컨센서스 | 보류: 한국 컨센서스는 FnGuide 등 유료 필요. 리비전 비율 0.7/0.3 개념만 |
| earnings-preview | 컨센서스 표, 4분기 beat/miss, 고저 스프레드 >약 20% 불확실 (earnings-preview/SKILL.md:L94) | yfinance | (b) | 보류 |
| earnings-recap | 발표 후 beat/miss, 서프라이즈%, 주가 반응 요약 | yfinance | (b) | 보류(서술형) |
| company-valuation | DCF 5년 FCFF + WACC(ke=rf+beta*ERP, rf 4.5%, ERP 5.5%, g 2.5%, kd 5.5%, 세율 3년 중앙값 15~30% 클램프), TV는 Gordon과 exit 15x EBITDA 평균, 상대가치 피어 중앙값, 가중 DCF50/상대50(SOTP 있으면 40/30/30), 민감도 WACC ±1% x g 1.5-3.5%; 게이트: wacc<=g 중단, TV/EV >0.85 또는 <0.45 경고 (company-valuation/SKILL.md:L78-L90, L169-L189) | yfinance 재무 | (b) | 보류(밸류에이션 위원 관점 후보지만 한국은 OpenDART+컨센서스 필요, 가정값 미국 기준) |
| etf-premium | (가격-NAV)/NAV*100; 밴드 ±0.05% 정상, 0.25% 이내 경미, 1% 이내 주목, 3% 이내 유의, 3% 초과 스트레스 (etf-premium/SKILL.md:L109, L156-L160) | yfinance NAV | 데이터/ETF 전용 | 보류(주식 엔진 범위 밖). 한국 ETF는 iNAV 괴리율로 대체 가능 |
| saas-valuation-compression | ARR 배수 = 밸류/ARR, 압축% = (후기-전기)/전기*100, 밸류 성장 = ARR 성장 x 배수 변화 (곱셈 분해) (saas-valuation-compression/SKILL.md:L50-L69) | 비상장 라운드 데이터, 웹 검색 | (d) 정성/비상장 | 제외 |
| options-payoff | 옵션 손익 곡선 대화형 위젯(IV 기본 20%, rf 4.3%) (options-payoff/SKILL.md:L41-L42) | 옵션 체인 | UI 도구 | 제외 |
| yfinance-data | yfinance 호출 안내(시세, 재무, 옵션, 보유자 등) | Yahoo | 데이터 도구 | 제외(한국은 KRX/OpenDART) |
위 8개는 문서(프롬프트 + 코드 템플릿)만 있고 독립 실행 코드 없음. 라이선스 MIT.

### finance-skills/기타 카테고리 (data-providers · social-readers · startup-tools · ui-tools · skill-creator)
| 카테고리 | 스킬 | 요약 | 분류 |
|---|---|---|---|
| data-providers | finance-sentiment, fintel-data, hormuz-strait, hyperliquid-reader, tradingview-mcp, tradingview-reader | 감성/공매도·기관 데이터(Fintel), 호르무즈 해협 해운, 하이퍼리퀴드 온체인 거래소 조회, TradingView 읽기 | 데이터 도구(대부분 미국·크립토, 유료/외부 의존) |
| social-readers | discord, linkedin, opencli, telegram, twitter, yc-reader | SNS 수집 | 데이터 도구, 이식 가치 낮음 |
| startup-tools | startup-analysis | 스타트업 분석 프롬프트 | (d) |
| ui-tools | generative-ui | 위젯 생성 UI | 해당 없음 |
| skill-creator | skill-creator | 스킬 작성 도우미 | 해당 없음 |
(각 SKILL.md 줄 수: plugins/data-providers/skills/*/SKILL.md 119-219줄, social-readers 159-251줄. 내용 정독하지 않음, 헤더·설명 수준.)

### quant-skills/6종 — backtest-review · data-scrub · risk-report · indicator-design · strategy-critique · hedge-lab
> 저장소: shakeebshaan-claude-code-quant-skills (6b39f8f, MIT). md만 존재(skills/*/SKILL.md 총 420줄 + README). 크립토(BTC) 맥락이 강함. 실행 코드 없음(템플릿 코드 2개).
| 스킬 | 수치 기준(근거) | 분류 | 이식 판단 |
|---|---|---|---|
| backtest-review | 과최적화: 파라미터 1개당 표본 약 1,000 미만 시 경고, IS->OOS 성능 하락 >40% 시 과최적 의심, Kelly 분수 <0.25 (>1x는 도박), 체결은 종가보다 다음 봉 시가가 정직, BTC 현물 왕복 약 10bps, 판정 SHIP/FIX/SCRAP (quant-skills/skills/backtest-review/SKILL.md:L22-L24, L28, L39, L42, L53-L56) | (d) 검증 체크리스트 | 채택: 엔진 백테스트 게이트 규칙(파라미터 수/표본 비, OOS 하락 40%) |
| data-scrub | 일봉 데이터 검증: low<=open,close<=high, volume>=0, 중복/비단조 타임스탬프, volume=0 & O=C 면 stale, high==low & 거래량>0 의심, |수익률|>20% 플래그, 거래량 > 30봉 중앙값의 20배 스파이크 (data-scrub/SKILL.md:L30-L43, L57-L76). 심각도 BLOCK/WARN/OK | 데이터 도구 | 채택: 수집 단계 품질 게이트. 한국은 20%를 가격제한 +-30% 고려 재설정, 수정주가/액면분할 확인 |
| risk-report | Sharpe, Sortino, MDD(+기간), Calmar=CAGR/|MDD|, VaR/CVaR 95·99, 꼬리비율, 왜도·첨도, 월 적중률. 경고 임계: Sharpe>3 의심, MDD>40% 위험, 왜도<-1, 첨도>5 (risk-report/SKILL.md:L10-L44, L52-L75, L80-L84). 코드: sortino 분모가 하방편차 아닌 r<0 표본 std(관례적 정의와 약간 다름) | (a) 수익률 계열 기반 | 채택: 백테스트 리포트 지표 + 경고선 |
| indicator-design | 지표는 파라미터 3개 이하, AND 조건 4개 이하(초과 시 과최적), 윈도 계산은 shift(1)로 룩어헤드 방지, "높은 거래량"=20일 90분위 초과 예시 (indicator-design/SKILL.md:L21-L23, L42, L66-L67) | (d) 설계 가이드 | 부분: 위원회 규칙 추가 시 복잡도 상한 가이드 |
| strategy-critique | 18개 적대적 질문(엣지 근거, 용량, 레짐, 숨은 공매도 변동성 등), 위험등급 LOW/MEDIUM/HIGH/CATASTROPHIC (strategy-critique/SKILL.md:L10-L49). 수치 없음 | (d) 정성 | 제외(운영 체크리스트로만 참고) |
| hedge-lab | 크립토 선물/펀딩/베이시스 헤지 구조. 보호풋 예시 15% OTM 30일 만기(L39). 한국 현물 주식 엔진과 무관 | (d) | 제외 |

#### 그룹 소결
이식 후보(우선순위순).
1. SEPA 트렌드 템플릿 8조건(진입 게이트, 일봉만): 종가>MA50>MA150>MA200, MA200 상승 >=1개월(이상 4-5개월), 종가>=52주 저점*1.30, 종가>=52주 고점*0.75, RS>70백분위(선호 85-90+). finance-skills/.../sepa-strategy/SKILL.md:L83-L90. 한국은 RS를 코스피+코스닥 전종목 12개월 수익률 백분위로 자체 계산.
2. SEPA 시장환경 레짐 + 리스크율 + 사이징: Bull 1-2% / Choppy 0.5-1% / Bear 0%, 최대 6-8 / 2-3 / 0종목, Shares=(계좌*리스크%)/(진입가-손절가), 3-4연패 시 0.5%. sepa-strategy/SKILL.md:L179-L183, L195, L212; references/market-environment.md:L7-L48. 지수 200MA와 "200MA 아래 종목 비율 >50%=Bear"는 일봉만으로 계산 가능. 1주 단위·호가단위 라운딩만 반영.
3. SEPA 청산 3단계 + 피벗 진입 트리거: 초기 -7~8%, +8%에서 절반 매도+스탑=진입가, +15%에서 25% 추가 매도 후 20MA 종가 이탈 시 전량(+20-25% 급등 시 10MA), 진입은 피벗~+5% 구간, 거래량>=20일 평균 1.5x(1.2x 미만 회피), R/R>=2:1. sepa-strategy/SKILL.md:L147-L153, L167-L169, L206-L212; position-sizing.md:L103-L138.
4. 8/20 MA 눌림목 trend_pullback(진입): MA8>MA20 & 종가>MA20 & 종가<MA8*1.008 & RSI14 [42,72] (RSI는 SMA 방식), 청산 종가<MA20 or RSI14>74, 점수=MA8/MA20-1. a-share-strategy-allmarket-multi-swing-defensive/scripts/strategy_lab/strategies.py:L36-L52; strategy_params.py:L7-L19. 따라서 이 스킬의 새로운 점은 신호 자체보다 필터: 비용 차감 엣지>0 (왕복 45bps, 한국은 재산정), 16개 파라미터 이웃 합의율>=0.67 (daily_decisions.py:L72-L104; strategy_params.py:L21-L30).
5. MACD 공명 점수(위원회 관점 1개): 추세 40(MA60 방향 20+종가 위치 10+MA20/60 구조 10)+MACD 35(0축 위 15, GC/적주 재확대 10, 60분 동조 10)+시장 15+이벤트 10, 85/70/55 컷. macd-trend-resonance-stock-picker/SKILL.md:L146-L162. 소항목 부분점수 기준은 미정의라 엔진에서 정의 필요. 60분 항목은 주봉 MACD로 대체 [추정].
6. 유동성/상관 리스크 게이트: 제곱근 충격 sigma*sqrt(주문/ADV), 25bps 경고/50bps 강경고(stock-liquidity/SKILL.md:L120-L126, L394-L395), 롤링 상관 20/60/120 및 하락일 상관 모니터(stock-correlation/SKILL.md:L262-L296). 데이터 점검은 quant-skills data-scrub의 OHLC 정합성·20% 이상치·거래량 20배 스파이크 규칙(data-scrub/SKILL.md:L30-L43)과 백테스트 게이트 "IS->OOS 하락 40%·파라미터/표본 비"(backtest-review/SKILL.md:L22-L24).
보류: tuige-shortline-trading(수치 없음, 상한가 릴레이), 2차 골든크로스(수치 정의 없음; 쓴다면 pivot 폭·하락폭 직접 정의), 밸류에이션·컨센서스 계열(한국 데이터 유료).


---

## 21. staskh/trading_skills · rkiding/awesome-finance-skills
> 저장소들: staskh-trading-skills (staskh/trading_skills, 012abbf, MIT), rkiding-awesome-finance-skills (rkiding/awesome-finance-skills, 853f09b, Apache-2.0)

### staskh/scanner-bullish — 강세 추세 스캐너 (복합 점수)
| 항목 | 내용 |
|---|---|
| 기법·출처 | SMA20/50, RSI14, MACD(12/26/9 pandas-ta 기본 [추정]), EMA9/21 및 MACD 크로스 신선도, ADX14/DI, 기간수익률 모멘텀을 가산 점수로 합산. 원저자 개인 구성(고전 지표 조합), 출처 인용 없음 |
| 분류 | (a) 일봉만으로 구현 가능 (OHLC만 사용, 거래량 미사용) |
| 필요 데이터 | yfinance 일봉 3개월(기본 `period="3mo"`), 최소 50봉; 어닝일은 점수와 무관(출력용) — 무료 |
| 주요 파일 | staskh-trading-skills/src/trading_skills/scanner_bullish.py, technicals.py(`compute_raw_indicators`) |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: 위원회의 "추세 관점" 점수기. 이진 가산 구조라 가중치 재조정 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·가중치 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 종가 > SMA20 / SMA50 | 각 +1.0 | staskh-trading-skills/src/trading_skills/scanner_bullish.py:L98-L112 |
| 2 | RSI14 구간 | 50~70 +1.0 / 30≤RSI<50 +0.5 / <30 +0.25 / >70 0점(과열은 가점 없음) | scanner_bullish.py:L115-L125 |
| 3 | MACD | MACD선>시그널 +1.0; 히스토그램이 전봉보다 증가 +0.5 | scanner_bullish.py:L133-L140 |
| 4 | EMA9 vs EMA21 | 위 +0.5 / 아래 -0.25 | scanner_bullish.py:L146-L152 |
| 5 | 이중 크로스 확인 | EMA·MACD 마지막 크로스 방향 일치 + 둘 다 10봉 이내(`_FRESH_DAYS=10`): 상승 +1.0/하락 -1.0; 일치하나 오래됨: ±0.5; 방향 충돌 -0.5; 둘 중 하나라도 크로스 없음 0 | scanner_bullish.py:L12, L15-L61 |
| 6 | ADX | ADX>25 & +DI>-DI: +1.5; 그 외 +DI>-DI: +0.5; -DI 우위는 0점 | scanner_bullish.py:L165-L171 |
| 7 | 모멘텀 보너스 | `clip(period_return%/20, -1, +2)`; period_return = 조회구간 첫 종가 대비 현재 (3mo ≈ 63봉) | scanner_bullish.py:L90, L173-L175 |
| 8 | 크로스 탐지 | 히스토그램/EMA차의 부호가 전봉 ≤0 → 현봉 >0이면 up(반대는 down), 마지막 발생 후 경과 봉수 days_ago | technicals.py:L74-L119 |
| 9 | 지표 파라미터 | RSI 14, SMA 20/50, EMA 9/21, MACD 기본, ADX 14 | technicals.py:L152-L206 |
| 10 | 데이터 하한 | 종가 NaN 제거 후 50봉 미만이면 제외 | scanner_bullish.py:L79-L80 |

**점수·등급**: 이론 최대 9.5(1+1+1+1+0.5+0.5+1.0+1.5+2), 최저 -2.25(EMA -0.25, 이중 하락 -1.0, 모멘텀 -1 — 코드로 계산). 해석: >6 강한 강세, 4~6 보통, 2~4 중립/약, <2 약세 (SKILL.md:L93-L98). 상위 N(기본 30) 정렬 (scanner_bullish.py:L204-L228). 점수 구간은 코드가 아닌 문서에만 있음.
**출력 형식**: JSON(score, price, period_return_pct, pct_from_sma20/50, rsi, macd*, ema9/21, 각 crossover{direction,days_ago}, adx/dmp/dmn, signals[] 문자열) (scanner_bullish.py:L177-L198).
**SKILL.md와 코드 차이**: 거의 일치. 문서는 RSI 30-50을 "neutral"로 표기, 코드 L122 동일. 문서에 ">70 점수 없음"이 명시되지 않음(코드로만 확인). 오류 시 종목을 조용히 제외(L199-L201).
**한국 시장 적용**: 지표 자체는 시장 무관. 3개월 63봉 기준이라 KRX 거래일(연 ~245일) 기준으로 윈도를 봉 수로 고정할 것. 점수 가산이 공선적(SMA·EMA·MACD·ADX 모두 추세)이라 위원회에서는 "추세" 단일 관점으로 묶고 RSI는 별도 "과열/눌림" 관점으로 분리 권장 [추정]. 어닝 조회(`get_earnings_info`)는 KRX에서 DART 공시일정으로 대체하거나 제외.

### staskh/technical-analysis — 지표 요약 + 신호
| 항목 | 내용 |
|---|---|
| 기법·출처 | RSI/MACD/볼린저/SMA/EMA/ATR/ADX + 연환산 변동성·샤프. pandas-ta 사용 |
| 분류 | (a) 일봉만 |
| 필요 데이터 | yfinance 일봉 (기본 3mo), 무료 |
| 주요 파일 | src/trading_skills/technicals.py, utils.py |
| 라이선스 | MIT |
| 이식 판단 | 부분: 지표 정의는 표준. 신호 임계는 고전값뿐이라 이식 가치 낮음 |

| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | RSI 신호 | RSI14>70 overbought, <30 oversold | technicals.py:L260-L267 |
| 2 | MACD 크로스 | 히스토그램 전봉<0→현봉>0 bullish_crossover, 반대 bearish | technicals.py:L277-L281 |
| 3 | 볼린저 | length 20, std 2; 종가<하단/상단< 신호; bandwidth=(상-하)/중*100 | technicals.py:L285-L300 |
| 4 | SMA 골든/데드 | SMA20 vs SMA50 전봉-현봉 부호 교차 | technicals.py:L310-L316 |
| 5 | EMA 세트 | EMA12/26 + EMA9/21 값, 크로스 | technicals.py:L320-L331 |
| 6 | ATR | length 14, percent=ATR/종가*100 | technicals.py:L335-L340 |
| 7 | ADX | >25 strong_trend | technicals.py:L349-L356 |
| 8 | 샤프(문서 외) | mean*252/연변동성 (무위험 0) — risk.py의 샤프(무위험 4%)와 정의가 다름 | technicals.py:L359-L372, risk.py:L58-L61 |
[차이] SKILL.md:L48-L53 해석 문구와 코드 동일. 위 샤프 무위험률 불일치(technicals 0%, risk 4%)는 코드 내부 불일치.
한국 적용: 연환산 √252 → √245 내외 [추정], 무위험률 한국 국고채/CD 사용.

### staskh/chart-ema-rsi — EMA 9/20 + RSI 차트
| 항목 | 내용 |
|---|---|
| 기법·출처 | EMA(9)/EMA(20) 골든·데드 크로스 마커 + RSI14 70/30 밴드 |
| 분류 | (a) 일봉만; 시각화 도구 → 엔진에는 크로스 탐지 로직만 가치 |
| 데이터 | yfinance 일봉, 워밍업 120일 추가 다운로드 |
| 파일 | src/trading_skills/chart_ema_rsi.py |
| 라이선스 | MIT / 이식 판단: 보류(차트), 크로스 탐지의 "동일값 봉 무시, 첫 확실한 반대편 봉에 날짜 부여" 규칙만 참고 |

| # | 규칙 | 값 | 근거 |
|---|---|---|---|
| 1 | 기본 파라미터 | fast 9, slow 20, RSI 14, 밴드 70/30, WARMUP_DAYS 120 | chart_ema_rsi.py:L18-L22, L63-L65 |
| 2 | 크로스 정의 | diff=fast-slow, 0 제외 후 부호 변화 시점 = golden/death | chart_ema_rsi.py:L27-L43 |
| 3 | trend | fast>slow면 bullish | chart_ema_rsi.py:L145 |
[차이] scanner는 EMA 9/21, chart는 EMA 9/20 (scanner_bullish→technicals.py:L172-L173 vs chart_ema_rsi.py:L63-L64).
(부기) correlation.py: 종가 수준(price level)끼리 `price_df.corr()` — 수익률 상관이 아니라 가격 수준 상관이라 허위 상관 위험. 이식 시 일수익률 상관으로 교체 (staskh-trading-skills/src/trading_skills/correlation.py:L24-L25).

### staskh/risk-assessment — 변동성·베타·VaR·낙폭·샤프
| 항목 | 내용 |
|---|---|
| 기법·출처 | 표준 모수적(parametric) VaR, 공분산 베타, 누적수익 기반 MDD, 샤프. 출처 인용 없음 |
| 분류 | (a) 일봉만 (+ 벤치마크 일봉 1개; 한국은 KOSPI/KOSDAQ 지수로 교체) |
| 필요 데이터 | yfinance 1년 일봉 + SPY, 무료 |
| 주요 파일 | src/trading_skills/risk.py, utils.py:L144-L152 |
| 라이선스 | MIT |
| 이식 판단 | 채택(리스크 게이트·사이징 입력): 계산식이 단순·표준. 단 아래 결함 보정 |

**규칙·계산식**
| # | 규칙 | 계산식 | 근거 |
|---|---|---|---|
| 1 | 수익률·변동성 | r=종가.pct_change(); daily_vol=std(ddof=1); annual=daily*sqrt(252) | staskh-trading-skills/src/trading_skills/utils.py:L144-L152 |
| 2 | 최소 표본 | 수익률 20개 미만이면 오류 | risk.py:L25-L26 |
| 3 | 베타 | 종목·SPY 수익률 날짜 교집합 >20개일 때 cov(ddof=1)[0,1] / np.var(ddof=0); 분산 0이면 1.0; 교집합 부족 시 None | risk.py:L36-L45 |
| 4 | VaR95/99 (1일) | `mean - 1.645*daily_vol`, `mean - 2.326*daily_vol` (정규 가정, 평균 포함, 음수로 표기) | risk.py:L48-L50 |
| 5 | MDD | cum=(1+r).cumprod(); dd=(cum-cummax)/cummax; min | risk.py:L53-L56 |
| 6 | 샤프 | (mean*252 - 0.04)/annual_vol, 무위험 4% 고정 | risk.py:L58-L61 |
| 7 | 포지션 지표 | shares=int(금액/현재가); $VaR=금액*|VaR|; $MDD=금액*|MDD| | risk.py:L86-L93 |
**점수·등급**: 없음(수치만). SKILL.md는 "포지션 사이징을 제안"하라고만 하고 공식 없음 (SKILL.md:L36).
**출력 형식**: JSON {volatility{daily,annual %}, beta, var{var_95_daily,var_99_daily %}, max_drawdown %, sharpe_ratio, return{mean_daily,total_period}, position{...}} (risk.py:L63-L93).
**SKILL.md와 코드 차이**: 문서 키 `var_95`/`var_99`/`position_risk`(risk-assessment/SKILL.md:L30-L34) vs 코드 `var.var_95_daily`/`position` (risk.py:L73-L93) [차이]. 베타 분자 ddof=1, 분모 ddof=0이라 n/(n-1)배 약간 과대(250표본이면 +0.4%) — 코드 결함 [추정: 영향 미미]. `round(beta,3) if beta`는 beta==0이면 None 출력 (risk.py:L72).
**한국 시장 적용**: 벤치마크 KOSPI(KS11)/KOSDAQ 선택(소속 시장별). ±30% 가격제한이 있어 정규 VaR이 꼬리를 과소평가 → 경험적(역사적) 분위수 VaR 병행 권장 [추정]. 거래정지·결측일은 pct_change가 0/큰 값을 만드므로 정지일 제외. 연환산 252→KRX 거래일 약 245 [추정]. 무위험률 4%→국고채 3년/CD 금리.

### staskh/spread-analysis — 옵션 스프레드 손익 계산
범위 밖(브로커/옵션). 수직/대각/스트래들/스트랭글/아이언콘도르의 순지불·최대손익·손익분기를 옵션 체인 mid가격((bid+ask)/2, 0이면 lastPrice)으로 계산 (staskh-trading-skills/src/trading_skills/spreads.py:L9-L29, L48-L72). [차이] SKILL.md:L49는 `probability`(IV 기반 수익확률) 출력을 약속하지만 spreads.py에 해당 문자열이 없음(grep 무결과). KRX 개별 주식옵션은 사실상 없어 이식 불가. 라이선스 MIT.

### staskh/fundamentals — 재무 지표 + Piotroski F-Score
| 항목 | 내용 |
|---|---|
| 기법·출처 | Yahoo info 필드 덤프(fundamentals.py) + Piotroski F-Score(Joseph Piotroski 2000, SKILL.md에 명시) 변형 구현 |
| 분류 | (b) 재무 데이터 필요 |
| 필요 데이터 | yfinance 분기 재무제표(NI, OCF), 연간 재무제표·대차대조표 2개년 (Net Income, Operating Cash Flow, Total Assets, Long Term Debt, Current Assets/Liabilities, Share Issued, Gross Profit, Total Revenue). 무료, 한국 종목 커버리지는 불완전 [추정] → OpenDART로 대체 |
| 주요 파일 | src/trading_skills/fundamentals.py, piotroski.py |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택: F-Score를 "재무 건전성" 관점 점수(0~9)와 하드 게이트(예: <4 신규진입 금지)로. 단 아래 구현 결함 보정 필요 |

**규칙·계산식 (Piotroski, 각 +1점, 결측은 0점)**
| # | 규칙 | 계산식 | 근거 |
|---|---|---|---|
| 1 | 순이익 > 0 | 최근 4분기 NI 합계(`get_value`가 열 합산) > 0 | staskh-trading-skills/src/trading_skills/piotroski.py:L33, L59-L60, L67, L165 |
| 2 | ROA > 0 | TTM NI / 최근 연간 총자산 (평균자산 아님) | piotroski.py:L124-L126, L175 |
| 3 | OCF > 0 | 최근 4분기 영업현금흐름 합 > 0 | piotroski.py:L70, L185 |
| 4 | OCF > NI | 발생액(accrual) 대용 | piotroski.py:L195-L199 |
| 5 | 장기부채 감소 | 연간 Long Term Debt 올해 < 전년 | piotroski.py:L209-L213 |
| 6 | 유동비율 증가 | 유동자산/유동부채 올해 > 전년 | piotroski.py:L129-L138, L224-L228 |
| 7 | 희석 없음 | "Share Issued" 올해 <= 전년 | piotroski.py:L102-L107, L242-L246 |
| 8 | 매출총이익률 증가 | GP/Revenue 올해 > 전년 | piotroski.py:L141-L150, L257-L261 |
| 9 | 자산회전율 증가 | Revenue/총자산 올해 > 전년 | piotroski.py:L153-L162, L275-L279 |
**점수·등급**: >=8 Excellent, 6-7 Good, 4-5 Fair, <4 Poor (piotroski.py:L293-L300).
**출력 형식**: {symbol, score, max_score 9, criteria{각 passed/value/description/data_available}, interpretation}. fundamentals.py는 info(PER/PBR/PEG/ROE/ROA/마진/부채비율/FCF/공매도비율 등 27개 키, L18-L46), 최근 4분기 손익, 최근 8개 실적(EPS 추정/실제/서프라이즈%, L76-L84).
**SKILL.md와 코드 차이**: 구현이 원 논문과 다름 — 원 논문의 ΔROA 항목이 없고 대신 "순이익>0"과 "ROA>0"이 중복(둘 다 부호 동일, 사실상 같은 신호를 2점 부여) [차이, 코드 기준]. `recent_ni and recent_total_assets` 같은 참(truthiness) 검사 때문에 값이 정확히 0이면 결측 취급(L125). 데이터 결측 시 실패(0점) 처리로 해외·소형주는 점수가 낮게 편향.
**한국 시장 적용**: OpenDART 사업보고서/분기보고서 XBRL에서 동일 9항목 산출 가능 [추정]. K-IFRS는 매출총이익 항목이 없는 기업(서비스업 등)이 있어 항목 8 결측 처리 규칙 필요. Share Issued 대신 발행주식총수 변동(유상증자·CB 전환) 사용. 금융업은 제외.

### staskh/whale-hunting — 옵션 대량체결 탐지 (이상치 알고리즘만 이식 가치)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 옵션 체인 "투입금액(invested)" 이상치 탐지: 수정 Z-점수(MAD 기반, Iglewicz-Hoaglin 3.5 컷오프 [추정 출처]) + 거래당 금액 규칙 + 방향성 필터 |
| 분류 | 범위 밖(브로커/옵션). 단 이상치 알고리즘은 (a)로 일봉 거래대금 이상 탐지에 전용 가능 |
| 필요 데이터 | Yahoo 옵션체인(무료) + Massive(구 Polygon) 초단위 바 API(`MASSIVE_API_KEY`, 유료 [추정]); 키 없으면 yahoo only |
| 파일 | src/trading_skills/massive/whales.py, .claude/skills/whale-hunting/SKILL.md |
| 라이선스 | MIT / 이식 판단: 부분(옵션 부분 폐기, `_modified_z_score`와 거래량>미결제 규칙의 발상만 "거래대금 급증" 탐지에 활용) |

| # | 규칙 | 계산식·임계값 | 근거 |
|---|---|---|---|
| 1 | 수정 Z-점수 | Mz=0.6745*(x-median)/MAD, Mz>sigma_z(기본 3.5)면 이상치; MAD=0이면 중앙값 초과 전부 | staskh-trading-skills/src/trading_skills/massive/whales.py:L65-L89 |
| 2 | 투입금액 | invested = 가격(vwap 또는 lastPrice) * 거래량 * 100(승수) | whales.py:L163, L450 |
| 3 | 1차 후보(야후) | 수정Z 이상치 OR 당일거래량 > 미결제약정(OI); reason = z_score/volume>oi/both | whales.py:L361-L384 |
| 4 | 2차 고래 확정(초단위) | 수정Z 이상치 OR (invested/transactions >= $1,000,000) | whales.py:L181-L187 |
| 5 | 소액다건 제외 | 이상치여도 invested/transactions <= $50,000이면 제외 | whales.py:L192-L199 |
| 6 | 방향성 흐름 | 손익분기가 현물 대비 +1.5% 이상인 콜 / -1.5% 이하 풋만 방향성(DIRECTIONAL_PCT=1.5) | whales.py:L276, L328-L343 |
| 7 | 해석 | 방향성 C/P < 0.5 약세, > 2.0 강세; transactions=1이면 최강 신호 | whale-hunting/SKILL.md (해석 절) |
[차이] SKILL.md는 `--sigma`(표준편차 배수, 기본 3.0)를 문서화하나 실행 스크립트는 `--sigma-z`만 정의 (.claude/skills/whale-hunting/scripts/whale_hunting.py:L25-L45). 실제 임계는 수정Z 3.5.
한국 적용: KRX 옵션은 KOSPI200 지수옵션 중심(개별종목옵션 미미) → 고래 탐지 직접 이식 불가. 대안으로 일별 거래대금(또는 거래량)에 MAD 수정Z>3.5를 적용해 "수급 이상" 플래그, KRX 투자자별(외국인·기관) 순매수 일별 데이터와 결합 [추정].

### staskh/insider-trading — SEC Form 4 요약
| 항목 | 내용 |
|---|---|
| 기법·출처 | yfinance `insider_transactions`(SEC Form 4)를 90일 창으로 집계, 순매수금액 부호로 판정 |
| 분류 | (c) 이벤트/공시 데이터 필요 |
| 필요 데이터 | yfinance(무료), 한국은 DART 임원·주요주주 특정증권 소유상황보고서 [추정] |
| 파일 | src/trading_skills/insider_trading.py |
| 라이선스 | MIT / 이식 판단: 부분 — 단순 순매수금액 부호는 약한 신호라 임계·직책 가중 추가 필요 |

| # | 규칙 | 내용 | 근거 |
|---|---|---|---|
| 1 | 조회 창 | 기본 days_back=90, Start Date >= now-90일 | insider_trading.py:L73, L86, L95 |
| 2 | 거래 분류 | 텍스트에 sale/sell/sold → sell; purchase/buy/bought → buy; exercise/option/conversion → exercise; 그 외 other (매도 키워드가 먼저 검사됨) | insider_trading.py:L21-L32 |
| 3 | 판정 | net_value = 매수금액합 - 매도금액합; >0 net_buying, <0 net_selling, 0 neutral | insider_trading.py:L120-L133 |
| 4 | 다종목 순위 | net_value 내림차순 | insider_trading.py:L153-L157 |
| 5 | 가격 보정 | value/shares, 없으면 텍스트 "at price N" 정규식 | insider_trading.py:L43-L50, L13-L18 |
결함: 직책 가중·최소금액·클러스터(다수 임원 동시 매수) 규칙 없음, 옵션행사·주식보상(award)도 sell/other로 섞임 [추정: 분류 키워드 한계]. 점수 없음 3단 라벨만.

### staskh/news-sentiment — 뉴스 헤드라인 조회 (감성 계산 없음)
코드는 헤드라인·출판사·시각만 가져온다. 감성 점수·사전·모델이 전혀 없고 "헤드라인으로 직접 판단하라"고 LLM에 맡김 (news-sentiment/SKILL.md "Judge the sentiment from the headlines yourself"; staskh-trading-skills/src/trading_skills/news.py:L105-L134). 소스: yfinance Ticker.news → 실패/빈 응답 시 Yahoo RSS(feeds.finance.yahoo.com, L17, L115). RSS는 종목 태깅일 뿐 해당 종목 기사가 아닐 수 있음(L19-L22). 분류 (d) 정성 위주 → 규칙 엔진 부적합. 한국은 네이버 금융/DART 공시 + 별도 감성모델 필요 [추정]. MIT. 이식: 보류(뉴스 소스 폴백 구조 "빈 응답과 실패를 구분" 원칙만 참고, news.py:L108-L111).

### rkiding/alphaear-sentiment — 뉴스 감성 (BERT 또는 LLM 프롬프트)
| 항목 | 내용 |
|---|---|
| 기법·출처 | HuggingFace 텍스트분류 파이프라인 결과를 [-1,1] 점수로 변환; LLM 모드는 프롬프트만 제공(코드 내 LLM 호출 제거됨) |
| 분류 | (c) 뉴스 필요 / 일부 (d) |
| 필요 데이터 | 뉴스 제목 텍스트(SQLite `daily_news` 테이블), transformers/torch, 모델 다운로드(무료) |
| 데이터 소스 | 중국어 중심: 기본 모델이 중국어, 뉴스 소스 예시 "wallstreetcn"(华尔街见闻) — 중국/A주 지향 |
| 주요 파일 | rkiding-awesome-finance-skills/skills/alphaear-sentiment/scripts/sentiment_tools.py, SKILL.md |
| 라이선스 | Apache-2.0 |
| 이식 판단 | 보류. 한국어 금융 감성모델(예: KR-FinBert 계열 [추정])로 교체 시에만 "뉴스 위원" 입력으로 부분 사용 |

| # | 규칙 | 값 | 근거 |
|---|---|---|---|
| 1 | 모드 | SENTIMENT_MODE 환경변수 auto/bert/llm (기본 auto) | alphaear-sentiment/scripts/sentiment_tools.py:L10, L35 |
| 2 | 기본 모델 | `uer/roberta-base-finetuned-chinanews-chinese` (BERT_SENTIMENT_MODEL로 교체) | sentiment_tools.py:L47 |
| 3 | 점수 변환 | 라벨에 neg 포함 → -conf; neu 포함 → 0; 그 외 +conf(=라벨 무관 양수) | sentiment_tools.py:L150-L154 |
| 4 | 라벨 | score>0.1 positive, < -0.1 negative, 그 외 neutral; max_length 512 절단 | sentiment_tools.py:L144, L158 |
| 5 | 배치 | 제목만 분석, 이미 sentiment_score가 있는(0이 아닌) 행 제외, limit 50 | sentiment_tools.py:L166-L191 |
| 6 | LLM 프롬프트 | JSON {score -1~1, label, reason}; 구간 Pos 0.1~1, Neg -1~-0.1, Neutral -0.1~0.1 | alphaear-sentiment/SKILL.md:L35-L46 |
[차이] SKILL.md/README는 "FinBERT"라 하나(SKILL.md:L10, L18; README.md:L60) 코드 기본 모델은 FinBERT가 아니라 중국어 chinanews RoBERTa다. 이 모델은 감성이 아닌 뉴스 주제 분류기로 알려져 있어 [추정], 그 경우 라벨에 neg/neu가 없어 모든 점수가 양수 신뢰도가 되는 오작동 가능(sentiment_tools.py:L150-L154). 또한 `not item.get('sentiment_score')`는 점수 0.0인 중립 기사를 반복 재분석(L179).

### rkiding/alphaear-predictor — Kronos 시계열 예측 + 뉴스 보정
| 항목 | 내용 |
|---|---|
| 기법·출처 | Kronos 금융 K선 파운데이션 모델(HF `NeoQuasar/Kronos-base` + `Kronos-Tokenizer-base`)을 추론에 사용 + 저자가 추가한 "뉴스 투영층"(MiniLM 임베딩 384차원 -> d_model Linear) 소규모 학습 + LLM 정성 보정 프롬프트. Kronos 원저작은 별도 연구팀 [추정] |
| 분류 | (d) 자동매매 부적합(비결정적 생성모델 + LLM 주관 보정) — 일봉 OHLCV만 쓰는 부분은 (a)지만 결정론 엔진과 맞지 않음 |
| 필요 데이터 | OHLCV 일봉(`open,high,low,close,volume`) 최근 lookback개; 뉴스 텍스트(선택); torch/transformers/sentence-transformers, GPU 권장. 데이터 소스: akshare(A주·홍콩, 동방재부 폴백)·yfinance(미국) |
| 주요 파일 | rkiding-awesome-finance-skills/skills/alphaear-predictor/scripts/kronos_predictor.py, forecast_agent.py, scripts/utils/predictor/training.py, model/kronos.py, references/PROMPTS.md |
| 라이선스 | Apache-2.0 (모델 가중치·Kronos 코드 라이선스는 별도 확인 필요) |
| 이식 판단 | 보류. 예측값을 신호로 쓰려면 별도 백테스트 필요, 저장소에 검증 근거 부족 |

| # | 규칙 | 값 | 근거 |
|---|---|---|---|
| 1 | 예측 파라미터 | lookback 20, pred_len 5 (영업일), T=1.0, top_p=0.9, sample_count=1, max_context 512 — 샘플링 생성이라 실행마다 결과가 다름 | alphaear-predictor/scripts/kronos_predictor.py:L107, L114, L132, L148-L158 |
| 2 | 최소 데이터 | len(df) < lookback이면 빈 결과; forecast_agent는 lookback보다 짧아도 10봉 이상이면 축소 사용 | kronos_predictor.py:L122-L124; forecast_agent.py:L52-L57 |
| 3 | 뉴스 보정 | 학습된 `kronos_news_*.pt`가 있고 news_text가 있을 때만, 텍스트 앞 1000자를 임베딩해 hidden에 bias로 더함(`news_proj(emb)`) | kronos_predictor.py:L70-L102, L137-L141; model/kronos.py:L273-L274 |
| 4 | 학습 데이터 생성 | 일간 등락 |change_pct| > 2.0% 날을 "쇼크"로 추출(종목당 최대 5개, 직전 50봉 이력), 1년치 | training.py:L75-L104 |
| 5 | 인과 검증 | 바이두 검색 결과를 LLM에 주고 "이 뉴스가 그 변동을 설명하는가" JSON 판정, is_causal true인 것만 학습셋 (최대 200건) | training.py:L109-L172, L198 |
| 6 | 학습 | 투영층만 학습, Adam lr=1e-3, 30 epoch, 80/20 분할(seed 42), 손실=CrossEntropy(s1)+(s2)의 평균(첫 예측 토큰만) | training.py:L228-L241, L249-L255, L284 |
| 7 | 평가 | base vs news MAE 비교, improvement=(b_mae-n_mae)/b_mae*100; 검증 표본 소수 | training.py:L336-L398 (evaluation 일부) |
| 8 | LLM 보정 프롬프트 | OHLC 예측을 뉴스 맥락으로 "주관적으로" 조정, 점수·수치 규칙 없음 | alphaear-predictor/references/PROMPTS.md:L3-L43 |
**출력 형식**: List[KLinePoint(date, open, high, low, close, volume)] (schema/models.py:L79-L85), 방향·확률·신뢰구간 없음. 매수/매도 신호 정의 자체가 없다.
**SKILL.md와 코드 차이**: SKILL.md 예시 `from scripts.utils.kronos_predictor import ...; predictor.predict("600519", horizon="7d")` (SKILL.md:L28-L35)는 실제 코드와 불일치 — 파일은 `scripts/kronos_predictor.py`, 클래스에는 `predict()`가 아니라 `get_base_forecast(df, lookback, pred_len, news_text)`만 있고(kronos_predictor.py:L114) 종목코드·"7d" 인자를 받지 않음 [차이]. 저장소에 학습된 가중치 `kronos_news_v1_20260101_0015.pt`(약 1.28MB)가 커밋돼 있음. 예시 종목 600519는 중국 A주(贵州茅台).
**한국 시장 적용**: Kronos는 다시장 K선으로 사전학습됐다고 알려져 있으나 [추정] 한국 일봉 적합성은 미검증. 뉴스 쇼크 기준 2.0%는 A주 ±10% 한도 기준 설정으로 보이며 [추정] KRX ±30%·종목 변동성 대비 정규화(예: ATR 대비) 필요. 학습 파이프라인은 바이두 검색·중국어 프롬프트 고정.

### rkiding/alphaear-signal-tracker — 투자신호(ISQ) 구조화 + 진화 판정 (LLM 프롬프트 패턴)
| 항목 | 내용 |
|---|---|
| 기법·출처 | LLM이 뉴스에서 `InvestmentSignal`(정성 신호)을 만들고, 새 정보로 Strengthened/Weakened/Falsified/Unchanged를 판정하는 프롬프트. "ISQ"(Investment Signal Quality) 5차원은 저자 정의 |
| 분류 | (d) 정성 위주 / 일부 (c) 뉴스 필요. 코드에 결정론적 추적 로직 없음 |
| 필요 데이터 | 뉴스 검색(Baidu/DDG 등), 주가, LLM(agno 프레임워크), SQLite |
| 주요 파일 | rkiding-awesome-finance-skills/skills/alphaear-signal-tracker/SKILL.md, references/PROMPTS.md, scripts/schema/isq_template.py, scripts/schema/models.py, scripts/fin_agent.py |
| 라이선스 | Apache-2.0 |
| 이식 판단 | 부분: ISQ 가중합 공식과 "이미 가격에 반영됐는가(price-in)" 개념을 뉴스 관점 점수에 차용. 추적 판정은 LLM 의존이라 보류 |

| # | 규칙 | 값 | 근거 |
|---|---|---|---|
| 1 | 신호 스키마 | sentiment_score -1~1, confidence 0~1, intensity 1~5(정수), expectation_gap 0~1, timeliness 0~1, expected_horizon(T+N), price_in_status(미정가/부분/충분) | alphaear-signal-tracker/scripts/schema/models.py:L36-L44 |
| 2 | 종합 점수 | overall = 0.35*confidence + 0.30*(intensity/5) + 0.20*expectation_gap + 0.15*timeliness, [0,1] 클립; sentiment(방향)는 가중합에서 제외 | scripts/schema/isq_template.py:L175, L199-L204, L368-L381 |
| 3 | 점수 해석 | <0.3 비추천, 0.3~0.6 참고, 0.6~0.8 양호, >=0.8 강력 | isq_template.py:L178-L181 |
| 4 | 시간창 해석 | timeliness 0.8~1.0 = 반응창 1주 미만, 0.5~0.8 = 1주~1개월, 0.2~0.5 = 1~3개월 | isq_template.py:L153-L156 |
| 5 | 진화 판정 | 코드 없음. 프롬프트가 "논리가 바뀌었나(Falsified/Realized/strengthened)"를 LLM에 묻고 sentiment_score/confidence/expectation_gap을 갱신 | references/PROMPTS.md:L49-L72 |
| 6 | 티커 환각 방지 | 코드 5~6자리 숫자만 허용, DB에 존재, 리서치 결과 또는 원문/출처에 코드·공식명이 언급된 경우만 유지 | scripts/fin_agent.py:L24-L101 (sanitize_signal_output) |
[차이] SKILL.md:L43은 `scripts/fin_agent.py`의 `track_signal` 메서드를 보라고 하나 해당 메서드가 없다(fin_agent.py 정의: `__init__`, `_clean_digits`, `sanitize_signal_output`뿐, 106줄). "Strengthened/Weakened/Falsified/Unchanged"는 SKILL.md 서술일 뿐 코드 enum/임계값이 없음.
한국 적용: 5~6자리 숫자 코드 검증은 KRX 6자리와 호환(A주·홍콩 5자리 가정이라 규칙 수정 필요). 소스(Baidu/중국 뉴스) 교체. 규칙 엔진에서는 LLM 출력 점수를 입력으로 받을 때 "범위 클립·티커 검증·출처 필수" 가드가 유용 [추정].

### staskh/report-stock — 종합 추천 규칙 (scanner + Piotroski + 밸류에이션 결합)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 다른 스킬 점수를 정수 포인트로 재합산해 3단 추천. 분류 (b)+(a) / 이식: 부분(위원회 합의 규칙의 소형 예시) / MIT |
| 파일 | staskh-trading-skills/src/trading_skills/report.py:L245-L341 |

| # | 규칙 | 포인트 | 근거 |
|---|---|---|---|
| 1 | 추세 | bullish score >=6 이면 +2, >=4 이면 +1, 그 외 위험 표시 | report.py:L264-L271 |
| 2 | PMCC 적합도 | >=9 +2, >=7 +1 (옵션이라 범위 밖) | report.py:L274-L281 |
| 3 | 밸류에이션 | forwardPE <15 이면 +1, >30 이면 위험 | report.py:L284-L289 |
| 4 | RSI | >70 또는 <30은 위험 문구만(포인트 없음) | report.py:L292-L296 |
| 5 | Piotroski | >=7 +1, <=3 위험 | report.py:L299-L304 |
| 6 | 보조 | ADX>=25, 배당수익률>2%, ROE>15%는 강점 문구(포인트 없음); 배당성향>80%, 부채비율>100%, 매출성장<0은 위험 문구 | report.py:L307-L322 |
| 7 | 판정 | points>=4 BUY, >=2 HOLD/MONITOR, 그 외 AVOID/WAIT | report.py:L325-L333 |
[차이] 문구가 "score/8"(report.py:L266)이나 scanner_bullish 이론 최대는 9.5 — 표기 불일치(임계 6/4는 scanner SKILL 해석과 동일).

### 기타 staskh 스킬 (짧은 표)
| 스킬 | 내용 | 분류 | 이식 |
|---|---|---|---|
| scanner-pmcc | 옵션 PMCC(저비용 커버드콜) 후보 점수. 최대 14점; 추세점수 SMA50 ±1.0, RSI>50 ±0.5, MACD ±0.5 (범위 -2~+2, scanner_pmcc.py:L467-L503), 실적 근접 점수(실적 45일 초과 +1.0 / 단기만기 내 -2.0 / 그 사이 -1.0, L506-L538), 주간옵션 감지(만기 간격 <=10일, L541-L556) | 범위 밖(옵션) | "실적 발표 임박 시 감점/회피" 규칙만 참고(한국은 DART 일정으로 대체 [추정]) |
| ib-stop-loss | 기준가=max(현재가, 평단) 후 stop=기준*(1-stop_pct/100), 기본 stop_pct 40(SKILL.md:L93), 조기경고=stop_pct/2 (broker/stop_loss.py:L31-L56, L287-L288) | 범위 밖(브로커) | 청산 규칙 아이디어: 기준가 래칫(평단 아래로 내리지 않음) |
| ib-trailing-stop | IB 네이티브 TRAIL 주문, 기본 trail_pct 20, 초기 기준=max(현재가, 평단), forced면 현재가 (broker/trailing_stop.py:L32-L66, L415) | 범위 밖(브로커) | 트레일링 청산 비율 설정의 참고값 20%(주식 기본) [KRX는 ±30% 한도·변동성 맞춰 ATR 기반 권장 추정] |
| ib-account/portfolio/trades-history/option-chain/collar/pmcc-advisor/find-short-roll/delta-adjusted-notional/portfolio-action-report/create-consolidated-report | IBKR 계좌·옵션·롤·콜라 관리, TWS/Gateway 필요 | 범위 밖(브로커/옵션) | 폐기 |
| option-chain, greeks | 옵션 체인·블랙숄즈 그릭스(black_scholes.py 237줄) | 범위 밖(옵션) | 폐기 |
| earnings-calendar, calendar | 어닝일·경제 캘린더(NASDAQ, ForexFactory 스크레이프) | (c) | 한국은 DART·KRX 일정으로 대체 시 이벤트 회피 필터로만 |
| price-history, stock-quote | yfinance 일봉/시세 조회 래퍼 | (a) | 이미 보유 기능 |
| markdown-to-pdf | 보고서 PDF 변환 | 비거래 | 폐기 |
| correlation (technical-analysis 하위) | 가격수준 상관 — 결함 | (a) | 수익률 상관으로 재구현 시 포트폴리오 집중도 게이트에 사용 |

### rkiding 나머지 스킬 (짧은 표)
| 스킬 | 내용 | 분류 | 이식 |
|---|---|---|---|
| alphaear-news | 핫뉴스 수집: newsnow.busiyi.world 집계 API로 财联社·华尔街见闻·微博 등 중국 소스 + Polymarket (alphaear-news/scripts/news_tools.py:L14-L60) | (c) 중국 소스 | 폐기(소스 불일치) |
| alphaear-stock | A주/홍콩/미국 티커 검색·일봉(akshare, 동방재부 직접호출 폴백, 미국은 yfinance) (alphaear-stock/scripts/stock_tools.py:L157-L181, L290-L310) | (a) 중국 | 폐기(KRX 데이터는 별도 소스) |
| alphaear-search | Jina/DDG/Baidu 웹검색 + 로컬 RAG | (c) | 폐기 |
| alphaear-reporter / logic-visualizer | LLM 보고서 작성, Draw.io 인과도 | (d) | 폐기 |
| alphaear-deepear-lite | 외부 DeepEar Lite 대시보드 신호 조회 | (c) 외부 서비스 | 폐기(외부 의존) |
| skill-creator | 스킬 스캐폴딩 | 비거래 | 폐기 |
공통: rkiding 스킬은 저장소 안에서 같은 파일(database_manager.py, stock_tools.py 등)이 스킬 폴더마다 복제돼 있다(26k줄 중 대부분 중복).

#### 그룹 소결
이식할 것(우선순위):
1. 위원회 "추세" 관점 점수기 — scanner-bullish 가산표를 단일 관점으로: 종가>SMA20 +1, >SMA50 +1, MACD>시그널 +1, 히스토그램 증가 +0.5, EMA9>EMA21 +0.5(아니면 -0.25), ADX14>25 & +DI>-DI +1.5(+DI 우위만 +0.5), 모멘텀 clip(수익률%/20, -1, +2); 이론 범위 -2.25~+9.5, 해석 >6 강/4~6 보통/<2 약 (scanner_bullish.py:L98-L175, SKILL.md:L93-L98). 단 RSI는 별도 관점으로 분리하고 한국 거래일 기준 63봉 윈도 고정.
2. 이중 크로스 신선도 규칙 — EMA9/21과 MACD 히스토그램 부호 교차가 같은 방향이고 둘 다 10봉 이내면 +1.0(하락은 -1.0), 일치하나 오래되면 ±0.5, 방향 충돌 -0.5 (scanner_bullish.py:L12-L61; 탐지 technicals.py:L74-L119). 진입 트리거 후보.
3. 리스크 게이트 입력 — risk.py의 일변동성·연환산(√252→KRX 일수), VaR95 = mean-1.645*σ, VaR99 = mean-2.326*σ, MDD(누적곱 기반), 베타 cov/var, 최소 20수익률 (risk.py:L25, L36-L61). 단 정규 VaR은 ±30% 한도 종목에서 과소평가하므로 경험적 분위수 병행, 베타 분모 ddof 통일.
4. 재무 건전성 관점 — Piotroski 9항목을 OpenDART로 재구현(결함 보정: 중복된 NI>0/ROA>0 중 하나를 ΔROA로 교체), 등급 >=8/6~7/4~5/<4, 하드 게이트 예: <4 신규 진입 금지 (piotroski.py:L164-L300).
5. 수급 이상 탐지 — whale의 수정 Z(0.6745*(x-median)/MAD > 3.5, MAD=0이면 중앙값 초과 전부)를 일별 거래대금·외국인/기관 순매수에 적용 (whales.py:L65-L89). 옵션 부분은 폐기.
6. 신호 품질 가중합과 가드 — ISQ 0.35*확신도+0.30*강도/5+0.20*기대차+0.15*시급성(사실상 뉴스 관점이 LLM 점수를 받을 때의 정규화 틀), LLM 출력의 티커·출처 검증 (isq_template.py:L175-L204; fin_agent.py:L24-L101). Kronos 예측·FinBERT 표기 감성은 검증 근거 부족/비결정성으로 보류.
확인 못 한 것: pandas-ta 기본 파라미터(MACD 12/26/9, RSI/ADX 평활 방식)는 라이브러리 소스를 읽지 않은 [추정]; Kronos 원 라이선스·사전학습 데이터; chinanews 모델의 실제 라벨(주제 분류기라는 점은 [추정]); alphaear 학습 평가 수치 결과(저장소에 결과 로그 없음).


---

## 22. agiprolabs/claude-trading-skills (퀀트 일반 스킬 중심)
> 저장소: agiprolabs/claude-trading-skills (커밋 981e1d7, 2026-09-02, MIT) · 범위: 깊게 18종 / 짧게 12종 / 나머지 목록

### regime-detection — 시장 레짐 판별
| 항목 | 내용 |
|---|---|
| 기법·출처 | ATR 백분위(변동성) + ADX(추세 강도) + EMA 기울기(방향) + BB폭 백분위 + R/S Hurst + CUSUM + (선택) Gaussian HMM. 원논문 인용 없음(Hamilton 등 미언급, grep 확인) [추정: 표준 기법] |
| 분류 | (a) 일봉만으로 구현 가능 (HMM은 hmmlearn 필요, 선택) |
| 필요 데이터 | OHLCV (HMM 권장 피처에 volume ratio 포함) |
| 주요 파일 | skills/regime-detection/scripts/detect_regime.py, scripts/regime_backtest.py, references/methodology.md, references/strategy_adaptation.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 레짐 필터(4분면) + 사이징 승수. Hurst는 부분 채택(노이즈 큼), HMM 보류 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 기본 파라미터 | ATR 14, ADX 14, BB 20/2.0, VOL_LOOKBACK 100, HURST_MAX_LAG 50, EMA 20/50 | skills/regime-detection/scripts/detect_regime.py:L34-L41 |
| 2 | ATR 백분위 | TR=max(H-L,|H-Cprev|,|L-Cprev|); ATR=TR 단순 rolling(14) 평균(Wilder 아님); 백분위=ATR.rolling(100).rank(pct=True) | detect_regime.py:L181-L220 |
| 3 | ADX | +DM=high.diff().clip(0), -DM=(-low.diff()).clip(0), 작은 쪽 0; ATR·DM·DX 모두 ewm(span=14, adjust=False); DX=100*|+DI-(-DI)|/(합+1e-10) | detect_regime.py:L223-L260 |
| 4 | 추세 방향 | EMA20; slope=ema.diff(5); +1 = slope>0 AND close>ema, -1 = slope<0 AND close<ema, 그 외 0 | detect_regime.py:L263-L279 |
| 5 | BB 폭 백분위 | width=(2*2.0*std20)/sma20; rolling(100).rank(pct) | detect_regime.py:L282-L300 |
| 6 | Hurst(R/S) | lag 2..min(50,n/4), lag별 chunk의 R/S 평균, log-log polyfit 기울기, [0,1] 클램프, 데이터 부족(<2*max_lag)이면 0.5; 롤링은 로그수익률 100개 창 | detect_regime.py:L303-L372 |
| 7 | 변동성 3단계 | vol_pct<0.30 low, >0.70 high, 그 외 normal | detect_regime.py:L389-L392 |
| 8 | 추세 3단계 | ADX>25 trending, <20 ranging, 사이 transitional | detect_regime.py:L394-L397 |
| 9 | Hurst 3단계 | H<0.4 mean_reverting, >0.6 trending, 사이 random_walk | detect_regime.py:L404-L407 |
| 10 | 4분면 | trending & vol!=high=quiet_trend; trending & high=volatile_trend; 비추세 & !high=quiet_range; 비추세 & high=volatile_range (transitional은 비추세로 취급) | detect_regime.py:L409-L421 |
| 11 | 분면별 권고 | quiet_trend: 추세추종 풀사이즈, 2x ATR 트레일링; volatile_trend: 50% 사이즈, 3x ATR; quiet_range: 평균회귀, 1.5x ATR 고정손절; volatile_range: 25% 또는 관망, 3x ATR | detect_regime.py:L431-L468 |
| 12 | 백테스트용 레짐 | ADX>22 추세, vol_pct>0.65 고변동 (detect_regime.py와 다름) | regime_backtest.py:L179-L200 |
| 13 | 적응형 사이즈 승수 | quiet_trend 1.0 / volatile_trend 0.50 / quiet_range 0.75 / volatile_range 0.25 | regime_backtest.py:L299-L306 |
| 14 | 적응형 신호 | 추세 레짐=EMA(10,30) 크로스(매수 시 fast>slow & 전봉 fast<=slow); 레인지 레짐=RSI14 <35 매수, >65 매도; 롱온리, 수수료 10bp/편도 | regime_backtest.py:L28-L39, L308-L322 |
| 15 | CUSUM | z=(r-mean)/std, S+=max(0,S+ + z-0.5), S-=max(0,S- - z-0.5), >h(기본 2.0; 문서 권장 2~5) 시 변화점+리셋. 문서: 최근 50~100봉으로 μ,σ 재계산 | skills/regime-detection/SKILL.md:L168-L190 (코드블록), references/methodology.md:L155-L170 |
| 16 | HMM | GaussianHMM(n_components=2~3, covariance_type="full", n_iter=100); 피처 로그수익률+롤링변동성+거래량비; 상태 라벨은 임의(해석 필요) | SKILL.md:L195-L212, references/methodology.md:L186-L200 |
| 17 | 전환 플레이북 | 신호 2개 이상 정렬 시 사이즈 50%로 축소 -> 3~5봉 대기 -> 5봉 이상 지속될 때 전략 전환; 단일 봉 신호로 완전 전환 금지. 조기경보: BB폭 75p 상향돌파, ADX 20 상향돌파+거래량 2배, ADX 30 이상에서 하락+DI 수렴 | references/strategy_adaptation.md:L125-L143 |

**출력 형식**: classify_regime -> dict{volatility, trend, direction, hurst, quadrant}; 권고 문자열 리스트(detect_regime.py:L375-L428). 위원회 점수로 쓰려면 사이즈 승수(표 13)를 그대로 매핑 가능.

**SKILL.md와 코드 차이**
- [차이] SKILL.md는 ATR 백분위 <25/>75 구분(SKILL.md 'ATR Volatility Percentile' 절)이나 코드는 0.30/0.70(detect_regime.py:L389-L392), 백테스트는 0.65(regime_backtest.py:L190).
- [차이] ADX 임계: 분류 25/20, 백테스트 단일 22.
- 데모 코드: detect_regime.py:L45-L75는 합성 데이터(4개 구간 75봉씩), regime_backtest.py:L43는 합성 500봉. 성과 수치는 검증 가치 없음. detect_regime.py는 BIRDEYE_API_KEY로 가상자산 OHLCV를 가져옴(L28-L29, L111) — 이식 시 불필요.
- SKILL.md에서 compute_atr_percentile은 rolling.apply(rank)지만 코드는 rolling.rank(pct=True)로 동일 의미.

**한국 시장 적용**: 가상자산용 파라미터 표(ADX 7~14, ATR lookback 20~100)는 무시, 주식 열은 ATR 100~200, ADX 14~28, Hurst 창 200+(SKILL.md:L160-L167). 코스피/코스닥 지수 단위로 레짐 계산 후 종목 필터에 쓰는 구성이 자연스럽다 [추정]. ±30% 상한 때문에 갭이 큰 종목은 TR이 커져 ATR 백분위가 왜곡될 수 있음 [추정]. 숏 제약이 크므로 'down' 방향 레짐은 신규 진입 금지/청산 가속으로만 사용.

### mean-reversion — 평균회귀(ADF·Hurst·VR·반감기·OU·z-score·페어)
| 항목 | 내용 |
|---|---|
| 기법·출처 | ADF(Dickey-Fuller), R/S Hurst, Lo-MacKinlay 분산비, AR(1) 반감기, Ornstein-Uhlenbeck, z-score 밴드, Engle-Granger 페어. 저자 인용은 코드 주석 수준(MacKinnon 근사 임계, Lo-MacKinlay z) |
| 분류 | (a) 일봉 종가만으로 구현 가능 |
| 필요 데이터 | 종가(로그가격), 페어는 2종목 종가 |
| 주요 파일 | skills/mean-reversion/scripts/mean_reversion_test.py, scripts/pairs_scanner.py, references/strategy_design.md, SKILL.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택 — 평균회귀 진입 트리거(위원회 점수기)+청산(시간손절). ADF/VR 사전검정은 데이터 품질/종목 필터. 페어는 숏 제약 때문에 보류 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | ADF(상수, 증강 lag=1) | Δy = a + b*y(t-1) + Σ c*Δy(t-k); t=b/SE; 임계 하드코딩 -3.43(1%), -2.86(5%), -2.57(10%), p는 근사 구간값 0.005/0.03/0.07/0.20 (진짜 p-value 아님) | skills/mean-reversion/scripts/mean_reversion_test.py:L38-L96 |
| 2 | 분산비 VR(q=5) | log가격; VR=Var(q-기간수익)/(q*Var(1기간)); z=(VR-1)/sqrt(2(q-1)/(3n)) (동분산 Lo-MacKinlay); p<0.05 & VR<1 평균회귀, VR>1 추세 | mean_reversion_test.py:L152-L194 |
| 3 | 반감기 | Δx=a+b*x(t-1); b<0일 때 HL=-ln2/ln(1+b), 평균 mu=-a/b; b>=0이면 -1(비회귀) | mean_reversion_test.py:L197-L242 |
| 4 | OU 매핑 | theta=-ln(1+b)/dt; sigma=resid_std*sqrt(2θ/(1-e^{-2θdt})); HL=ln2/theta | mean_reversion_test.py:L245-L301 |
| 5 | Hurst(R/S) | min_window 10, 창 크기 w=max(w+1,int(1.5w)) 기하증가 ~ n//2까지, log-log 기울기; H<0.5 평균회귀. 길이<20이면 예외 | mean_reversion_test.py:L99-L149 |
| 6 | z-score | z=(P-rolling_mean)/rolling_std; lookback=2*반감기(기본), 고정 대안 20(일봉) | mean_reversion_test.py:L304-L323; references/strategy_design.md:L26-L28 |
| 7 | 상태머신 | 무포지션: z<-entry 롱, z>+entry 숏; 롱 청산 z>-exit_z, 손절 z<-stop_z; 숏 대칭. 기본 entry 2.0 / exit 0.0 / stop 3.0 | mean_reversion_test.py:L326-L371 |
| 8 | 임계 프로파일 | 보수 entry 2.5/exit 0.25/stop 3.5; 중간 2.0/0/3.0; 공격 1.5/-0.5(오버슈트)/4.0; 시간손절 3x/2x/4x 반감기 | references/strategy_design.md:L30-L37 |
| 9 | 반감기 기반 운용 | lookback 2x HL, 보유 목표 1x HL, 최대 보유 3x HL, 재계산 주기 0.5x HL | SKILL.md:L114-L121 |
| 10 | z 비례 사이징 | size = base*min(|z|/entry, max_scale=2.0) | SKILL.md:L166-L170; references/strategy_design.md:L73 |
| 11 | 분할 진입 | |z| 1.5/2.0/2.5/3.0에서 각 25%씩 (누적 25/50/75/100%) | references/strategy_design.md:L80-L88 |
| 12 | 리스크 규칙 | 손실 포지션 -2% (포트폴리오), 연속 5패 시 중단 및 정상성 재검정, 일 DD>3% 당일 중단, 주 DD>5% 사이즈 50%, 월 DD>10% 전략 중단 | references/strategy_design.md:L156-L172 |
| 13 | 레짐 게이트 | 횡보 레짐에서만 신규 진입, 추세 전환 시 손절 타이트, 변동성 급등/붕괴 시 전량 청산 | references/strategy_design.md:L177-L180 |
| 14 | 최소 기대 이동 | 왕복비용*2 이상 기대 회귀폭 필요(예: 왕복 60bp->120bp); 표본 최소 50거래(Sharpe 100+, DD 200+) | references/strategy_design.md:L192-L201 |
| 15 | 페어 품질점수(0~100) | 공적분 통과 +40(p<0.10 이면 +20) + Hurst<0.5 시 20*(0.5-H)/0.5 + 1<HL<50 +20 + |pearson|>0.5 +10 + |spearman|>0.5 +10; 페어 lookback=max(10,int(2*HL)); |z|<0.5이면 AT MEAN | skills/mean-reversion/scripts/pairs_scanner.py:L218-L318 (L275-L285 채점) |
| 16 | 인샘플/아웃 | 60%/40% 분할, 롤링·앵커드 | references/strategy_design.md:L207-L210 |

**출력 형식**: dict(test_statistic, p_value_approx, conclusion), half_life, OU(theta,mu,sigma), 포지션 배열(1/-1/0), 페어 표(quality_score, signal: BUY/SELL SPREAD/AT MEAN/NO SIGNAL).

**SKILL.md와 코드 차이**
- [차이] pairs_scanner.py:L70-L72는 주석에 "공적분용 더 엄격한 값 사용"이라 쓰고 실제로는 일반 ADF 임계(-2.86 등)를 그대로 사용 -> Engle-Granger 임계(5% 약 -3.3~-3.4 [추정])보다 느슨해 공적분 과대판정 위험. 이식 시 정확한 EG 임계 또는 statsmodels coint 사용 필요.
- [차이] ADF p-value는 4구간 근사값(mean_reversion_test.py:L77-L89).
- SKILL.md:L142-L165 z-signal 예시는 `...` 생략(스텁); 실제 구현은 mean_reversion_test.py:L326.
- 합성 데이터(generate_demo_data L374)와 Birdeye API(L408) 사용 -> 데모/가상자산용. 성과 수치 없음.
- 레이어드 진입 표 vs 단일 상태머신: 코드에는 분할 진입 구현 없음(문서만).

**한국 시장 적용**: 가상자산 DEX 비용(30bp) 예시는 한국 거래세+수수료(약 0.2%+0.015%x2 [추정])로 대체해 '최소 기대 이동' 계산. 일봉 lookback 20 기본 사용 가능. 단일 종목 평균회귀는 ±30% 가격제한/VI/거래정지·관리종목 필터가 필요. 숏 레그가 필요한 페어/롱숏은 개인 공매도 제약으로 롱온리 변형(저평가 레그만 매수)만 가능.

### exit-strategies — 청산 전략(손절·익절·트레일링·시간·신호·유동성)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 고정% 손절, ATR 손절/트레일링(Chandelier Exit, Le Beau/Elder 계열 [추정]), EMA 트레일링, Parabolic SAR(Wilder), SuperTrend, R-배수 분할익절, 래칫 스톱, 시간 손절. 원저자 인용 없음 |
| 분류 | (a) 일봉 OHLC만으로 구현 가능 (시총 이정표·PumpFun 규칙은 해당 없음(가상자산)) |
| 필요 데이터 | OHLC(+ATR14), 거래량(유동성 청산) |
| 주요 파일 | skills/exit-strategies/SKILL.md, scripts/exit_simulator.py, scripts/stop_loss_calculator.py, references/{stop_loss_methods,trailing_stops,take_profit_strategies}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 청산 모듈: 우선순위 체인(하드스톱>ATR트레일>익절>시간), 분할익절+래칫, 변동성 백분위 스케일 손절 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | ATR 손절 | stop = entry - ATR(14)*mult; mult 1.5 타이트/2.0 표준(기본)/3.0 스윙 | skills/exit-strategies/SKILL.md:L22-L47 |
| 2 | 승률-배수 대응표 | 1.0x: 승률>65%, R:R 1~2:1 / 1.5x >55% / 2.0x >45% 3~5:1 / 2.5x >40% / 3.0x >35% 5~10:1 | references/stop_loss_methods.md:L67-L75 |
| 3 | 일봉 ATR 기간 | 일봉 ATR(14~20) | references/stop_loss_methods.md:L77-L86 |
| 4 | 변동성 적응 손절 | pct=ATR이력 내 백분위; vol_scale=0.7+0.6*pct; 손절=entry-ATR*base(2.0)*vol_scale (0.7x~1.3x) | references/stop_loss_methods.md:L96-L124 |
| 5 | 지지선 손절 | 최근 N봉 최저가 아래 offset 2% | references/stop_loss_methods.md:L128-L152 |
| 6 | 고정% 손절 | 5/10/15/20% 표, 하드스톱 최대 20% (코드 예 FIXED_STOP_PCTS=[0.05,0.10,0.15,0.20]) | references/stop_loss_methods.md:L9-L19; scripts/stop_loss_calculator.py:L38 |
| 7 | 손절 안티패턴 | 라운드넘버 1~3% 아래로 오프셋; 손절 거리 최소 1x ATR(권장 1.5~2x); 위험이 계좌 5% 초과면 사이즈 축소; 손절 이동은 유리한 방향만 | references/stop_loss_methods.md:L215-L248 |
| 8 | R 목표 | risk=entry-stop; TP=entry+risk*R; 스타일별 R: 스캘프 1.5/2, 데이트레이드 2/3, 스윙 3/5; 손익분기 승률 1:1>50%, 2:1>33%, 3:1>25%, 5:1>17% | SKILL.md:L49-L63; references/take_profit_strategies.md:L45-L64 |
| 9 | 분할익절(코드) | 목표 R [2,3,5], 각 25% 매도, 마지막 25% 문볼은 고점대비 15% 트레일; 1차 체결 시 stop=entry(본전), 2차+ 시 stop=entry+risk*직전목표R | scripts/exit_simulator.py:L35-L36, L181-L271 |
| 10 | 분할익절(문서) | 4트랜치 25%씩: 2R/4R/8R/트레일링(EMA20 또는 고점-15%) | references/take_profit_strategies.md:L68-L106 |
| 11 | 래칫 스톱 | 2R->본전, 3R->+1R, 5R->+3R, 10R->+7R | references/trailing_stops.md:L251-L272 |
| 12 | % 트레일 | stop=최고가*(1-trail); 스캘프3~5%, 데이 7~12%, 스윙 15~25%, 밈 20~35%; 코드 기본 0.10 | references/trailing_stops.md:L54-L61; SKILL.md:L87-L100 |
| 13 | Chandelier | 최고가(lookback 22) - ATR*mult(기본 2.5 SKILL, 문서표 3.0); 변동성 레짐별 ATR10 x 2.0/3.0/4.0 | SKILL.md:L102-L112; references/trailing_stops.md:L105-L112, L243-L250 |
| 14 | ATR 트레일(코드) | peak=최고 종가; trail=max(이전, peak-ATR_t*2.5); close<=trail이면 청산; 초기 trail=entry-ATR0*mult | scripts/exit_simulator.py:L133-L178 |
| 15 | EMA 트레일 | close<EMA가 M봉 연속(문서 3봉, 코드 EMA_CONSEC=2); EMA 10/20/50 | SKILL.md:L121-L130; scripts/exit_simulator.py:L32-L33 |
| 16 | Parabolic SAR | 표준 AF 0.02/0.02/0.20; 가상자산 0.01/0.01/0.15 | references/trailing_stops.md:L117-L147 |
| 17 | 시간 손절 | bars_held>max_hold AND pnl<=0 청산; 스윙 3~5일/10~20봉 (시뮬 TIME_STOP_BARS=50) | SKILL.md:L132-L148; scripts/exit_simulator.py:L34, L322 |
| 18 | 신호 청산 | RSI14>70 롱 청산; MACD 약세 크로스; 트레일 조임 용도로 병행 권장 | SKILL.md:L150-L167 |
| 19 | 유동성 청산 | 거래량 MA10 < MA50*0.3 이면 청산 | SKILL.md:L169-L181 |
| 20 | 결합 템플릿 | hard_stop -20%(priority1) > ATR trail 2.5x/14(2) > 분할익절 2R/4R/8R 각25%(3) > 시간 50봉 미수익시(4); ATR트레일은 1차 익절 체결 후 활성 | SKILL.md:L224-L263 |
| 21 | 손절-사이징 연계 | stop_loss_calculator 기본 RISK_PCT=0.02, 사이즈=계좌*2%/손절거리; RR 표 [2,3,5,10] | scripts/stop_loss_calculator.py:L35, L41-L44, L97-L130 |

**출력 형식**: 시뮬레이터 dict(strategy, exit_bar, exit_price, exit_reason, pnl_pct, peak_price); 계산기는 표 출력.

**SKILL.md와 코드 차이**
- [차이] Chandelier: 문서는 최고가(highs, lookback 22) 기준, exit_simulator는 최고 종가(peak) 기준·lookback 없음(L133-L178). 문서 기본 mult 2.5 vs 레퍼런스 표 기본 3.0.
- [차이] SKILL.md:L160-L162 MACD 청산 예: MACDs(시그널선) < MACDh(히스토그램)를 비교 — 컬럼 혼동으로 보이는 오류 [추정]. 이식 금지, MACD<시그널로 재작성.
- [차이] 시뮬은 종가만 검사(장중 저가 터치 미반영) -> 일봉 이식 시 저가 기준 체결/갭 처리 필요.
- 시뮬은 합성 가격(seed 42, 200봉)이라 전략별 수익률 비교는 근거가 약함(exit_simulator.py:L24-L26, L40).
- 밈/PumpFun/시총 이정표(SKILL.md:L183-L222)는 해당 없음(가상자산).

**한국 시장 적용**: 청산가는 호가단위(가격대별 1~1,000원)로 반올림, 손절가 갭 하락 시 시가 체결 가정(일봉은 저가<손절이면 min(시가, 손절) 처리 [추정]). 하한가 근접(-30%) 시 청산 불능 가능성은 유동성 청산 규칙(#19)으로 보강. 동시호가(15:20~15:30) 청산 옵션. 일봉 기본값은 ATR14, 2.0~2.5x, 시간손절 10~20봉이 무난 [추정].

### position-sizing — 포지션 사이징(고정비율·변동성·켈리·유동성·안티마팅게일·포트폴리오 한도)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Fixed fractional(Van Tharp/Vince 계열 [추정]), 변동성 타깃팅, Kelly, 안티마팅게일. 원저자 인용 없음 |
| 분류 | (a) 일봉(ATR)+계좌정보만으로 가능. 유동성 항목은 AMM 풀 가정이라 해당 없음(가상자산) -> 일평균거래대금 한도로 대체 |
| 필요 데이터 | 진입가·손절가, ATR14, 승률/손익비(거래 이력) |
| 주요 파일 | skills/position-sizing/SKILL.md, scripts/size_calculator.py, scripts/portfolio_sizer.py, references/{sizing_formulas,practical_guide}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 사이징 모듈: "네 방법 중 최소값" 사다리 + 포트폴리오 한도 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 고정비율 | units = (계좌*risk%)/|entry-stop|; risk 티어 0.5~1% 보수 / 1~2% 표준 / 3~5% 공격 | skills/position-sizing/SKILL.md:L24-L61 |
| 2 | 비용 반영 | effective_risk = |entry-stop| + entry*fee*2(왕복) + entry*slippage; units = risk_amount/effective_risk (기본 FEE_RATE 0.003, SLIPPAGE_EST 0.005) | scripts/size_calculator.py:L57-L58, L63-L106 |
| 3 | 변동성 조정 | units = (계좌*target_vol 2%)/ATR14 (= 하루 ATR 변동이 계좌 2%) | SKILL.md:L63-L90; scripts/size_calculator.py:L109-L143 |
| 4 | 켈리 | f=(p*b-q)/b, 기본 fraction 0.25(권장), 0.5 중간, 1.0 금지; 손절거리로 환산: units=계좌*f*fraction/|entry-stop| (켈리 분수를 '위험 비율'로 사용) | SKILL.md:L92-L139; scripts/size_calculator.py:L146-L197 |
| 5 | 유동성 | max_trade = pool*max_slippage; 단일 거래 풀의 2%, 포지션 5%, 풀 깊이 >= 10x 포지션 | SKILL.md:L141-L172 |
| 6 | 안티마팅게일 | 연패 시 mult=max(0.5, 1-연패*0.25); 연승 시 min(2.0, 1+연승*0.25) | SKILL.md:L174-L200 |
| 7 | 사다리 | final = min(켈리, 고정비율, 변동성, 유동성) — 구속 제약을 보고 | SKILL.md:L202-L220 |
| 8 | 계좌 수준 한도 | 단일 종목 10%, 상관 묶음 25%, 총 노출 50~80%, 동시 포지션 5~10 (코드 상수 10%/25%/70%, 위험 2%) | SKILL.md:L222-L233; scripts/portfolio_sizer.py:L26-L33 |
| 9 | 상관 조정 위험 | 같은 섹터 포지션 상관 0.5 고정, 타 섹터 0: Var=Σrisk_i^2 + 2*0.5*Σ_{i<j} risk_i*risk_j; sqrt | scripts/portfolio_sizer.py:L227-L269 |
| 10 | 신규 포지션 예산 | max_new=min(총노출한도(70%)-현재노출, 단일한도 10%); 섹터 여유=25%*계좌-섹터 노출 | scripts/portfolio_sizer.py:L272-L319 |
| 11 | 계좌 규모별 | 소액 1~2%/단일 10%/총 50~70%; 중간 0.5~1%/8%/40~60%; 대형 0.25~0.5%/5%/30~50% | references/practical_guide.md:L17-L38 |
| 12 | 조정 규칙 | 3연패 -> 정상 50%; 고점대비 DD>10% -> 최소 사이즈; 신규 전략 25%에서 시작, 50+거래 실적 후 25->100% 확대 | references/practical_guide.md:L80-L100 |
| 13 | 켈리 분수 효율 | 0.5x -> 성장률 75%, 0.25x -> 44%, 0.1x -> 19% | references/sizing_formulas.md:L139-L156 |

**출력 형식**: dict(units, value, risk_amount, effective_risk, full_kelly, fractional_kelly, has_edge, ...) 및 표 출력.

**SKILL.md와 코드 차이**
- [차이] 켈리 사이징 코드가 켈리 분수를 '자본 대비 손실 위험 비율'로 해석(units=계좌*f/손절거리). 켈리 f는 본래 투입 자본 비율(손익비 b 기준)이므로 손절=1단위 손실로 환산하는 가정이 필요 — 일관되나 문서의 "position_value=계좌*f" 해석과 혼동 소지.
- [차이] expected_growth_fraction=f*(2-f/f*) 식은 f<<1 근사 [추정]; 검증 없이 사용 금지(size_calculator.py:L195).
- 데모 입력(계좌 $10,000, 진입 1.50, 손절 1.30) 기본값은 예시일 뿐. portfolio_sizer 데모 포지션은 합성(L108).
- PumpFun 사이징(SKILL.md:L235-L252)과 AMM 슬리피지는 해당 없음(가상자산).

**한국 시장 적용**: units는 정수 주 단위 내림, 호가단위 반올림 후 손절거리 재계산. 비용은 거래세+수수료(왕복 약 0.25~0.3% [추정])를 fee 항목에 반영. 유동성 한도는 '20일 평균 거래대금의 일정% (예: 1~5%) [추정]'로 변환. 총노출 70%/단일 10%는 한국 개별 종목 5~10종목 구성에 그대로 쓸 수 있음. 가격제한 ±30%로 손절 갭 리스크는 상한이 있으나 하한가 잠김 시 청산 불가 -> 손절이 보장되지 않으므로 계좌 위험 2%는 실제로 초과할 수 있음.

### kelly-criterion — 켈리 기준(분수 켈리·거래이력 추정·안정성)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Kelly(1956, Bell Labs; SKILL.md:L8 명시), 분수 켈리, Wilson 구간, 롤링 켈리 안정성 점수. Thorp 등은 미인용(grep 확인) |
| 분류 | (a) 거래 이력만 있으면 구현 가능(일봉 전략의 청산 손익 리스트) |
| 필요 데이터 | 거래별 손익 리스트(백테스트/실거래) |
| 주요 파일 | skills/kelly-criterion/SKILL.md, scripts/kelly_calculator.py, scripts/kelly_from_trades.py, references/{kelly_derivation,practical_kelly}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 사이징 상한(캡)과 사후 분석(전략 건강 점검). 켈리 값 자체를 사이징 직접 입력으로 쓰지 않고 min()의 한 항으로 사용 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 켈리 | f*=(p*b-q)/b, b=평균이익/평균손실, edge=p*b-q | skills/kelly-criterion/scripts/kelly_calculator.py:L43-L70 |
| 2 | 성장률 | G(f)=p*ln(1+f*b)+q*ln(1-f); f>=1이면 -inf | kelly_calculator.py:L73-L97 |
| 3 | 분수 표 | 기본 0.10/0.25/0.33/0.50, 민감도 승률 오프셋 ±2/5/10%p | kelly_calculator.py:L36-L37 |
| 4 | 권장 분수(문서) | 0.10x(<30거래), 0.25x(30~100), 0.50x(100+), 1.0x 금지; 최소 50거래, 선호 100+, 공격 200+ | skills/kelly-criterion/SKILL.md:L77-L97 |
| 5 | 보수적 승률 | Wilson 하한(z=1.96)으로 p 대체 -> conservative_kelly | SKILL.md:L111-L127; scripts/kelly_from_trades.py:L99-L121, L175-L180 |
| 6 | 분수 자동 추천 | 표본: <30 ->0.10, <50 ->0.15, <100 ->0.25, <200 ->0.33, 이상 0.50; 안정성: <0.3 ->0.10, <0.5 ->0.20, <0.7 ->0.30, 이상 0.50; 엣지: >0.30 ->0.15, >0.15 ->0.30, 아니면 0.50; 세 값의 min; edge<=0이면 0 | scripts/kelly_from_trades.py:L243-L306 |
| 7 | 롤링 켈리 | 창 30거래, 안정성 = 1-CV/2 (CV=표준편차/|평균|), 유효값 5개 미만 0 | kelly_from_trades.py:L41, L194-L240 |
| 8 | 엣지 등급(코드) | <0 음수; <0.02 무의미; <0.05 약함; <0.10 보통; <0.20 좋음; <0.50 우수(과적합 확인); 이상 의심 | kelly_calculator.py:L122-L144 |
| 9 | 분수별 성장·DD(문서) | 0.5x 성장 ~75%/DD 25~40%; 0.25x ~50%?/DD 12~20%; 2배 과투자=성장 0 | SKILL.md:L62-L75 |
| 10 | 동시 포지션 | 개별 켈리 합>1이면 비례 축소; 상관 보정 n_eff=n/(1+(n-1)*ρ), 각 f*n_eff/n; 총 켈리 캡 1.0(실무 0.6~0.8) | SKILL.md:L141-L178 |
| 11 | 연속 켈리 | f*=(μ-r)/σ² | SKILL.md:L229-L246 |
| 12 | 비용 차감 | 켈리 계산 전 추정 비용을 엣지에서 차감 | SKILL.md:L219-L227 |

**출력 형식**: dict(win_rate, win_rate_ci, avg_win, avg_loss, payoff_ratio, edge, kelly_full, conservative_kelly), 추천 분수+사유 문자열, 롤링 켈리 리스트, 안정성 점수.

**SKILL.md와 코드 차이**
- [차이] 엣지 등급: 문서 L129-L139는 0.02~0.10 marginal/0.10~0.20 good/>0.20 excellent이나 코드는 0.02/0.05/0.10/0.20/0.50 6단계. 코드 기준 사용.
- [차이] SKILL.md:L246 "Sharpe²/(2σ)"는 부정확: f*=(μ-r)/σ²=Sharpe/σ, 성장률 g=Sharpe²/2 [추정: 표준 이론]. 
- [차이] approx_max_drawdown(kelly_calculator.py:L100-L119)은 fraction*0.6 선형 휴리스틱(주석 자체가 rough)이라 문서의 DD 표(25~40% 등)와 근거가 약함 — 이식 금지.
- kelly_from_trades는 데모(generate_demo_trades, seed 42, 100건, L47)로 동작; 실제 이식은 우리 백테스트 거래 목록을 넣으면 됨.

**한국 시장 적용**: 거래 손익에 세금/수수료 차감 후 계산(규칙 #12). 일봉 단기 전략은 거래 수가 적어 50거래 미만 -> 0.10x 구간이 현실적. 종목 간 상관이 높은 국내 시장(테마주)에서는 규칙 #10의 상관 보정을 쓰고, 총 켈리 캡 0.6~0.8은 현금 비중 규칙으로 쓸 수 있음.

### risk-management — 포트폴리오 리스크 관리(낙폭 단계·일/주 한도·서킷브레이커·VaR)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 낙폭 단계 대응, 일/주 손실 한도, 연속 손실 브레이커, 변동성 브레이커, 역사적 VaR/CVaR, HHI 집중도. 원저자 인용 없음 |
| 분류 | (a) 계좌 손익·일봉 수익률만으로 구현 가능. 스마트컨트랙트·러그·브리지·MEV 항목은 해당 없음(가상자산) |
| 필요 데이터 | 에쿼티 커브, 포지션 목록, 거래 손익 이력 |
| 주요 파일 | skills/risk-management/SKILL.md, scripts/risk_dashboard.py, scripts/drawdown_analyzer.py, references/{circuit_breakers,drawdown_management,exposure_limits}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 리스크 게이트(낙폭 단계표, 연속손실, 변동성 브레이커, 총노출 표) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 최대 낙폭 정지 | 보수 -15% / 중간 -20% / 공격 -25% 시 전면 정지 | skills/risk-management/SKILL.md:L22-L31 |
| 2 | 낙폭 단계 | <5% Normal(풀사이즈); <10% Caution(25~50% 축소); <15% Warning(최소 사이즈); <20% Critical(신규 중단); 이상 Emergency(전면 정지, 48~72h 휴식) | SKILL.md:L87-L95; scripts/drawdown_analyzer.py:L219-L241; scripts/risk_dashboard.py:L239-L256 |
| 3 | 회복 필요 수익 | gain=dd/(1-dd) (-20% -> +25%, -50% -> +100%) | scripts/drawdown_analyzer.py:L203-L216; SKILL.md:L97-L109 |
| 4 | 일 손실 한도 | 보수 -3% / 중간 -4% / 공격 -5% (실현+미실현); 연속 N일(2/3/3) 도달 시 주간 정지 | SKILL.md:L34-L43; references/circuit_breakers.md:L55-L63 |
| 5 | 주 손실 한도 | -5% 사이즈 50%, -7% 최소 사이즈, -10% 전면 정지 | SKILL.md:L44-L50 |
| 6 | 연속 손실 | 3연패 사이즈 50%, 5연패 최소 사이즈, 7연패 24h 정지+점검; 해제는 2연승 | SKILL.md:L115-L123; references/circuit_breakers.md:L105-L117 |
| 7 | 변동성 브레이커 | baseline=20일 수익률 std; current=5일 std; current>2x baseline -> 노출 50% 및 손절 확대, >3x -> 25%; 해제는 <=1.5x(3x 후 2x) | references/circuit_breakers.md:L120-L172 |
| 8 | 시스템 실패 | 체결가가 기대가에서 5% 초과 괴리 시 정지 | references/circuit_breakers.md:L182-L192 |
| 9 | 총 노출 표 | 강한 추세+저변동 80%, 보통 60%, 고변동 40%, DD>10% 30%, DD>15% 20%, 브레이커 가동 0% | references/exposure_limits.md:L44-L57 |
| 10 | 전략별 최대 포지션 | 추세추종 5%, 평균회귀 3%, 모멘텀/스캘프 2%, 돌파 3% | references/exposure_limits.md:L22-L30 |
| 11 | 확신도 승수 | 높음 100% / 중간 50% / 낮음 25% (한도 내) | references/exposure_limits.md:L32-L42 |
| 12 | 집중도 | 단일 섹터 30%, 단일 전략 40%, 동시 포지션 5~10 | SKILL.md:L52-L72 |
| 13 | 대시보드 기본 한도 | 단일 10%, 총 80%, 일 3%, DD 경고 10%/위험 15%/정지 20%, 연속 손실 3, 섹터 30%, 포지션 10 | scripts/risk_dashboard.py:L32-L42 |
| 14 | HHI | 비중(%)^2 합; <1500 분산, 1500~2500 보통, >2500 높음 | scripts/risk_dashboard.py:L165-L181 |
| 15 | VaR/CVaR | 역사적 95%: index=int(0.05*n), 정렬 후 해당 값; CVaR=그 이하 평균 | SKILL.md:L139-L166 |
| 16 | 보조 지표 | Calmar(연수익/MDD), Sortino, 30일 롤링 Sharpe, 연승/연패 추적 | SKILL.md:L182-L187 |

**출력 형식**: 상태 문자열(Normal/Caution/Warning/Critical/Emergency)+권고, 한도별 OK/WARN/CRIT 대시보드, DrawdownSummary(기간·깊이·회복 기간).

**SKILL.md와 코드 차이**
- [차이] 일 한도 리셋은 "UTC 자정"(SKILL.md:L40) — 한국은 KST 장 시작 기준 거래일로 바꿔야 함. 
- [차이] 문서 낙폭 정지(-15/-20/-25%)와 단계표(20% Emergency)가 다른 체계로 공존; 대시보드 코드는 10/15/20 사용(risk_dashboard.py:L36-L38).
- 대시보드 데모 포지션/에쿼티는 합성(risk_dashboard.py:L483, drawdown_analyzer.py:L361). 임계값의 실증 근거는 없음(경험칙).
- ES 구현은 표본이 20개 미만이면 tail이 비어 0 반환 가능(SKILL.md:L155-L165) [추정].

**한국 시장 적용**: 일 단위 리스크 규칙은 거래일 기준 KST로 재정의, 계좌 -3% 일 손실 시 익일 신규 중단. 동시 포지션 상한은 한국 소형 계좌에서 5~10. VaR는 ±30% 가격제한 때문에 꼬리가 절단되나 하한가 연속 시 청산 불가이므로 CVaR 대신 '하한가 시나리오' 스트레스(-30%)를 별도 점검 [추정]. 시스템 실패 브레이커의 5% 괴리는 호가/VI 단일가 때문에 완화된 기준 필요.

### walk-forward-validation — 워크포워드·퍼지/엠바고·DSR·PBO
| 항목 | 내용 |
|---|---|
| 기법·출처 | Walk-forward(롤링/확장), Purging·Embargo·CPCV(López de Prado 2018 명시, SKILL.md:L96-L98), Deflated Sharpe Ratio(Bailey & López de Prado 2014, references/overfit_detection.md:L13), PBO(Bailey et al. 2017, L78), Bonferroni/Holm/BH 보정 |
| 분류 | (a) 일봉 백테스트 수익률만으로 구현 가능 (검증 계층) |
| 필요 데이터 | 전략 일별 수익률 행렬(전략×시간), 시도한 전략/파라미터 수 |
| 주요 파일 | skills/walk-forward-validation/SKILL.md, scripts/walk_forward.py, scripts/overfit_detector.py, references/{methodology,overfit_detection,practical_guide}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 검증 모듈: 폴드 생성기 + DSR(합격선 0.95) + PBO(<0.5) + 최소 백테스트 길이 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | WF 폴드 | 기본 train 90, test 14, step 14, rolling/expanding, purge 0, embargo 0; rolling: train=[off, off+train); expanding: [0, train+off); effective_train_end=train_end-purge; test_start=train_end+embargo; test_end>n이면 종료; 최소 표본=train+purge+embargo+test | skills/walk-forward-validation/scripts/walk_forward.py:L48-L53, L96-L183 |
| 2 | 롤링 vs 확장 | 롤링: 최근 레짐 적응·6개월 미만; 확장: 레짐 안정 모델 | SKILL.md:L51-L58 |
| 3 | Purging | 라벨 구간이 테스트와 겹치는 학습 샘플 제거: ts[i]+label_horizon < test_start_time | SKILL.md:L62-L79 |
| 4 | Embargo | 일봉 2~5봉, 시간봉 6~24봉; 경험칙 엠바고 >= 라벨 horizon의 2배 | SKILL.md:L81-L94 |
| 5 | 창 크기(가상자산 일봉) | 스윙 train 30~90일/test 7~14일/embargo 2~5일; 포지션 90~180/30/5~10 (주식은 252일 train 언급) | SKILL.md:L161-L176 |
| 6 | CPCV | N개 연속 그룹, k개 테스트 그룹 조합 C(N,k)경로 (N=6,k=2 -> 15) | SKILL.md:L96-L106 |
| 7 | DSR | SR_std=sqrt((1-γ3*SR+(γ4-1)/4*SR²)/(T-1)); E[max SR]=z(1-1/N)*(1-γ)+γ*z(1-1/(N*e)), γ=0.5772; DSR=Φ((SR-E[max])/SR_std); SR는 비연율화 후 계산; DSR>0.95 유의 | scripts/overfit_detector.py:L103-L170 |
| 8 | DSR 해석 | >0.95 강한 근거, 0.80~0.95 보통, 0.50~0.80 약함, <0.50 과적합 | references/overfit_detection.md:L59-L66 |
| 9 | PBO | 기본 n_groups=6, n_test_groups=2; IS 평균수익 최고 전략의 OOS 순위 상대값 w=(rank+1)/n_strategies; w>0.5인 경로 비율=PBO; PBO>0.50 과적합 판정; logit 클램프 0.01~0.99 | scripts/overfit_detector.py:L173-L274 |
| 10 | PBO 해석 | <0.10 낮음, 0.10~0.30 보통, 0.30~0.50 높음, >0.50 과적합 가능성 큼 | references/overfit_detection.md:L100-L107 |
| 11 | 최소 백테스트 길이 | T = ceil(1 + (1-γ3*SR+(γ4-1)/4*SR²)*(z_conf/SR)²), 기본 conf 0.95 | scripts/overfit_detector.py:L276-L308 |
| 12 | 다중검정 | Bonferroni α/N; Holm 단계적; BH(FDR) | scripts/overfit_detector.py:L311-L349; references/overfit_detection.md:L113-L140 |
| 13 | 체크리스트 | DSR>0.95, 학습/테스트 Sharpe 비율 <2.0, OOS 지표만 보고 | references/practical_guide.md:L135-L165 |

**출력 형식**: Fold(train/test 인덱스, 날짜 라벨), FoldResult(train/test Sharpe, 수익, MDD, hit rate), DSRResult(dsr_pvalue, is_significant), PBOResult(pbo, n_paths, logit_values, is_overfit), MinBTLResult.

**SKILL.md와 코드 차이**
- [차이] SKILL.md:L124-L126 docstring은 kurtosis를 "excess"라 쓰나 식은 (γ4-1)/4에 raw 첨도(정규=3)를 가정(overfit_detector.py:L108, 문서 references L41) — raw 첨도를 넣어야 함.
- [차이] DSR의 E[max SR]에 시도한 전략 SR들의 분산 스케일(sqrt(V[SR_n]))이 없음 -> 원 논문 대비 단순화 [추정]. 시도 수 N이 크면 과소/과대 보정 가능.
- [차이] walk_forward.run_walk_forward는 데모: SMA(10,30) 고정 파라미터라 train 구간에서 최적화를 하지 않음(L301-L366) — 진짜 WFO(IS 최적화->OOS 평가)가 아님. 합성 가격(annual_vol 0.8, L234-L239), 샤프 연율화 365(L186).
- [차이] PBO 코드는 CPCV 경로에 purge/embargo를 적용하지 않음(L196-L246), 성과 지표는 평균 수익(샤프 아님). 문서(SKILL.md:L96-L102)는 퍼징을 주장.
- 위 PBO 합성 데이터(generate_synthetic_strategies, 20전략 중 진짜 2개, L352)는 데모.

**한국 시장 적용**: 연율화 365 -> 약 245(KRX 거래일) [추정]. 일봉 swing 기준 train 252일/test 21~63일/embargo 5일(보유기간 기준 2배)로 환산 [추정]. 상장폐지·거래정지 종목을 포함한 생존편향 없는 유니버스가 필수(SKILL.md:L164 가상자산 항목과 동일 문제). DSR의 N에는 파라미터 그리드 크기를 포함.

### volatility-modeling — 변동성 추정·예측(실현변동성·EWMA·GARCH·변동성 콘)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Close-to-close, Parkinson(1980), Garman-Klass(1980), Yang-Zhang(2000, 문서 수식만), RiskMetrics EWMA(λ=0.94), GARCH(1,1)(Bollerslev; 논문 인용은 없음 [추정]), 변동성 콘 |
| 분류 | (a) 일봉 OHLC만으로 구현 가능 (GARCH MLE는 scipy 필요) |
| 필요 데이터 | OHLC 일봉 |
| 주요 파일 | skills/volatility-modeling/SKILL.md, scripts/estimate_volatility.py, scripts/vol_forecast.py, references/{estimators,volatility_cones}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 변동성 타깃 사이징 입력과 레짐(변동성 축)으로 사용. GARCH MLE는 부분(일봉 소수 종목엔 EWMA로 충분) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | Close-to-close | 로그수익 rolling std(ddof=1)*sqrt(연율화) | skills/volatility-modeling/scripts/estimate_volatility.py:L175-L189 |
| 2 | Parkinson | sqrt(mean(ln(H/L)²)/(4 ln2))*sqrt(A); 문서상 CC 대비 효율 약 5배 | estimate_volatility.py:L192-L208; SKILL.md:L59-L70 |
| 3 | Garman-Klass | gk=0.5*ln(H/L)²-(2ln2-1)*ln(C/O)²; sqrt(mean(gk).clip(0))*sqrt(A) | estimate_volatility.py:L211-L235; SKILL.md:L72-L84 |
| 4 | Yang-Zhang(문서만) | σ²=σ²_overnight+k σ²_OC+(1-k)σ²_RS, k=0.34/(1.34+(n+1)/(n-1)), RS=mean[ln(H/C)ln(H/O)+ln(L/C)ln(L/O)]; 효율 약 8 | references/estimators.md:L108-L132 (코드 구현 없음: estimate_volatility.py def 목록에 부재) |
| 5 | EWMA | var_t=λ var_{t-1}+(1-λ) r²_{t-1}; λ 0.94(일), 0.97(주); 다단계 예측은 평평 | estimate_volatility.py:L36, L238-L268; SKILL.md:L92-L107, L177-L179 |
| 6 | GARCH 고정 | alpha 0.08, beta 0.88; omega=Var(r)*(1-α-β), 하한 1e-10; 초기 var=처음 20개 분산 | estimate_volatility.py:L270-L308 |
| 7 | GARCH MLE | 가우시안 -0.5Σ[ln σ²+r²/σ²]; SLSQP; 초기 omega=Var*0.04, α0.08, β0.88; 경계 α[1e-4,0.5], β[0.3,0.999], α+β<=0.9999 | scripts/vol_forecast.py:L254-L325 |
| 8 | GARCH 예측 | σ²_{t+h}=V_L+(α+β)^h(σ²_t-V_L), V_L=ω/(1-α-β); 예측 지평 [1,7,14,30,60,90] | SKILL.md:L181-L196; vol_forecast.py:L38 |
| 9 | 변동성 콘 | 창 [7,14,30,60,90], 백분위 [5,25,50,75,95]; 현재 vol>75p 고평가(평균회귀 예상), <25p 압축(확장 예상) | estimate_volatility.py:L37-L38, L311-L352; SKILL.md:L141-L145 |
| 10 | 연율 vol 레짐 | <40% 저, 40~80 보통, 80~120 고, >120 위기(가상자산 기준) | estimate_volatility.py:L355-L373; SKILL.md:L164-L173 |
| 11 | 변동성 타깃 | weight = target_vol(일 2%)/current_vol(일) | SKILL.md:L200-L208 |
| 12 | 전략 선택 | vol 백분위 <25 평균회귀, >75 모멘텀 돌파, 그 외 균형 | SKILL.md:L217-L228 |

**출력 형식**: 연율/일 변동성 시계열, 추정기 비교표, 콘 표(창×백분위), GARCH 파라미터(ω,α,β, persistence)와 예측 경로.

**SKILL.md와 코드 차이**
- [차이] 콘 창: 문서 5/10/20/60/120일(SKILL.md:L134-L137) vs 코드 7/14/30/60/90(estimate_volatility.py:L37).
- [차이] Yang-Zhang는 문서에만 있고 코드에 구현 없음(주식 시가 갭이 있는 한국 일봉에는 오히려 필요 -> 이식 시 직접 구현).
- 데모: generate_demo_data(estimate_volatility.py:L42)·generate_demo_returns(vol_forecast.py:L42, 참값 ω=5e-6, α0.10, β0.85) 합성. L62의 합성 변동성 식은 이상한 상수 조합 [추정: 의미 없는 데모].
- 연율화 365 고정(L35, vol_forecast.py:L36), 연율 vol 레짐 임계(40/80/120%)는 가상자산 기준.

**한국 시장 적용**: 연율화 sqrt(245) [추정]. 레짐 임계는 코스피 개별주 기준으로 재보정(대략 저 <25%, 보통 25~50, 고 50~80, 위기 >80 [추정]) — 고정값 이식 금지, 종목별 자기 이력 백분위(콘/ATR 백분위)로 상대화. 시가 갭(전일 종가->시가)과 점심 휴장 없음, 시간외 단일가는 일봉 OHLC에 반영 안 됨 -> Garman-Klass보다 Yang-Zhang 또는 CC 병행. ±30% 한도로 극단 수익률이 절단되므로 GARCH 꼬리 가정은 과대평가될 수 있음.

### signal-classification — 트리 모델 신호 분류(XGBoost/GBM, 워크포워드, 임계 최적화)
| 항목 | 내용 |
|---|---|
| 기법·출처 | XGBoost/sklearn GradientBoosting 이진분류(전방수익 라벨), 워크포워드+갭, 확률 임계(Profit Factor) 최적화, SHAP 중요도. 논문 인용 없음 |
| 분류 | (a) 일봉 OHLCV 파생 피처로 구현 가능 (ML 의존: xgboost/sklearn/shap) |
| 필요 데이터 | OHLCV 파생 피처, 전방수익 라벨 |
| 주요 파일 | skills/signal-classification/SKILL.md, scripts/train_classifier.py, scripts/walk_forward_backtest.py, references/{model_guide,validation_methods}.md |
| 라이선스 | MIT |
| 이식 판단 | 부분/보류 — 규칙 엔진의 결정론 원칙과 충돌(재현·설명 가능성). 위원회의 보조 점수기(관점 1개)로 실험할 가치. 라벨링·갭·비용차감 임계 최적화 절차만 검증 도구로 채택 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 라벨 | 전방 N봉 수익 > +1% -> 1, < -1% -> 0, 그 사이 NaN(학습 제외); 코드 기본 horizon 12, threshold 0.01 (문서 예 horizon 24) | skills/signal-classification/scripts/train_classifier.py:L48-L49, L126-L145; SKILL.md:L25-L55 |
| 2 | 워크포워드 | 코드 기본 train 60 / test 20 / step 10 / gap 12(=horizon); 문서 기본 720/168/24/24(시간봉) | train_classifier.py:L50-L53; SKILL.md:L102-L144 |
| 3 | 모델 하이퍼파라미터 | XGB: n_estimators 200, max_depth 4, lr 0.05, subsample 0.8, colsample 0.8, min_child_weight 5, gamma 0.1; 폴백 GBM 100/4/0.05/0.8 | train_classifier.py:L195-L227 |
| 4 | 확률 임계 최적화 | thresholds 0.45~0.85 step 0.01; 신호 수>=10; 수익률-비용(0.005 왕복) 후 PF=총이익/총손실 최대; 문서 범위 0.50~0.85, 통상 0.60~0.75 | train_classifier.py:L334-L372; SKILL.md:L216-L262 |
| 5 | 비용 | 왕복 0.5%(50bp)를 순수익에서 차감 | SKILL.md:L278-L284; scripts/walk_forward_backtest.py:L46 |
| 6 | 불균형 대응 | 중립구간 제거, scale_pos_weight, SMOTE(룩어헤드 주의), 임계 상향 | SKILL.md:L269-L277 |
| 7 | 백테스트 | 신호 시 진입 후 FORWARD_HORIZON(12)봉 보유, 순수익 계산; 랜덤 신호·바이앤홀드와 비교; train 100/test 30/step 15/gap 12 | scripts/walk_forward_backtest.py:L39-L46, L309-L360, L396, L432 |
| 8 | 피처 감쇠 | 롤링 성과 모니터링 후 재학습 | SKILL.md:L286-L288 |

**출력 형식**: 폴드별 accuracy/precision/recall/F1/AUC, OOS 확률 배열, 최적 임계·PF·신호 수, SHAP 순위.

**SKILL.md와 코드 차이**
- [차이] 문서 임계 탐색 범위 0.50~0.85 / 코드 0.45~0.85, 코드는 비용 차감 포함(문서 L226-L258 예시는 미포함).
- [차이] 기본 horizon 24(문서) vs 12(코드), 창 크기 크게 다름(720/168 vs 60/20).
- 임계 최적화가 풀링된 OOS 예측에 직접 적용(train_classifier.py:L568-L573) -> 임계 자체가 OOS에 과적합(2차 검증 없음) [추정].
- 데이터는 전부 합성(generate_synthetic_data L57, generate_price_data L50: 사인 주기 신호 삽입). 보고 성과 무의미.

**한국 시장 적용**: 라벨 horizon 5~10 거래일, 갭=horizon. 비용 0.5% -> 거래세+수수료+슬리피지로 재산정(약 0.3~0.5% [추정]). 일봉 단일 종목 학습 데이터가 적어(250/년) 교차종목 풀링 필요. 결정론 엔진 목표와 맞지 않으므로 채택 시 고정 시드·모델 버전 고정 필수.

### strategy-framework — 전략 정의 템플릿·수명주기·스코어카드(GO/REVIEW/NO-GO)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 전략 문서 템플릿 + 8단계 수명주기 + 가중 스코어카드. 학술 출처 없음(경험칙) |
| 분류 | (a) 백테스트 요약 통계만 필요 — 사후 분석/검증 게이트 |
| 필요 데이터 | 백테스트 결과(샤프, MDD, PF, 승률, 평균 손익비, 거래 수, IS->OOS 샤프 저하율) |
| 주요 파일 | skills/strategy-framework/SKILL.md, scripts/strategy_scorecard.py, references/{strategy_template,strategy_types}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 전략 승격 게이트(검증/사후 분석). 수치는 한국 일봉에 맞게 재보정 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 종합점수 | 가중합: 엣지 0.30 + 리스크 0.25 + 일관성 0.20 + 표본수 0.10 + 강건성 0.15 | skills/strategy-framework/scripts/strategy_scorecard.py:L109, L153, L225, L272, L314, L338 |
| 2 | 엣지 점수 | 샤프 >=2.0:95, >=1.5:80, >=1.0:65, >=0.5:40, >=0:20, 미만 0; PF>=2.0 +10, PF<1.2 -10 | strategy_scorecard.py:L69-L109 |
| 3 | 리스크 점수 | MDD<=10%:95, <=15:80, <=20:65, <=30:40, <=50:20, 초과 0; 수익/MDD>=3 +10, <1 -10 | strategy_scorecard.py:L112-L153 |
| 4 | 표본수 점수 | 거래 >=500:95, >=200:80, >=100:65, >=50:40, >=20:20, 미만 5; (승률 신뢰구간 마진>0.10이면 -10) | strategy_scorecard.py:L228-L272 |
| 5 | 강건성 점수 | OOS 샤프 저하율: <=0:95(데이터 확인), <=15%:85, <=30%:65, <=50%:40, 초과 15, 미제공 50 | strategy_scorecard.py:L275-L314 |
| 6 | 일관성 | 50 시작; 승률 가점 추세형(>=0.45:+20, >=0.35:+10, >=0.25 중립, 미만 -20), 평균회귀형(>=0.60:+20, >=0.50:+10, >=0.40, 미만 -10/-20); 기대값(R)=승률*손익비-(1-승률) >0.5면 +10 | strategy_scorecard.py:L156-L225 |
| 7 | 판정 | 즉시 NO-GO: 샤프<0 또는 PF<1.0 또는 기대값<0 또는 MDD>50%; GO: 종합>=70 and 우려 0건; REVIEW: >=55; 그 외 NO-GO | strategy_scorecard.py:L355-L385 |
| 8 | 우려/제안 조건 | MDD>25% 우려, 거래<50 우려, PF<1.2 우려; 샤프>3.0은 룩어헤드 의심 제안; 승률<0.35 & 손익비<2 개선 제안 | strategy_scorecard.py:L345-L370 |
| 9 | 등급 | A>=90, B>=75, C>=60, D>=40, F | strategy_scorecard.py:L452-L467 |
| 10 | 라이브 승격 최소 기준 | 추세추종: 거래>=100, OOS 샤프>1.0, PF>1.5, MDD<20%, 승률>35%, 손익비>2.0; 평균회귀: 100, >1.0, >1.5, <15%, >55%, >1.0; 스캘핑: 500, >1.5, >1.3, <10%, >55%, >1.0 | skills/strategy-framework/SKILL.md:L164-L175 |
| 11 | 수명주기 | 백테스트 100거래+, 70/30 워크포워드 -> 페이퍼 2주 또는 30거래 중 긴 쪽(백테스트와 25% 이상 차이면 조사) -> 소액 라이브 30거래 -> 증액 주 25% -> 모니터(일/주/월) -> 은퇴(30일 롤링 샤프<0, 3개월 연속 손실, 레짐 영구 변화) | SKILL.md:L109-L162 |
| 12 | 전략 문서 필드 | 개요/진입/청산(손절·익절·트레일·시간·신호·우선순위)/사이징/리스크/필터(시장·종목·시간)/성과기준 | references/strategy_template.md:L10-L107 |

**출력 형식**: Scorecard(구성요소별 점수·등급·가중치, overall_score, recommendation GO/REVIEW/NO-GO, concerns, suggestions).

**SKILL.md와 코드 차이**: 승격 기준표(SKILL.md:L164-L175)는 스코어카드 코드에 직접 반영되지 않음(코드는 별도 점수 구간). 코드의 일관성 점수는 승률 구간을 전략 유형별로 분기. 데모 전략 3개(L589)는 가짜 입력. 수치는 모두 경험칙이며 출처 없음.

**한국 시장 적용**: 샤프 연율화 245일, 표본수 기준(100거래)은 일봉 스윙에서 달성이 어렵므로 종목 풀링 거래 수로 계산. 수명주기의 페이퍼 단계는 KRX 모의투자 또는 자체 시뮬로 대체. 승격 기준은 비용(거래세 포함) 차감 후 지표로 평가.

### custom-indicators — 가상자산 맞춤 지표 9종(NVT·MVRV·거래소 유입·펀딩·OI·보유자·유동성·스마트머니·회전율)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 온체인/파생 지표(NVT, MVRV는 업계 통용 지표). 인용 없음 |
| 분류 | 대부분 해당 없음(가상자산). 단 일부 구조는 (c) 시장 폭·수급 데이터로 대응물 존재: 회전율, 유동성 점수, 스마트머니 순매수 비율 |
| 필요 데이터 | CoinGecko/DefiLlama API, 온체인 지갑·펀딩·OI (한국 주식에 없음) |
| 주요 파일 | skills/custom-indicators/SKILL.md, scripts/compute_crypto_indicators.py, scripts/holder_momentum.py |
| 라이선스 | MIT |
| 이식 판단 | 보류(전체). 아이디어만 차용: 수급 점수(외국인·기관 순매수/거래대금), 회전율, 유동성 합성 점수 |

**차용 가능한 계산식(코드 확인)**
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 스마트머니 순유입 비율 | net=(스마트 매수-매도)/총거래대금; >0.10 강한 강세, >0.05 강세, <-0.05 약세, <-0.10 강한 약세 | skills/custom-indicators/scripts/compute_crypto_indicators.py:L540-L567 |
| 2 | 회전율(token velocity) | 일 거래량/유통주식수; >0.30 과열, >0.15 높음, >0.05 보통, >0.02 낮음 | compute_crypto_indicators.py:L570-L596 |
| 3 | 유동성 점수 | 0.4*min(1,깊이/포지션)+0.3*max(0,1-스프레드bp/100)+0.3*min(1,풀TVL/(포지션*10)); >=0.8 excellent, >=0.5 good, >=0.3 fair | compute_crypto_indicators.py:L495-L537 |
| 4 | OI-가격 매트릭스 | OI 7일 변화 >1% & 가격 >1% 추세확인 / OI 상승·가격 비상승 약세 축적 / OI 하락·가격 상승 숏스퀴즈 / 둘 다 하락 롱청산 | compute_crypto_indicators.py:L410-L447 |
| 5 | NVT / MVRV | NVT=시총/일 온체인 거래액 (<15 강한 강세, <25, <65 중립, <100, 이상 강한 약세); MVRV=시총/실현시총 (<0.5, <1.0, <2.0, <3.5) | compute_crypto_indicators.py:L288-L359 |

**출력 형식**: 지표값 + 신호 문자열(STRONG BULLISH~STRONG BEARISH), 대시보드 출력.
**SKILL.md와 코드 차이**: 확인한 범위에서 정의 일치. generate_demo_data(L127)는 합성 데모. API 키 필요 항목 다수.
**한국 시장 적용**: 스마트머니 비율 -> (외국인+기관 순매수)/거래대금(KRX 투자자별 매매동향, 일별 데이터 가능 [추정]); 회전율 -> 일 거래량/상장주식수(임계는 한국 기준으로 재보정 필요); 유동성 점수 -> 20일 평균 거래대금·호가 스프레드(호가단위 대비) 합성. (c) 수급 데이터 필요.

### cointegration-analysis — 공적분·페어 트레이딩(Engle-Granger·Johansen·롤링 안정성)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Engle-Granger 2단계(양방향), Johansen(문서만, statsmodels 호출 예), Phillips-Ouliaris(문서만), 롤링 공적분 모니터링. 논문 인용 문구는 없음(grep) |
| 분류 | (a) 일봉 종가 2종목 이상. 단 숏 레그 필요 -> 한국 개인에게 제약 |
| 필요 데이터 | 두 종목 이상의 종가 (200+ 관측 권장) |
| 주요 파일 | skills/cointegration-analysis/SKILL.md, scripts/test_cointegration.py, scripts/pairs_backtest.py, references/{methodology,pairs_trading}.md |
| 라이선스 | MIT |
| 이식 판단 | 보류(롱숏 페어). 롤링 p-value/헤지비율 드리프트 모니터링 규칙과 EG 임계값은 평균회귀 필터로 부분 채택 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 페어 사전 필터 | Pearson 상관 > 0.7로 후보 축소 후 공적분 검정 | skills/cointegration-analysis/SKILL.md:L121-L124 |
| 2 | Engle-Granger | y=a+b*x OLS -> 잔차 ADF; 양방향(y~x, x~y) 검정; EG 전용 임계 1% -3.90, 5% -3.34, 10% -3.04로 판정 (일반 ADF 임계보다 엄격) | scripts/test_cointegration.py:L155-L248 (임계 L196 부근 "eg_critical") |
| 3 | ADF p 근사 | 임계점 보간표: (-3.43,0.01),(-2.86,0.05),(-2.57,0.10),(-1.94,0.30),(-1.62,0.50),(-0.50,0.90),(0,0.95),(1.0,0.99); 코드 주석: 운영은 statsmodels adfuller 권장 | test_cointegration.py:L117-L153 |
| 4 | 스프레드 | spread=y-b*x-a; z=(spread-mean)/std | SKILL.md:L135-L140 |
| 5 | 스프레드 건전성 | ADF p<0.05, Hurst<0.5, 반감기 5~60일이 viable | SKILL.md:L142-L148 |
| 6 | 롤링 모니터링 | 60~90일 창; 정상 p<0.05 / 경고 0.05~0.10 / 중단 >0.10; 헤지비율 변화 <10% / 10~25% / >25%; 반감기 5~60 / 60~120 / >120 또는 <5일 | SKILL.md:L154-L183; scripts/test_cointegration.py:L24 (ROLLING_WINDOW=60) |
| 7 | 백테스트 파라미터 | entry z 2.0, exit 0.0, stop 3.0, 레그당 비용 0.3%, 자본 10만, 레그당 10% 자본; z는 롤링(lookback 60) 평균·표준편차로 룩어헤드 방지; 헤지비율은 학습구간 OLS | scripts/pairs_backtest.py:L31-L36, L130-L180 |
| 8 | 시간 손절 | 진입 후 40봉 초과 시 청산(주석: 반감기 약 20의 2배) | scripts/pairs_backtest.py:L183-L400 (time_stop 부근, 출력 라인 약 L288) |
| 9 | 수량 | qty_x = qty_y*hedge_ratio*y/x (달러 중립 근사) | scripts/pairs_backtest.py:L183-L400 |
| 10 | 함정 | 표본 >200 필요(최소 100), 전체표본 헤지비 추정 후 같은 표본 백테스트 금지, 왕복 4회 거래(레그당 0.3%이면 1.2%) | SKILL.md:L204-L225 |

**출력 형식**: dict(hedge_ratio, intercept, adf_stat, eg_critical_values, cointegrated_5pct/10pct, half_life, hurst, spread stats), 롤링 p-value/헤지비 시계열, 백테스트 거래 리스트·성과.

**SKILL.md와 코드 차이**
- [차이] mean-reversion 스킬의 pairs_scanner.py는 일반 ADF 임계(-2.86)로 공적분을 판정(느슨)하는 반면, 이 스킬의 test_cointegration.py는 EG 임계(-3.34)를 사용 -> 이 스킬 쪽이 정확.
- Johansen/Phillips-Ouliaris는 SKILL.md 예시 코드만 있고 scripts에 구현이 없음(def 목록 확인). 
- 백테스트는 합성 공적분 쌍(generate_cointegrated_pair L85)이라 성과 무의미.

**한국 시장 적용**: 후보는 동일 업종·모자회사/우선주(보통주-우선주 스프레드는 한국 특유의 평균회귀 후보 [추정]). 롱숏이 어려우므로 (1) 우선주/보통주 괴리 롱온리 (2) ETF-선물 차익은 제외. 거래세(매도 약 0.2%)+수수료로 레그당 0.3% 가정은 한국에서 매도 레그에만 거래세가 붙어 비대칭. 대차·공매도 제약(개인 대주 가능 종목 제한)으로 숏 레그는 사실상 인버스 ETF 대체 정도.

### correlation-analysis — 상관분석(롤링·EWMA·클러스터·유효 종목 수·꼬리 의존·상관 레짐)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Pearson/Spearman/Kendall, 롤링·EWMA 상관, 고유값 분해, Ward 계층 클러스터링(거리=sqrt(2(1-ρ)), Mantegna 계열 [추정]), 하측 꼬리 의존, 상관 z-score 레짐. 원저자 인용 없음 |
| 분류 | (a) 일봉 종가(수익률)만으로 구현 가능 |
| 필요 데이터 | 복수 종목 일별 수익률 (가격이 아닌 수익률) |
| 주요 파일 | skills/correlation-analysis/SKILL.md, scripts/correlation_matrix.py, scripts/rolling_correlation.py, references/{methodology,portfolio_applications}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 리스크 게이트(동일 클러스터 노출 한도, 유효 종목 수), 상관 급등 시 노출 축소 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 수익률 기반 | 상관은 항상 가격이 아닌 수익률로 계산 | skills/correlation-analysis/SKILL.md:L28-L40 |
| 2 | 창 | 단기 20 / 중기 60 / 장기 120일 | scripts/rolling_correlation.py:L31; SKILL.md:L98-L104 |
| 3 | EWMA 상관 | cov=E[xy]-E[x]E[y]; var=E[x²]-E[x]²; span 60; 분모 0이면 NaN | rolling_correlation.py:L148-L168 |
| 4 | 상관 레짐 | 롤링 상관의 120일 평균·표준편차로 z; z>+2.0 HIGH_CORR, z<-2.0 LOW_CORR (문서 예 lookback 252) | rolling_correlation.py:L171-L200; SKILL.md:L223-L236 |
| 5 | 클러스터 | 거리 = sqrt(2(1-ρ)), 대각 0, 대칭화, Ward linkage, fcluster t=1.0 (코드는 최대 5 클러스터) | correlation_matrix.py:L178-L204; SKILL.md:L160-L184 |
| 6 | 유효 종목 수 | N_eff = 1/(1/N + (1-1/N)*평균상관); 고유값 엔트로피 N_eff=exp(-Σp ln p); 1번째 고유값 비중=시장 요인 강도 | correlation_matrix.py:L230-L272 |
| 7 | 하측 꼬리 의존 | P(Y<q_y | X<q_x), q=0.05 | rolling_correlation.py:L32, L227-L270; SKILL.md:L185-L211 |
| 8 | 레짐별 상관 대표값 | 상승 0.4~0.7, 횡보 0.2~0.5, 폭락 0.8~0.95, 회복 0.5~0.7 | SKILL.md:L212-L222 |
| 9 | 최소분산 | w = Σ^-1 1 / (1' Σ^-1 1) | SKILL.md:L147-L158 |

**출력 형식**: 상관행렬(Pearson/Spearman), 극단 페어, 클러스터 라벨·덴드로그램 텍스트, 다양성 지표 dict, 롤링 상관·레짐 DataFrame, 꼬리 의존 계수.

**SKILL.md와 코드 차이**: SKILL.md의 EWMA 상관은 ewm.std 기반(L89-L94), 코드는 분산 공식으로 구현(다른 수치). 가상자산 상관 대표값 표(L239-L258)는 해당 없음(가상자산). 코드 fetch는 CoinGecko(해당 없음), 데모 합성(correlation_matrix.py:L83, rolling_correlation.py:L73).

**한국 시장 적용**: 한국은 테마/업종 동조가 강해 클러스터 한도(동일 클러스터 25%, risk-management/position-sizing의 correlated 25%와 연계)에 바로 쓸 수 있음. 결측(거래정지) 일은 상관 계산에서 제외/보간 주의. 상관 레짐 z>2는 시장 급락 시 노출 축소 트리거로 사용.

### feature-engineering — 트레이딩 ML 피처(카탈로그 43종·정상성·룩어헤드 방지)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 가격/거래량/기술/시간 피처, ADF 정상성, 롤링 정규화, 분산·상관(0.9)·MDI·순열·상호정보 선택. 인용 없음 |
| 분류 | 가격·거래량·기술·시간 피처는 (a) 일봉만. 마이크로구조(체결 단위)·온체인 피처는 해당 없음(가상자산) |
| 필요 데이터 | OHLCV |
| 주요 파일 | skills/feature-engineering/SKILL.md, references/feature_catalog.md, references/pitfalls.md, scripts/build_features.py, scripts/feature_importance.py |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택 — 위원회 점수기의 입력 피처 정의(정상 형태 변환 규칙), 데이터 품질/룩어헤드 체크리스트 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 가격 피처 | log_return, momentum_5/10/20=close/close[N]-1, acceleration=mom5_t-mom5_{t-5}, high_low_range=(H-L)/C, close_position=(C-L)/(H-L), gap=O_t/C_{t-1}-1, rolling skew/kurt(20) | skills/feature-engineering/references/feature_catalog.md:L8-L22 |
| 2 | 거래량 피처 | volume_ratio=V/MA20(>2 스파이크), volume_ma_ratio=SMA5/SMA20, obv_slope(10일 회귀기울기), dollar_volume/롤링평균, volume_cv=std20/mean20 | feature_catalog.md:L24-L38 |
| 3 | 기술 피처 | RSI14, MACD(12,26,9) 히스토그램, BB(20,2) 위치/폭, ATR14/close, ADX14(>25 추세, <20 횡보), Stoch(14,3), CCI20(±100), MFI14, Supertrend(10,3) | feature_catalog.md:L40-L53 |
| 4 | 시작 세트 12개 | log_return, return_volatility, momentum_10, close_position, volume_ratio, volume_ma_ratio, rsi, bb_position, atr_ratio, adx, hour_sin/cos | feature_catalog.md:L108-L120 |
| 5 | 정상화 | 가격->로그수익, 거래량->비율, OBV->기울기, RSI 등 유계 지표는 그대로 | SKILL.md:L132-L160 |
| 6 | 정규화 | 롤링 60 z-score, 전체표본 z-score 금지(룩어헤드) | SKILL.md:L163-L185 |
| 7 | 선택 | VarianceThreshold 0.01 -> 상관 >0.9 쌍 제거(타깃 상관 높은 쪽 유지) -> RF 중요도 -> 상호정보 | SKILL.md:L202-L245; scripts/feature_importance.py:L32 |
| 8 | 라벨 | forward=close.shift(-N)/close-1; 임계 1h 1%, 4h 3%, 일봉 5%; 코드 기본 N=5, 임계 1% | SKILL.md:L246-L275; scripts/build_features.py:L50-L51, L376-L393 |
| 9 | 룩어헤드 금지 4원칙 | 롤링만 사용, 타깃만 앞으로 shift, 특성-타깃 정렬 검증, 시간순 분할 | SKILL.md:L186-L201 |
| 10 | 학습 전 체크리스트 | 타깃과 lag0 상관 >0.5인 피처 없음, 피처 수 < 표본/15, ADF p<0.05, 클래스 불균형 점검(>70% 또는 <10%), 폐지 종목 포함 | references/pitfalls.md:L235-L248 |

**출력 형식**: 피처 DataFrame(+forward_return, label), 품질 리포트(결측·정상성), MDI/순열 중요도, 중복 피처 목록.
**SKILL.md와 코드 차이**: [차이] SKILL.md:L137-L146는 `from scipy.stats import adfuller`로 쓰나 adfuller는 statsmodels 함수(문서 오류). 일봉 라벨 임계 5%(문서) vs 코드 1%. 데이터는 합성(generate_synthetic_ohlcv L58)/Birdeye. 
**한국 시장 적용**: 시간 피처(hour_sin/cos)는 일봉에서 불필요(요일·월말·옵션만기·배당락일 피처로 대체 [추정]). gap 피처는 한국 일봉에서 시초 단일가 갭으로 유효. 폐지/관리종목 포함(생존편향 제거) 필수. 모든 피처는 당일 종가 확정 후(15:30) 계산, 익일 시가 체결로 라벨 정렬.

### portfolio-analytics — 성과·리스크 지표 모음(Sharpe·Sortino·Calmar·Omega·VaR·롤링·거래 통계)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 표준 성과 지표, quantstats 연동 리포트. 인용 없음 |
| 분류 | (a) 에쿼티 커브/수익률만 필요 — 사후 분석 |
| 필요 데이터 | 에쿼티 시계열, 거래별 손익, (벤치마크 수익률) |
| 주요 파일 | skills/portfolio-analytics/SKILL.md, scripts/analyze_portfolio.py, scripts/compare_strategies.py, references/{metrics_guide,quantstats_guide}.md |
| 라이선스 | MIT |
| 이식 판단 | 채택 — 사후 분석 지표 정의(단, Sortino 수정 필요) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 연율화 기본값 | periods_per_year=252 (함수 기본값) | skills/portfolio-analytics/scripts/analyze_portfolio.py:L69-L100, L180-L283 |
| 2 | CAGR | (끝/시작)^(365.25/일수)-1 (달력일) | analyze_portfolio.py:L42-L54 |
| 3 | Sharpe | mean(r-rf)/std(r-rf)*sqrt(252) | analyze_portfolio.py:L180-L196 |
| 4 | Sortino | mean(excess)/std(음수 수익만)*sqrt(252) | analyze_portfolio.py:L199-L216 |
| 5 | Calmar | CAGR/|MDD| | analyze_portfolio.py:L219-L233 |
| 6 | Omega | 임계 초과분 합/미달분 합(기본 0) | analyze_portfolio.py:L236-L251 |
| 7 | Information Ratio | mean(활성)/std(활성)*sqrt(252) | analyze_portfolio.py:L254-L275 |
| 8 | VaR/CVaR | 95% 역사적 분위수/꼬리 평균 | analyze_portfolio.py:L102-L129 |
| 9 | 최대 시간 수중(time underwater) | 고점 갱신 없이 지속한 최대 기간 | analyze_portfolio.py:L159-L177 |
| 10 | 거래 통계 | win_rate, avg_win, avg_loss, 최대 이익/손실, PF=총이익/총손실, expectancy=평균 손익 | analyze_portfolio.py:L304-L341 |
| 11 | 롤링 Sharpe | 롤링 창 Sharpe (rolling_sharpe) | analyze_portfolio.py:L278-L301 |

**출력 형식**: 텍스트 리포트(수익·리스크·비율·거래 통계·월별 표), 전략 비교 표(compare_strategies.py).
**SKILL.md와 코드 차이**: [차이] Sortino 분모는 표준(목표 이하 편차 sqrt(mean(min(x,0)^2)))이 아니라 음수 수익률 표본의 std(analyze_portfolio.py:L212) -> 값이 달라짐, 이식 시 표준식으로 구현 [추정: 일반 정의]. calmar_ratio의 periods_per_year 인자는 미사용(주석). 데모 에쿼티는 합성(L382).
**한국 시장 적용**: periods_per_year 252 -> 약 245 [추정]. 무위험률 rf는 CD91일/기준금리로 설정. 벤치마크는 코스피/코스닥 지수. 수수료·거래세 차감 후 수익률로 계산.

### slippage-modeling — 슬리피지·체결비용 모델(AMM 가격충격·멱법칙 곡선·손익분기)
| 항목 | 내용 |
|---|---|
| 기법·출처 | 정곱(constant-product) AMM 충격식, CLMM, Jupiter 견적 기반 슬리피지 곡선 + 멱법칙 적합, 왕복 손익분기. 인용 없음 |
| 분류 | 핵심(AMM·Jupiter·우선수수료·MEV)은 해당 없음(가상자산/DeFi). 일반화 가능: 멱법칙 슬리피지 곡선, 왕복 손익분기, 분할 집행 개념 |
| 필요 데이터 | 주식은 호가창 깊이/일 거래대금 (일봉만으로는 근사) -> (c)에 가까움 |
| 주요 파일 | skills/slippage-modeling/SKILL.md, scripts/slippage_curve.py, scripts/execution_cost.py, references/{cost_model,slippage_math}.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 — 손익분기·분할 집행 수식과 멱법칙 최대 주문 크기만 차용. 나머지 보류 |

**차용 가능 규칙**
| # | 규칙 | 계산식 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 정곱 AMM 충격 | impact = Δx/(x+Δx) (매수), Δy/(y+Δy) (매도) — 호가창 모델에 직접 적용 불가 | skills/slippage-modeling/SKILL.md:L61-L82 |
| 2 | 멱법칙 슬리피지 | slippage_bps = a * size^b (로그-로그 OLS), 최대 크기 q_max=(threshold/a)^(1/b) | scripts/slippage_curve.py:L294-L350; SKILL.md:L142-L149 |
| 3 | 손익분기 왕복 | 총 왕복 bp = 진입 비용 + 청산 비용(충격*1.2 + 수수료 + 우선수수료 + MEV*0.5); 필요 상승률 = rt/(10000-rt)*100 | scripts/execution_cost.py:L359-L392 |
| 4 | 문서 손익분기 | roundtrip = entry_impact + exit_impact + 2*fee + 2*priority + mev | SKILL.md:L126-L140 |
| 5 | 분할 집행 | n=ceil(총량/q_max), 간격 2~10초(arb 재균형), TWAP 균등 분할 | SKILL.md:L151-L167 |
| 6 | 표본 크기 | 곡선 측정 사이즈 [0.01 ... 50] SOL 11점 | scripts/slippage_curve.py:L46 |

**SKILL.md와 코드 차이**: 문서 손익분기는 청산 충격=진입 충격, 코드는 청산 충격에 1.2배 가중(execution_cost.py:L359-L392). 슬리피지 곡선 데모는 합성(build_slippage_curve_demo L254). 우선수수료 SOL 0.0001/0.001/0.005, MEV 임계 1/5/20 SOL(L44-L51)은 해당 없음(가상자산).
**한국 시장 적용**: 정규장 시장가 체결 슬리피지는 호가단위·잔량 기반으로 별도 모델 필요. 일봉 엔진용 단순화: 슬리피지(bp) = k*(주문금액/20일 평균 거래대금)^0.5~1 [추정], 동시호가(15:20~15:30)·VI(2분 단일가)·하한가 잠김은 체결 불가 가정. 왕복 비용 = 수수료 약 0.015%x2 + 거래세(매도 약 0.2% [확인 필요]) + 슬리피지.

### market-microstructure-traditional — 전통 시장 미시구조(스프레드·Kyle λ·제곱근 충격·OBI·Avellaneda-Stoikov·IS)
| 항목 | 내용 |
|---|---|
| 기법·출처 | Glosten-Milgrom(1985), Kyle(1985), Almgren-Chriss, 제곱근 충격 법칙, Cont 외(2014) 호가 불균형, Avellaneda-Stoikov, Perold(1988) Implementation Shortfall, Poisson/Hawkes. 모두 SKILL.md 본문에 명시 |
| 분류 | 체결/호가 단위 데이터가 필요 -> (c)/(d)에 가까움. 일봉 엔진에는 제곱근 충격식(일 거래량·변동성만 필요)과 IS 사후분석만 적용 가능 |
| 필요 데이터 | 호가창·체결 틱(스프레드, Kyle λ, OBI); 제곱근 충격은 일봉(ADV, 일 변동성) |
| 주요 파일 | skills/market-microstructure-traditional/SKILL.md, scripts/spread_analysis.py, scripts/market_maker_sim.py, references/{price_formation,execution_quality,cex_vs_dex}.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택 — 제곱근 충격식(슬리피지 추정), IS 사후분석. 시장조성·OBI·Kyle λ는 보류(틱 데이터 없음) |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 제곱근 충격 | impact = c * σ_daily * sqrt(주문수량/ADV), c 기본 0.1 (범위 0.05~0.20) | skills/market-microstructure-traditional/SKILL.md:L133-L158 |
| 2 | Almgren-Chriss | permanent = γ*(shares/ADV); temporary = η*(shares/시간)^α, α 0.5~0.7 | SKILL.md:L116-L131 |
| 3 | Kyle λ | 중간가 변화를 부호 거래량에 OLS 회귀한 기울기(절편 없음) | SKILL.md:L74-L112; scripts/spread_analysis.py:L227-L273 |
| 4 | 스프레드 3종 | quoted(호가), effective(2*|체결가-중간가|), realized(N초 후 중간가 대비) | SKILL.md:L27-L56; scripts/spread_analysis.py:L162-L225 |
| 5 | 호가 불균형 | (bid-ask)/(bid+ask) in [-1,1], 1~5호가 합산이 단기 방향 예측 | SKILL.md:L161-L186 |
| 6 | Avellaneda-Stoikov | reservation = mid - q*γ*σ²*T; spread = γσ²T + (2/γ) ln(1+γ/k); 시뮬 기본 γ 0.05, k 1.5, 최소 스프레드 10bp, 재고 한도 50 | SKILL.md:L223-L242; scripts/market_maker_sim.py:L47-L60 |
| 7 | VWAP 슬리피지 | (평균 체결가-VWAP)/VWAP*10000 bp | SKILL.md:L246-L259 |
| 8 | Implementation Shortfall | (체결가-결정가)*수량 = 지연+충격+타이밍+기회비용 | SKILL.md:L261-L277 |

**출력 형식**: SpreadMetrics(스프레드·Kyle λ), 시뮬 결과(손익·재고·체결 기록).
**SKILL.md와 코드 차이**: 스프레드/시뮬 데이터는 합성(generate_synthetic_orderbook L59, simulate_price_path L93). CEX vs AMM 비교(SKILL.md:L279-L336)와 메이커/테이커 수수료는 가상자산 중심. 
**한국 시장 적용**: 제곱근 충격식의 σ는 일 변동성, ADV는 20일 평균 거래량; 호가단위(가격대별 1~1,000원)가 소형 저가주에서 최소 스프레드 하한을 만들므로 틱 대비 스프레드(bp) 필터가 유용 [추정]. IS는 결정 시점(전일 종가)과 익일 시가 체결 차이로 일봉 엔진에 적용: 시가 갭 비용 측정. 시장조성 모델은 개인 자동매매에 부적합(d).

### ohlcv-processing — OHLCV 정제·갭 처리·리샘플·다중 소스 병합
| 항목 | 내용 |
|---|---|
| 기법·출처 | 구조 검증, 불가능 캔들 복구, 스파이크/제로볼륨 플래그, 갭 채움, 리샘플 규칙, 다중 소스 병합. 인용 없음 |
| 분류 | (a) 일봉 OHLCV만으로 구현 가능 — 데이터 품질 |
| 필요 데이터 | OHLCV (복수 소스 병합 시 2개 이상) |
| 주요 파일 | skills/ohlcv-processing/SKILL.md, scripts/process_ohlcv.py, scripts/merge_sources.py, references/{data_quality,resampling_guide}.md |
| 라이선스 | MIT |
| 이식 판단 | 부분 채택 — 데이터 품질 게이트(불가능 캔들/NaN/음수/중복 검사, 리샘플 규칙). 스파이크 보간·갭 ffill은 한국 시장에서 위험하여 변형 필요 |

**규칙·계산식**
| # | 규칙 | 계산식·임계값·기본값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 정규 포맷 | UTC DatetimeIndex, 소문자 open/high/low/close/volume, 오름차순, 중복 없음(중복은 마지막 유지), 숫자 강제 | skills/ohlcv-processing/scripts/process_ohlcv.py:L29, L234-L273; SKILL.md:L20-L45 |
| 2 | 불가능 캔들 | high<low, high<open, high<close, low>open, low>close; 복구는 O/H/L/C 4개의 max/min으로 high/low 재계산 | process_ohlcv.py:L276-L335, L337-L392 |
| 3 | 스파이크 | |수익률| > 3.0 * 롤링 20 표준편차(min_periods 5) 플래그; 정리 시 시간 보간으로 대체 | process_ohlcv.py:L276-L335, L337-L392 (spike_window=20, spike_threshold=3.0) |
| 4 | 기타 이상 | 거래량<=0 플래그만(삭제 안 함), 음수 가격 행 삭제, NaN 플래그 | process_ohlcv.py:L276-L392 |
| 5 | 갭 채움 | date_range 재색인; ffill(limit=max_gap 5) 또는 시간 보간; 채운 행 is_filled 표시; 채워진 거래량=0 | process_ohlcv.py:L394-L441 |
| 6 | 리샘플 | open first, high max, low min, close last, volume sum; close NaN 행 제거; 사다리 1min->5min->15min->1h->4h->1D | process_ohlcv.py:L31-L39, L443-L472 |
| 7 | 정규화 | returns / log_returns / minmax / zscore (minmax·zscore는 전체표본 통계 -> 룩어헤드 주의) | process_ohlcv.py:L474-L516 |
| 8 | 다중 소스 병합 | 최대 가격 불일치 5.0%, 정렬 허용오차 30초, 충돌 시 higher_volume 소스 우선(또는 source1/2) | scripts/merge_sources.py:L31-L34, L267-L353 |

**출력 형식**: 정제된 OHLCV DataFrame(+anomaly_* 플래그, is_filled), 품질 리포트 dict(결측, 갭, 이상 건수), 병합 불일치 리포트.

**SKILL.md와 코드 차이**: 확인 범위에서 일치. 데모 데이터는 합성(process_ohlcv.py:L43), 수집은 Birdeye(L138, 해당 없음). 
**한국 시장 적용(중요)**: (1) 갭 채움: 휴장일·거래정지는 데이터 결측이 아니라 '비거래'이므로 달력 재색인/ffill 금지 — KRX 거래일 캘린더로 대체. (2) 스파이크 보간: 3σ 규칙은 상/하한가(±30%)·감자·액면분할·권리락 갭을 오류로 판정 -> 보간하면 실제 급등락을 지움; 수정주가(분할·배당 조정)와 corporate action 반영 여부를 먼저 검증해야 함. (3) 거래량 0은 거래정지 신호로 별도 처리. (4) 시간대는 KST(UTC+9), 일봉 확정은 15:30 이후. (5) 가격 불일치 5% 허용은 일봉 소스 병합에는 과대 — 0.5~1% 수준으로 재설정 [추정]. 불가능 캔들 검사·중복·정렬 검사는 그대로 채택.

### 짧게 보는 스킬 12종 (무엇을 하는지·핵심 수치)
| 스킬 | 요약(코드/문서 확인) | 분류·판단 |
|---|---|---|
| pandas-ta | pandas-ta 130+ 지표 래퍼. 해석 임계: RSI14 >70/<30, CCI20 ±100, Williams%R14 -20/-80, ADX14 >25 추세/<20 횡보, SuperTrend(10,3), BB(20,2) (skills/pandas-ta/SKILL.md:L79-L107). 전략 패턴 문서: 스캘프 EMA9/21+RSI+Stoch, 손절 1.5x ATR, 청산 EMA 반전 또는 RSI>75 (references/strategy_patterns.md:L5-L43) | (a) 일봉 가능, 지표 계산 라이브러리. 보류(우리 엔진은 자체 구현) |
| ta-lib | TA-Lib C 래퍼 150+ 함수 + 캔들패턴 61종(값 ±100/0). 신뢰도 Tier1 망치·유성·장악·도지·마루보즈·적삼병/흑삼병(몸통비 기반), Tier2 하라미·관통·먹구름, Tier3 갭 의존(샛별·저녁별·버림받은아기·킥킹) — 가상자산 24/7 기준 구분이라 한국 정규장에서는 갭 패턴 신뢰도가 반대로 올라감 [추정] (references/candlestick_patterns.md:L113-L137; SKILL.md:L190-L205) | (a). 캔들 패턴은 위원회의 보조 관점으로 부분 채택 가능, 단 독립 근거 약함 |
| vectorbt | 벡터화 백테스트. 예시 수수료 0.3%, 슬리피지 0.5%, 초기자금 1만 (skills/vectorbt/SKILL.md:L54-L60); 파라미터 그리드 fast 5~25(2 간격) x slow 20~60(5 간격)=80조합 (L78-L90); 최소 거래 수 필터 문서화 (references/optimization_guide.md:L46-L55) | (a). 우리 Python 엔진이 이미 있으므로 보류. 그리드 서치는 DSR의 N에 반영 필수 |
| backtrader | 이벤트 기반 백테스트: Cerebro, 수수료 0.3%, Sharpe/DrawDown analyzer, 브래킷 주문 스크립트 (skills/backtrader/SKILL.md:L46-L53, L113-L117) | (a). 보류. 브래킷(손절+익절 동시) 주문 패턴만 참고 |
| trading-visualization | mplfinance/matplotlib/plotly 차트(캔들, 에쿼티, 낙폭, 상관 히트맵), 다크 테마, 멀티패널 (skills/trading-visualization/SKILL.md:L18-L150) | 사후 분석 UI. 웹앱은 자체 차트 사용 -> 해당 없음(구현 라이브러리 수준) |
| trade-journal | 거래 JSON 기록 + 행동 패턴 탐지: 복수매매(직전 손실 후 15분 이내 재진입), FOMO(셋업 점수 <5/10, 이미 1 ATR 이상 이동 후 진입), 손실 보유시간 > 이익 보유시간 경고, 틸트(손실 후 사이즈 >1.5배) (skills/trade-journal/SKILL.md:L167-L215) | (a) 사후 분석. 자동매매에서는 '복수/틸트' 규칙을 사이즈 가드(손실 후 사이즈 증가 금지)로 치환해 채택 가능 |
| trade-accounting | 복식부기 원장, 계정과목, 손익계산서·대차대조표·현금흐름표 (SKILL.md:L31-L258) | 사후 분석/장부. 해당 없음에 가까움(세금 파트는 미국 기준: L258 'Trading P&L vs Tax P&L'). 체결-수수료-거래세 장부 설계 참고 정도 |
| sentiment-analysis | 소셜/뉴스 센티먼트: 언급 속도(>3 트렌딩, >10 바이럴), 극성=(긍정-부정)/전체, 공포탐욕 0~100(25/45/56/75 경계), 소셜 거래량 z>2, 펀딩·거래소 유입 대리지표 (skills/sentiment-analysis/SKILL.md:L37-L100) | (c) 뉴스·소셜 데이터 필요. 한국 적용은 뉴스/커뮤니티 수집원 별도 필요 -> 보류 |
| options-pricing | 스텁: 기본 Black-Scholes만 구현, 나머지는 계획 (skills/options-pricing/SKILL.md:L8) | 해당 없음(스텁, 가상자산 옵션) |
| fixed-income | 스텁: 기본 채권 계산기만, DeFi 대출금리 (skills/fixed-income/SKILL.md:L8) | 해당 없음(스텁) |
| liquidity-analysis | Solana DEX 풀 TVL/깊이/집중도 점수: 거래 크기 <풀 깊이의 2%이면 슬리피지 <1% (SKILL.md:L12); 유동성 점수 깊이 40 + 다양성 15 + ... 가중 (L161-L178) | 해당 없음(가상자산/DeFi). 개념만 거래대금 대비 주문 비중 한도로 차용 |
| rl-execution | RL 주문 집행(상태: 잔량·시간·스프레드 등, 보상: 슬리피지), TWAP/VWAP/Almgren-Chriss(E[cost]+λVar[cost]); 대형 주문(일 거래량 >1%)에만 가치, 소액은 시장가+슬리피지 한도로 충분 (skills/rl-execution/SKILL.md:L78-L175) | (d) 개인 규모 일봉 엔진에 부적합. 해당 없음 |

### 나머지 38종 목록 (전수 대조: `ls skills/` 68종 = 깊게 18 + 짧게 12 + 아래 38)
| 스킬 | 한 줄 설명 | 사유 |
|---|---|---|
| birdeye-api | Solana 토큰 가격·OHLCV·거래·보안 데이터 API | 해당 없음: 가상자산 데이터 소스 |
| coingecko-api | CoinGecko 시세/시총/차트 API | 해당 없음: 가상자산 데이터 소스 |
| copy-trading | Solana 지갑 평가·복제매매 전략 | 해당 없음: 가상자산/온체인 |
| cost-basis-engine | FIFO/LIFO/HIFO/평균단가 원가 계산 | 해당 없음: 미국 세금(한국은 이동평균/신고 방식 상이) |
| crypto-tax-export | Koinly/IRS 8949 등 세금 형식 내보내기 | 해당 없음: 가상자산/미국 세금 |
| defillama-api | DeFi TVL·DEX 거래량·스테이블코인 데이터 | 해당 없음: DeFi |
| dex-execution | Jupiter 집계기 스왑 견적·서명·확정 | 해당 없음: DEX 실행(지갑 서명 포함) |
| dex-pool-analysis | Raydium/Orca/Meteora 풀 구조·수수료 비교 | 해당 없음: DeFi |
| dexscreener-api | 멀티체인 DEX 페어 데이터 API | 해당 없음: 가상자산 데이터 소스 |
| helius-api | Helius 강화 Solana RPC·DAS·웹훅 | 해당 없음: Solana 인프라 |
| impermanent-loss | AMM 비영구적 손실 계산·손익분기 | 해당 없음: DeFi LP |
| jito-bundles | Jito 번들 MEV 보호·팁 전략 | 해당 없음: Solana MEV |
| kalshi-api | Kalshi 거래소 인증·주문·웹소켓 | 해당 없음: 예측시장 |
| kalshi-crypto-index-markets | Kalshi 암호화폐/지수 구간 시장 브래킷 | 해당 없음: 예측시장 |
| kalshi-weather-markets | Kalshi 기온 구간 계약 확률 매핑 | 해당 없음: 예측시장 |
| lp-math | AMM 정곱/집중 유동성·LP 지분 수학 | 해당 없음: DeFi LP |
| market-microstructure | DEX 주문흐름·매수/매도 압력(Solana) | 해당 없음: DEX (전통 버전은 market-microstructure-traditional에서 다룸) |
| mev-analysis | 샌드위치 공격 탐지·보호 | 해당 없음: Solana MEV |
| polymarket-api | Polymarket CLOB/Gamma API·EIP-712 인증 | 해당 없음: 예측시장 |
| prediction-market-live-ops | 예측시장 라이브 운영 원칙(증거 게이트, 백테스트 위생, 하우스머니 래칫) | 해당 없음: 예측시장. 단 백테스트 위생 문장(결정 시점 이전 마지막 봉만 조인 = 룩어헤드 방지, 패시브 체결 백테스트는 상한값, 수익 집중도 top-N 점검, 조기 정산 선택편향, 사전 선언 중단 조건)은 일반 검증 원칙으로 참고 가능: skills/prediction-market-live-ops/SKILL.md:L15-L47 |
| prediction-market-strategy | 이진 예측시장 전략·사이징·백테스트 계층 | 해당 없음: 예측시장 |
| pumpfun-mechanics | PumpFun 본딩커브·졸업·PumpSwap 이전 | 해당 없음: 가상자산 |
| raptor-dex | SolanaTracker 자체 호스팅 DEX 집계기 | 해당 없음: Solana 인프라 |
| regulatory-reporting | [스텁] IRS 8949·FBAR 등 보고서 | 해당 없음: 미국 세금/스텁 |
| shredstream | Jito ShredStream 사전 실행 스트리밍 | 해당 없음: Solana 인프라 |
| solana-rpc | Solana JSON-RPC 계정·잔고·트랜잭션 | 해당 없음: Solana 인프라 |
| solana-tx-building | Solana 트랜잭션 구성·우선수수료 | 해당 없음: Solana 인프라 |
| solanatracker-api | Solana 토큰 데이터·PnL·1초 OHLCV | 해당 없음: 가상자산 데이터 소스 |
| sybil-detection | 조율된 지갑 클러스터·워시 트레이딩 탐지 | 해당 없음: 온체인 |
| tax-liability-tracking | 실시간 세금 부담 추적·세금 인지 매매 신호 | 해당 없음: 미국 세금 |
| tax-loss-harvesting | 세금 손실 확정 기회 점수화 | 해당 없음: 미국 세금 |
| token-economics | 토큰 공급·베스팅·인플레이션 평가 | 해당 없음: 가상자산 |
| token-holder-analysis | 홀더 분포·집중도·내부자 탐지(Solana) | 해당 없음: 온체인 (개념은 대주주/수급 집중도와 유사하나 데이터 불가) |
| wallet-profiling | 지갑 행동 분류·성과 분석 | 해당 없음: 온체인 |
| wash-sale-detection | 미국 2025 가상자산 워시세일 61일 창 | 해당 없음: 미국 세금 |
| whale-tracking | 대형 지갑 모니터링·스마트머니 신호 | 해당 없음: 온체인 (대응 개념: 외국인·기관 수급) |
| yellowstone-grpc | Yellowstone gRPC 실시간 스트리밍 | 해당 없음: Solana 인프라 |
| yield-analysis | DeFi 수익률(APR/APY·지속가능성) 평가 | 해당 없음: DeFi |

#### 그룹 소결
이식 우선순위(수치는 코드/문서 확인값, 한국 일봉용 재보정 전제):
1. 레짐 4분면 필터: ATR(14) 100일 백분위 <0.30 저/>0.70 고, ADX(14) >25 추세/<20 횡보 -> 사이즈 승수 1.0/0.5/0.75/0.25 (quiet_trend/volatile_trend/quiet_range/volatile_range); 전환 시 50% 축소 후 3~5봉 대기·5봉 지속 시 전략 전환 (skills/regime-detection/scripts/detect_regime.py:L375-L428, scripts/regime_backtest.py:L299-L306, references/strategy_adaptation.md:L125-L143).
2. 청산 체인: 하드스톱 -20% > ATR 트레일(2.5x, 14) > 분할익절 2R/3R/5R 25%씩+래칫(2R 본전, 3R +1R, 5R +3R) > 시간손절(50봉 미수익 시); 손절폭은 ATR 백분위로 0.7~1.3 스케일 (skills/exit-strategies/SKILL.md:L224-L263, references/trailing_stops.md:L251-L272, references/stop_loss_methods.md:L96-L124). 단 [차이]: MACD 청산 예제 오류.
3. 사이징 사다리: final=min(켈리, 고정비율(2% 위험), 변동성(ATR 목표 2%), 유동성), 단일 10%/상관묶음 25%/총노출 70% + 연패 3회 50%·DD>10% 최소 사이즈 (skills/position-sizing/SKILL.md:L202-L233, references/practical_guide.md:L80-L100). 켈리는 Wilson 하한 승률 + 표본 수·안정성·엣지 min 규칙으로 0.10~0.50 분수 (skills/kelly-criterion/scripts/kelly_from_trades.py:L243-L306).
4. 리스크 게이트: 낙폭 5/10/15/20% 단계(25~50% 축소, 최소 사이즈, 신규 중단, 전면 정지), 일 -3~-5%, 주 -5/-7/-10%, 변동성 브레이커(5일 vol > 20일 vol x2 -> 노출 50%, x3 -> 25%) (skills/risk-management/SKILL.md:L22-L123, references/circuit_breakers.md:L120-L172).
5. 검증 모듈: 퍼지+엠바고 워크포워드, DSR>0.95(N=시도 수), PBO<0.5(CPCV N=6,k=2), 스코어카드 GO(>=70, 우려 0건)/REVIEW(>=55) (skills/walk-forward-validation/scripts/overfit_detector.py:L103-L274, skills/strategy-framework/scripts/strategy_scorecard.py:L338-L385). 데모 코드의 한계([차이]) 반영해 직접 재구현.
6. 평균회귀 트리거: z=(P-MA)/σ, lookback=2x 반감기(또는 20), 진입 |z|>2.0, 청산 z 0 교차, 손절 |z|>3.0, 시간손절 3x 반감기, ADF/VR/Hurst 사전 검정, 분할 진입 |z| 1.5/2.0/2.5/3.0 25%씩 (skills/mean-reversion/SKILL.md:L114-L170, references/strategy_design.md:L30-L88). 단 ADF 임계 하드코딩/EG 임계 오류([차이])는 정확한 검정으로 대체.
추가: 상관 클러스터(Ward, 거리 sqrt(2(1-ρ)))로 동일 클러스터 노출 한도, 데이터 품질 게이트(불가능 캔들 검사)는 채택하되 스파이크 보간·갭 ffill은 한국 시장에서 금지.


---

## 23. Anthropic 공식: financial-services · knowledge-work-plugins(finance)
> 저장소들: anthropics-financial-services (anthropics/financial-services, 커밋 3e32c22, 2026-11-12, Apache-2.0), anthropics-knowledge-work-plugins (anthropics/knowledge-work-plugins, 커밋 e91a134, 2026-11-13, 루트 및 finance/ 모두 Apache-2.0 텍스트 확인)
>
> 약어(플러그인 위치 표기용): A: = plugins/agent-plugins/, V: = plugins/vertical-plugins/, P: = plugins/partner-built/. 근거 경로는 약어 없이 저장소 폴더명부터 전부 적었다.
> 총평(소스 확인): SKILL.md 112개 중 이름 기준 고유 64개. 같은 이름 28종(총 76개 사본)은 md5 동일(차이 없음)이다. A: 폴더는 V: 원본의 복제본이고 동기화 스크립트가 있다(anthropics-financial-services/scripts/sync-agent-skills.py:L2-L9). 두 저장소에는 매매 신호·백테스트·기술적 지표·포지션 사이징 스킬이 하나도 없다. 대부분 투자은행(IB)·리서치 문서·PE·회계 작업 자동화이고, 수치 규칙은 밸류에이션·스크리닝·일부 채권/FX/변동성 해석에 집중된다.

### 고유 스킬 목록
분류: (a) 일봉만으로 구현 가능, (b) 재무 데이터 필요, (c) 시장 폭·거시·뉴스 데이터 필요, (d) 자동매매에 부적합. 중복 열의 "동일"은 md5 일치를 뜻한다. 같은 이름 사본의 내용 차이는 하나도 없었다.

| 스킬 | 플러그인(중복 위치) | 한 줄 설명 | 분류 | 필요 데이터/커넥터 |
|---|---|---|---|---|
| catalyst-calendar | V:equity-research | 커버 종목의 실적·컨퍼런스·규제·거시 이벤트를 달력으로 정리하고 주간 프리뷰 작성 | (c) | 이벤트 일정(IR 페이지, 블룸버그/FactSet 확인 권고). 전용 커넥터 없음 |
| earnings-analysis | V:equity-research, A:earnings-reviewer (동일) | 실적 발표 후 8-12쪽 DOCX 업데이트 리포트(beat/miss, 추정치 개정) | (d) 정성·문서 | 웹 검색, 컨센서스 |
| earnings-preview | V:equity-research, A:earnings-reviewer (동일) | 실적 전 컨센서스·시나리오(Bull/Base/Bear)·체크리스트 1쪽 프리뷰 | (b) | 컨센서스, 옵션 내재변동폭 |
| idea-generation | V:equity-research, A:market-researcher (동일) | 가치·성장·퀄리티·공매도·특수상황 스크린과 테마 스윕 | (b) | 재무·내부자·공매도 잔고 데이터 |
| initiating-coverage | V:equity-research | 5단계 커버리지 개시 리포트(30-50쪽) | (d) 정성·문서 | 재무모델, DOCX |
| model-update | V:equity-research, A:earnings-reviewer (동일) | 실적·가이던스 반영 모델 갱신과 목표주가 재산정 | (d) 엑셀 모델 | 기존 모델 파일 |
| morning-note | V:equity-research, A:earnings-reviewer (동일) | 아침회의용 간밤 이슈·아이디어 노트 | (d) 정성·문서 | 뉴스 |
| sector-overview | V:equity-research, A:market-researcher, A:pitch-agent (동일) | 업종 구도 리포트 | (d) 정성·문서 | 웹 |
| thesis-tracker | V:equity-research | 투자 논지·근거·위험·촉매·손절 트리거 갱신 로그와 스코어카드 | (d) 정성이나 구조는 이식 가능 | 없음(구조적 저장 권고) |
| 3-statement-model | V:financial-analysis, A:model-builder, A:pitch-agent (동일) | 3대 재무제표 템플릿 채우기 | (d) 엑셀 | 재무 데이터 |
| audit-xls | V:financial-analysis 외 A: 6곳(earnings-reviewer, gl-reconciler, model-builder, month-end-closer, pitch-agent, statement-auditor) (동일) | 스프레드시트 수식 오류·모델 정합성 점검 | (d) 범위 밖: 문서/엑셀 | 없음 |
| clean-data-xls | V:financial-analysis | 지저분한 스프레드시트 정리 | (d) 범위 밖: 문서/엑셀 | 없음 |
| competitive-analysis | V:financial-analysis, A:market-researcher (동일) | 경쟁 구도 덱 프레임워크 | (d) 정성·문서 | 웹 |
| comps-analysis | V:financial-analysis, A:market-researcher, A:model-builder, A:pitch-agent (동일) | 비교기업 운영지표·밸류에이션 멀티플 표(사분위 통계) | (b) | 재무·시총·컨센서스 |
| dcf-model | V:financial-analysis, A:model-builder, A:pitch-agent (동일) | 엑셀 DCF(WACC, 터미널가치, 민감도표) | (b) | SEC 공시, 시장 데이터 |
| deck-refresh | V:financial-analysis, A:pitch-agent (동일) | PPT 숫자 갱신 | (d) 범위 밖: 문서/PPT | 없음 |
| ib-check-deck | V:financial-analysis, A:pitch-agent (동일) | 피치덱 숫자 일관성·문구 검수 | (d) 범위 밖: 문서/PPT | 없음 |
| lbo-model | V:financial-analysis, A:model-builder, A:pitch-agent (동일) | LBO 엑셀 템플릿 | (d) IB/PE | 재무 |
| ppt-template-creator | V:financial-analysis | PPT 템플릿에서 스킬 생성 | (d) 범위 밖: 문서/PPT | 없음 |
| pptx-author | V:financial-analysis, A:market-researcher, A:meeting-prep-agent, A:pitch-agent (동일) | 헤드리스 .pptx 생성 | (d) 범위 밖: 문서/PPT | 없음 |
| xlsx-author | V:financial-analysis 외 A: 8곳(earnings-reviewer, gl-reconciler, kyc-screener, model-builder, month-end-closer, pitch-agent, statement-auditor, valuation-reviewer) (동일) | 헤드리스 .xlsx 생성 | (d) 범위 밖: 문서/엑셀 | 없음 |
| skill-creator | V:financial-analysis | 새 스킬 작성 가이드 | (d) 메타 도구 | 없음 |
| buyer-list | V:investment-banking | 매각 자문용 인수 후보 리스트 | (d) IB | 딜 DB |
| cim-builder | V:investment-banking | 비밀유지 정보 메모(CIM) 초안 | (d) IB | 없음 |
| datapack-builder | V:investment-banking | CIM·공시에서 재무 데이터팩 구성 | (d) IB | 공시, MCP |
| deal-tracker | V:investment-banking | 진행 딜 일정·마감 관리 | (d) IB | 없음 |
| merger-model | V:investment-banking | 인수 시 EPS 희석/증가 분석 | (d) IB | 재무 |
| pitch-deck | V:investment-banking, A:pitch-agent (동일) | IB 피치덱 템플릿 채우기 | (d) IB | 엑셀/CSV |
| process-letter | V:investment-banking | 입찰 안내 레터 | (d) IB | 없음 |
| strip-profile | V:investment-banking | 회사 요약 스트립 프로파일 | (d) IB | 재무 |
| teaser | V:investment-banking | 익명 1쪽 티저 | (d) IB | 없음 |
| ai-readiness | V:private-equity | 포트폴리오사 AI 기회 순위 | (d) PE | 포트폴리오 재무 |
| dd-checklist | V:private-equity | 실사 체크리스트 | (d) PE | 없음 |
| dd-meeting-prep | V:private-equity | 실사 미팅 질문 준비 | (d) PE | 없음 |
| deal-screening | V:private-equity | 인바운드 딜을 펀드 기준으로 Pass/Fail | (d) PE(기준 값은 사용자 입력) | CIM |
| deal-sourcing | V:private-equity | 타깃 발굴과 창업자 아웃리치 메일 | (d) PE | CRM |
| ic-memo | V:private-equity, A:valuation-reviewer (동일) | 투자위원회 메모 | (d) PE | 실사 자료 |
| portfolio-monitoring | V:private-equity, A:valuation-reviewer (동일) | 포트폴리오사 KPI 대 계획 신호등 | (d) PE | 월·분기 패키지 |
| returns-analysis | V:private-equity, A:valuation-reviewer (동일) | IRR/MOIC 민감도표 | (d) PE | 딜 가정 |
| unit-economics | V:private-equity | SaaS ARR·LTV/CAC·NDR 분석 | (d) PE/SaaS | 회사 내부 데이터 |
| value-creation-plan | V:private-equity | 인수 후 EBITDA 브리지·100일 계획 | (d) PE | 없음 |
| accrual-schedule | V:fund-admin, A:month-end-closer (동일) | 월말 발생액 스케줄·분개 초안 | (d) 범위 밖: 회계/운영 | 원장 |
| break-trace | V:fund-admin, A:gl-reconciler (동일) | 대사 차이 원인 추적 | (d) 범위 밖: 회계/운영 | 원장 |
| gl-recon | V:fund-admin, A:gl-reconciler (동일) | 원장 대 보조원장 대사 | (d) 범위 밖: 회계/운영 | 원장 |
| nav-tieout | V:fund-admin, A:statement-auditor (동일) | LP 명세서 대 NAV 팩 대조 | (d) 범위 밖: 회계/운영 | NAV 팩 |
| roll-forward | V:fund-admin, A:month-end-closer (동일) | 계정 롤포워드 | (d) 범위 밖: 회계/운영 | 원장 |
| variance-commentary | V:fund-admin, A:month-end-closer (동일) | 월말 변동 코멘트 | (d) 범위 밖: 회계/운영 | 원장 |
| kyc-doc-parse | V:operations, A:kyc-screener (동일) | 온보딩 서류 KYC 필드 추출 | (d) 범위 밖: 회계/운영 | 서류 |
| kyc-rules | V:operations, A:kyc-screener (동일) | KYC/AML 규칙 적용·위험 등급 | (d) 범위 밖: 회계/운영 | 파싱된 레코드 |
| client-report | A:meeting-prep-agent (고유) | 고객용 성과 리포트 | (d) 웰스 문서 | 계좌 데이터 |
| client-review | A:meeting-prep-agent (고유) | 고객 미팅 준비 | (d) 웰스 문서 | 계좌 데이터 |
| investment-proposal | A:meeting-prep-agent (고유) | 신규 고객 투자 제안서 | (d) 웰스 문서 | 없음 |
| bond-futures-basis | P:lseg | 채권선물 베이시스·CTD·내재 레포 | (c) 채권/파생, 주식엔진 범위 밖 | LSEG MCP |
| bond-relative-value | P:lseg | 채권 G-spread 분해·금리 시나리오 | (c) 채권, 범위 밖 | LSEG MCP |
| fixed-income-portfolio | P:lseg | 채권 포트폴리오 듀레이션·DV01·현금흐름 | (c) 채권, 범위 밖 | LSEG MCP(YieldBook) |
| fx-carry-trade | P:lseg | FX 캐리 대비 변동성 비율 | (c) FX, 범위 밖 | LSEG MCP |
| macro-rates-monitor | P:lseg | 거시·수익률곡선·실질금리·스왑스프레드 대시보드 | (c) | LSEG MCP |
| option-vol-analysis | P:lseg | 변동성 곡면·그릭스·내재 대 실현 변동성 | (c) 옵션 데이터 필요. 실현변동성 부분만 (a) | LSEG MCP |
| swap-curve-strategy | P:lseg | 스왑 곡선·스프레드·곡선 트레이드 | (c) 금리, 범위 밖 | LSEG MCP |
| equity-research | P:lseg | IBES 컨센서스·펀더멘털·가격 스냅샷 노트 | (b)+(c) | LSEG MCP |
| earnings-preview-beta | P:spglobal | 실적 프리뷰 4-5쪽 HTML(LTM/NTM P/E, 피어) | (b)+(c) | S&P MCP(Kensho) |
| funding-digest | P:spglobal | 주간 펀딩 라운드 요약 PPT 1장 | (d) 문서 | S&P MCP |
| tear-sheet | P:spglobal | 회사 티어시트 DOCX | (d) 문서 | S&P MCP |
| verify | claude-for-msft-365-install/.claude/skills/ (고유) | MS365 애드인 관리 스크립트 검증용 개발자 스킬 | (d) 범위 밖: 운영 | 없음 |
| audit-support, close-management, financial-statements, journal-entry, journal-entry-prep, reconciliation, sox-testing, variance-analysis (8종, 고유) | knowledge-work-plugins/finance/skills/ | 결산·분개·대사·SOX·재무제표·변동분석 | (d) 범위 밖: 회계/운영 | Snowflake·Databricks·BigQuery 등 ERP 계열 |

분류 집계(고유 72 = financial-services 64 + KWP finance 8): (a) 0, (b) 6 (idea-generation, earnings-preview, comps-analysis, dcf-model, lseg/equity-research, spglobal/earnings-preview-beta), (c) 8 (catalyst-calendar 1 + lseg 7종: bond-futures-basis, bond-relative-value, fixed-income-portfolio, fx-carry-trade, macro-rates-monitor, option-vol-analysis, swap-curve-strategy), (d) 58 (financial-services 50 + KWP finance 8).
(d)의 financial-services 50종 내역: 회계/운영(fund-admin 6, kyc 2, verify 1) 9, IB 9, PE 10, 엑셀·PPT·모델·메타 도구 11, 웰스 3, 리서치 문서 6, S&P 문서 2.
knowledge-work-plugins 나머지 폴더(partner-built: apollo, brand-voice, common-room, slack, zoom-plugin, data 플러그인 등)를 backtest/trading/stock/portfolio 등으로 grep한 결과 투자·트레이딩 스킬은 없었다. 히트한 human-resources/comp-analysis는 보상 분석, legal/legal-risk-assessment는 법무 위험이다.

### 수치 기준이 있는 스킬
접두 경로: FS = anthropics-financial-services/plugins, KWP = anthropics-knowledge-work-plugins. 표의 근거는 이 약어를 풀면 `<저장소 폴더명>/<상대경로>:L..` 형식이다 (예: FS/vertical-plugins/... = anthropics-financial-services/plugins/vertical-plugins/...).

#### idea-generation (스크리닝 기준)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 가치 스크린 | P/E < 섹터 중앙값; EV/EBITDA < 역사 평균; FCF 수익률 > 5%; P/B < 1.5x; 최근 90일 내부자 매수; 배당수익률 > 시장 평균 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/idea-generation/SKILL.md:L24-L30 |
| 2 | 성장 스크린 | 매출 YoY > 15%; 이익 YoY > 20%; 매출 성장 가속; 마진 확대; ROIC > 15%; SaaS NRR > 110% | 같은 파일:L32-L38 |
| 3 | 퀄리티 스크린 | 5년 이상 꾸준한 매출 성장; 마진 안정/확대; ROE > 15%; 낮은 D/E; 높은 FCF 전환; 내부자 지분 > 5% | 같은 파일:L40-L46 |
| 4 | 공매도 스크린 | 매출 감소/둔화; 마진 압축; 매출 대비 매출채권·재고 증가; 내부자 매도; 정당화 안 되는 프리미엄; 높은 공매도 잔고+펀더멘털 악화; 감사인 교체·재작성 | 같은 파일:L48-L55 |
| 5 | 특수상황 스크린 | 락업 만료 IPO/SPAC; 12개월 내 분사; 구조조정 졸업; 행동주의; 부진 기업 경영진 교체 | 같은 파일:L57-L62 |
| 6 | 후보 수와 운영 | 단축 목록 5-10개; 혼잡 거래 회피(보유·공매도 잔고·애널리스트 수 확인); 스크린별 적중률 추적 | 같은 파일:L102, L111, L113 |
- 한국 적용 메모: P/E·P/B·ROE·ROIC·FCF·부채비율은 OpenDART 재무제표(무료, 키 필요)로 직접 계산 가능하다 [추정: 분기 지연과 연결/별도 기준 정리 필요]. "섹터 중앙값"은 KRX 업종 분류로 자체 계산한다. 내부자 매수는 DART 임원·주요주주 소유보고, 공매도 잔고는 KRX 공매도 통계로 대체 가능 [추정]. 스크린 값 자체는 정해진 정책이 아니라 예시 숫자라 백테스트로 재검증해야 한다.

#### thesis-tracker (구조)
| # | 규칙 | 구조·갱신 방식 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 논지 정의 필드 | 종목, 롱/숏, 1-2문장 논지, 근거 3-5개, 위험 3-5개(논지 무효화 조건), 촉매, 목표가/가치, 손절 트리거 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/thesis-tracker/SKILL.md:L12-L20 |
| 2 | 갱신 로그 | 날짜, 데이터 포인트, 근거(pillar)에 미치는 영향(강화/약화/중립), 행동(유지/증액/축소/청산), 확신도(상/중/하) | 같은 파일:L26-L32 |
| 3 | 스코어카드 | 근거별 원래 기대 대 현재 상태 대 추세(안정/우려/관찰) 표 | 같은 파일:L36-L42 |
| 4 | 촉매 달력 | 날짜, 이벤트, 예상 영향, 메모 | 같은 파일:L46-L50 |
| 5 | 운영 원칙 | 논지는 반증 가능해야 함; 반증 증거도 동일 엄격도로 기록; 최소 분기 1회 재검토; 구조화 포맷으로 세션 간 저장 | 같은 파일:L63-L67 |
- 한국 적용 메모: 수치 임계값은 없다(정성 구조). 자동매매에서는 진입 시점의 "진입 근거 점수·위원회 관점별 점수·손절/목표 규칙"을 이 구조(논지, 근거별 상태, 갱신 로그, 행동, 확신도)의 DB 테이블로 저장해 사후 분석에 쓸 수 있다. [추정]

#### catalyst-calendar (이벤트 목록)
| # | 규칙 | 내용 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 수집 범주 | 실적(발표일·장전/장후), 주총, 투자자의 날, 부채 만기; 기업 이벤트(신제품, 규제 결정, M&A, 락업 만료); 산업 이벤트(컨퍼런스, 월간 지표); 거시(FOMC, 고용·CPI·GDP, 중앙은행) | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/catalyst-calendar/SKILL.md:L21-L46 |
| 2 | 달력 컬럼 | 날짜, 이벤트, 종목/섹터, 유형, 영향(H/M/L), 우리 포지션(롱/숏/중립), 메모; 색: 빨강 높음, 노랑 중간, 초록 일상 | 같은 파일:L50-L52, L83 |
| 3 | 이벤트 전 포지션 | "이진 이벤트 전 리스크 관리"와 사전 포지셔닝 권고는 서술만 있고 수치 규칙 없음 | 같은 파일:L66-L69 |
| 4 | 운영 메모 | 실적일은 IR/블룸버그/FactSet로 재확인; 사전 정정공시 이력 종목 추적; 과거 촉매의 실제 결과를 보관해 패턴화 | 같은 파일:L79-L84 |
- 한국 적용 메모: 수치가 없는 체크리스트다. 일봉 엔진에서는 "실적 발표 전후 N일 신규 진입 금지/포지션 축소" 같은 이벤트 필터로 변환 가능하나 N은 소스에 없으므로 백테스트로 정해야 한다. 한국 일정 소스는 DART 공시(잠정실적, 주총소집), KRX 휴장·옵션만기 달력, 한국은행·FOMC 일정으로 대체 [추정]. 영향 H/M/L 등급 기준은 소스에 정의되어 있지 않다.

#### earnings-preview / earnings-analysis / model-update (실적 이벤트)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 프리뷰 정량 항목 | 매출·EPS 대 컨센서스(총계와 세그먼트), 총/영업/순 마진 확대 여부, FCF, 가이던스 대 컨센서스 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/earnings-preview/SKILL.md:L21-L26 |
| 2 | 업종별 지표 | SaaS ARR·NRR·RPO; 소매 동일점포매출; 산업재 수주잔고·book-to-bill; 금융 NIM·대출성장; 헬스케어 처방량 | 같은 파일:L28-L33 |
| 3 | 시나리오 3종 | Bull/Base/Bear 표(매출, EPS, 핵심 동인, 주가 반응); 과거 유사 실적의 주가 반응으로 보정; 옵션 내재 변동폭과 비교 | 같은 파일:L35-L48, L72-L73 |
| 4 | 체크리스트 | 결과를 좌우할 3-5개 항목 선정 | 같은 파일:L50-L56 |
| 5 | beat/miss 정량화 | "매출이 $120M 또는 3% 상회"처럼 금액과 %로 표기; 이유 설명 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/earnings-analysis/SKILL.md:L40-L43 |
| 6 | 목표가 변경 기준 | 추정치 변화 >5% 이면 보통 목표가 변경; <5% 이면 유지 가능 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/earnings-analysis/references/workflow.md:L340-L343 |
| 7 | 데이터 신선도 | 실적 발표일이 오늘로부터 3개월 이내인지 확인, 아니면 재검색 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/earnings-analysis/SKILL.md:L124-L134 |
| 8 | 모델 갱신 | 실적 후 항목별 Prior/Actual/Delta 표; FY 추정 old/new/변화 표; 가치 방법별 Prior/Updated 표 | anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/model-update/SKILL.md:L24-L31, L48-L52, L64-L69 |
- 한국 적용 메모: 서프라이즈 크기의 임계값(예: beat 몇 % 이상이 강한 신호)은 소스에 없다. 컨센서스는 FnGuide 등 유료 데이터가 필요하고 OpenDART만으로는 컨센서스를 대체할 수 없다. 대신 DART 잠정실적 공시 대비 직전 분기·전년 동기 증감(YoY, QoQ)은 무료로 계산 가능하다 [추정]. "실적 후 주가 반응 이력"은 일봉으로 계산 가능한 유일한 항목이다 [추정].

#### comps-analysis (비교기업 계산 규칙)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 통계 행 | Max, 75th, Median, 25th, Min; `=QUARTILE(range,3)`/`=QUARTILE(range,1)`; 평균이 아니라 중앙값 우선 | anthropics-financial-services/plugins/vertical-plugins/financial-analysis/skills/comps-analysis/SKILL.md:L145, L206-L208, L394 |
| 2 | 멀티플 공식 | EV/Revenue=EV/LTM매출; EV/EBITDA=EV/LTM EBITDA; P/E=시총/순이익; PEG=P/E/성장률(%) | 같은 파일:L250-L256 |
| 3 | Rule of 40 | 성장률% + FCF 마진% | 같은 파일:L194 |
| 4 | 정합성 검사 | 총마진 > EBITDA 마진 > 순마진; EV/Revenue 0.5-20x, EV/EBITDA 8-25x, P/E 10-50x가 통상 범위 | 같은 파일:L377-L381 |
| 5 | 이상치 | 2 표준편차 초과 값은 조건부 서식으로 강조 | 같은 파일:L471 |
| 6 | 경고 플래그 | 데이터 출처 간 차이 >10%; EBITDA 음수 기업에 EBITDA 멀티플 금지(매출 멀티플 사용); 하이퍼그로스 없는 P/E >100x | 같은 파일:L563-L567 |
| 7 | 모든 파생값은 입력 셀을 참조하는 수식 | 하드코딩 금지 | 같은 파일:L94-L97 |
- 한국 적용 메모: 상대가치 점수(자기 업종 내 분위수)를 계산하는 아이디어는 이식 가능하다. 입력은 OpenDART 재무+일봉 시총으로 만들 수 있다. 위 범위값(8-25x 등)은 미국 대형주 기준 예시라 KRX 분포로 재산정해야 한다 [추정].

#### dcf-model (DCF 계산 규칙)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | UFCF | EBIT − 세금(EBIT×t) = NOPAT; + D&A − CapEx − ΔNWC | anthropics-financial-services/plugins/vertical-plugins/financial-analysis/skills/dcf-model/SKILL.md:L176-L186 |
| 2 | 가정 범위 | CapEx 매출의 4-8%(유지 2-3% + 성장 2-5%); ΔNWC는 매출 변화액의 -2%~+2%; 세율 21-28% | 같은 파일:L184-L197, L107 |
| 3 | 자기자본비용 | Ke = Rf + β×ERP; β는 5년 월간 대 지수; ERP 5.0-6.0% | 같은 파일:L203-L210 |
| 4 | WACC | E/V×Ke + D/V×Kd×(1−t); 가중치는 시총 대 순부채 기준 | 같은 파일:L226-L234 |
| 5 | WACC 전형 범위 | 대형 안정 7-9%; 성장 9-12%; 고위험 12-15% | 같은 파일:L243-L246 |
| 6 | 터미널가치 | TV = FCF_final×(1+g)/(WACC−g); g<WACC 필수; g 보수 2.0-2.5%, 중립 2.5-3.5%, 공격 3.5-5.0% | 같은 파일:L279-L287 |
| 7 | 할인 | 연중 발생 가정 mid-year; 5년 모델 마지막 기간 4.5 | 같은 파일:L251, L306 |
| 8 | TV 비중 점검 | TV/EV 50-70% 정상; >75% 과의존; <40% 보수적 | 같은 파일:L309-L312 |
| 9 | 민감도 | WACC×터미널g 5x5, 중앙 셀=기준 가정; 시나리오 Bear 8-12%, Base 12-16%, Bull 16-20% 성장 예시 | 같은 파일:L60, L148-L150, L540-L545 |
| 10 | [차이] 검증 스크립트 | 코드는 TV 비중 >80% 또는 <40% 일 때 경고(SKILL.md의 >75% 와 다름); WACC 5%-20% 밖이면 경고; g ≥ WACC 이면 CRITICAL | anthropics-financial-services/plugins/vertical-plugins/financial-analysis/skills/dcf-model/scripts/validate_dcf.py:L145, L177, L216, L221 |
- 한국 적용 메모: 일봉 자동매매의 신호로 쓰기에는 입력(WACC, 성장률) 불확실성이 크고 갱신 주기가 분기다. 활용한다면 "내재가치 대비 괴리"를 느린 필터로만 쓴다 [추정]. 한국은 Rf=국고채 10년, 지수=KOSPI/KOSDAQ로 바꾼다. 소스는 미국 국채·SEC 전제다.

#### deal-screening, returns-analysis, unit-economics, portfolio-monitoring (PE)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | deal-screening | 기준 표(매출, EBITDA, 마진, 성장, 섹터, 지역, EV, 배수, 고객집중, 경영진 연속성)는 모두 빈칸. 수치는 사용자(펀드) 입력. 판정은 Pass/Further Diligence/Hard Pass | anthropics-financial-services/plugins/vertical-plugins/private-equity/skills/deal-screening/SKILL.md:L28-L48 |
| 2 | returns-analysis | MOIC = 엑시트 지분가치/투자 지분; IRR은 (1+r)^n 풀이; 수익 기여 분해(성장, 멀티플, 레버리지); 거래비용 통상 EV의 2-4% | anthropics-financial-services/plugins/vertical-plugins/private-equity/skills/returns-analysis/SKILL.md:L104-L112, L118 |
| 3 | unit-economics | LTV = ARPU×총마진/이탈률; LTV:CAC >3x 양호, >5x 최상, <2x 우려; NDR >120% 최상, >110% 양호, <100% 우려; 총유지율 >95/>90/<85%; CAC 회수 <12/<18/>24개월; Magic Number >0.75x; Rule of 40 | anthropics-financial-services/plugins/vertical-plugins/private-equity/skills/unit-economics/SKILL.md:L28-L31, L61-L66 |
| 4 | portfolio-monitoring | 계획 대비 신호등: 초록 5% 이내, 노랑 5-15% 미달, 빨강 >15% 미달 또는 약정 위반 위험 | anthropics-financial-services/plugins/vertical-plugins/private-equity/skills/portfolio-monitoring/SKILL.md:L37-L39 |
- 한국 적용 메모: 비상장 딜 중심이라 상장주식 일봉 엔진과 거리가 멀다. portfolio-monitoring의 5%/15% 3단계 신호등만 "계획 대비 실적 괴리 경보" 형태로 포지션 모니터링에 차용 가능하다 [추정].

#### lseg 스킬 (option-vol-analysis, fx-carry-trade, macro-rates-monitor, bond-relative-value, swap-curve-strategy, bond-futures-basis, equity-research, fixed-income-portfolio)
LSEG 스킬은 도구 호출 순서와 출력 서식 중심이고 계산은 "도구가 한다"고 명시한다(예: bond-relative-value SKILL.md:L8 "let the tools compute"). 소스에 있는 계산식은 아래뿐이다.
| # | 스킬 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | option-vol-analysis | 종가 기준 실현변동성 20/60/90일 창을 내재변동성 1M/3M/6M ATM과 짝지음; 프리미엄 = IV − RV; 신호 Rich/Cheap; 25-delta 리스크리버설(스큐), 버터플라이(곡면 곡률); 변동성 체제 low/normal/elevated/crisis(수치 경계는 소스에 없음) | anthropics-financial-services/plugins/partner-built/lseg/skills/option-vol-analysis/SKILL.md:L25-L29, L52-L59 |
| 2 | fx-carry-trade | 연환산 캐리 = 선물환 포인트로 산출; 캐리/변동성 비율 = 연환산 캐리 / ATM 내재변동성; 1Y 일봉으로 52주 범위·추세·현재 위치 평가 | 같은 폴더 fx-carry-trade/SKILL.md:L12, L26-L29 (anthropics-financial-services/plugins/partner-built/lseg/skills/fx-carry-trade/SKILL.md) |
| 3 | macro-rates-monitor | 2s10s, 3M-10Y 기울기; 곡선 모양 정상/평탄/역전/험프; 실질금리 = 명목 − 브레이크이븐; 스왑스프레드 = 스왑금리 − 국채수익률(2/5/10Y) | anthropics-financial-services/plugins/partner-built/lseg/skills/macro-rates-monitor/SKILL.md:L25-L27 |
| 4 | bond-relative-value | G-spread, 잔여 스프레드 = G-spread − 신용곡선 스프레드; 평행이동 -100/-50/0/+50/+100bp 시나리오 | anthropics-financial-services/plugins/partner-built/lseg/skills/bond-relative-value/SKILL.md:L26-L28 |
| 5 | swap-curve-strategy | 2s10s, 5s30s, 2s5s10s 버터플라이; 스왑스프레드; DV01 중립 사이징; 3M 캐리·롤다운 추정 | anthropics-financial-services/plugins/partner-built/lseg/skills/swap-curve-strategy/SKILL.md:L26-L28, L57 |
| 6 | bond-futures-basis | 총베이시스, 캐리, 순베이시스(BNOC), 내재 레포를 시장 단기금리와 비교 | anthropics-financial-services/plugins/partner-built/lseg/skills/bond-futures-basis/SKILL.md:L26 |
| 7 | fixed-income-portfolio | 시가가중 평균 수익률·듀레이션·DV01·컨벡시티; 충격 ±50/100/200bp | anthropics-financial-services/plugins/partner-built/lseg/skills/fixed-income-portfolio/SKILL.md:L26, L29 |
| 8 | equity-research | 52주 범위 내 위치, YTD/1Y 수익률, 베타(도구 제공), 3개월 일봉으로 거래량·모멘텀 평가; 선행 P/E = 가격/컨센서스 EPS; 컨센서스 분산 | anthropics-financial-services/plugins/partner-built/lseg/skills/equity-research/SKILL.md:L26-L29 |
- 한국 적용 메모: 일봉만으로 구현 가능한 것은 (1) 실현변동성 20/60/90일, (2) 52주 범위 내 위치, (3) 1Y/YTD 수익률, (4) 3개월 거래량 추세이다. 모두 표준 지표이고 소스가 임계값을 주지 않는다. 나머지(내재변동성, 컨센서스, 금리곡선, 스왑)는 LSEG 유료 데이터가 필요하고 채권·FX 스킬은 KRX 주식 엔진 범위 밖이다. 거시 대시보드의 곡선 기울기·실질금리 분류를 "시장 레짐 필터"로 쓰려면 한국은행 ECOS(무료 API)·금융투자협회 채권 수익률로 대체해야 한다 [추정].

#### spglobal 스킬 (earnings-preview-beta, tear-sheet, funding-digest)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 파생지표 | 총마진 = 매출총이익/매출; 영업마진 = 영업이익/매출; 매출 YoY = (당분기 − 전년동기)/전년동기; EPS YoY는 기저가 음수면 "n.m." | anthropics-financial-services/plugins/partner-built/spglobal/skills/earnings-preview-beta/SKILL.md:L287-L291 |
| 2 | LTM/NTM P/E | LTM P/E = 가격 / 최근 4개 분기 EPS 합; NTM P/E = 가격 / 향후 4개 분기 컨센서스 평균 EPS 합 | 같은 파일:L292-L293 |
| 3 | 수익률 | YTD, 1년, 30일, 90일; 모든 티커의 공통 첫 날짜를 기준으로 계산 | 같은 파일:L294 |
| 4 | 피어 | 상위 5-7개 경쟁사와 8분기 EPS, 12개월 일봉, 시총, 향후 4분기 컨센서스 | 같은 파일:L114-L119 |
| 5 | 운영 규칙 | 용어는 LTM/NTM만 사용(trailing/forward 금지); 분기를 달력일로 추정하지 않음; 원시 데이터는 호출 직후 파일에 기록 | 같은 파일:L18, L20, L28 |
- tear-sheet(`.../spglobal/skills/tear-sheet/SKILL.md:L392`)는 파생지표 계산 단계가 있으나 문서 생성이 목적이다. funding-digest는 기본 기간 7일(`.../funding-digest/SKILL.md:L98`)의 펀딩 라운드 요약이라 주식 매매와 무관하다.

#### knowledge-work-plugins finance (variance-analysis만 수치)
| # | 규칙 | 계산식·임계값 | 근거(파일:줄) |
|---|---|---|---|
| 1 | 변동 중요성 임계 | 예산 대비 10%, 전기 대비 15%, 예측 대비 5%, 전월 대비 20% 중 하나 초과 시 조사; 손익 항목 금액 기준은 매출의 0.5%-1% | anthropics-knowledge-work-plugins/finance/skills/variance-analysis/SKILL.md:L108-L113 |
- 한국 적용 메모: 회계 변동 분석용이다. 재무제표 변화(전기 대비 15%)를 "펀더멘털 급변 플래그"로 쓰는 응용은 가능하나 근거는 임의 관례다. [추정]

### 데이터 커넥터
financial-services는 커넥터를 financial-analysis(core)의 .mcp.json에 모아두고 다른 플러그인이 공유한다(anthropics-financial-services/README.md:L119). 소스는 "MCP 접근은 제공사 구독 또는 API 키가 필요할 수 있다"고만 적는다(anthropics-financial-services/README.md:L136). 아래 "유료 여부"는 소스에 명시된 것과 [추정]을 구분했다.

| 커넥터 | 설정 위치(.mcp.json 엔드포인트) | 사용 스킬 | 유료 여부 |
|---|---|---|---|
| Daloopa | financial-analysis/.mcp.json, https://mcp.daloopa.com/server/mcp | 재무 모델 입력 | 구독 필요 [추정]. 소스는 일반 문구만 |
| Morningstar | 같은 파일, https://mcp.morningstar.com/mcp | 리서치 데이터 | 구독 필요 [추정] |
| S&P Global (Kensho/Capital IQ) | 같은 파일 및 partner-built/spglobal/.mcp.json, https://kfinance.kensho.com/integrations/mcp | spglobal 3종, 비교기업 | 명시: LLM-ready API 구독 또는 Capital IQ Pro 필요(anthropics-financial-services/plugins/partner-built/spglobal/README.md:L14, L39) |
| FactSet | 같은 파일, https://mcp.factset.com/mcp | 컨센서스, 재무 | 구독 필요 [추정] |
| Moody's | 같은 파일, https://api.moodys.com/genai-ready-data/m1/mcp | 신용 | 구독 필요 [추정] |
| MT Newswires | 같은 파일, https://vast-mcp.blueskyapi.com/mtnewswires | 뉴스 | 구독 필요 [추정] |
| Aiera | 같은 파일, https://mcp-pub.aiera.com | 실적 콜 | 구독 필요 [추정] |
| LSEG | 같은 파일(.../lfa/mcp) 및 partner-built/lseg/.mcp.json(.../lfa/mcp/server-cl) | lseg 8종 | 명시: 유효한 자격증명과 상품별 데이터 사용권 필요(anthropics-financial-services/plugins/partner-built/lseg/README.md:L61-L62) |
| PitchBook | 같은 파일, https://premium.mcp.pitchbook.com/mcp | 딜·PE | 구독 필요 [추정] |
| Chronograph | 같은 파일, https://ai.chronograph.pe/mcp | PE 포트폴리오 | 구독 필요 [추정] |
| Egnyte, Box | 같은 파일 | 문서 저장소 | 계정 필요 [추정] |
| (investment-banking, private-equity) | 각 .mcp.json의 mcpServers는 비어 있음 | - | - |
| knowledge-work-plugins finance | finance/.mcp.json: Snowflake·Databricks(URL 빈 값), BigQuery, Slack, Google Calendar·Gmail(URL 빈 값) | 결산 스킬 | 사용자 환경에 따름. [차이] finance/CONNECTORS.md는 이메일·오피스를 Microsoft 365로 적었으나 .mcp.json에는 gmail/google calendar가 있다 |
근거 파일: anthropics-financial-services/plugins/vertical-plugins/financial-analysis/.mcp.json:L2-L51 (11-12개 서버). README 표는 11개 커넥터라 적었고(anthropics-financial-services/README.md:L107) 실제 .mcp.json에는 12개가 있다(LSEG 포함, Egnyte, Box 포함) [차이: 개수 표기]. 한국 시장 데이터를 주는 커넥터는 확인하지 못했다. 한국 대안: 재무는 OpenDART(무료, 키 필요), 컨센서스는 FnGuide 등 유료, 주가는 KRX/증권사 API [추정].

### scripts/ 와 managed-agent-cookbooks/ 파이썬
저장소 전체 파이썬·셸 3,413줄(claude-for-msft-365-install 및 dcf validate 3중 복제 포함)이다. 아래는 모두 읽기만 했고 실행하지 않았다. 매매·시세·금융 계산 로직은 validate_dcf.py 외에 없다.
| 파일 | 하는 일 |
|---|---|
| anthropics-financial-services/scripts/check.py (219줄) | 플러그인·매니페스트 JSON/YAML 파싱, 참조 경로 존재 확인 린트(:L2-L13) |
| anthropics-financial-services/scripts/validate.py (42줄) | 관리형 에이전트 출력 JSON을 스키마로 검증(:L2-L8) |
| anthropics-financial-services/scripts/sync-agent-skills.py (44줄) | V: 원본 스킬을 A: 복제본으로 동기화(:L2-L9) |
| anthropics-financial-services/scripts/version_bump.py (209줄) | 수정된 플러그인 plugin.json 버전을 패치 +1(:L2-L10) |
| anthropics-financial-services/scripts/orchestrate.py (89줄) | 에이전트 출력의 handoff_request JSON을 허용 목록·스키마로 검증하고 다른 에이전트에 steer 하는 참조용 이벤트 루프(참조 전용 명시, :L2-L12) |
| anthropics-financial-services/scripts/deploy-managed-agent.sh (194줄), test-cookbooks.sh (27줄) | 쿡북을 POST /v1/agents로 배포, 드라이런으로 본문 검증 |
| anthropics-financial-services/plugins/vertical-plugins/financial-analysis/skills/dcf-model/scripts/validate_dcf.py (292줄, 3곳 복제) | 엑셀 DCF 검증: g≥WACC, WACC 5-20%, TV 비중(위 DCF 표 #10) |
| .../ib-check-deck/scripts/extract_numbers.py (305줄, 2곳 복제) | PPT 마크다운에서 숫자·단위·슬라이드를 추출해 일관성 검사 |
| .../skill-creator/scripts/*.py | 스킬 뼈대 생성·검증·패키징 |
| anthropics-financial-services/claude-for-msft-365-install/ | Office 애드인 부트스트랩 서버(FastAPI) 및 관리 스크립트. 금융과 무관 |
| anthropics-financial-services/managed-agent-cookbooks/ | 파이썬 파일 없음. 10개 에이전트의 agent.yaml, 하위 에이전트 yaml, steering-examples.json, README(리더·쓰기 권한 분리 설계)만 있다 |
knowledge-work-plugins의 파이썬은 bio-research 스킬용 스크립트이고 finance와 무관하다.
보안 점검: 지시문 주입 의심 문장은 발견하지 못했다. 설치·실행 문구는 일반 문서 수준이다(예: anthropics-financial-services/plugins/partner-built/spglobal/skills/funding-digest/SKILL.md:L224 "npm install simple-icons sharp", anthropics-financial-services/plugins/vertical-plugins/equity-research/skills/initiating-coverage/references/task4-chart-generation.md:L207 "pip install matplotlib ..."). 따르지 않았다.

### 자동매매 엔진 관점 평가
- 솔직한 결론: 두 저장소는 "애널리스트·IB·PE·회계 업무 자동화"이며, 일봉 기반 결정론적 규칙 엔진에 직접 이식할 신호 로직은 사실상 없다. 분류 (a)는 0개이고, 수치 임계값도 대부분 예시값이며 검증 근거(백테스트)가 소스에 없다.
- thesis-tracker: 사후 분석·거래 일지에 적합하다. 논지/근거/위험/촉매/손절 트리거와 갱신 로그(날짜, 데이터, 영향, 행동, 확신도) 필드를 거래 기록 스키마에 대응시킬 수 있다. 위원회 관점별 점수를 "근거" 항목으로 두고 사후에 어느 관점이 맞았는지 집계하는 용도다. 구현 난이도 낮음.
- 실적 이벤트 체크리스트(earnings-preview, catalyst-calendar): 이벤트 필터로 변환 가능하다. 단, N일 윈도·반응 크기는 소스에 없어 직접 백테스트해야 한다. DART 공시일 기반으로 구현 가능하다.
- idea-generation의 5개 스크린(가치/성장/퀄리티/공매도/특수상황): 재무 필터 후보. OpenDART로 구현 가능한 항목(P/B, ROE, 매출·이익 성장, 부채비율, FCF)만 골라 위원회의 "펀더멘털 관점" 점수로 쓰는 정도. 값(5%, 15%, 20%)은 재검증 필요.
- comps-analysis/dcf-model의 계산 규칙: 업종 내 분위수 점수와 TV 비중·g<WACC 같은 정합성 검사는 아이디어 차용 가능. 단 DCF는 일봉 엔진에 느린 필터 이상으로 쓰기 어렵다.
- lseg(변동성·FX·금리): 한국 주식 일봉 엔진에는 부적합. 실현변동성(20/60/90일)·52주 범위 위치는 일봉으로 구현 가능한 표준 지표이나 이 저장소에서 새로 배울 것은 없다.
- portfolio-monitoring 신호등, variance-analysis 임계값: 계획 대비 괴리 경보 개념 정도.

#### 그룹 소결 — 쓸 만한 것 2~5개
1. thesis-tracker 구조 (사후 분석 DB 스키마): 근거(L12-L20), 갱신 로그(L26-L32), 스코어카드(L36-L42). 한국 적용: 내부 데이터만으로 가능, 비용 0.
2. 실적·이벤트 필터 (earnings-preview L21-L26, catalyst-calendar L21-L46): 이벤트 전후 신규 진입 제한 규칙의 항목 목록. 윈도 수치는 직접 백테스트. DART 공시 일정 사용.
3. idea-generation 스크린 목록 (L24-L62): 가치·성장·퀄리티 기준을 OpenDART 재무 기반 펀더멘털 관점 후보로. 한국은 컨센서스 항목 제외.
4. comps/dcf 정합성 검사 아이디어 (comps L377-L381, L563-L567; dcf L309-L312): 업종 내 분위수 상대가치 점수와 이상치(2 표준편차) 제외. 입력은 DART+일봉 시총.
5. (보조) 신호등 3단계 (portfolio-monitoring L37-L39): 5%/15% 괴리 경보를 포지션 모니터링 아이디어로만 차용.


---

## 부록 A. 확인만 한 저장소 (목록·미러·파생)

| 저장소 | 확인한 것 | 판단 |
|---|---|---|
| AI4Finance-Foundation/FinRobot (커밋 63e1884, 루트 Apache-2.0) | `finrobot_desktop/skills/` 아래 SKILL.md 56개가 Anthropic financial-services 스킬을 변환한 것이다. `finrobot_desktop/skills/ATTRIBUTION.md:L1-L9`가 "Anthropic financial-services-plugins에서 파생, 형식 변환만, 내용 동일"이라고 밝히고, `UPSTREAM_VERSION.txt`에 2026-03-31 변환, 56개라고 적혀 있다. 머리말 형식이 달라 파일 해시는 다르다. | §23과 같은 내용이라 따로 분석하지 않았다. [차이] ATTRIBUTION.md는 업스트림 라이선스를 MIT로 적지만 현재 anthropics/financial-services 루트 LICENSE는 Apache-2.0이다(변환 시점의 라이선스는 확인하지 못했다). |
| Qyntc/CTK | `git ls-remote`로 존재만 확인했다. 검색 결과 설명은 tradermonty 스킬의 미러다. | 클론하지 않았다. 미러라는 판단은 [추정]이다. |
| baggat236/ai-trading-skills | 검색 결과(jsDelivr README)에는 나오지만 GitHub에서 "Repository not found"였다. | 제외 |
| majiayu000/claude-skill-registry | 존재 확인. 검색 결과상 `skills/data/canslim-screener`를 포함한 대형 스킬 모음(레지스트리)이다. | 클론하지 않았다. tradermonty와 다른 소형 CANSLIM 구현이라는 검색 설명은 [추정]이다. |
| ComposioHQ/awesome-claude-skills (커밋 be2a406, README만 희소 체크아웃) | README에서 trading·finance·stock·quant·crypto를 grep했다. 금융 매매 스킬 항목은 없고 Composio 앱 연동 스킬(검색상 finage-automation 등)만 있다. | 해당 없음 |
| travisvn/awesome-claude-skills (커밋 1da55aa) | README grep 결과 금융·트레이딩 항목이 없다. | 해당 없음 |
| VoltAgent/awesome-agent-skills (커밋 6d483e2) | README에서 찾은 금융 관련 항목: binance(crypto-market-rank, trading-signal, spot), coinbase/trade, shouldnotappearcalm/a-share-skill, coupler-io/skills, EveryInc/charlie-cfo-skill, deanpeters 금융 지표 문서 등. | a-share-skill만 §20에서 분석했다. 나머지는 가상자산 거래소 공식 주문 도구이거나 비매매 재무 도구라 범위 밖이다. |

이 밖에 같은 작업 공간에 다른 조사용 클론(TradingAgents, ai-hedge-fund, kiwoom-official 등)이 있다. 이것들은 SKILL.md 기반 스킬 모음이 아니어서 이 문서의 범위에서 뺐다(Kiwoom-Plugins만 §10에 포함).

## 부록 B. 클론 위치와 기준 커밋

모든 클론은 조사할 때 임시 폴더(`research-src/<폴더>`)에 받았다. 지금은 남아 있지 않을 수 있으니, 다시 볼 때는 아래 표의 원 저장소와 커밋으로 받는다.

| 폴더 | 원 저장소 | 커밋 |
|---|---|---|
| tradermonty-claude-trading-skills | github.com/tradermonty/claude-trading-skills | fdfff010e1efe181ebe9c11a0109ef5f8b736147 |
| sinkytiger-day-trader-skill-kr | github.com/sinkytiger/day-trader-skill-kr | 256cd811bac736498c547557c7d1a9cf3360f435 |
| jakeschincariol-day-trader-skill | github.com/Jakeschincariol/day-trader-skill | 3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd |
| kiwoom-plugins | github.com/Kiwoom-Securities/Kiwoom-Plugins | 7dcf8218f2fc791082decd48932dfdc4276a769e |
| nomadamas-k-skill (희소 체크아웃) | github.com/NomaDamas/k-skill | 9766d20fb1fe1a5eb1d10ef5ff9872c8d6fc4985 |
| shouldnotappearcalm-a-share-skill | github.com/shouldnotappearcalm/a-share-skill | 8874bd1c46813ddb188aa293e6f9ae34f016ba4d |
| himself65-finance-skills | github.com/himself65/finance-skills | a0850786e72aa23b92862f9f1635b0de506fe206 |
| shakeebshaan-claude-code-quant-skills | github.com/shakeebshaan/claude-code-quant-skills | 6b39f8feb4a77f486eed509e40c02a0c69b7750f |
| staskh-trading-skills | github.com/staskh/trading_skills | 012abbfba4d3a35ce6d53e19379ed8a07a938e81 |
| rkiding-awesome-finance-skills | github.com/rkiding/awesome-finance-skills | 853f09b4d0baae747759ed31e21ed5c5b2316a5f |
| agiprolabs-claude-trading-skills | github.com/agiprolabs/claude-trading-skills | 981e1d736cdc02bdc1c55c74ec9224e956414706 |
| anthropics-financial-services | github.com/anthropics/financial-services | 3e32c2287dcb637c184c01cc0ad82d6af7e9bb0f |
| anthropics-knowledge-work-plugins | github.com/anthropics/knowledge-work-plugins | e91a134584eb798bac7fb0379358006a2b63b965 |
| FinRobot | github.com/AI4Finance-Foundation/FinRobot | 63e1884a42ea7b729551a5424b4bd6a65af636e0 |
| composiohq-awesome-claude-skills (README만) | github.com/ComposioHQ/awesome-claude-skills | be2a406907dbc61b73e6827ded415c96139d13a2 |
| travisvn-awesome-claude-skills | github.com/travisvn/awesome-claude-skills | 1da55aa810f206d3fe2005e7e3989b15a275d942 |
| voltagent-awesome-agent-skills | github.com/VoltAgent/awesome-agent-skills | 6d483e29da745a010d88974ef6d0e50d15755e9a |
