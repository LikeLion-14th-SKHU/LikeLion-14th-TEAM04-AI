"""검증 게이트(Harness 7.1) 출력 스키마.

게이트 위치: Stage 3 직후, 사용자 선택 전 (AI_Dev_PipeLine.md 7.1).
Haiku가 컨셉 이미지 1장당 1건의 GateResult를 반환한다.

Structured Outputs 제약: 수치 범위(minimum/maximum) 표현 불가 → score는 코드에서 0~100 클램프.
필드명 참고: 설계 문서의 "pass"는 파이썬 예약어라 "passed"로 명명.
"""
from pydantic import BaseModel, ConfigDict


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool              # 세 기준(스펙 반영·브랜드 정합성·시각 결함) + 실현 가능성 통과 여부
    score: int                # 0~100 — 통과 컷 정렬용 (코드에서 클램프)
    fail_reasons: list[str]   # 불합격 사유 — 전원 불합격 시 Stage 3 재생성 프롬프트에 피드백됨


def gate_json_schema() -> dict:
    return GateResult.model_json_schema()


def clamp_score(result: GateResult) -> GateResult:
    """스키마로 강제 못 하는 score 범위를 코드로 보정."""
    if not 0 <= result.score <= 100:
        result = result.model_copy(update={"score": max(0, min(100, result.score))})
    return result
