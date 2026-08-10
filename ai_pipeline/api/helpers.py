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
    return path


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
