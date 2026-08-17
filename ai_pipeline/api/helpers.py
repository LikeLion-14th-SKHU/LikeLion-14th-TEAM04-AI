"""API 공용 헬퍼 — base64 업로드 저장, storage 경로 ↔ 정적 URL 변환."""
from __future__ import annotations

import base64
import binascii
import uuid
from pathlib import Path

from fastapi import HTTPException

from ai_pipeline.config import settings

STATIC_PREFIX = "/ai/static"


def save_base64_image(data_b64: str) -> Path:
    """base64 이미지 → storage/uploads/ 저장 (확장자는 매직 바이트로 판별)."""
    try:
        data = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="image_base64가 올바른 base64가 아닙니다")
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="이미지 데이터가 너무 작습니다")

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    elif data[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    else:
        raise HTTPException(status_code=400, detail="지원 포맷은 JPEG/PNG 입니다")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    path = settings.upload_dir / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    normalize_exif_rotation(path)
    return path


# Claude API 이미지 상한 5MB(base64 전) — 여유를 두고 이 값 초과 시 재압축
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
# 분석용으로 충분한 최대 변 길이 (Claude 고해상도 비전 상한 2576px에 맞춤)
MAX_LONG_EDGE = 2560


def normalize_exif_rotation(path: Path) -> None:
    """폰 사진 정규화: EXIF 회전 적용 + 대형 사진 축소·재압축.

    - EXIF Orientation≠1이면 픽셀에 직접 회전 적용 (모델은 EXIF를 무시할 수 있음)
    - 5MB 초과 원본은 Claude API가 400으로 거절 → 긴 변 2560px로 축소 후 재압축
    실패해도 원본 그대로 진행 (치명적 아님 — 단, 대형 사진은 이후 단계에서 실패 가능).
    """
    try:
        from PIL import Image, ImageOps

        needs_resize = path.stat().st_size > MAX_UPLOAD_BYTES
        with Image.open(path) as im:
            rotated = im.getexif().get(0x0112, 1) != 1   # Orientation 태그
            needs_resize = needs_resize or max(im.size) > MAX_LONG_EDGE
            if not (rotated or needs_resize):
                return
            fixed = ImageOps.exif_transpose(im) if rotated else im
            if max(fixed.size) > MAX_LONG_EDGE:
                scale = MAX_LONG_EDGE / max(fixed.size)
                fixed = fixed.resize(
                    (round(fixed.width * scale), round(fixed.height * scale)),
                    Image.LANCZOS,
                )
            if path.suffix.lower() == ".png":
                fixed.save(path)
            else:
                fixed = fixed.convert("RGB")
                fixed.save(path, quality=90)
    except Exception:  # noqa: BLE001
        pass


def storage_url(path: Path) -> str:
    """storage/ 하위 파일 경로 → 프론트가 접근할 정적 URL (/ai/static/...)."""
    rel = path.resolve().relative_to(settings.storage_dir.resolve())
    return f"{STATIC_PREFIX}/{rel.as_posix()}"


def resolve_storage_ref(ref: str) -> Path:
    """정적 URL 또는 storage 상대 경로 → 실제 파일 경로 (경로 탈출 방지 포함)."""
    if ref.startswith(STATIC_PREFIX):
        ref = ref[len(STATIC_PREFIX):]
    ref = ref.lstrip("/")
    if ref.startswith("storage/"):
        ref = ref[len("storage/"):]

    path = (settings.storage_dir / ref).resolve()
    if not path.is_relative_to(settings.storage_dir.resolve()):
        raise HTTPException(status_code=400, detail="storage 밖 경로는 참조할 수 없습니다")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"파일이 없습니다: {ref}")
    return path
