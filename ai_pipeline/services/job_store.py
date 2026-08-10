"""인메모리 job 저장소 — FastAPI BackgroundTasks 기반 비동기 작업 추적.

해커톤 규모 전제: 단일 프로세스, 인메모리 dict + Lock이면 충분 (별도 인프라 불필요).
uvicorn을 다중 워커로 띄우면 깨지므로 워커 1개로 운용할 것 (main.py 주석 참고).

job.internal 은 API로 노출되지 않는 서버 내부 상태 보관용
(예: pipeline-run이 사용자 선택을 기다리는 동안 들고 있을 게이트 통과 컨셉들의 파일 경로·스펙).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ai_pipeline.schemas.job import JobInfo, JobStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    job_id: str
    status: JobStatus = "running"
    stage: str | None = None
    detail: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    internal: dict[str, Any] = field(default_factory=dict)  # API 비노출

    def to_info(self) -> JobInfo:
        return JobInfo(
            job_id=self.job_id,
            status=self.status,
            stage=self.stage,
            detail=self.detail,
            result=self.result,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, *, stage: str | None = None, detail: str | None = None) -> Job:
        job = Job(job_id=str(uuid.uuid4()), stage=stage, detail=detail)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = _now()
            return job

    def fail(self, job_id: str, error: str) -> Job:
        return self.update(job_id, status="failed", error=error, detail=None)

    def clear(self) -> None:  # 테스트용
        with self._lock:
            self._jobs.clear()


# 모듈 싱글톤 — 앱 전역에서 공유
store = JobStore()
