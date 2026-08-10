"""POST /ai/v1/narrative — Stage 1: 복합 이해 & 서사 생성 (동기).

Stage 1 모듈은 팀원(KNY_dev_v1) 개발분 — 이 브랜치에 병합되기 전까지는 501을 반환한다.
병합되면 코드 수정 없이 그대로 동작한다 (지연 import).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ai_pipeline.api.helpers import save_base64_image
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.user_input import UserInput

router = APIRouter()


class NarrativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_base64: str | None = None   # 옷 사진 (JPEG/PNG). 없으면 텍스트만으로 분석
    user_input: UserInput


def load_stage1_analyze():
    """지연 import — 테스트에서 monkeypatch 가능하도록 함수로 분리."""
    try:
        from ai_pipeline.services.stage1_narrative import analyze
        return analyze
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Stage 1 모듈이 아직 이 브랜치에 없습니다 (KNY_dev_v1 병합 후 사용 가능)",
        )


@router.post("/narrative", response_model=AnalysisResult, summary="Stage 1: 복합 이해 & 서사 생성")
def narrative(req: NarrativeRequest) -> AnalysisResult:
    analyze = load_stage1_analyze()
    image_path = save_base64_image(req.image_base64) if req.image_base64 else None
    return analyze(image_path, req.user_input)
