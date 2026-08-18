"""Stage 2 출력(design_spec) 스키마 — 단일 원천. 설계 근거: Stage2.md 5절.

Structured Outputs 제약(2026-08 기준)에 맞춰 작성:
- 모든 객체에 additionalProperties: false (ConfigDict(extra="forbid")가 생성)
- minimum/maximum, minLength, minItems 등 수치 제약 사용 금지 → 코드 검증으로 대체
- enum은 지원됨 → risk_profile / intervention_level에 사용
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskProfile = Literal["safe", "balanced", "bold"]

# 개입 강도 스펙트럼 (Stage2.md 1절). 수치 제약 대신 enum으로 표현.
InterventionLevel = Literal[0, 1, 2, 3, 4, 5]

# risk_profile별 허용 개입 강도 — 코드 검증에 사용 (스키마로는 표현 불가)
RISK_LEVEL_RANGE: dict[str, tuple[int, int]] = {
    "safe": (1, 2),
    "balanced": (2, 3),
    "bold": (4, 5),
}


class AppliedElement(BaseModel):
    """옷의 요소 → 제품 위치 매핑. reason이 창의성의 코어 (Stage2.md 3절)."""
    model_config = ConfigDict(extra="forbid")

    from_element: str   # 옷에서 가져오는 요소 (예: "소매의 해진 부분")
    to_element: str     # 제품에서 적용되는 위치 (예: "스트랩의 스티치 디테일")
    reason: str         # 사연과 연결한 근거 — 후보 카드에 노출됨


class DesignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_name: str                       # 후보 카드용 짧은 컨셉명
    category: str                           # MCM 카테고리 (예: "미니 레더백")
    category_reason: str | None             # 자동 제안 모드의 선정 이유 / 지정 모드는 null
    base_product: str | None                # 레퍼런스 product_id (data/_index.json)
                                            # — 레퍼런스 없는 악세사리 모드에서만 null 허용
    risk_profile: RiskProfile
    intervention_level: InterventionLevel
    creation_method: str                    # 자유 서술 — 열거형 제한 없음
    applied_elements: list[AppliedElement]
    image_prompt: str                       # Stage 3 전달용 영문 편집 지시문


class CandidateList(BaseModel):
    """Stage 2의 최종 출력 — 후보 3개 포트폴리오 (safe / balanced / bold)."""
    model_config = ConfigDict(extra="forbid")

    candidates: list[DesignSpec]


def candidate_list_json_schema() -> dict:
    """Structured Outputs에 전달할 JSON 스키마."""
    return CandidateList.model_json_schema()


def validate_portfolio(
    result: CandidateList, n_expected: int = 3, allow_null_base: bool = False
) -> list[str]:
    """스키마로 표현 못 하는 포트폴리오 규칙을 코드로 검증. 위반 목록을 반환(비면 통과).

    Structured Outputs가 타입·enum은 보장하므로 여기서는 '구성 규칙'만 본다:
    후보 수, risk_profile 중복, profile별 개입 강도 범위.
    """
    problems: list[str] = []

    if len(result.candidates) != n_expected:
        problems.append(f"후보 수가 {len(result.candidates)}개 (기대: {n_expected})")

    profiles = [c.risk_profile for c in result.candidates]
    if len(set(profiles)) != len(profiles):
        problems.append(f"risk_profile 중복: {profiles}")

    for c in result.candidates:
        lo, hi = RISK_LEVEL_RANGE[c.risk_profile]
        if not (lo <= c.intervention_level <= hi):
            problems.append(
                f"'{c.concept_name}': {c.risk_profile}인데 intervention_level={c.intervention_level} (허용: {lo}~{hi})"
            )
        if not c.applied_elements:
            problems.append(f"'{c.concept_name}': applied_elements가 비어 있음")
        if c.base_product is None and not allow_null_base:
            problems.append(f"'{c.concept_name}': base_product가 null (레퍼런스 모드에서는 필수)")

    return problems
