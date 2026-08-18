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


class SubCategoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: str
    count: int                            # 해당 서브의 레퍼런스 보유 수
    reference_free: bool                  # True면 레퍼런스 없이 AI 자유 생성 (악세사리)


class MainCategoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main: str                             # 의류 / 가방 / 악세사리
    subs: list[SubCategoryOut]


class CategoriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[MainCategoryOut]


def ensure_valid_category(target_category: str | None) -> None:
    """target_category(서브 값) 검증 공용 헬퍼 — 목록 밖 값이면 422 (pipeline-run에서도 사용)."""
    if target_category is not None and not brand_assets.is_valid_category(target_category):
        allowed = {m: subs for m, subs in brand_assets.RECREATION_TAXONOMY.items()}
        raise HTTPException(
            status_code=422,
            detail=f"지원하지 않는 재창조 카테고리: '{target_category}' (허용 서브: {allowed})",
        )


@router.get("/recreation-categories", response_model=CategoriesResponse,
            summary="재창조 목표 카테고리 계층 목록 (프론트 토글용 — 메인 3종 × 서브)")
def recreation_categories() -> CategoriesResponse:
    return CategoriesResponse(
        categories=[MainCategoryOut(**m) for m in brand_assets.available_categories()]
    )


@router.post("/design-spec", response_model=CandidateList, summary="Stage 2: 재창조 스펙 후보 3개")
def design_spec(req: DesignSpecRequest) -> CandidateList:
    ensure_valid_category(req.target_category)
    return generate_design_specs(req.analysis, target_category=req.target_category)
