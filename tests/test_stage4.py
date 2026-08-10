"""Stage 4 (Meshy) 검증 수트 — MockTransport로 API 키 없이 전체 흐름 검증."""
import json

import httpx
import pytest

from ai_pipeline.config import settings
from ai_pipeline.services.stage4_meshy_3d import (
    MeshyError,
    build_create_payload,
    generate_3d_model,
    image_to_data_uri,
)

FAKE_GLB = b"glTF-binary-fake-content"


@pytest.fixture
def concept_image(tmp_path):
    """가짜 컨셉 이미지 (jpg)."""
    p = tmp_path / "concept_safe.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return p


# ---------------------------------------------------------------------------
# 입력 변환
# ---------------------------------------------------------------------------


def test_image_to_data_uri(concept_image):
    uri = image_to_data_uri(concept_image)
    assert uri.startswith("data:image/jpeg;base64,")


def test_image_to_data_uri_rejects_unsupported(tmp_path):
    p = tmp_path / "concept.avif"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="jpg/png"):
        image_to_data_uri(p)


def test_build_create_payload(concept_image):
    payload = build_create_payload(concept_image)
    assert payload["enable_pbr"] is True, "PBR 텍스처가 Meshy 채택 근거 (비세토스·가죽 질감)"
    assert payload["target_formats"] == ["glb"]
    assert payload["image_url"].startswith("data:image/jpeg;base64,")


# ---------------------------------------------------------------------------
# 전체 흐름 (Mock API)
# ---------------------------------------------------------------------------


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        base_url=settings.meshy_base_url,
        transport=httpx.MockTransport(handler),
    )


def test_generate_3d_model_happy_path(concept_image, tmp_path):
    """등록 → PENDING → IN_PROGRESS → SUCCEEDED → GLB 다운로드 전체 흐름."""
    poll_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/image-to-3d"):
            body = json.loads(request.content)
            assert body["image_url"].startswith("data:image/jpeg")
            return httpx.Response(200, json={"result": "task-123"})
        if request.url.path.endswith(".glb"):
            return httpx.Response(200, content=FAKE_GLB)
        if request.method == "GET" and "task-123" in request.url.path:
            poll_count["n"] += 1
            if poll_count["n"] == 1:
                return httpx.Response(200, json={"status": "PENDING", "progress": 0})
            if poll_count["n"] == 2:
                return httpx.Response(200, json={"status": "IN_PROGRESS", "progress": 55})
            return httpx.Response(
                200,
                json={
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "model_urls": {"glb": str(request.url.copy_with(path="/files/task-123.glb"))},
                    "thumbnail_url": "https://example.com/thumb.png",
                    "consumed_credits": 5,
                },
            )
        return httpx.Response(404)

    progress_log = []
    result = generate_3d_model(
        concept_image,
        out_dir=tmp_path,
        on_progress=lambda p, s: progress_log.append((p, s)),
        client=_mock_client(handler),
    )

    assert result.glb_path.exists()
    assert result.glb_path.read_bytes() == FAKE_GLB
    assert result.glb_path.name == "concept_safe.glb"
    assert result.task_id == "task-123"
    assert result.consumed_credits == 5
    assert progress_log[0] == (0, "PENDING") and progress_log[-1] == (100, "SUCCEEDED")


def test_generate_3d_model_failed_task(concept_image, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"result": "task-fail"})
        return httpx.Response(
            200, json={"status": "FAILED", "progress": 30, "task_error": {"message": "bad input"}}
        )

    with pytest.raises(MeshyError, match="FAILED"):
        generate_3d_model(concept_image, out_dir=tmp_path, client=_mock_client(handler))


def test_poll_timeout(concept_image, tmp_path, monkeypatch):
    """영원히 PENDING이면 타임아웃 — 무한 루프 방지 검증."""
    monkeypatch.setattr(settings, "meshy_poll_interval_s", 0.01)
    monkeypatch.setattr(settings, "meshy_timeout_s", 0.05)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"result": "task-slow"})
        return httpx.Response(200, json={"status": "PENDING", "progress": 0})

    with pytest.raises(MeshyError, match="타임아웃"):
        generate_3d_model(concept_image, out_dir=tmp_path, client=_mock_client(handler))


def test_missing_api_key_message(concept_image, monkeypatch):
    monkeypatch.setattr(settings, "meshy_api_key", "")
    with pytest.raises(MeshyError, match="MESHY_API_KEY"):
        generate_3d_model(concept_image)


# ---------------------------------------------------------------------------
# 실호출 스모크 (MESHY_API_KEY 있을 때만 — 크레딧 소모 주의)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not settings.meshy_api_key, reason="MESHY_API_KEY 없음 (.env)")
def test_generate_3d_model_smoke(tmp_path):
    """실제 크레딧을 소모하므로 storage/images의 실제 컨셉 이미지가 있을 때만 의미 있음."""
    images = sorted(settings.image_output_dir.glob("*.jpg")) if settings.image_output_dir.exists() else []
    if not images:
        pytest.skip("storage/images에 컨셉 이미지 없음 — 먼저 run_stage3.py 실행")
    result = generate_3d_model(images[-1], out_dir=tmp_path, on_progress=lambda p, s: print(f"{s} {p}%"))
    assert result.glb_path.exists()
    assert result.glb_path.stat().st_size > 100_000, "GLB치고 너무 작음"
