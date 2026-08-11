"""Stage 5 출력(curation) 스키마.

Structured Outputs 제약(2026-08 기준)에 맞춰 작성:
- 모든 객체에 ConfigDict(extra="forbid") 지정
- 수치 제약(minItems 등) 대신 코드 검증(validate_curation)으로 검증
- product_id는 curation_json_schema()에서 동적으로 valid_ids enum을 주입하여 환각 방지
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    reason: str  # 2~3문장 — 사연의 구체 내용과 연결
    tagline: str  # 한 줄 (25자 내외) — 제품 카드 하단 문구


class CurationResult(BaseModel):
    """Stage 5의 최종 출력 — 추천 제품 2~3개 및 큐레이션 서사."""
    model_config = ConfigDict(extra="forbid")

    recommendations: list[Recommendation]


def curation_json_schema(valid_ids: list[str]) -> dict:
    """Structured Outputs용 JSON 스키마 생성 — valid_ids를 enum으로 동적 주입."""
    schema = CurationResult.model_json_schema()
    schema["$defs"]["Recommendation"]["properties"]["product_id"]["enum"] = valid_ids
    return schema


def validate_curation(
    result: CurationResult,
    valid_ids: list[str],
    base_product: str | None = None,
    n_min: int = 2,
    n_max: int = 3,
) -> list[str]:
    """스키마로 표현하기 힘든 큐레이션 규칙을 코드로 검증. 위반 목록을 반환(비어있으면 통과).

    검증 항목:
    1. 추천 개수가 2~3개인가
    2. product_id 중복이 없는가
    3. product_id가 카탈로그 valid_ids에 포함되는가
    4. 재창조 베이스 제품(base_product)이 추천에 포함되지 않았는가
    """
    problems: list[str] = []

    rec_count = len(result.recommendations)
    if not (n_min <= rec_count <= n_max):
        problems.append(f"추천 개수가 {rec_count}개임 (허용: {n_min}~{n_max}개)")

    pids = [r.product_id for r in result.recommendations]
    if len(set(pids)) != len(pids):
        problems.append(f"추천 product_id 중복 발생: {pids}")

    for r in result.recommendations:
        if r.product_id not in valid_ids:
            problems.append(f"카탈로그에 없는 product_id 포함: '{r.product_id}'")

    if base_product and base_product in pids:
        problems.append(
            f"재창조에 사용된 베이스 제품('{base_product}')이 큐레이션 추천에 포함됨"
        )

    return problems
