"""GET /ai/v1/jobs/{job_id} — 비동기 job 진행 상황·결과 폴링."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_pipeline.schemas.job import JobInfo
from ai_pipeline.services.job_store import store

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobInfo, summary="job 상태 조회 (폴링)")
def get_job(job_id: str) -> JobInfo:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job이 없습니다")
    return job.to_info()
