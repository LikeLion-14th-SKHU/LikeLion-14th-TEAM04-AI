"""POST /ai/v1/pipeline-run — E2E 전체 파이프라인 (비동기, 202 + job_id).

상태 흐름 (DEVELOPMENT_PLAN 3절):
  running(stage 1→2→3→gate) → awaiting_selection (후보 카드 제시)
  → POST /ai/v1/jobs/{job_id}/select → running(stage 4[→5]) → done

사용자 선택 지점: job이 awaiting_selection이 되면 result.candidates에 후보 목록이 실린다.
백엔드는 사용자의 선택을 select 엔드포인트로 전달하면 3D 변환이 재개된다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict

from ai_pipeline.api.endpoints.stage1 import load_stage1_analyze
from ai_pipeline.api.helpers import save_base64_image, storage_url
from ai_pipeline.schemas.user_input import UserInput
from ai_pipeline.services.harness_gate import GatedConcept, gate_with_retry
from ai_pipeline.services.job_store import store
from ai_pipeline.services.stage2_design import generate_design_specs
from ai_pipeline.services.stage3_concept import generate_concept_images
from ai_pipeline.services.stage4_meshy_3d import generate_3d_model

router = APIRouter()


class PipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_base64: str                 # 옷 사진 (JPEG/PNG)
    user_input: UserInput
    target_category: str | None = None
    use_pro: bool = False


class JobAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str


class SelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_index: int              # awaiting_selection의 result.candidates 인덱스


def run_until_selection(
    job_id: str,
    clothing: Path,
    user_input: UserInput,
    target_category: str | None,
    use_pro: bool,
) -> None:
    """Stage 1 → 2 → 3 → 게이트까지 실행하고 사용자 선택 대기 상태로 전환."""
    try:
        analyze = load_stage1_analyze()

        store.update(job_id, stage="1", detail="옷 분석·사연 해석 중")
        analysis = analyze(clothing, user_input)

        store.update(job_id, stage="2", detail="재창조 디자인 스펙 생성 중")
        specs = generate_design_specs(analysis, target_category=target_category)

        store.update(job_id, stage="3", detail="컨셉 이미지 생성 중")
        concepts = generate_concept_images(specs.candidates, clothing, use_pro=use_pro)

        store.update(job_id, stage="gate", detail="품질·브랜드 정합성 검증 중")
        outcome = gate_with_retry(
            concepts,
            regenerate=lambda s: generate_concept_images(s, clothing, use_pro=use_pro),
        )

        candidates_payload = [
            {
                "index": i,
                "spec": g.concept.spec.model_dump(),
                "image_url": storage_url(g.concept.image_path),
                "gate": g.gate.model_dump(),
            }
            for i, g in enumerate(outcome.candidates)
        ]
        store.update(
            job_id,
            status="awaiting_selection", stage=None,
            detail="후보 중 1개를 선택하세요 (POST /ai/v1/jobs/{job_id}/select)",
            result={
                "analysis": analysis.model_dump(),
                "candidates": candidates_payload,
                "all_failed": outcome.all_failed,
                "regenerated": outcome.regenerated,
            },
        )
        # 선택 후 재개에 필요한 내부 상태 (API 비노출)
        job = store.get(job_id)
        assert job is not None
        job.internal["gated"] = outcome.candidates
        job.internal["analysis"] = analysis
    except HTTPException as e:            # stage1 미병합(501) 등
        store.fail(job_id, e.detail if isinstance(e.detail, str) else str(e.detail))
    except Exception as e:  # noqa: BLE001
        store.fail(job_id, str(e))


def run_after_selection(job_id: str, selected: GatedConcept) -> None:
    """선택된 컨셉 1개 → Stage 4 (3D) → (가능하면) Stage 5 → done."""
    try:
        store.update(job_id, status="running", stage="4", detail="3D 모델 생성 중 (30~60초)")
        model3d = generate_3d_model(
            selected.concept.image_path,
            on_progress=lambda p, s: store.update(job_id, detail=f"3D 변환 {s} {p}%"),
        )

        job = store.get(job_id)
        assert job is not None and job.result is not None
        result = dict(job.result)
        result["selected"] = {
            "spec": selected.concept.spec.model_dump(),
            "image_url": storage_url(selected.concept.image_path),
        }
        result["glb_url"] = storage_url(model3d.glb_path)
        result["front_image_url"] = (
            storage_url(model3d.front_image_path) if model3d.front_image_path else None
        )
        result["thumbnail_url"] = model3d.thumbnail_url

        # Stage 5 (팀원 개발분) — 병합돼 있으면 실행, 아니면 curation 없이 완료
        try:
            from ai_pipeline.services.stage5_curation import generate_curation

            store.update(job_id, stage="5", detail="럭셔리 큐레이션 중")
            curation = generate_curation(job.internal["analysis"], selected.concept.spec)
            result["curation"] = curation.model_dump() if hasattr(curation, "model_dump") else curation
        except ImportError:
            result["curation"] = None   # Stage 5 미병합 — 병합되면 자동으로 포함됨

        store.update(job_id, status="done", stage=None, detail=None, result=result)
    except Exception as e:  # noqa: BLE001
        store.fail(job_id, str(e))


@router.post("/pipeline-run", response_model=JobAccepted, status_code=202,
             summary="E2E 파이프라인 실행 (비동기 — 후보 제시 후 선택 대기)")
def pipeline_run(req: PipelineRequest, background: BackgroundTasks) -> JobAccepted:
    load_stage1_analyze()   # stage1 미병합이면 job 만들기 전에 501
    clothing = save_base64_image(req.image_base64)
    job = store.create(stage="1", detail="파이프라인 시작")
    background.add_task(
        run_until_selection, job.job_id, clothing, req.user_input, req.target_category, req.use_pro
    )
    return JobAccepted(job_id=job.job_id)


@router.post("/jobs/{job_id}/select", response_model=JobAccepted, status_code=202,
             summary="후보 선택 → 3D 변환 재개 (pipeline-run 전용)")
def select_candidate(job_id: str, req: SelectRequest, background: BackgroundTasks) -> JobAccepted:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job이 없습니다")
    if job.status != "awaiting_selection":
        raise HTTPException(status_code=409, detail=f"선택 가능한 상태가 아닙니다 (현재: {job.status})")

    gated: list[GatedConcept] = job.internal.get("gated", [])
    if not 0 <= req.candidate_index < len(gated):
        raise HTTPException(status_code=400, detail=f"candidate_index 범위 밖 (0~{len(gated) - 1})")

    background.add_task(run_after_selection, job_id, gated[req.candidate_index])
    return JobAccepted(job_id=job_id)
