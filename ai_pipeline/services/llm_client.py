"""Anthropic 클라이언트 래퍼.

책임:
- Structured Outputs(output_config.format) 호출 한 가지 형태로 통일
- 호출마다 사용량(usage)을 JSONL 트레이스로 기록 (AI_Dev_PipeLine.md 7.3)

주의:
- Sonnet 5: temperature/top_p 비기본값 지정 시 400 → 아예 넣지 않는다. thinking은 생략(adaptive 기본).
- Haiku 4.5(게이트): output_config.effort 미지원 → effort=None으로 호출할 것.
- system 블록에 trace_id·타임스탬프 금지 (프롬프트 캐시 무효화). trace는 로그에만 남긴다.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import anthropic

from ai_pipeline.config import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # .env(settings) 우선, 없으면 None → SDK가 환경변수/프로필에서 자동 해석
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    return _client


def structured_call(
    *,
    model: str,
    system_blocks: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    stage: str,
    max_tokens: int = 16000,
    effort: str | None = "high",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """스키마 강제 호출. 파싱된 dict를 반환한다.

    output_config.format이 스키마 준수를 보장하므로 별도 JSON 방어 코드는 두지 않는다.
    """
    trace_id = trace_id or str(uuid.uuid4())
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if effort is not None:
        output_config["effort"] = effort

    t0 = time.monotonic()
    response = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
        output_config=output_config,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    _write_trace(
        trace_id=trace_id,
        stage=stage,
        model=model,
        latency_ms=latency_ms,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        },
        stop_reason=response.stop_reason,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"모델이 요청을 거부함 (trace_id={trace_id})")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _write_trace(**fields: Any) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    path = settings.log_dir / f"{fields['trace_id']}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fields, ensure_ascii=False) + "\n")
