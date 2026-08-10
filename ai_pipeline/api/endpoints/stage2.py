"""POST /ai/v1/design-spec — Stage 2: 재창조 디자인 스펙 후보 3개 (동기)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.design_spec import CandidateList
from ai_pipeline.services.stage2_design import generate_design_specs

router = APIRouter()


class DesignSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResult
    target_category: str | None = None   # None이면 AI 자동 제안 모드


@router.post("/design-spec", response_model=CandidateList, summary="Stage 2: 재창조 스펙 후보 3개")
def design_spec(req: DesignSpecRequest) -> CandidateList:
    return generate_design_specs(req.analysis, target_category=req.target_category)
