"""POST /ai/v1/image-to-3d — Stage 4: Meshy 3D 변환 (비동기, 202 + job_id).

Meshy 생성이 30~60초라 동기 응답 불가 — job으로 감싸고 GET /ai/v1/jobs/{job_id}로 폴링.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, ConfigDict

from ai_pipeline.api.helpers import resolve_storage_ref, storage_url
from ai_pipeline.services.job_store import store
from ai_pipeline.services.stage4_meshy_3d import generate_3d_model

router = APIRouter()


class ImageTo3DRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # concept-image 응답의 image_url (/ai/static/images/xxx.jpg) 을 그대로 넣으면 됨
    image_ref: str


class JobAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str


def run_3d_job(job_id: str, image_path: Path) -> None:
    try:
        result = generate_3d_model(
            image_path,
            on_progress=lambda p, s: store.update(job_id, detail=f"3D 변환 {s} {p}%"),
        )
        store.update(
            job_id,
            status="done", stage=None, detail=None,
            result={
                "glb_url": storage_url(result.glb_path),
                "thumbnail_url": result.thumbnail_url,
                "consumed_credits": result.consumed_credits,
            },
        )
    except Exception as e:  # noqa: BLE001 — job 실패는 상태로 전달
        store.fail(job_id, str(e))


@router.post("/image-to-3d", response_model=JobAccepted, status_code=202,
             summary="Stage 4: Meshy 3D 변환 (비동기 — jobs로 폴링)")
def image_to_3d(req: ImageTo3DRequest, background: BackgroundTasks) -> JobAccepted:
    image_path = resolve_storage_ref(req.image_ref)   # 존재·경로 검증은 202 전에
    job = store.create(stage="4", detail="3D 변환 대기 중")
    background.add_task(run_3d_job, job.job_id, image_path)
    return JobAccepted(job_id=job.job_id)
