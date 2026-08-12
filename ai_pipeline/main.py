"""MCM Upcycled Memory — AI Pipeline Engine (FastAPI).

실행 (프로젝트 루트):
    uvicorn ai_pipeline.main:app --reload
    → Swagger UI: http://localhost:8000/docs

⚠️ 워커는 반드시 1개로 (기본값) — job 저장소가 인메모리라 다중 워커에서는 job 조회가 깨진다.
생성 산출물(컨셉 이미지·GLB)은 /ai/static/... 정적 URL로 서빙된다.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ai_pipeline.api.router import api_router
from ai_pipeline.config import settings

app = FastAPI(
    title="MCM Upcycled Memory — AI Pipeline Engine",
    version="0.1.0",
    description=(
        "옷 사진 + 사연 → 재창조 디자인 → 컨셉 이미지(게이트 통과) → 3D 굿즈 → 큐레이션.\n\n"
        "- 동기: `/ai/v1/narrative`, `/ai/v1/design-spec`, `/ai/v1/concept-image`, `/ai/v1/curation`\n"
        "- 비동기(202+job_id → `/ai/v1/jobs/{job_id}` 폴링): `/ai/v1/image-to-3d`, `/ai/v1/pipeline-run`\n"
        "- `pipeline-run`은 후보 제시 후 `awaiting_selection` 상태로 대기 → "
        "`/ai/v1/jobs/{job_id}/select`로 선택하면 3D 변환 재개"
    ),
)

# 생성 산출물 정적 서빙 (컨셉 이미지, GLB) — 응답의 image_url/glb_url이 이 경로를 가리킴
settings.storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/ai/static", StaticFiles(directory=settings.storage_dir), name="static")

# MCM 제품 이미지 서빙 (큐레이션 카드용) — 추천 응답의 image_url이 /ai/assets/... 를 가리킴
# ⚠️ 브랜드 이미지는 로컬 시연 서버에서만 서빙 — public 배포 금지 (저작권)
app.mount("/ai/assets", StaticFiles(directory=settings.asset_root), name="assets")

app.include_router(api_router, prefix="/ai/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"service": "MCM Upcycled Memory — AI Pipeline Engine", "docs": "/docs"}
