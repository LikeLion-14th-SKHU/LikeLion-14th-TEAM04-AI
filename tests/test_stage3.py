"""Stage 3 검증 수트 — 단위(키 불필요) + 실호출 스모크(GOOGLE_API_KEY 있을 때만)."""
import os

import pytest

from ai_pipeline.config import settings
from ai_pipeline.schemas.design_spec import DesignSpec
from ai_pipeline.services import brand_assets
from ai_pipeline.services.stage3_concept import build_inputs


def _spec(base_product: str) -> DesignSpec:
    return DesignSpec.model_validate(
        {
            "concept_name": "Sunday Ride",
            "category": "미니 레더백",
            "category_reason": None,
            "base_product": base_product,
            "risk_profile": "safe",
            "intervention_level": 2,
            "creation_method": "데님 패치",
            "applied_elements": [
                {"from_element": "해진 소매", "to_element": "플랩 패치", "reason": "세월의 흔적"}
            ],
            "image_prompt": "Attach a worn denim patch onto the front flap. plain light-gray studio background, front view, product only, no props.",
        }
    )


@pytest.fixture
def clothing_image(tmp_path):
    """가짜 옷 사진 — 실제 PNG 바이트가 필요하므로 인덱스의 아무 이미지나 복사."""
    src = settings.asset_root / brand_assets.load_index()[0]["file"]
    dst = tmp_path / "clothing.png"
    dst.write_bytes(src.read_bytes())
    return dst


def test_find_by_product_id():
    entry = brand_assets.load_index()[0]
    assert brand_assets.find_by_product_id(entry["product_id"]) == entry
    assert brand_assets.find_by_product_id("없는-제품") is None


def test_build_inputs_with_valid_reference(clothing_image):
    real_id = brand_assets.load_index()[0]["product_id"]
    inputs, ref_used = build_inputs(_spec(real_id), clothing_image)

    assert ref_used == real_id
    assert inputs[0]["type"] == "text"
    assert "plain light-gray studio background" in inputs[0]["text"]
    assert "first image is the customer's old clothing" in inputs[0]["text"]
    images = [b for b in inputs if b["type"] == "image"]
    assert len(images) == 2, "옷 사진 + 레퍼런스 = 2장"
    assert all(b["mime_type"] == "image/png" and b["data"] for b in images)


def test_build_inputs_without_reference_falls_back(clothing_image):
    """base_product가 인덱스에 없으면 옷 사진만으로 진행 (경고성 동작)."""
    inputs, ref_used = build_inputs(_spec("hallucinated-product-id"), clothing_image)

    assert ref_used is None
    images = [b for b in inputs if b["type"] == "image"]
    assert len(images) == 1, "레퍼런스 없이 옷 사진만"


@pytest.mark.skipif(
    not (settings.google_api_key or os.getenv("GOOGLE_API_KEY")),
    reason="GOOGLE_API_KEY 없음 (.env 또는 환경변수)",
)
def test_generate_concept_image_smoke(clothing_image, tmp_path):
    from ai_pipeline.services.stage3_concept import generate_concept_image

    real_id = brand_assets.load_index()[0]["product_id"]
    result = generate_concept_image(_spec(real_id), clothing_image, out_dir=tmp_path)

    assert result.image_path.exists()
    assert result.image_path.stat().st_size > 10_000, "10KB 미만이면 정상 이미지가 아님"
