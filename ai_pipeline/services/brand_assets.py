"""MCM 브랜드 자산 로더.

- data/_index.json: 레퍼런스 이미지 인덱스 (단일 진실 원천 — 파일 경로를 직접 파싱하지 않는다)
- ai_pipeline/data/mcm_brand_assets.json: 디자인 코드 (프롬프트 캐싱 대상 텍스트의 원천)
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_pipeline.config import settings


@lru_cache(maxsize=1)
def load_index() -> list[dict[str, Any]]:
    return json.loads(settings.asset_index_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_design_code() -> dict[str, Any]:
    return json.loads(settings.brand_assets_path.read_text(encoding="utf-8"))


def design_code_text() -> str:
    """디자인 코드 JSON을 프롬프트용 텍스트로 렌더링.

    ⚠️ 결정론적이어야 한다(캐시 접두사) — dict 순서는 JSON 파일 순서를 그대로 따른다.
    """
    code = load_design_code()
    lines: list[str] = []
    for section, content in code.items():
        lines.append(f"## {section}")
        if isinstance(content, dict):
            for k, v in content.items():
                lines.append(f"- {k}: {v}")
        elif isinstance(content, list):
            for item in content:
                lines.append(f"- {item}")
        else:
            lines.append(str(content))
        lines.append("")
    return "\n".join(lines).strip()


def select_references(
    category: str | None = None,
    k: int | None = None,
    index: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """레퍼런스 이미지 항목 선별.

    - category 지정: 해당 카테고리에서 라인이 겹치지 않게 k개
    - category=None (자동 제안 모드): 전체에서 라인이 겹치지 않게 k개 (다양성 우선)
    """
    k = k or settings.n_reference_images
    entries = index if index is not None else load_index()

    if category is not None:
        entries = [e for e in entries if e["category"] == category]

    picked: list[dict[str, Any]] = []
    seen_lines: set[str] = set()
    # 1차: 라인 중복 없이
    for e in entries:
        if e["line"] not in seen_lines:
            picked.append(e)
            seen_lines.add(e["line"])
        if len(picked) >= k:
            return picked
    # 2차: 부족하면 중복 허용
    for e in entries:
        if e not in picked:
            picked.append(e)
        if len(picked) >= k:
            break
    return picked


def available_categories() -> list[dict[str, Any]]:
    """사용자가 지정 가능한 재창조 목표 카테고리 목록 (인덱스에서 도출 — DB가 늘면 자동 확장).

    보유 수량 내림차순. count는 프론트가 "선택지 신뢰도" 표시에 쓸 수 있게 함께 준다.
    """
    counts: dict[str, int] = {}
    for e in load_index():
        counts[e["category"]] = counts.get(e["category"], 0) + 1
    return [
        {"category": c, "count": n}
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def is_valid_category(category: str) -> bool:
    return any(c["category"] == category for c in available_categories())


def find_by_product_id(product_id: str) -> dict[str, Any] | None:
    """product_id로 인덱스 항목 조회 (Stage 3가 base_product 레퍼런스 이미지를 찾을 때 사용)."""
    for entry in load_index():
        if entry["product_id"] == product_id:
            return entry
    return None


def image_block(entry: dict[str, Any]) -> dict[str, Any]:
    """인덱스 항목 → Anthropic image content block (base64 PNG)."""
    path: Path = settings.asset_root / entry["file"]
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def reference_caption(entry: dict[str, Any]) -> str:
    """이미지 블록 옆에 붙일 캡션 — 모델이 base_product를 인덱스 ID로 답하게 유도."""
    parts = [f"product_id={entry['product_id']}", f"라인={entry['line']}", f"컬러={entry['color']}"]
    if entry.get("size"):
        parts.append(f"사이즈={entry['size']}")
    if entry.get("note"):
        parts.append(entry["note"])
    return f"[레퍼런스: {', '.join(parts)}]"
