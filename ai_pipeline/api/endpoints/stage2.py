"""POST /ai/v1/design-spec — Stage 2: 재창조 디자인 스펙 후보 3개 (동기).
GET  /ai/v1/recreation-categories — 사용자가 지정 가능한 재창조 목표 카테고리 목록.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.design_spec import CandidateList
from ai_pipeline.services import brand_assets
from ai_pipeline.services.stage2_design import generate_design_specs

router = APIRouter()


class DesignSpecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResult
    target_category: str | None = None   # None이면 AI 자동 제안 모드


class CategoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    count: int                            # 해당 카테고리의 레퍼런스 보유 수


class CategoriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryOut]         # 보유 수량 내림차순


def ensure_valid_category(target_category: str | None) -> None:
    """target_category 검증 공용 헬퍼 — 목록 밖 값이면 422 (pipeline-run에서도 사용)."""
    if target_category is not None and not brand_assets.is_valid_category(target_category):
        allowed = [c["category"] for c in brand_assets.available_categories()]
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 재창조 카테고리: '{target_category}' (허용: {allowed})",
        )


@router.get("/recreation-categories", response_model=CategoriesResponse,
            summary="재창조 목표 카테고리 목록 (프론트 토글용 — DB에서 자동 도출)")
def recreation_categories() -> CategoriesResponse:
    return CategoriesResponse(
        categories=[CategoryOut(**c) for c in brand_assets.available_categories()]
    )


@router.post("/design-spec", response_model=CandidateList, summary="Stage 2: 재창조 스펙 후보 3개")
def design_spec(req: DesignSpecRequest) -> CandidateList:
    ensure_valid_category(req.target_category)
    return generate_design_specs(req.analysis, target_category=req.target_category)
