"""Stage 4 — Image-to-3D 변환 (Meshy openapi v1).

게이트 통과 + 사용자 선택을 거친 컨셉 이미지 1장을 GLB 3D 모델로 변환한다.

API 흐름 (docs.meshy.ai 확인, 2026-08):
  POST {base}/image-to-3d              → {"result": "<task_id>"}   (Bearer 인증)
  GET  {base}/image-to-3d/{task_id}    → {"status": PENDING|IN_PROGRESS|SUCCEEDED|FAILED|CANCELED,
                                          "progress": 0~100, "model_urls": {"glb": ...}, ...}
  GLB 다운로드 URL은 만료 시간이 있으므로 SUCCEEDED 즉시 다운로드한다.

주의:
- 크레딧 소모 API — 파이프라인에서 호출은 항상 1건 (n배 비용 구간은 이미지 생성까지)
- 실패한 태스크는 크레딧이 환불됨 (공식 문서)
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from ai_pipeline.config import settings
from ai_pipeline.services.llm_client import _write_trace

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELED"}


class MeshyError(RuntimeError):
    """Meshy 태스크 실패/타임아웃."""


@dataclass
class Model3D:
    """Stage 4 산출물."""
    glb_path: Path
    task_id: str
    trace_id: str
    thumbnail_url: str | None
    consumed_credits: int | None
    front_image_path: Path | None = None   # 투명 배경 정면 PNG (컬렉션 그리드용, 렌더 실패 시 None)


def _make_client() -> httpx.Client:
    if not settings.meshy_api_key:
        raise MeshyError("MESHY_API_KEY가 없습니다 — .env 확인")
    return httpx.Client(
        base_url=settings.meshy_base_url,
        headers={"Authorization": f"Bearer {settings.meshy_api_key}"},
        timeout=60,
    )


def image_to_data_uri(image_path: Path) -> str:
    """컨셉 이미지(jpg/png) → Meshy image_url용 base64 data URI."""
    suffix = image_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif suffix == ".png":
        mime = "image/png"
    else:
        raise ValueError(f"Meshy가 지원하지 않는 포맷: {suffix} (jpg/png만 가능)")
    data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def build_create_payload(image_path: Path) -> dict[str, Any]:
    """태스크 생성 요청 본문. 텍스처 품질(PBR)이 채택 근거이므로 enable_pbr을 켠다.

    품질 튜닝 노브는 config(.env)로 조정: MESHY_TEXTURE_RESOLUTION, MESHY_TEXTURE_PROMPT.
    """
    payload: dict[str, Any] = {
        "image_url": image_to_data_uri(image_path),
        "ai_model": "latest",
        "should_texture": True,
        "enable_pbr": True,           # 비세토스 패턴·가죽 질감 재현 (AI_Dev_PipeLine.md Stage 4 선정 근거)
        "texture_resolution": settings.meshy_texture_resolution,
        "target_formats": ["glb"],    # 웹 뷰어('추억의 옷장')용
    }
    if settings.meshy_texture_prompt.strip():
        payload["texture_prompt"] = settings.meshy_texture_prompt.strip()[:600]  # API 상한 600자
    return payload


def create_task(image_path: Path, client: httpx.Client) -> str:
    resp = client.post("/image-to-3d", json=build_create_payload(image_path))
    resp.raise_for_status()
    body = resp.json()
    task_id = body.get("result") or body.get("id")
    if not task_id:
        raise MeshyError(f"태스크 ID를 찾을 수 없음 — 응답: {body}")
    return task_id


def poll_task(
    task_id: str,
    client: httpx.Client,
    *,
    on_progress: Callable[[int, str], None] | None = None,
    interval_s: float | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """SUCCEEDED까지 폴링. FAILED/CANCELED/타임아웃이면 MeshyError."""
    interval_s = interval_s if interval_s is not None else settings.meshy_poll_interval_s
    timeout_s = timeout_s if timeout_s is not None else settings.meshy_timeout_s
    deadline = time.monotonic() + timeout_s

    while True:
        resp = client.get(f"/image-to-3d/{task_id}")
        resp.raise_for_status()
        task = resp.json()
        status = task.get("status")

        if on_progress:
            on_progress(int(task.get("progress") or 0), status or "?")

        if status == "SUCCEEDED":
            return task
        if status in TERMINAL_STATUSES:  # FAILED / CANCELED
            err = (task.get("task_error") or {}).get("message", "")
            raise MeshyError(f"태스크 {status}: {err or '(사유 없음)'} — 크레딧은 환불됨")
        if time.monotonic() > deadline:
            raise MeshyError(f"타임아웃 ({timeout_s:.0f}초) — task_id={task_id} 는 Meshy 대시보드에서 확인 가능")

        time.sleep(interval_s)


def download_glb(task: dict[str, Any], out_path: Path, client: httpx.Client) -> Path:
    glb_url = (task.get("model_urls") or {}).get("glb")
    if not glb_url:
        raise MeshyError(f"model_urls.glb가 없음 — 응답 키: {list(task)}")
    # 호스트 분기: API 호스트면 클라이언트 재사용, 외부 자산 호스트(서명 URL)면
    # 인증 헤더 없이 요청 (S3류 서명 URL은 Authorization 헤더가 있으면 거부될 수 있음)
    api_host = httpx.URL(settings.meshy_base_url).host
    url_host = httpx.URL(glb_url).host if not glb_url.startswith("/") else api_host
    if url_host == api_host:
        resp = client.get(glb_url)
    else:
        resp = httpx.get(glb_url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return out_path


def generate_3d_model(
    image_path: Path,
    *,
    out_dir: Path | None = None,
    on_progress: Callable[[int, str], None] | None = None,
    trace_id: str | None = None,
    client: httpx.Client | None = None,   # 테스트 주입용
) -> Model3D:
    """Stage 4 진입점: 컨셉 이미지 1장 → GLB 파일."""
    trace_id = trace_id or str(uuid.uuid4())
    out_dir = out_dir or settings.model_output_dir
    own_client = client is None
    client = client or _make_client()

    t0 = time.monotonic()
    try:
        task_id = create_task(image_path, client)
        task = poll_task(task_id, client, on_progress=on_progress)
        glb_path = download_glb(task, out_dir / f"{image_path.stem}.glb", client)
    finally:
        if own_client:
            client.close()

    # 컬렉션 그리드용 투명 배경 정면 썸네일 (실패해도 치명적 아님 — glb만 제공)
    from ai_pipeline.services.glb_render import render_front_png_safe

    front_image_path = render_front_png_safe(glb_path)
    latency_ms = int((time.monotonic() - t0) * 1000)

    _write_trace(
        trace_id=trace_id,
        stage="4",
        model="meshy-image-to-3d",
        latency_ms=latency_ms,
        task_id=task_id,
        consumed_credits=task.get("consumed_credits"),
        input_ref=str(image_path),
        output_ref=str(glb_path),
    )
    return Model3D(
        glb_path=glb_path,
        task_id=task_id,
        trace_id=trace_id,
        thumbnail_url=task.get("thumbnail_url"),
        consumed_credits=task.get("consumed_credits"),
        front_image_path=front_image_path,
    )
