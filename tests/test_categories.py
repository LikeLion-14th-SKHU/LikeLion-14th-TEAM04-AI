"""재창조 목표 카테고리 (사용자 지정) — 목록 도출·검증·API 노출 테스트."""
from fastapi.testclient import TestClient

from ai_pipeline.main import app
from ai_pipeline.services import brand_assets

client = TestClient(app)


def test_available_categories_from_index():
    cats = brand_assets.available_categories()
    names = [c["category"] for c in cats]
    assert "가방" in names and "신발" in names and "후드티" in names
    # 합성 카테고리는 정규화로 소멸했어야 함
    assert "자켓/코트" not in names and "티셔츠/셔츠" not in names and "팬츠/쇼츠" not in names
    # 보유 수량 내림차순
    counts = [c["count"] for c in cats]
    assert counts == sorted(counts, reverse=True)
    assert all(c["count"] > 0 for c in cats)


def test_is_valid_category():
    assert brand_assets.is_valid_category("가방")
    assert brand_assets.is_valid_category("신발")
    assert not brand_assets.is_valid_category("우산")
    assert not brand_assets.is_valid_category("자켓/코트")


def test_categories_endpoint():
    r = client.get("/ai/v1/recreation-categories")
    assert r.status_code == 200
    body = r.json()
    assert len(body["categories"]) >= 5
    assert body["categories"][0]["count"] >= body["categories"][-1]["count"]


def test_design_spec_rejects_unknown_category(sample_analysis):
    r = client.post(
        "/ai/v1/design-spec",
        json={"analysis": sample_analysis.model_dump(), "target_category": "우산"},
    )
    assert r.status_code == 422
    assert "우산" in r.json()["detail"]
