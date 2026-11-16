"""키움 오류 분류. 업무 오류도 HTTP 200으로 오므로 본문 return_code와 메시지 속 세부 코드로 나눈다."""

from __future__ import annotations

RATE_CODES = frozenset({1700, 1701, 1702})
AUTH_RETRY_CODES = frozenset({8005, 8031, 8103})  # 토큰 재확인·재발급 후 1회 재시도
CREDENTIAL_CODES = frozenset({8001, 8002, 8011, 8012, 8020})
MODE_MISMATCH_CODES = frozenset({8030, 8031})
IP_CODES = frozenset({8010, 8040, 8050})
MOCK_UNSUPPORTED = 8104

# 화면에 보여줄 해결 방법
HINTS: dict[int, str] = {
    8001: "앱키·시크릿키가 맞는지, 실전 키와 모의 키를 바꿔 넣지 않았는지 확인하세요.",
    8005: "토큰이 만료됐거나 다른 곳에서 새 토큰을 받아 폐기됐습니다. 같은 키로 다른 프로그램을 돌리고 있지 않은지 확인하세요.",
    8010: "토큰을 발급받은 IP와 요청 IP가 다릅니다. 서버의 고정 공인 IP를 확인하세요.",
    8030: "실전 키를 모의투자 주소에(또는 반대로) 쓰고 있습니다.",
    8031: "실전 토큰을 모의투자 주소에(또는 반대로) 쓰고 있습니다.",
    8050: "이 서버의 IP가 키움 포털에 등록돼 있지 않습니다. API 사용신청 화면에서 IP를 등록하세요.",
    8104: "모의투자에서 지원하지 않는 기능입니다.",
    1700: "호출 한도를 넘었습니다. 잠시 뒤 다시 시도합니다.",
    1902: "종목 정보를 찾을 수 없습니다. 종목코드를 확인하세요.",
}


class KiwoomError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, api_id: str = "", http_status: int = 200) -> None:
        super().__init__(message)
        self.code = code
        self.api_id = api_id
        self.http_status = http_status

    @property
    def hint(self) -> str:
        return HINTS.get(self.code or 0, "")


class KiwoomRateLimited(KiwoomError):
    """유량 초과(HTTP 429 또는 1700~1702)."""


class KiwoomAuthError(KiwoomError):
    """토큰·자격 증명·IP 문제."""


class KiwoomNotConfigured(KiwoomError):
    """앱키가 설정되지 않음."""


def classify(code: int | None, message: str, *, api_id: str, http_status: int) -> KiwoomError:
    if http_status == 429 or (code in RATE_CODES):
        return KiwoomRateLimited(message or "호출 한도 초과", code=code, api_id=api_id, http_status=http_status)
    if http_status == 401 or code in AUTH_RETRY_CODES | CREDENTIAL_CODES | IP_CODES | MODE_MISMATCH_CODES:
        return KiwoomAuthError(message or "인증 실패", code=code, api_id=api_id, http_status=http_status)
    return KiwoomError(message or "키움 API 오류", code=code, api_id=api_id, http_status=http_status)
