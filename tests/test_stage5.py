"""Stage 5 검증 수트.

- 단위 테스트: API 키 없이 실행 가능 (카탈로그 검증·스키마 enum 주입·코드 검증)
- 스모크 테스트: ANTHROPIC_API_KEY가 있을 때만 실호출 1회
"""
import json
import os
from pathlib import Path

import pytest

from ai_pipeline.config import settings
from ai_pipeline.schemas.analysis import AnalysisResult
from ai_pipeline.schemas.curation import (
    CurationResult,
    Recommendation,
    curation_json_schema,
    validate_curation,
)
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services.stage5_curation import (
    build_system_blocks,
    build_user_content,
    generate_curation,
    load_catalog,
)

# ---------------------------------------------------------------------------
# 단위 테스트 (API 키 필요 없음)
# ---------------------------------------------------------------------------


def test_catalog_all_product_ids_exist_in_index():
    """mcm_catalog.json의 모든 product_id가 data/_index.json에 실존하는지 오타 검증."""
    catalog = load_catalog()
    products = catalog.get("products", [])
    assert len(products) >= 10, f"카탈로그 제품 수가 너무 적음: {len(products)}"

    index_path = settings.asset_index_path
    assert index_path.exists(), f"_index.json 경로 부재: {index_path}"
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    index_ids = {item["product_id"] for item in index_data}

    for p in products:
        pid = p["product_id"]
        assert pid in index_ids, f"카탈로그 product_id '{pid}'가 data/_index.json에 존재하지 않음"


def test_curation_json_schema_enum_injection():
    """curation_json_schema()에 valid_ids가 enum으로 제대로 주입되는지 검증."""
    valid_ids = ["dessau-cognac", "aren-black-s", "pina-black"]
    schema = curation_json_schema(valid_ids)

    rec_prop = schema["$defs"]["Recommendation"]["properties"]["product_id"]
    assert rec_prop.get("enum") == valid_ids


def test_validate_curation_pass():
    """정상적인 CurationResult가 validate_curation을 통과하는지 검증."""
    valid_ids = ["dessau-cognac", "aren-black-s", "pina-black", "tracy-cognac-l"]
    base_product = "dessau-cognac"

    result = CurationResult(
        recommendations=[
            Recommendation(
                product_id="aren-black-s",
                reason="정갈한 블랙 비세토스 토트백은 아버지가 자전거를 태워주시던 시절의 단정한 추억과 조화를 이룹니다.",
                tagline="단정한 일상을 채우는 데일리 백",
            ),
            Recommendation(
                product_id="pina-black",
                reason="부드러운 프리미엄 레더 실루엣은 따뜻했던 과거의 온기를 전해주는 최고의 동행입니다.",
                tagline="따스한 온기를 전하는 버킷백",
            ),
        ]
    )

    problems = validate_curation(result, valid_ids, base_product=base_product)
    assert problems == []


def test_validate_curation_catches_violations():
    """validate_curation이 각종 위반 사례를 정확히 잡아내는지 검증."""
    valid_ids = ["dessau-cognac", "aren-black-s", "pina-black"]
    base_product = "dessau-cognac"

    # 1. 개수 미달 (1개)
    r1 = CurationResult(
        recommendations=[
            Recommendation(product_id="aren-black-s", reason="r1", tagline="t1")
        ]
    )
    p1 = validate_curation(r1, valid_ids, base_product=base_product)
    assert any("개수" in p for p in p1)

    # 2. 중복 product_id
    r2 = CurationResult(
        recommendations=[
            Recommendation(product_id="aren-black-s", reason="r1", tagline="t1"),
            Recommendation(product_id="aren-black-s", reason="r2", tagline="t2"),
        ]
    )
    p2 = validate_curation(r2, valid_ids, base_product=base_product)
    assert any("중복" in p for p in p2)

    # 3. 존재하지 않는 product_id
    r3 = CurationResult(
        recommendations=[
            Recommendation(product_id="aren-black-s", reason="r1", tagline="t1"),
            Recommendation(product_id="unknown-bag-id", reason="r2", tagline="t2"),
        ]
    )
    p3 = validate_curation(r3, valid_ids, base_product=base_product)
    assert any("카탈로그에 없는" in p for p in p3)

    # 4. base_product 포함 위반
    r4 = CurationResult(
        recommendations=[
            Recommendation(product_id="aren-black-s", reason="r1", tagline="t1"),
            Recommendation(product_id="dessau-cognac", reason="r2", tagline="t2"),  # base_product!
        ]
    )
    p4 = validate_curation(r4, valid_ids, base_product=base_product)
    assert any("베이스 제품" in p for p in p4)


# ---------------------------------------------------------------------------
# 스모크 테스트 (API 키 필요)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") and not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY 필요",
)
def test_stage5_live_smoke(sample_analysis: AnalysisResult):
    """Stage 5 실호출 스모크 테스트."""
    sample_design_spec = DesignSpec.model_validate(
        {
            "concept_name": "Denim Heritage Bucket",
            "category": "가방",
            "category_reason": None,
            "base_product": "dessau-cognac",
            "risk_profile": "safe",
            "intervention_level": 2,
            "creation_method": "데님 패치 및 스티치 이식",
            "applied_elements": [
                {
                    "from_element": "해진 소매",
                    "to_element": "스트랩 스티치",
                    "reason": "20년 세월의 추억을 간직",
                }
            ],
            "image_prompt": "Attach denim patch. plain light-gray studio background, front view, product only, no props.",
        }
    )

    result = generate_curation(sample_analysis, sample_design_spec)
    assert isinstance(result, CurationResult)
    assert 2 <= len(result.recommendations) <= 3
    for r in result.recommendations:
        assert r.product_id != "dessau-cognac"
        assert len(r.reason) > 10
        assert len(r.tagline) > 2
