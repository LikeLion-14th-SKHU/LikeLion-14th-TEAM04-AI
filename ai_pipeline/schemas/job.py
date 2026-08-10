"""job 기반 비동기 API의 상태 스키마 (DEVELOPMENT_PLAN 3절).

장기 실행 작업(image-to-3d, pipeline-run)은 202 + job_id를 즉시 반환하고,
백엔드/프론트는 GET /ai/v1/jobs/{job_id} 로 진행 상황을 폴링한다.

상태 전이:
  running → done | failed                          (image-to-3d)
  running → awaiting_selection → running → done    (pipeline-run: 후보 제시 → 사용자 선택 → 3D)
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

JobStatus = Literal["running", "awaiting_selection", "done", "failed"]


class JobInfo(BaseModel):
    """GET /ai/v1/jobs/{job_id} 응답."""
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    stage: str | None          # 진행 중인 단계 표시용: "1" | "2" | "3" | "gate" | "4" | "5"
    detail: str | None         # 사람이 읽을 진행 설명 (프론트 로딩 문구용)
    result: dict[str, Any] | None   # done: 최종 산출물 / awaiting_selection: 후보 목록
    error: str | None
    created_at: str
    updated_at: str
