"""FastAPI 계약 테스트 — 서비스 계층은 mock, API 키 불필요.

핵심 검증: 동기/비동기 구분, job 상태 전이(running → awaiting_selection → done),
선택 엔드포인트의 상태 가드, 정적 URL 변환.
(TestClient는 BackgroundTasks를 응답 직후 동기 실행하므로 폴링 없이 상태를 단언할 수 있다.)
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_pipeline.api.endpoints import full_pipeline as fp
from ai_pipeline.api.endpoints import stage2 as ep2
from ai_pipeline.api.endpoints import stage4 as ep4
from ai_pipeline.config import settings
from ai_pipeline.main import app
from ai_pipeline.schemas.design_spec import CandidateList, DesignSpec
from ai_pipeline.schemas.verification import GateResult
from ai_pipeline.services.harness_gate import GatedConcept, GateOutcome
from ai_pipeline.services.job_store import store
from ai_pipeline.services.stage3_concept import ConceptImage
from ai_pipeline.services.stage4_meshy_3d import Model3D

client = TestClient(app)

# 1x1 JPEG (유효한 매직 바이트 포함)
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
)


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


def _spec(profile: str = "safe", level: int = 2) -> DesignSpec:
    return DesignSpec.model_validate(
        {
            "concept_name": f"컨셉-{profile}",
            "category": "미니 레더백",
            "category_reason": None,
            "base_product": "dessau-cognac",
            "risk_profile": profile,
            "intervention_level": level,
            "creation_method": "패치",
            "applied_elements": [
                {"from_element": "해진 소매", "to_element": "플랩", "reason": "흔적 보존"}
            ],
            "image_prompt": "Attach patch. plain light-gray studio background, front view, product only, no props.",
        }
    )


def _candidate_list() -> CandidateList:
    return CandidateList(candidates=[_spec("safe", 2), _spec("balanced", 3), _spec("bold", 5)])


def _fake_concept(profile: str) -> ConceptImage:
    settings.image_output_dir.mkdir(parents=True, exist_ok=True)
    p = settings.image_output_dir / f"apitest_{profile}.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake")
    return ConceptImage(spec=_spec(profile), image_path=p, trace_id="t", reference_used=None)


def _fake_outcome() -> GateOutcome:
    gated = [
        GatedConcept(concept=_fake_concept("safe"), gate=GateResult(passed=True, score=90, fail_reasons=[])),
        GatedConcept(concept=_fake_concept("balanced"), gate=GateResult(passed=True, score=80, fail_reasons=[])),
    ]
    return GateOutcome(candidates=gated, all_failed=False, regenerated=False)


def _fake_model3d(image_path: Path) -> Model3D:
    return Model3D(
        glb_path=settings.model_output_dir / "apitest.glb",
        task_id="task-x", trace_id="t", thumbnail_url="http://t/thumb.png", consumed_credits=5,
    )


# ---------------------------------------------------------------------------
# 기본
# ---------------------------------------------------------------------------


def test_root_and_docs():
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200


def test_jobs_404():
    assert client.get("/ai/v1/jobs/none").status_code == 404


# ---------------------------------------------------------------------------
# 동기 엔드포인트
# ---------------------------------------------------------------------------


def test_design_spec_endpoint(monkeypatch, sample_analysis):
    monkeypatch.setattr(ep2, "generate_design_specs", lambda a, target_category=None: _candidate_list())
    resp = client.post(
        "/ai/v1/design-spec",
        json={"analysis": sample_analysis.model_dump(), "target_category": None},
    )
    assert resp.status_code == 200
    assert len(resp.json()["candidates"]) == 3


def test_narrative_before_merge_returns_501_or_works(sample_analysis):
    """Stage 1 모듈이 브랜치에 없으면 501, 병합돼 있으면 이 테스트는 통과로 간주."""
    try:
        import ai_pipeline.services.stage1_narrative  # noqa: F401
        pytest.skip("Stage 1 병합됨 — 501 경로는 더 이상 해당 없음")
    except ImportError:
        pass
    resp = client.post(
        "/ai/v1/narrative",
        json={
            "image_base64": TINY_JPEG_B64,
            "user_input": {
                "category": {"main": "의류", "sub": "셔츠"},
                "material": "데님",
                "condition": ["해짐"],
                "story": "아버지의 셔츠",
            },
        },
    )
    assert resp.status_code == 501


def test_concept_image_rejects_bad_base64():
    resp = client.post(
        "/ai/v1/concept-image",
        json={"clothing_image_base64": "!!!not-base64!!!", "candidates": [_spec().model_dump()]},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 비동기: image-to-3d
# ---------------------------------------------------------------------------


def test_image_to_3d_job_flow(monkeypatch):
    concept = _fake_concept("safe")   # storage/images 밑에 실존 파일
    monkeypatch.setattr(ep4, "generate_3d_model", lambda p, on_progress=None: _fake_model3d(p))

    resp = client.post("/ai/v1/image-to-3d", json={"image_ref": f"/ai/static/images/{concept.image_path.name}"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    job = client.get(f"/ai/v1/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert job["result"]["glb_url"] == "/ai/static/models/apitest.glb"


def test_image_to_3d_missing_file_404():
    resp = client.post("/ai/v1/image-to-3d", json={"image_ref": "/ai/static/images/no-such.jpg"})
    assert resp.status_code == 404


def test_image_to_3d_path_escape_blocked():
    resp = client.post("/ai/v1/image-to-3d", json={"image_ref": "../data/bag/x.png"})
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# 비동기: pipeline-run → awaiting_selection → select → done
# ---------------------------------------------------------------------------


def _patch_pipeline(monkeypatch, sample_analysis):
    monkeypatch.setattr(fp, "load_stage1_analyze", lambda: (lambda img, ui: sample_analysis))
    monkeypatch.setattr(fp, "generate_design_specs", lambda a, target_category=None: _candidate_list())
    monkeypatch.setattr(fp, "generate_concept_images", lambda specs, c, use_pro=False: [_fake_concept("safe")])
    monkeypatch.setattr(fp, "gate_with_retry", lambda concepts, regenerate=None: _fake_outcome())
    monkeypatch.setattr(fp, "generate_3d_model", lambda p, on_progress=None: _fake_model3d(p))


def _pipeline_payload() -> dict:
    return {
        "image_base64": TINY_JPEG_B64,
        "user_input": {
            "category": {"main": "의류", "sub": "셔츠"},
            "material": "데님",
            "condition": ["해짐"],
            "story": "아버지의 셔츠",
        },
    }


def test_pipeline_full_flow(monkeypatch, sample_analysis):
    _patch_pipeline(monkeypatch, sample_analysis)

    # 1) 실행 → 후보 제시 대기
    resp = client.post("/ai/v1/pipeline-run", json=_pipeline_payload())
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    job = client.get(f"/ai/v1/jobs/{job_id}").json()
    assert job["status"] == "awaiting_selection"
    assert len(job["result"]["candidates"]) == 2
    assert job["result"]["candidates"][0]["image_url"].startswith("/ai/static/images/")

    # 2) 선택 → 3D → 완료
    resp = client.post(f"/ai/v1/jobs/{job_id}/select", json={"candidate_index": 0})
    assert resp.status_code == 202

    job = client.get(f"/ai/v1/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert job["result"]["glb_url"] == "/ai/static/models/apitest.glb"
    assert job["result"]["selected"]["spec"]["risk_profile"] == "safe"
    assert "curation" in job["result"], "Stage 5 미병합이어도 키는 존재 (None)"


def test_select_guards(monkeypatch, sample_analysis):
    _patch_pipeline(monkeypatch, sample_analysis)

    resp = client.post("/ai/v1/pipeline-run", json=_pipeline_payload())
    job_id = resp.json()["job_id"]

    # 범위 밖 인덱스
    assert client.post(f"/ai/v1/jobs/{job_id}/select", json={"candidate_index": 99}).status_code == 400
    # 정상 선택 후 재선택 → 409 (이미 awaiting_selection 아님)
    client.post(f"/ai/v1/jobs/{job_id}/select", json={"candidate_index": 0})
    assert client.post(f"/ai/v1/jobs/{job_id}/select", json={"candidate_index": 0}).status_code == 409
    # 없는 job → 404
    assert client.post("/ai/v1/jobs/nope/select", json={"candidate_index": 0}).status_code == 404
