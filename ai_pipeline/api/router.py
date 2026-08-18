"""/ai/v1 라우터 모음 — 백엔드 팀 연동 지점 (DEVELOPMENT_PLAN 3절 계약)."""
from fastapi import APIRouter

from ai_pipeline.api.endpoints import full_pipeline, jobs, stage1, stage2, stage3, stage4, stage5

api_router = APIRouter()
api_router.include_router(stage1.router, tags=["Stage 1 — 서사"])
api_router.include_router(stage2.router, tags=["Stage 2 — 디자인 스펙"])
api_router.include_router(stage3.router, tags=["Stage 3 — 컨셉 이미지 (+게이트)"])
api_router.include_router(stage4.router, tags=["Stage 4 — 3D 변환"])
api_router.include_router(stage5.router, tags=["Stage 5 — 큐레이션"])
api_router.include_router(full_pipeline.router, tags=["E2E 파이프라인"])
api_router.include_router(jobs.router, tags=["Jobs"])
