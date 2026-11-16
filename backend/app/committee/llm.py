"""Claude 호출 계층. 위원회 심의가 쓰는 좁은 인터페이스와 Anthropic SDK 구현.

- 공식 SDK(anthropic)만 쓴다.
- 구조화 출력(output_config.format)으로 JSON 스키마를 강제하고, 받은 뒤에도 다시 검증한다.
- 거절(stop_reason == "refusal")·잘림(max_tokens)·오류는 모두 호출한 쪽에서 '보류'로 처리한다.
- 비용은 응답의 usage로 추정한다(실제 청구액은 Anthropic 콘솔이 기준).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODEL = "claude-opus-5-5"
SELECTABLE_MODELS: tuple[str, ...] = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2")
MODEL_LABELS: dict[str, str] = {
    "claude-opus-5-5": "Claude Opus 5.5 (기본)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (더 빠르고 저렴)",
    "claude-haiku-5-5": "Claude Haiku 5.5 (가장 저렴)",
    "claude-fable-5-2": "Claude Fable 5.2 (가장 강력, 가장 비쌈)",
}
# 100만 토큰당 달러 (입력, 출력, 캐시 읽기). 2026-11 기준 공개 가격이며 바뀔 수 있다.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-2": (8.00, 40.00, 0.20),
}
CACHE_WRITE_MULTIPLIER = 1.25
# 서버 측 거절 대체(fallback)를 지원하는 모델. 거절되면 같은 호출 안에서 다른 모델이 이어받는다.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORTS: tuple[str, ...] = ("low", "medium", "high")


class LlmError(RuntimeError):
    """호출 실패. kind로 원인을 구분한다."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # not_configured | refusal | truncated | timeout | rate_limit | auth | api | invalid_output | budget


@dataclass(slots=True)
class LlmUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return estimate_cost(self.model, self.input_tokens, self.output_tokens, self.cache_read_tokens, self.cache_write_tokens)


@dataclass(slots=True)
class LlmResult:
    text: str
    usage: LlmUsage


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    price_in, price_out, price_cache = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (
        input_tokens * price_in + output_tokens * price_out + cache_read * price_cache
        + cache_write * price_in * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000


class LlmClient(Protocol):
    model: str

    async def complete(self, *, system: str, shared: str, task: str, schema: dict[str, Any], role: str) -> LlmResult:
        """system과 shared(종목 리포트)는 여러 호출이 공유하는 앞부분이라 캐시 대상이다. task만 역할마다 다르다."""
        ...


class AnthropicLlm:
    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, effort: str = "medium", timeout: float = 120.0,
                 max_tokens: int = 16_000) -> None:
        import anthropic

        if not api_key:
            raise LlmError("not_configured", "Claude API 키가 설정되지 않았습니다")
        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model if model in PRICES else DEFAULT_MODEL
        self._effort = effort if effort in EFFORTS else "medium"
        self._max_tokens = max_tokens

    async def aclose(self) -> None:
        await self._client.close()

    async def complete(self, *, system: str, shared: str, task: str, schema: dict[str, Any], role: str) -> LlmResult:
        anthropic = self._anthropic
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": [{"type": "text", "text": system}],
            "messages": [{
                "role": "user",
                "content": [
                    # 같은 종목의 강세·약세·리스크·최종 호출이 이 블록까지를 공유한다 → 캐시 읽기
                    {"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": task},
                ],
            }],
            # 생각(thinking)은 모델 기본값(적응형)에 맡기고 깊이는 effort로 조절한다.
            "output_config": {"effort": self._effort, "format": {"type": "json_schema", "schema": schema}},
        }
        try:
            if self.model in FALLBACK_MODELS:
                response = await self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
            else:
                response = await self._client.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise LlmError("timeout", "Claude 응답 시간 초과") from exc
        except anthropic.RateLimitError as exc:
            raise LlmError("rate_limit", "Claude 호출 한도 초과") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LlmError("auth", "Claude API 키가 올바르지 않거나 권한이 없습니다") from exc
        except anthropic.APIStatusError as exc:
            raise LlmError("api", f"Claude API 오류 (HTTP {exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError("api", "Claude API에 연결하지 못했습니다") from exc

        usage = LlmUsage(
            model=getattr(response, "model", self.model) or self.model,
            input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )
        if response.stop_reason == "refusal":
            error = LlmError("refusal", "Claude가 응답을 거절했습니다")
            error.usage = usage  # type: ignore[attr-defined]
            raise error
        if response.stop_reason == "max_tokens":
            error = LlmError("truncated", "Claude 응답이 길이 제한에 걸려 잘렸습니다")
            error.usage = usage  # type: ignore[attr-defined]
            raise error
        text = next((block.text for block in response.content if block.type == "text"), "")
        return LlmResult(text=text, usage=usage)
