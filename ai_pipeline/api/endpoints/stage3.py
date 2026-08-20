"""POST /ai/v1/concept-image — Stage 3 + 검증 게이트 통합 (동기, ~10-20초).

게이트가 사용자 선택 **앞**에 있으므로 별도 게이트 엔드포인트는 없다 —
백엔드는 이 응답의 통과 후보만 사용자에게 제시하면 된다 (AI_Dev_PipeLine.md 7.1).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ai_pipeline.api.helpers import save_base64_image, storage_url
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.schemas.verification import GateResult
from ai_pipeline.services.harness_gate import GateOutcome, gate_with_retry
from ai_pipeline.services.stage3_concept import generate_concept_images

router = APIRouter()


class ConceptImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clothing_image_base64: str            # 옷 사진 (JPEG/PNG)
    candidates: list[DesignSpec]          # Stage 2 응답의 candidates
    use_pro: bool = False                 # 발표용 최종컷 (gemini-3-pro-image)


class GatedCandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: DesignSpec
    image_url: str                        # /ai/static/... — 프론트 표시용
    gate: GateResult


class ConceptImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[GatedCandidateOut]   # 항상 n장 — 통과 컷(점수순) 먼저, 보충 컷(gate.passed=false)이 뒤
    all_failed: bool                      # True면 통과 컷 0장 (전원 보충 제시 — 표시 시 참고)
    regenerated: bool                     # 탈락분 재생성 1회가 발동했었는가


def _to_response(outcome: GateOutcome) -> ConceptImageResponse:
    return ConceptImageResponse(
        candidates=[
            GatedCandidateOut(
                spec=g.concept.spec,
                image_url=storage_url(g.concept.image_path),
                gate=g.gate,
            )
            for g in outcome.candidates
        ],
        all_failed=outcome.all_failed,
        regenerated=outcome.regenerated,
    )


@router.post("/concept-image", response_model=ConceptImageResponse,
             summary="Stage 3+게이트: 컨셉 이미지 생성 → Haiku 채점 → 통과 컷 점수순")
def concept_image(req: ConceptImageRequest) -> ConceptImageResponse:
    clothing = save_base64_image(req.clothing_image_base64)
    concepts = generate_concept_images(req.candidates, clothing, use_pro=req.use_pro)
    outcome = gate_with_retry(
        concepts,
        regenerate=lambda specs: generate_concept_images(specs, clothing, use_pro=req.use_pro),
    )
    return _to_response(outcome)
