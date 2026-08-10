"""POST /ai/v1/curation — Stage 5: 럭셔리 큐레이션 (동기).

Stage 5 모듈은 팀원 개발분 — 병합 전까지 501. 병합되면 코드 수정 없이 동작 (지연 import).
계약: 입력 analysis + design_spec(선택된 1개) → 추천 2~3개 {product_id, reason, tagline}.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.design_spec import DesignSpec

router = APIRouter()


class CurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResult
    design_spec: DesignSpec       # 사용자가 선택한 후보


def load_stage5_curation():
    """지연 import — Stage 5(팀원) 병합 전에는 501."""
    try:
        from ai_pipeline.services.stage5_curation import generate_curation
        return generate_curation
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Stage 5 모듈이 아직 이 브랜치에 없습니다 (팀원 개발 중 — 병합 후 사용 가능)",
        )


@router.post("/curation", summary="Stage 5: 럭셔리 큐레이션 (추천 + 이유 + tagline)")
def curation(req: CurationRequest) -> Any:
    generate_curation = load_stage5_curation()
    result = generate_curation(req.analysis, req.design_spec)
    return result.model_dump() if hasattr(result, "model_dump") else result
