"""POST /ai/v1/curation — Stage 5: 럭셔리 큐레이션 (동기).

응답은 LLM 출력(product_id, reason, tagline)에 표시용 정보를 서버가 결정론적으로 덧붙인 것:
- name_kr: 카탈로그의 한글 제품명
- image_url: /ai/assets/... 제품 사진 (data/_index.json 매칭, 없으면 null)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.curation import CurationResult
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services import brand_assets
from ai_pipeline.services.stage5_curation import generate_curation, load_catalog

router = APIRouter()


class CurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisResult
    design_spec: DesignSpec       # 사용자가 선택한 후보


class RecommendationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name_kr: str | None           # 카탈로그의 한글 제품명 (카드 제목용)
    reason: str
    tagline: str
    image_url: str | None         # /ai/assets/... 제품 사진 (없으면 null — 카드에서 생략)


class CurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[RecommendationOut]


def enrich_curation(result: CurationResult) -> CurationResponse:
    """LLM 추천에 제품명·사진 URL을 결정론적으로 부여 (환각 불가능한 코드 매칭)."""
    catalog = {p["product_id"]: p for p in load_catalog().get("products", [])}
    out = []
    for rec in result.recommendations:
        entry = brand_assets.find_by_product_id(rec.product_id)
        out.append(
            RecommendationOut(
                product_id=rec.product_id,
                name_kr=catalog.get(rec.product_id, {}).get("name_kr"),
                reason=rec.reason,
                tagline=rec.tagline,
                image_url=f"/ai/assets/{entry['file']}" if entry else None,
            )
        )
    return CurationResponse(recommendations=out)


@router.post("/curation", response_model=CurationResponse,
             summary="Stage 5: 럭셔리 큐레이션 (추천 + 이유 + tagline + 제품 사진)")
def curation(req: CurationRequest) -> CurationResponse:
    return enrich_curation(generate_curation(req.analysis, req.design_spec))
