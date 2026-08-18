"""Stage 2 검증 수트.

- 단위 테스트: API 키 없이 실행 가능 (스키마·레퍼런스 선별·프롬프트 조립·포트폴리오 검증)
- 스모크 테스트: ANTHROPIC_API_KEY가 있을 때만 실호출 1회
"""
import json
import os

import pytest

from ai_pipeline.config import settings
from ai_pipeline.schemas.design_spec import (
    CandidateList,
    candidate_list_json_schema,
    validate_portfolio,
)
from ai_pipeline.services import brand_assets
from ai_pipeline.services.stage2_design import (
    build_system_blocks,
    build_user_content,
    generate_design_specs,
)

# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


def _walk_objects(node):
    """JSON 스키마 안의 모든 object 노드를 순회."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _walk_objects(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_objects(item)


def test_schema_all_objects_forbid_additional_properties():
    """Structured Outputs 요구사항: 모든 object에 additionalProperties: false."""
    schema = candidate_list_json_schema()
    objects = list(_walk_objects(schema))
    assert objects, "object 노드가 없을 리 없음"
    for obj in objects:
        assert obj.get("additionalProperties") is False, f"위반 노드: {obj.get('title', obj)}"


def test_schema_has_no_unsupported_constraints():
    """Structured Outputs 미지원 제약(minimum/maxLength/minItems 등)이 없어야 한다."""
    text = json.dumps(candidate_list_json_schema())
    for banned in ('"minimum"', '"maximum"', '"minLength"', '"maxLength"', '"minItems"', '"maxItems"'):
        assert banned not in text, f"미지원 제약 포함: {banned}"


def test_schema_enums():
    schema = json.dumps(candidate_list_json_schema())
    assert '"safe"' in schema and '"balanced"' in schema and '"bold"' in schema


# ---------------------------------------------------------------------------
# 포트폴리오 코드 검증
# ---------------------------------------------------------------------------


def _make_candidate(profile: str, level: int, name: str = "c") -> dict:
    return {
        "concept_name": name,
        "category": "미니 레더백",
        "category_reason": None,
        "base_product": "dessau-cognac",
        "risk_profile": profile,
        "intervention_level": level,
        "creation_method": "패치",
        "applied_elements": [
            {"from_element": "해진 소매", "to_element": "스트랩 스티치", "reason": "세월의 흔적을 남김"}
        ],
        "image_prompt": "Attach denim patch onto flap. plain light-gray studio background, front view, product only, no props.",
    }


def test_validate_portfolio_pass():
    result = CandidateList.model_validate(
        {
            "candidates": [
                _make_candidate("safe", 2, "a"),
                _make_candidate("balanced", 3, "b"),
                _make_candidate("bold", 5, "c"),
            ]
        }
    )
    assert validate_portfolio(result) == []


def test_validate_portfolio_catches_violations():
    result = CandidateList.model_validate(
        {
            "candidates": [
                _make_candidate("safe", 5, "a"),      # safe인데 Lv5 — 위반
                _make_candidate("safe", 2, "b"),      # profile 중복 — 위반
                _make_candidate("bold", 4, "c"),
            ]
        }
    )
    problems = validate_portfolio(result)
    assert len(problems) >= 2
    assert any("중복" in p for p in problems)
    assert any("intervention_level" in p for p in problems)


# ---------------------------------------------------------------------------
# 레퍼런스 선별
# ---------------------------------------------------------------------------

FAKE_INDEX = [
    {"file": "bag/a.png", "category": "가방", "line": "aren", "product_id": "a", "color": "블랙", "angle": "front", "source": "s"},
    {"file": "bag/b.png", "category": "가방", "line": "aren", "product_id": "b", "color": "핑크", "angle": "front", "source": "s"},
    {"file": "bag/c.png", "category": "가방", "line": "stark", "product_id": "c", "color": "블랙", "angle": "front", "source": "s"},
    {"file": "wallet/d.png", "category": "지갑", "line": "tracy", "product_id": "d", "color": "코냑", "angle": "front", "source": "s"},
]


def test_select_references_prefers_line_diversity():
    picked = brand_assets.select_references(category="가방", k=2, index=FAKE_INDEX)
    lines = [e["line"] for e in picked]
    assert len(picked) == 2
    assert len(set(lines)) == 2, "같은 라인만 뽑히면 안 됨"


def test_select_references_category_filter():
    picked = brand_assets.select_references(category="지갑", k=3, index=FAKE_INDEX)
    assert all(e["category"] == "지갑" for e in picked)
    assert len(picked) == 1  # 지갑은 1개뿐 — 있는 만큼만


def test_select_references_real_index_loads():
    """실제 data/_index.json과의 통합 — 경로 정합성은 test_asset_index에서 별도 검증."""
    picked = brand_assets.select_references(category="가방", k=3)
    assert len(picked) == 3
    assert len({e["line"] for e in picked}) == 3


# ---------------------------------------------------------------------------
# 자산 인덱스 정합성 (수집 실수를 커밋 시점에 잡는 테스트)
# ---------------------------------------------------------------------------


def test_asset_index_paths_exist():
    for entry in brand_assets.load_index():
        path = settings.asset_root / entry["file"]
        assert path.exists(), f"인덱스에 있으나 파일 없음: {entry['file']}"


# ---------------------------------------------------------------------------
# 프롬프트 조립
# ---------------------------------------------------------------------------


def test_system_blocks_cache_and_content():
    blocks = build_system_blocks()
    assert blocks[0].get("cache_control") == {"type": "ephemeral"}, "디자인 코드 블록에 캐시 브레이크포인트"
    assert "비세토스" in blocks[0]["text"]
    joined = "".join(b["text"] for b in blocks)
    assert "safe" in joined and "bold" in joined, "포트폴리오 지시 누락"
    assert "reason" in joined, "매핑 원칙 누락"


def test_user_content_fixed_vs_auto_mode(sample_analysis):
    refs = brand_assets.select_references(category="가방", k=2)

    fixed = build_user_content(sample_analysis, "미니 레더백", refs)
    auto = build_user_content(sample_analysis, None, refs)

    n_images = sum(1 for b in fixed if b["type"] == "image")
    assert n_images == 2

    fixed_text = " ".join(b["text"] for b in fixed if b["type"] == "text")
    auto_text = " ".join(b["text"] for b in auto if b["type"] == "text")
    assert "미니 레더백" in fixed_text
    assert "자동 제안 모드" in auto_text
    assert "condition_cues" in fixed_text or "소매 해짐" in fixed_text, "분석 결과가 포함돼야 함"


def test_user_content_retry_feedback(sample_analysis):
    refs = brand_assets.select_references(category="가방", k=1)
    content = build_user_content(sample_analysis, None, refs, retry_problems=["risk_profile 중복: ..."])
    text = " ".join(b["text"] for b in content if b["type"] == "text")
    assert "반려 사유" in text


# ---------------------------------------------------------------------------
# 실호출 스모크 (API 키 있을 때만 — 과금 발생 주의)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")),
    reason="ANTHROPIC_API_KEY 없음 (.env 또는 환경변수)",
)
def test_generate_design_specs_smoke(sample_analysis):
    result = generate_design_specs(sample_analysis, target_category=None)
    assert len(result.candidates) == 3
    assert {c.risk_profile for c in result.candidates} == {"safe", "balanced", "bold"}
    for c in result.candidates:
        assert c.image_prompt.strip(), "image_prompt 비어 있음"
        assert c.applied_elements, "applied_elements 비어 있음"
